"""
Proactive Log Analyzer for AIOps DevOps Agent
Analyzes CloudWatch Logs to detect anomalies before they become failures

Features:
- Semantic log interpretation using Bedrock
- Pattern recognition across log streams
- Anomaly detection without predefined rules
- Predictive failure alerts
- Learning from historical patterns
"""

import json
import boto3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re

# AWS Clients
bedrock = boto3.client('bedrock-runtime')
logs = boto3.client('logs')
dynamodb = boto3.client('dynamodb')
sns = boto3.client('sns')
cloudwatch = boto3.client('cloudwatch')

# Environment Variables
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']
PATTERNS_TABLE = os.environ.get('PATTERNS_TABLE', 'aiops-patterns')
MODEL_ID = "amazon.titan-text-express-v1"
ANOMALY_THRESHOLD = float(os.environ.get('ANOMALY_THRESHOLD', '0.7'))

# Common error patterns to look for
ERROR_PATTERNS = [
    r'ERROR',
    r'FATAL',
    r'Exception',
    r'failed',
    r'timeout',
    r'connection refused',
    r'out of memory',
    r'disk full',
    r'permission denied',
    r'authentication failed'
]


def extract_log_insights(log_group: str, hours_back: int = 1) -> List[Dict]:
    """
    Query CloudWatch Logs Insights for recent error patterns
    """
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)
    
    # Query for errors and warnings
    query = """
    fields @timestamp, @message, @logStream
    | filter @message like /ERROR|WARN|Exception|failed/
    | sort @timestamp desc
    | limit 100
    """
    
    try:
        # Start query
        response = logs.start_query(
            logGroupName=log_group,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query
        )
        
        query_id = response['queryId']
        
        # Wait for query to complete
        import time
        max_wait = 30  # seconds
        waited = 0
        
        while waited < max_wait:
            result = logs.get_query_results(queryId=query_id)
            status = result['status']
            
            if status == 'Complete':
                return result.get('results', [])
            elif status == 'Failed':
                print(f"Query failed: {result}")
                return []
            
            time.sleep(1)
            waited += 1
        
        print(f"Query timeout after {max_wait}s")
        return []
        
    except Exception as e:
        print(f"Error querying logs: {e}")
        return []


def extract_error_patterns(log_messages: List[str]) -> Dict[str, int]:
    """
    Extract and count error patterns from log messages
    """
    pattern_counts = {}
    
    for message in log_messages:
        for pattern in ERROR_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    
    return pattern_counts


def get_historical_baseline(log_group: str, pattern: str) -> Dict:
    """
    Get historical baseline for a specific error pattern
    Returns average count and standard deviation
    """
    try:
        response = dynamodb.get_item(
            TableName=PATTERNS_TABLE,
            Key={
                'pattern_id': {'S': f"{log_group}#{pattern}"}
            }
        )
        
        if 'Item' in response:
            item = response['Item']
            return {
                'avg_count': float(item.get('avg_count', {}).get('N', '0')),
                'std_dev': float(item.get('std_dev', {}).get('N', '0')),
                'last_seen': item.get('last_seen', {}).get('S', ''),
                'total_occurrences': int(item.get('occurrence_count', {}).get('N', '0'))
            }
        
        return {'avg_count': 0, 'std_dev': 0, 'last_seen': '', 'total_occurrences': 0}
        
    except Exception as e:
        print(f"Error getting baseline: {e}")
        return {'avg_count': 0, 'std_dev': 0, 'last_seen': '', 'total_occurrences': 0}


def update_pattern_baseline(log_group: str, pattern: str, current_count: int):
    """
    Update historical baseline with new data point
    Uses exponential moving average
    """
    try:
        pattern_id = f"{log_group}#{pattern}"
        baseline = get_historical_baseline(log_group, pattern)
        
        # Calculate new average (exponential moving average with alpha=0.3)
        alpha = 0.3
        new_avg = alpha * current_count + (1 - alpha) * baseline['avg_count']
        
        # Update DynamoDB
        dynamodb.update_item(
            TableName=PATTERNS_TABLE,
            Key={'pattern_id': {'S': pattern_id}},
            UpdateExpression='SET avg_count = :avg, last_seen = :last, occurrence_count = occurrence_count + :inc',
            ExpressionAttributeValues={
                ':avg': {'N': str(new_avg)},
                ':last': {'S': datetime.utcnow().isoformat()},
                ':inc': {'N': str(current_count)}
            }
        )
        
    except Exception as e:
        print(f"Error updating baseline: {e}")


def detect_anomalies(current_patterns: Dict[str, int], log_group: str) -> List[Dict]:
    """
    Detect anomalies by comparing current patterns to historical baseline
    """
    anomalies = []
    
    for pattern, count in current_patterns.items():
        baseline = get_historical_baseline(log_group, pattern)
        
        # Skip if no historical data
        if baseline['total_occurrences'] < 10:
            update_pattern_baseline(log_group, pattern, count)
            continue
        
        # Calculate z-score (how many standard deviations from mean)
        avg = baseline['avg_count']
        std = baseline['std_dev'] if baseline['std_dev'] > 0 else avg * 0.5  # Fallback
        
        if std > 0:
            z_score = (count - avg) / std
        else:
            z_score = 0
        
        # Anomaly if z-score > 2 (more than 2 std devs above average)
        if z_score > 2:
            anomalies.append({
                'pattern': pattern,
                'current_count': count,
                'baseline_avg': avg,
                'z_score': z_score,
                'severity': min(10, int(z_score))  # Cap at 10
            })
        
        # Update baseline
        update_pattern_baseline(log_group, pattern, count)
    
    return anomalies


def analyze_logs_with_bedrock(log_samples: List[str], anomalies: List[Dict]) -> Dict:
    """
    Use Bedrock to perform semantic analysis of log patterns
    """
    
    # Take sample of recent logs
    log_sample = '\n'.join(log_samples[:20])  # First 20 logs
    
    anomaly_summary = '\n'.join([
        f"- {a['pattern']}: {a['current_count']} occurrences (baseline: {a['baseline_avg']:.1f}, z-score: {a['z_score']:.2f})"
        for a in anomalies
    ])
    
    prompt = f"""You are an expert DevOps AI analyzing application logs for potential issues.

RECENT LOG SAMPLES:
{log_sample}

DETECTED ANOMALIES (Statistical):
{anomaly_summary if anomalies else 'No statistical anomalies detected'}

ANALYSIS TASKS:

1. SEMANTIC INTERPRETATION
   - What is the application doing?
   - Are there any concerning patterns in the logs?
   - Do the errors indicate a specific problem?

2. ANOMALY ASSESSMENT
   - Are the statistical anomalies genuine issues or false positives?
   - What is the likely root cause?
   - Is this a symptom of a larger problem?

3. FAILURE PREDICTION
   - Could this lead to a system failure?
   - What is the probability of failure in the next hour? (0.0 to 1.0)
   - What components are at risk?

4. RECOMMENDED ACTIONS
   - Should we take proactive action?
   - What specific steps should be taken?
   - Urgency level (LOW/MEDIUM/HIGH/CRITICAL)

RESPOND IN VALID JSON FORMAT:
{{
  "summary": "Brief description of what's happening",
  "root_cause": "Likely root cause or 'Unknown'",
  "failure_probability": 0.75,
  "at_risk_components": ["component1", "component2"],
  "recommended_action": "Specific action to take",
  "urgency": "MEDIUM",
  "reasoning": "Explanation of your analysis"
}}
"""
    
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 1024,
            "stopSequences": [],
            "temperature": 0.2,
            "topP": 0.9
        }
    })
    
    try:
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json"
        )
        
        response_body = json.loads(response.get('body').read())
        llm_output = response_body.get('results')[0].get('outputText').strip()
        
        # Extract JSON
        if '```json' in llm_output:
            llm_output = llm_output.split('```json')[1].split('```')[0].strip()
        elif '```' in llm_output:
            llm_output = llm_output.split('```')[1].split('```')[0].strip()
        
        analysis = json.loads(llm_output)
        return analysis
        
    except Exception as e:
        print(f"Bedrock analysis error: {e}")
        return {
            'summary': 'Analysis failed',
            'root_cause': 'Unknown',
            'failure_probability': 0.0,
            'at_risk_components': [],
            'recommended_action': 'Manual review required',
            'urgency': 'LOW',
            'reasoning': str(e)
        }


def send_proactive_alert(log_group: str, analysis: Dict, anomalies: List[Dict]):
    """
    Send proactive alert if failure is predicted
    """
    failure_prob = analysis.get('failure_probability', 0.0)
    urgency = analysis.get('urgency', 'LOW')
    
    # Only alert if probability is above threshold
    if failure_prob < ANOMALY_THRESHOLD:
        print(f"Failure probability {failure_prob} below threshold {ANOMALY_THRESHOLD}, not alerting")
        return
    
    # Build alert message
    anomaly_details = '\n'.join([
        f"  • {a['pattern']}: {a['current_count']} occurrences (↑{a['z_score']:.1f}σ from baseline)"
        for a in anomalies
    ])
    
    message = f"""
╔══════════════════════════════════════════════════════════════════════╗
║         AIOps DevOps Agent - Proactive Failure Prediction            ║
╚══════════════════════════════════════════════════════════════════════╝

⚠️ POTENTIAL ISSUE DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Log Group: {log_group}
Urgency: {urgency}
Failure Probability: {failure_prob * 100:.1f}%

🔍 ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Summary: {analysis.get('summary', 'N/A')}
Root Cause: {analysis.get('root_cause', 'Unknown')}

📊 ANOMALIES DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{anomaly_details if anomalies else 'None (semantic analysis only)'}

⚡ AT RISK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Components: {', '.join(analysis.get('at_risk_components', ['Unknown']))}

💡 RECOMMENDED ACTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{analysis.get('recommended_action', 'Monitor closely')}

🧠 REASONING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{analysis.get('reasoning', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is a PROACTIVE alert. The system has not failed yet, but AI predicts
a potential issue. Consider taking preventive action.
    """
    
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"🔮 AIOps: Proactive Alert - {urgency} - {log_group}",
            Message=message
        )
        print(f"Proactive alert sent for {log_group}")
        
    except Exception as e:
        print(f"Failed to send alert: {e}")


def publish_metrics(log_group: str, anomaly_count: int, failure_probability: float):
    """
    Publish metrics to CloudWatch
    """
    try:
        cloudwatch.put_metric_data(
            Namespace='AIOps/LogAnalyzer',
            MetricData=[
                {
                    'MetricName': 'AnomalyCount',
                    'Value': anomaly_count,
                    'Unit': 'Count',
                    'Dimensions': [
                        {'Name': 'LogGroup', 'Value': log_group}
                    ]
                },
                {
                    'MetricName': 'FailureProbability',
                    'Value': failure_probability,
                    'Unit': 'None',
                    'Dimensions': [
                        {'Name': 'LogGroup', 'Value': log_group}
                    ]
                }
            ]
        )
    except Exception as e:
        print(f"Failed to publish metrics: {e}")


def handler(event, context):
    """
    Main handler for proactive log analysis
    Triggered by CloudWatch Events (scheduled every 5 minutes)
    """
    print(f"Log analyzer invoked: {json.dumps(event)}")
    
    # Get log groups to analyze from environment or event
    log_groups = os.environ.get('LOG_GROUPS', '').split(',')
    
    # Or get from event (for EventBridge scheduled rule)
    if 'log_groups' in event:
        log_groups = event['log_groups']
    
    if not log_groups or log_groups == ['']:
        print("No log groups configured")
        return {"status": "no_log_groups"}
    
    results = []
    
    for log_group in log_groups:
        log_group = log_group.strip()
        if not log_group:
            continue
        
        print(f"Analyzing log group: {log_group}")
        
        try:
            # Extract recent logs
            log_results = extract_log_insights(log_group, hours_back=1)
            
            if not log_results:
                print(f"No logs found in {log_group}")
                continue
            
            # Extract messages
            log_messages = []
            for result in log_results:
                for field in result:
                    if field.get('field') == '@message':
                        log_messages.append(field.get('value', ''))
            
            # Extract error patterns
            current_patterns = extract_error_patterns(log_messages)
            
            print(f"Found patterns: {current_patterns}")
            
            # Detect anomalies
            anomalies = detect_anomalies(current_patterns, log_group)
            
            print(f"Detected {len(anomalies)} anomalies")
            
            # Analyze with Bedrock
            analysis = analyze_logs_with_bedrock(log_messages, anomalies)
            
            print(f"Bedrock analysis: {json.dumps(analysis)}")
            
            # Send alert if needed
            send_proactive_alert(log_group, analysis, anomalies)
            
            # Publish metrics
            publish_metrics(
                log_group,
                len(anomalies),
                analysis.get('failure_probability', 0.0)
            )
            
            results.append({
                'log_group': log_group,
                'anomaly_count': len(anomalies),
                'failure_probability': analysis.get('failure_probability', 0.0),
                'urgency': analysis.get('urgency', 'LOW')
            })
            
        except Exception as e:
            print(f"Error analyzing {log_group}: {e}")
            results.append({
                'log_group': log_group,
                'error': str(e)
            })
    
    return {
        "status": "ok",
        "analyzed_log_groups": len(results),
        "results": results
    }
