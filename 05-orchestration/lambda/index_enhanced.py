"""
Enhanced AI DevOps Agent with Workflow & Mechanism Integration
Features:
- Workflow state management
- Historical incident tracking
- Pattern recognition
- Multi-stage recovery planning
- Correlation IDs
- Structured logging
"""

import json
import boto3
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# AWS Clients
bedrock = boto3.client('bedrock-runtime')
codebuild = boto3.client('codebuild')
sns = boto3.client('sns')
dynamodb = boto3.client('dynamodb')
stepfunctions = boto3.client('stepfunctions')
cloudwatch = boto3.client('cloudwatch')

# Environment Variables
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']
INCIDENT_TABLE = os.environ.get('INCIDENT_TABLE', 'aiops-incidents')
STATE_MACHINE_ARN = os.environ.get('STATE_MACHINE_ARN', '')
MODEL_ID = "amazon.titan-text-express-v1"
COOLDOWN_MINUTES = int(os.environ.get('COOLDOWN_MINUTES', '5'))
CONFIDENCE_THRESHOLD = float(os.environ.get('CONFIDENCE_THRESHOLD', '0.8'))

# Map of resource types to their CodeBuild projects
RESOURCE_RECOVERY_MAP = {
    "ec2": "aiops-devops-agent-apply",
    "lambda": "aiops-devops-agent-apply",
    "dynamodb": "aiops-devops-agent-apply",
    "s3": "aiops-devops-agent-apply",
    "rds": "aiops-devops-agent-apply",
    "ssm": "aiops-devops-agent-apply",
}

# Workflow States
class WorkflowState:
    DETECTING = "DETECTING"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COOLDOWN = "COOLDOWN"

# Event Classifications
class EventClassification:
    FAILURE = "FAILURE"
    TAMPERING = "TAMPERING"
    ANOMALY = "ANOMALY"
    NORMAL = "NORMAL"


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for tracking"""
    return f"incident-{uuid.uuid4()}"


def structured_log(level: str, message: str, correlation_id: str = None, **kwargs):
    """Structured logging with correlation ID"""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,
        "message": message,
        "correlation_id": correlation_id,
        **kwargs
    }
    print(json.dumps(log_entry))


def detect_resource_type(event_detail: Dict) -> str:
    """Detect which AWS resource type is affected"""
    event_name = event_detail.get('eventName', '')
    event_source = event_detail.get('eventSource', '')
    
    # EC2
    if 'ec2' in event_source or event_name in ['TerminateInstances', 'StopInstances']:
        return 'ec2'
    # Lambda
    elif 'lambda' in event_source or event_name in ['DeleteFunction', 'UpdateFunctionConfiguration']:
        return 'lambda'
    # DynamoDB
    elif 'dynamodb' in event_source or event_name in ['DeleteTable']:
        return 'dynamodb'
    # S3
    elif 's3' in event_source or event_name in ['DeleteBucket', 'PutBucketPolicy']:
        return 's3'
    # RDS
    elif 'rds' in event_source or event_name in ['DeleteDBInstance']:
        return 'rds'
    # SSM
    elif 'ssm' in event_source or event_name in ['PutParameter', 'DeleteParameter']:
        return 'ssm'
    
    return 'unknown'


def extract_resource_identifier(event_detail: Dict, resource_type: str) -> str:
    """Extract the specific resource ID/name from the event"""
    event_name = event_detail.get('eventName', '')
    request_params = event_detail.get('requestParameters', {})
    
    if resource_type == 'ec2':
        instances = request_params.get('instancesSet', {}).get('items', [])
        if instances:
            return instances[0].get('instanceId', 'unknown')
    elif resource_type == 'lambda':
        return request_params.get('functionName', 'unknown')
    elif resource_type == 'dynamodb':
        return request_params.get('tableName', 'unknown')
    elif resource_type == 's3':
        return request_params.get('bucketName', 'unknown')
    elif resource_type == 'ssm':
        return request_params.get('name', 'unknown')
    
    return 'unknown'


def check_cooldown(resource_type: str, resource_id: str) -> Tuple[bool, Optional[str]]:
    """
    Check if resource is in cooldown period to prevent recovery loops
    Returns: (is_in_cooldown, last_incident_id)
    """
    try:
        cutoff_time = (datetime.utcnow() - timedelta(minutes=COOLDOWN_MINUTES)).isoformat()
        
        response = dynamodb.query(
            TableName=INCIDENT_TABLE,
            IndexName='resource-timestamp-index',  # GSI needed
            KeyConditionExpression='resource_key = :rk AND incident_timestamp > :cutoff',
            ExpressionAttributeValues={
                ':rk': {'S': f"{resource_type}#{resource_id}"},
                ':cutoff': {'S': cutoff_time}
            },
            Limit=1,
            ScanIndexForward=False  # Most recent first
        )
        
        items = response.get('Items', [])
        if items:
            last_incident = items[0]
            last_state = last_incident.get('workflow_state', {}).get('S', '')
            
            # Only cooldown if last recovery was successful or in progress
            if last_state in [WorkflowState.EXECUTING, WorkflowState.VERIFYING, WorkflowState.COMPLETED]:
                return True, last_incident.get('incident_id', {}).get('S', '')
        
        return False, None
        
    except Exception as e:
        structured_log("ERROR", f"Error checking cooldown: {e}")
        return False, None


def get_similar_incidents(resource_type: str, event_type: str, limit: int = 5) -> List[Dict]:
    """
    Query historical incidents for pattern matching
    Returns list of similar past incidents
    """
    try:
        response = dynamodb.query(
            TableName=INCIDENT_TABLE,
            IndexName='resource-type-index',  # GSI needed
            KeyConditionExpression='resource_type = :rt',
            FilterExpression='event_classification = :et AND workflow_state = :completed',
            ExpressionAttributeValues={
                ':rt': {'S': resource_type},
                ':et': {'S': event_type},
                ':completed': {'S': WorkflowState.COMPLETED}
            },
            Limit=limit,
            ScanIndexForward=False
        )
        
        incidents = []
        for item in response.get('Items', []):
            incidents.append({
                'incident_id': item.get('incident_id', {}).get('S', ''),
                'recovery_actions': json.loads(item.get('recovery_actions', {}).get('S', '[]')),
                'recovery_duration': int(item.get('recovery_duration_seconds', {}).get('N', '0')),
                'success': item.get('success', {}).get('BOOL', False),
                'llm_analysis': item.get('llm_analysis', {}).get('S', '')
            })
        
        return incidents
        
    except Exception as e:
        structured_log("ERROR", f"Error fetching similar incidents: {e}")
        return []


def create_incident_record(
    correlation_id: str,
    event_details: Dict,
    resource_type: str,
    resource_id: str,
    workflow_state: str
) -> bool:
    """Store incident in DynamoDB with full context"""
    try:
        timestamp = datetime.utcnow().isoformat()
        
        item = {
            'incident_id': {'S': correlation_id},
            'incident_timestamp': {'S': timestamp},
            'resource_type': {'S': resource_type},
            'resource_id': {'S': resource_id},
            'resource_key': {'S': f"{resource_type}#{resource_id}"},
            'workflow_state': {'S': workflow_state},
            'event_details': {'S': json.dumps(event_details)},
            'created_at': {'S': timestamp},
            'updated_at': {'S': timestamp}
        }
        
        dynamodb.put_item(TableName=INCIDENT_TABLE, Item=item)
        return True
        
    except Exception as e:
        structured_log("ERROR", f"Error creating incident record: {e}", correlation_id)
        return False


def update_workflow_state(
    incident_id: str,
    new_state: str,
    additional_data: Dict = None
) -> bool:
    """Update workflow state and additional data"""
    try:
        update_expr = "SET workflow_state = :state, updated_at = :updated"
        expr_values = {
            ':state': {'S': new_state},
            ':updated': {'S': datetime.utcnow().isoformat()}
        }
        
        if additional_data:
            for key, value in additional_data.items():
                update_expr += f", {key} = :{key}"
                # Auto-detect type
                if isinstance(value, bool):
                    expr_values[f':{key}'] = {'BOOL': value}
                elif isinstance(value, (int, float)):
                    expr_values[f':{key}'] = {'N': str(value)}
                else:
                    expr_values[f':{key}'] = {'S': str(value)}
        
        dynamodb.update_item(
            TableName=INCIDENT_TABLE,
            Key={'incident_id': {'S': incident_id}},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values
        )
        return True
        
    except Exception as e:
        structured_log("ERROR", f"Error updating workflow state: {e}", incident_id)
        return False


def analyze_with_bedrock_enhanced(
    event_details: Dict,
    resource_type: str,
    resource_id: str,
    similar_incidents: List[Dict],
    correlation_id: str
) -> Dict:
    """
    Enhanced Bedrock analysis with historical context
    Returns: {
        'classification': 'FAILURE|TAMPERING|ANOMALY|NORMAL',
        'confidence': 0.0-1.0,
        'severity': 1-10,
        'reasoning': 'explanation',
        'predicted_impact': {...}
    }
    """
    
    # Build context from similar incidents
    historical_context = ""
    if similar_incidents:
        historical_context = "\n\nHistorical Context (Similar Past Incidents):\n"
        for idx, incident in enumerate(similar_incidents[:3], 1):
            historical_context += f"{idx}. Recovery took {incident['recovery_duration']}s, "
            historical_context += f"Success: {incident['success']}\n"
    
    prompt = f"""You are an expert DevOps AI Agent analyzing AWS infrastructure events.

EVENT DETAILS:
{json.dumps(event_details, indent=2)}

RESOURCE INFORMATION:
- Type: {resource_type}
- ID: {resource_id}
{historical_context}

ANALYSIS TASKS:

1. CLASSIFICATION - Categorize this event:
   - FAILURE: Critical resource deleted/terminated (requires immediate recovery)
   - TAMPERING: Unauthorized configuration change (security concern)
   - ANOMALY: Unusual behavior but not critical (monitor closely)
   - NORMAL: Expected operation (no action needed)

2. CONFIDENCE - Rate your confidence in this classification (0.0 to 1.0)

3. SEVERITY - Rate the severity of this event (1-10 scale)
   - 1-3: Low impact, informational
   - 4-6: Medium impact, affects single service
   - 7-8: High impact, affects multiple services
   - 9-10: Critical, system-wide outage

4. REASONING - Explain your analysis in 2-3 sentences

5. PREDICTED IMPACT - Estimate:
   - Affected services (list)
   - Estimated downtime (minutes)
   - Blast radius (localized/regional/global)

RESPOND IN VALID JSON FORMAT:
{{
  "classification": "FAILURE|TAMPERING|ANOMALY|NORMAL",
  "confidence": 0.95,
  "severity": 8,
  "reasoning": "Your explanation here",
  "predicted_impact": {{
    "affected_services": ["service1", "service2"],
    "estimated_downtime_minutes": 5,
    "blast_radius": "localized"
  }}
}}
"""
    
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 1024,
            "stopSequences": [],
            "temperature": 0.1,  # Lower temperature for more consistent analysis
            "topP": 0.9
        }
    })
    
    try:
        structured_log("INFO", "Invoking Bedrock for enhanced analysis", correlation_id)
        
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json"
        )
        
        response_body = json.loads(response.get('body').read())
        llm_output = response_body.get('results')[0].get('outputText').strip()
        
        structured_log("INFO", f"Bedrock response: {llm_output}", correlation_id)
        
        # Parse JSON response
        # Extract JSON from markdown code blocks if present
        if '```json' in llm_output:
            llm_output = llm_output.split('```json')[1].split('```')[0].strip()
        elif '```' in llm_output:
            llm_output = llm_output.split('```')[1].split('```')[0].strip()
        
        analysis = json.loads(llm_output)
        
        # Validate required fields
        required_fields = ['classification', 'confidence', 'severity', 'reasoning']
        for field in required_fields:
            if field not in analysis:
                raise ValueError(f"Missing required field: {field}")
        
        return analysis
        
    except json.JSONDecodeError as e:
        structured_log("ERROR", f"Failed to parse Bedrock JSON response: {e}", correlation_id)
        # Fallback to simple classification
        if "FAILURE" in llm_output or "TERMINATE" in llm_output or "DELETE" in llm_output:
            return {
                'classification': EventClassification.FAILURE,
                'confidence': 0.7,
                'severity': 8,
                'reasoning': 'Fallback classification based on keyword detection',
                'predicted_impact': {}
            }
        return {
            'classification': EventClassification.NORMAL,
            'confidence': 0.5,
            'severity': 2,
            'reasoning': 'Unable to parse LLM response, defaulting to NORMAL',
            'predicted_impact': {}
        }
        
    except Exception as e:
        structured_log("ERROR", f"Bedrock analysis error: {e}", correlation_id)
        raise


def generate_recovery_plan(
    analysis: Dict,
    resource_type: str,
    resource_id: str,
    similar_incidents: List[Dict],
    correlation_id: str
) -> Dict:
    """
    Use Bedrock to generate a detailed recovery plan
    Returns: {
        'steps': [{'action': '', 'timeout': 60, 'dependencies': []}],
        'estimated_duration': 120,
        'rollback_plan': {...}
    }
    """
    
    successful_recoveries = [inc for inc in similar_incidents if inc['success']]
    recovery_context = ""
    if successful_recoveries:
        recovery_context = "\n\nSUCCESSFUL PAST RECOVERIES:\n"
        for idx, inc in enumerate(successful_recoveries[:2], 1):
            recovery_context += f"{idx}. Actions: {inc['recovery_actions']}, "
            recovery_context += f"Duration: {inc['recovery_duration']}s\n"
    
    prompt = f"""You are a DevOps AI Agent creating a recovery plan.

INCIDENT ANALYSIS:
{json.dumps(analysis, indent=2)}

RESOURCE:
- Type: {resource_type}
- ID: {resource_id}
{recovery_context}

CREATE A STEP-BY-STEP RECOVERY PLAN:

1. IMMEDIATE ACTIONS (< 1 minute)
   - Quick wins to stabilize the system
   
2. PRIMARY RECOVERY (1-5 minutes)
   - Main restoration steps
   
3. VERIFICATION STEPS
   - How to confirm recovery success
   
4. ROLLBACK PLAN
   - What to do if recovery fails

For each step, specify:
- action_type: "terraform" | "aws_cli" | "script" | "manual"
- description: What this step does
- timeout_seconds: Maximum time allowed
- dependencies: List of previous step numbers
- success_criteria: How to verify this step succeeded

RESPOND IN VALID JSON FORMAT:
{{
  "steps": [
    {{
      "step_number": 1,
      "action_type": "terraform",
      "description": "Restore infrastructure using Terraform",
      "timeout_seconds": 300,
      "dependencies": [],
      "success_criteria": "Resource exists and is in running state"
    }}
  ],
  "estimated_duration_seconds": 300,
  "rollback_plan": {{
    "description": "If recovery fails, take snapshot and alert on-call engineer",
    "steps": ["step1", "step2"]
  }}
}}
"""
    
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 2048,
            "stopSequences": [],
            "temperature": 0.2,
            "topP": 0.9
        }
    })
    
    try:
        structured_log("INFO", "Generating recovery plan with Bedrock", correlation_id)
        
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
        
        recovery_plan = json.loads(llm_output)
        return recovery_plan
        
    except Exception as e:
        structured_log("ERROR", f"Error generating recovery plan: {e}", correlation_id)
        # Fallback to simple plan
        return {
            'steps': [
                {
                    'step_number': 1,
                    'action_type': 'terraform',
                    'description': f'Restore {resource_type} using Terraform',
                    'timeout_seconds': 300,
                    'dependencies': [],
                    'success_criteria': 'Resource restored'
                }
            ],
            'estimated_duration_seconds': 300,
            'rollback_plan': {'description': 'Manual intervention required', 'steps': []}
        }


def execute_recovery_simple(
    resource_type: str,
    correlation_id: str
) -> Dict:
    """
    Execute simple recovery using CodeBuild (current implementation)
    """
    try:
        codebuild_project = RESOURCE_RECOVERY_MAP.get(resource_type, "aiops-devops-agent-apply")
        
        structured_log("INFO", f"Starting CodeBuild project: {codebuild_project}", correlation_id)
        
        cb_resp = codebuild.start_build(
            projectName=codebuild_project,
            environmentVariablesOverride=[
                {
                    'name': 'CORRELATION_ID',
                    'value': correlation_id,
                    'type': 'PLAINTEXT'
                }
            ]
        )
        
        build_id = cb_resp['build']['id']
        
        structured_log("INFO", f"CodeBuild started: {build_id}", correlation_id)
        
        return {
            'success': True,
            'build_id': build_id,
            'project': codebuild_project
        }
        
    except Exception as e:
        structured_log("ERROR", f"CodeBuild execution failed: {e}", correlation_id)
        return {
            'success': False,
            'error': str(e)
        }


def send_enhanced_notification(
    incident_id: str,
    event_name: str,
    resource_type: str,
    resource_id: str,
    user_identity: str,
    analysis: Dict,
    recovery_result: Dict,
    timeline: Dict
):
    """Send enhanced notification with full context"""
    
    # Calculate total time
    total_time = sum(timeline.values())
    
    # Build timeline display
    timeline_display = "\n".join([
        f"  {stage.replace('_', ' ').title()}: {duration}s"
        for stage, duration in timeline.items()
    ])
    
    msg = f"""
╔══════════════════════════════════════════════════════════════════════╗
║         DevOps AI Agent - Automated Incident Response                ║
╚══════════════════════════════════════════════════════════════════════╝

🔴 INCIDENT DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Incident ID: {incident_id}
Event: {event_name}
Resource Type: {resource_type.upper()}
Resource ID: {resource_id}
User: {user_identity}

🤖 AI ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Classification: {analysis.get('classification', 'UNKNOWN')}
Confidence: {analysis.get('confidence', 0) * 100:.1f}%
Severity: {analysis.get('severity', 0)}/10
Reasoning: {analysis.get('reasoning', 'N/A')}

🔄 RECOVERY ACTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status: {'✅ SUCCESS' if recovery_result.get('success') else '❌ FAILED'}
Build ID: {recovery_result.get('build_id', 'N/A')}
Project: {recovery_result.get('project', 'N/A')}

⏱️ TIMELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{timeline_display}
Total Time: {total_time}s

📊 METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Detection: Real-time
Analysis: AI-powered (Bedrock)
Recovery: Automated (Infrastructure as Code)

🔗 CORRELATION ID: {incident_id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is an automated response. Full audit trail stored in DynamoDB.
    """
    
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"🚨 DevOps AI Agent: {resource_type.upper()} {analysis.get('classification', 'INCIDENT')} - {resource_id}",
            Message=msg
        )
        structured_log("INFO", "Notification sent", incident_id)
    except Exception as e:
        structured_log("ERROR", f"Failed to send notification: {e}", incident_id)


def publish_metrics(
    resource_type: str,
    classification: str,
    recovery_duration: int,
    success: bool
):
    """Publish custom CloudWatch metrics"""
    try:
        cloudwatch.put_metric_data(
            Namespace='AIOps/DevOpsAgent',
            MetricData=[
                {
                    'MetricName': 'IncidentCount',
                    'Value': 1,
                    'Unit': 'Count',
                    'Dimensions': [
                        {'Name': 'ResourceType', 'Value': resource_type},
                        {'Name': 'Classification', 'Value': classification}
                    ]
                },
                {
                    'MetricName': 'RecoveryDuration',
                    'Value': recovery_duration,
                    'Unit': 'Seconds',
                    'Dimensions': [
                        {'Name': 'ResourceType', 'Value': resource_type},
                        {'Name': 'Success', 'Value': str(success)}
                    ]
                }
            ]
        )
    except Exception as e:
        structured_log("ERROR", f"Failed to publish metrics: {e}")


def handler(event, context):
    """
    Enhanced Lambda handler with workflow and mechanism integration
    """
    start_time = datetime.utcnow()
    correlation_id = generate_correlation_id()
    
    structured_log("INFO", "Handler invoked", correlation_id, event=event)
    
    # Detect event type: Real-time vs CloudTrail
    detail_type = event.get('detail-type', '')
    detail = event.get('detail', {})
    
    # Parse event details
    if detail_type == 'EC2 Instance State-change Notification':
        event_name = 'EC2StateChange'
        resource_type = 'ec2'
        resource_id = detail.get('instance-id', 'unknown')
        state = detail.get('state', 'unknown')
        user_identity = 'System'
        
        structured_log("INFO", f"Real-time EC2 event: {resource_id} -> {state}", correlation_id)
        
    elif detail_type == 'AWS API Call via CloudTrail':
        event_name = detail.get('eventName', 'Unknown')
        user_identity = detail.get('userIdentity', {}).get('arn', 'Unknown')
        resource_type = detect_resource_type(detail)
        resource_id = extract_resource_identifier(detail, resource_type)
        
        structured_log("INFO", f"CloudTrail event: {event_name} on {resource_type}/{resource_id}", correlation_id)
        
    else:
        structured_log("WARN", f"Unknown event type: {detail_type}", correlation_id)
        return {"status": "ignored", "reason": "unknown_event_type"}
    
    # STAGE 1: Create incident record
    stage1_start = datetime.utcnow()
    create_incident_record(
        correlation_id=correlation_id,
        event_details=detail,
        resource_type=resource_type,
        resource_id=resource_id,
        workflow_state=WorkflowState.DETECTING
    )
    stage1_duration = (datetime.utcnow() - stage1_start).total_seconds()
    
    # STAGE 2: Check cooldown
    stage2_start = datetime.utcnow()
    in_cooldown, last_incident_id = check_cooldown(resource_type, resource_id)
    if in_cooldown:
        structured_log("WARN", f"Resource in cooldown period (last incident: {last_incident_id})", correlation_id)
        update_workflow_state(
            correlation_id,
            WorkflowState.COOLDOWN,
            {'cooldown_reason': f'Recent incident: {last_incident_id}'}
        )
        return {
            "status": "cooldown",
            "correlation_id": correlation_id,
            "last_incident": last_incident_id
        }
    stage2_duration = (datetime.utcnow() - stage2_start).total_seconds()
    
    # STAGE 3: Get similar incidents for context
    stage3_start = datetime.utcnow()
    similar_incidents = get_similar_incidents(resource_type, EventClassification.FAILURE)
    structured_log("INFO", f"Found {len(similar_incidents)} similar incidents", correlation_id)
    stage3_duration = (datetime.utcnow() - stage3_start).total_seconds()
    
    # STAGE 4: Enhanced AI analysis
    stage4_start = datetime.utcnow()
    update_workflow_state(correlation_id, WorkflowState.ANALYZING)
    
    try:
        analysis = analyze_with_bedrock_enhanced(
            event_details=detail,
            resource_type=resource_type,
            resource_id=resource_id,
            similar_incidents=similar_incidents,
            correlation_id=correlation_id
        )
        
        structured_log("INFO", f"Analysis complete: {analysis['classification']} (confidence: {analysis['confidence']})", correlation_id)
        
        # Store analysis
        update_workflow_state(
            correlation_id,
            WorkflowState.ANALYZING,
            {
                'event_classification': analysis['classification'],
                'confidence': analysis['confidence'],
                'severity': analysis['severity'],
                'llm_analysis': json.dumps(analysis)
            }
        )
        
    except Exception as e:
        structured_log("ERROR", f"Analysis failed: {e}", correlation_id)
        update_workflow_state(correlation_id, WorkflowState.FAILED, {'error': str(e)})
        return {"status": "error", "correlation_id": correlation_id, "error": str(e)}
    
    stage4_duration = (datetime.utcnow() - stage4_start).total_seconds()
    
    # STAGE 5: Decision - Should we recover?
    classification = analysis['classification']
    confidence = analysis['confidence']
    
    if classification not in [EventClassification.FAILURE, EventClassification.TAMPERING]:
        structured_log("INFO", f"No recovery needed: {classification}", correlation_id)
        update_workflow_state(correlation_id, WorkflowState.COMPLETED, {'recovery_needed': False})
        return {
            "status": "no_action",
            "correlation_id": correlation_id,
            "classification": classification
        }
    
    if confidence < CONFIDENCE_THRESHOLD:
        structured_log("WARN", f"Confidence too low: {confidence} < {CONFIDENCE_THRESHOLD}", correlation_id)
        update_workflow_state(
            correlation_id,
            WorkflowState.COMPLETED,
            {'recovery_needed': False, 'reason': 'low_confidence'}
        )
        # Send notification for manual review (optional - gracefully handle missing topic)
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=f"⚠️ DevOps AI Agent: Manual Review Required - {resource_id}",
                Message=f"Low confidence ({confidence}) for {classification} event. Please review manually.\nIncident ID: {correlation_id}"
            )
        except Exception as e:
            structured_log("WARN", f"SNS notification failed (topic may not exist): {e}", correlation_id)
        return {
            "status": "manual_review_required",
            "correlation_id": correlation_id,
            "confidence": confidence
        }
    
    # STAGE 6: Generate recovery plan
    stage6_start = datetime.utcnow()
    update_workflow_state(correlation_id, WorkflowState.PLANNING)
    
    recovery_plan = generate_recovery_plan(
        analysis=analysis,
        resource_type=resource_type,
        resource_id=resource_id,
        similar_incidents=similar_incidents,
        correlation_id=correlation_id
    )
    
    update_workflow_state(
        correlation_id,
        WorkflowState.PLANNING,
        {'recovery_plan': json.dumps(recovery_plan)}
    )
    stage6_duration = (datetime.utcnow() - stage6_start).total_seconds()
    
    # STAGE 7: Execute recovery
    stage7_start = datetime.utcnow()
    update_workflow_state(correlation_id, WorkflowState.EXECUTING)
    
    recovery_result = execute_recovery_simple(resource_type, correlation_id)
    
    stage7_duration = (datetime.utcnow() - stage7_start).total_seconds()
    
    # STAGE 8: Update final state
    total_duration = (datetime.utcnow() - start_time).total_seconds()
    
    final_state = WorkflowState.COMPLETED if recovery_result['success'] else WorkflowState.FAILED
    
    update_workflow_state(
        correlation_id,
        final_state,
        {
            'recovery_result': json.dumps(recovery_result),
            'recovery_duration_seconds': total_duration,
            'success': recovery_result['success']
        }
    )
    
    # STAGE 9: Send notification
    timeline = {
        'incident_creation': stage1_duration,
        'cooldown_check': stage2_duration,
        'context_retrieval': stage3_duration,
        'ai_analysis': stage4_duration,
        'recovery_planning': stage6_duration,
        'recovery_execution': stage7_duration
    }
    
    send_enhanced_notification(
        incident_id=correlation_id,
        event_name=event_name,
        resource_type=resource_type,
        resource_id=resource_id,
        user_identity=user_identity,
        analysis=analysis,
        recovery_result=recovery_result,
        timeline=timeline
    )
    
    # STAGE 10: Publish metrics
    publish_metrics(
        resource_type=resource_type,
        classification=classification,
        recovery_duration=int(total_duration),
        success=recovery_result['success']
    )
    
    structured_log("INFO", f"Handler complete: {final_state}", correlation_id, duration=total_duration)
    
    return {
        "status": "ok",
        "correlation_id": correlation_id,
        "classification": classification,
        "confidence": confidence,
        "recovery_triggered": True,
        "build_id": recovery_result.get('build_id'),
        "total_duration_seconds": total_duration
    }
