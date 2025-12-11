"""
Telemetry Agent - Deep Query of Metrics, Logs, and Traces
Queries CloudWatch Metrics/Logs, X-Ray, Application Signals
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from agent_framework import BaseAgent, AgentType, AgentPriority, agent_registry
import boto3


@agent_registry.register
class TelemetryAgent(BaseAgent):
    """
    Telemetry agent for deep querying of observability data
    
    Responsibilities:
    - Query CloudWatch Metrics for resource health
    - Query CloudWatch Logs for error patterns
    - Query X-Ray for distributed traces
    - Correlation ID tracking across services
    - Anomaly detection in metrics
    """
    
    def __init__(self, correlation_id: str, config: Dict[str, Any] = None):
        super().__init__(correlation_id, config)
        
        # Determine region to query
        self.target_region = config.get('region', os.environ.get('AWS_REGION', 'us-east-1'))
        
        # Initialize clients for target region
        self.cloudwatch = boto3.client('cloudwatch', region_name=self.target_region)
        self.logs_client = boto3.client('logs', region_name=self.target_region)
        self.xray = boto3.client('xray', region_name=self.target_region)
    
    @property
    def agent_type(self) -> AgentType:
        return AgentType.TELEMETRY
    
    @property
    def priority(self) -> AgentPriority:
        return AgentPriority.HIGH  # Telemetry runs after triage
    
    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze telemetry data for the incident
        
        Returns:
            {
                'metrics': {...},
                'logs': {...},
                'traces': {...},
                'anomalies': [...],
                'correlation_data': {...}
            }
        """
        resource_type = context.get('resource_type', 'unknown')
        resource_id = context.get('resource_id', 'unknown')
        event_details = context.get('event_details', {})
        region = context.get('region', self.target_region)
        
        self.log("INFO", f"Analyzing telemetry for {resource_type}/{resource_id} in {region}")
        
        # Update clients if region in context differs from init (dynamic region switching)
        if region != self.target_region:
            self._update_clients(region)
        
        # Get time window (last 15 minutes before incident)
        incident_time = datetime.fromisoformat(
            event_details.get('eventTime', datetime.utcnow().isoformat()).replace('Z', '+00:00')
        )
        start_time = incident_time - timedelta(minutes=15)
        end_time = incident_time
        
        # Query metrics
        metrics = self._query_metrics(resource_type, resource_id, start_time, end_time)
        
        # Query logs
        logs = self._query_logs(resource_type, resource_id, start_time, end_time)
        
        # Query traces (if available)
        traces = self._query_traces(self.correlation_id, start_time, end_time)
        
        # Detect anomalies
        anomalies = self._detect_anomalies(metrics, logs)
        
        # Build correlation data
        correlation_data = self._build_correlation_data(metrics, logs, traces)
        
        return {
            'metrics': metrics,
            'logs': logs,
            'traces': traces,
            'anomalies': anomalies,
            'correlation_data': correlation_data,
            'telemetry_health_score': self._calculate_health_score(metrics, anomalies)
        }
    
    def execute(self, context: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute telemetry actions
        
        Actions:
        - Store telemetry data in DynamoDB
        - Create CloudWatch dashboard for incident
        - Publish telemetry metrics
        """
        # Store telemetry results
        self._store_telemetry_results(self.correlation_id, analysis)
        
        # Publish metrics
        self._publish_telemetry_metrics(analysis)
        
        return {
            'telemetry_collected': True,
            'metrics_count': len(analysis['metrics']),
            'log_entries_count': len(analysis['logs'].get('entries', [])),
            'traces_count': len(analysis['traces'].get('traces', [])),
            'anomalies_detected': len(analysis['anomalies']),
            'health_score': analysis['telemetry_health_score']
        }
    
    def _query_metrics(
        self,
        resource_type: str,
        resource_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """Query CloudWatch metrics for the resource"""
        try:
            # Map resource type to CloudWatch namespace and dimensions
            metric_config = self._get_metric_config(resource_type, resource_id)
            
            if not metric_config:
                return {'error': 'No metric configuration for resource type'}
            
            metrics_data = {}
            
            for metric_name in metric_config['metrics']:
                response = self.cloudwatch.get_metric_statistics(
                    Namespace=metric_config['namespace'],
                    MetricName=metric_name,
                    Dimensions=metric_config['dimensions'],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=60,  # 1 minute
                    Statistics=['Average', 'Maximum', 'Minimum']
                )
                
                datapoints = response.get('Datapoints', [])
                if datapoints:
                    metrics_data[metric_name] = {
                        'datapoints': sorted(datapoints, key=lambda x: x['Timestamp']),
                        'average': sum(d['Average'] for d in datapoints) / len(datapoints),
                        'max': max(d['Maximum'] for d in datapoints),
                        'min': min(d['Minimum'] for d in datapoints)
                    }
            
            return metrics_data
            
        except Exception as e:
            self.log("ERROR", f"Error querying metrics: {e}")
            return {'error': str(e)}
    
    def _update_clients(self, region: str):
        """Update AWS clients for a different region"""
        self.log("INFO", f"Switching telemetry clients to region: {region}")
        self.target_region = region
        self.cloudwatch = boto3.client('cloudwatch', region_name=region)
        self.logs_client = boto3.client('logs', region_name=region)
        self.xray = boto3.client('xray', region_name=region)

    def _get_metric_config(self, resource_type: str, resource_id: str) -> Optional[Dict]:
        """Get metric configuration for resource type"""
        configs = {
            'ec2': {
                'namespace': 'AWS/EC2',
                'dimensions': [{'Name': 'InstanceId', 'Value': resource_id}],
                'metrics': ['CPUUtilization', 'NetworkIn', 'NetworkOut', 'StatusCheckFailed']
            },
            'lambda': {
                'namespace': 'AWS/Lambda',
                'dimensions': [{'Name': 'FunctionName', 'Value': resource_id}],
                'metrics': ['Invocations', 'Errors', 'Duration', 'Throttles']
            },
            'dynamodb': {
                'namespace': 'AWS/DynamoDB',
                'dimensions': [{'Name': 'TableName', 'Value': resource_id}],
                'metrics': ['ConsumedReadCapacityUnits', 'ConsumedWriteCapacityUnits', 'UserErrors']
            },
            'rds': {
                'namespace': 'AWS/RDS',
                'dimensions': [{'Name': 'DBInstanceIdentifier', 'Value': resource_id}],
                'metrics': ['CPUUtilization', 'DatabaseConnections', 'ReadLatency', 'WriteLatency']
            }
        }
        
        return configs.get(resource_type)
    
    def _query_logs(
        self,
        resource_type: str,
        resource_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """Query CloudWatch Logs for error patterns"""
        try:
            # Determine log group based on resource type
            log_group = self._get_log_group(resource_type, resource_id)
            
            if not log_group:
                return {'entries': [], 'error': 'No log group found'}
            
            # Query logs using Insights
            query = f"""
            fields @timestamp, @message
            | filter @message like /ERROR|Exception|Failed|Timeout/
            | sort @timestamp desc
            | limit 50
            """
            
            response = self.logs.start_query(
                logGroupName=log_group,
                startTime=int(start_time.timestamp()),
                endTime=int(end_time.timestamp()),
                queryString=query
            )
            
            query_id = response['queryId']
            
            # Wait for query to complete (max 10 seconds)
            import time
            for _ in range(10):
                result = self.logs.get_query_results(queryId=query_id)
                status = result['status']
                
                if status == 'Complete':
                    entries = []
                    for row in result.get('results', []):
                        entry = {field['field']: field['value'] for field in row}
                        entries.append(entry)
                    
                    return {
                        'entries': entries,
                        'log_group': log_group,
                        'error_count': len(entries)
                    }
                elif status == 'Failed':
                    return {'entries': [], 'error': 'Query failed'}
                
                time.sleep(1)
            
            return {'entries': [], 'error': 'Query timeout'}
            
        except Exception as e:
            self.log("ERROR", f"Error querying logs: {e}")
            return {'entries': [], 'error': str(e)}
    
    def _get_log_group(self, resource_type: str, resource_id: str) -> Optional[str]:
        """Get log group name for resource"""
        log_groups = {
            'lambda': f'/aws/lambda/{resource_id}',
            'ecs': f'/ecs/{resource_id}',
            'rds': f'/aws/rds/instance/{resource_id}/error'
        }
        
        return log_groups.get(resource_type)
    
    def _query_traces(
        self,
        correlation_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """Query X-Ray traces for distributed tracing"""
        try:
            # Query X-Ray for traces with correlation ID
            response = self.xray.get_trace_summaries(
                StartTime=start_time,
                EndTime=end_time,
                FilterExpression=f'annotation.correlation_id = "{correlation_id}"'
            )
            
            trace_summaries = response.get('TraceSummaries', [])
            
            # Get detailed traces
            if trace_summaries:
                trace_ids = [t['Id'] for t in trace_summaries[:5]]  # Limit to 5
                
                traces_response = self.xray.batch_get_traces(TraceIds=trace_ids)
                traces = traces_response.get('Traces', [])
                
                return {
                    'traces': traces,
                    'trace_count': len(traces),
                    'has_errors': any(t.get('HasError') for t in trace_summaries)
                }
            
            return {'traces': [], 'trace_count': 0, 'has_errors': False}
            
        except Exception as e:
            self.log("ERROR", f"Error querying traces: {e}")
            return {'traces': [], 'error': str(e)}
    
    def _detect_anomalies(self, metrics: Dict, logs: Dict) -> List[Dict]:
        """Detect anomalies in metrics and logs"""
        anomalies = []
        
        # Check for metric anomalies
        for metric_name, data in metrics.items():
            if 'error' in data:
                continue
            
            # Simple threshold-based anomaly detection
            avg = data.get('average', 0)
            max_val = data.get('max', 0)
            
            # CPU > 80%
            if metric_name == 'CPUUtilization' and avg > 80:
                anomalies.append({
                    'type': 'metric',
                    'metric': metric_name,
                    'severity': 'high',
                    'description': f'High CPU utilization: {avg:.1f}%'
                })
            
            # Error rate > 5%
            if metric_name == 'Errors' and avg > 5:
                anomalies.append({
                    'type': 'metric',
                    'metric': metric_name,
                    'severity': 'high',
                    'description': f'High error rate: {avg:.1f}'
                })
        
        # Check for log anomalies
        error_count = logs.get('error_count', 0)
        if error_count > 10:
            anomalies.append({
                'type': 'log',
                'severity': 'medium',
                'description': f'High error log count: {error_count} errors in 15 minutes'
            })
        
        return anomalies
    
    def _build_correlation_data(
        self,
        metrics: Dict,
        logs: Dict,
        traces: Dict
    ) -> Dict[str, Any]:
        """Build correlation data across telemetry sources"""
        return {
            'has_metrics': bool(metrics and 'error' not in metrics),
            'has_logs': bool(logs.get('entries')),
            'has_traces': bool(traces.get('traces')),
            'correlation_strength': self._calculate_correlation_strength(metrics, logs, traces)
        }
    
    def _calculate_correlation_strength(self, metrics: Dict, logs: Dict, traces: Dict) -> float:
        """Calculate correlation strength (0.0-1.0)"""
        strength = 0.0
        
        if metrics and 'error' not in metrics:
            strength += 0.4
        if logs.get('entries'):
            strength += 0.3
        if traces.get('traces'):
            strength += 0.3
        
        return strength
    
    def _calculate_health_score(self, metrics: Dict, anomalies: List) -> float:
        """Calculate overall health score (0.0-1.0)"""
        if not metrics or 'error' in metrics:
            return 0.5  # Unknown
        
        # Start with perfect health
        health = 1.0
        
        # Deduct for anomalies
        health -= len(anomalies) * 0.1
        
        return max(0.0, min(1.0, health))
    
    def _store_telemetry_results(self, incident_id: str, analysis: Dict[str, Any]):
        """Store telemetry results in DynamoDB"""
        try:
            self.dynamodb.update_item(
                TableName=self.config.get('incident_table', 'aiops-incidents'),
                Key={'incident_id': {'S': incident_id}},
                UpdateExpression='SET telemetry_results = :results, updated_at = :updated',
                ExpressionAttributeValues={
                    ':results': {'S': json.dumps(analysis, default=str)},
                    ':updated': {'S': datetime.utcnow().isoformat()}
                }
            )
        except Exception as e:
            self.log("ERROR", f"Error storing telemetry results: {e}")
    
    def _publish_telemetry_metrics(self, analysis: Dict[str, Any]):
        """Publish telemetry metrics to CloudWatch"""
        try:
            self.cloudwatch.put_metric_data(
                Namespace='AIOps/Telemetry',
                MetricData=[
                    {
                        'MetricName': 'AnomaliesDetected',
                        'Value': len(analysis['anomalies']),
                        'Unit': 'Count'
                    },
                    {
                        'MetricName': 'HealthScore',
                        'Value': analysis['telemetry_health_score'],
                        'Unit': 'None'
                    }
                ]
            )
        except Exception as e:
            self.log("ERROR", f"Error publishing metrics: {e}")
