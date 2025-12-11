"""
Multi-Agent Orchestrator Lambda
Main entry point for multi-agent AIOps system
"""

import json
import os
from datetime import datetime
from typing import Dict, Any

# Import agent framework and all agents
from agent_framework import AgentCoordinator, AgentType, agent_registry
from triage_agent import TriageAgent
from telemetry_agent import TelemetryAgent
from remediation_agent import RemediationAgent
from risk_agent import RiskAgent
from comms_agent import CommunicationsAgent

import boto3

# AWS clients
dynamodb = boto3.client('dynamodb')

# Environment variables
INCIDENT_TABLE = os.environ.get('INCIDENT_TABLE', 'aiops-incidents')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
CODEBUILD_PROJECT = os.environ.get('CODEBUILD_PROJECT', 'aiops-devops-agent-apply')
DEFAULT_EMAIL = os.environ.get('DEFAULT_EMAIL', 'nimish.mehta@gmail.com')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'noreply@aiops.example.com')


def structured_log(level: str, message: str, correlation_id: str = None, **kwargs):
    """Structured logging"""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'level': level,
        'message': message,
        'correlation_id': correlation_id,
        **kwargs
    }
    print(json.dumps(log_entry))


def generate_correlation_id() -> str:
    """Generate unique correlation ID"""
    import uuid
    return f"incident-{uuid.uuid4()}"


def detect_resource_type(event_detail: Dict) -> str:
    """Detect resource type from event"""
    event_name = event_detail.get('eventName', '')
    event_source = event_detail.get('eventSource', '')
    
    if 'ec2' in event_source or event_name in ['TerminateInstances', 'StopInstances']:
        return 'ec2'
    elif 'lambda' in event_source or event_name in ['DeleteFunction']:
        return 'lambda'
    elif 'dynamodb' in event_source or event_name in ['DeleteTable']:
        return 'dynamodb'
    elif 's3' in event_source or event_name in ['DeleteBucket']:
        return 's3'
    elif 'rds' in event_source or event_name in ['DeleteDBInstance']:
        return 'rds'
    elif 'ssm' in event_source:
        return 'ssm'
    
    return 'unknown'


def extract_resource_identifier(event_detail: Dict, resource_type: str) -> str:
    """Extract resource ID from event"""
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
    elif resource_type == 'rds':
        return request_params.get('dBInstanceIdentifier', 'unknown')
    elif resource_type == 'ssm':
        return request_params.get('name', 'unknown')
    
    return 'unknown'


def create_incident_record(correlation_id: str, context: Dict) -> bool:
    """Create initial incident record in DynamoDB"""
    try:
        timestamp = datetime.utcnow().isoformat()
        
        item = {
            'incident_id': {'S': correlation_id},
            'incident_timestamp': {'S': timestamp},
            'resource_type': {'S': context['resource_type']},
            'resource_id': {'S': context['resource_id']},
            'resource_key': {'S': f"{context['resource_type']}#{context['resource_id']}"},
            'workflow_state': {'S': 'DETECTING'},
            'event_details': {'S': json.dumps(context['event_details'], default=str)},
            'created_at': {'S': timestamp},
            'updated_at': {'S': timestamp}
        }
        
        dynamodb.put_item(TableName=INCIDENT_TABLE, Item=item)
        return True
        
    except Exception as e:
        structured_log("ERROR", f"Error creating incident record: {e}", correlation_id)
        return False


def update_workflow_state(incident_id: str, state: str, data: Dict = None) -> bool:
    """Update workflow state in DynamoDB"""
    try:
        update_expr = "SET workflow_state = :state, updated_at = :updated"
        expr_values = {
            ':state': {'S': state},
            ':updated': {'S': datetime.utcnow().isoformat()}
        }
        
        if data:
            for key, value in data.items():
                update_expr += f", {key} = :{key}"
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


def handler(event, context):
    """
    Main Lambda handler for multi-agent orchestration
    """
    start_time = datetime.utcnow()
    correlation_id = generate_correlation_id()
    
    structured_log("INFO", "Multi-agent orchestrator invoked", correlation_id, event=event)
    
    # Parse event
    detail_type = event.get('detail-type', '')
    detail = event.get('detail', {})
    
    # Detect resource type and ID
    if detail_type == 'EC2 Instance State-change Notification':
        event_name = 'EC2StateChange'
        resource_type = 'ec2'
        resource_id = detail.get('instance-id', 'unknown')
        user_identity = 'System'
    elif detail_type == 'AWS API Call via CloudTrail':
        event_name = detail.get('eventName', 'Unknown')
        user_identity = detail.get('userIdentity', {}).get('arn', 'Unknown')
        resource_type = detect_resource_type(detail)
        resource_id = extract_resource_identifier(detail, resource_type)
    elif detail_type == 'Regional Event':
        # Handle forwarded events from satellite regions
        nested_detail = json.loads(event.get('Detail', '{}'))
        event_name = nested_detail.get('eventName', 'RegionalEvent')
        resource_type = detect_resource_type(nested_detail)
        resource_id = extract_resource_identifier(nested_detail, resource_type)
        user_identity = 'RegionalForwarder'
        detail = nested_detail # promote nested detail
    else:
        structured_log("WARN", f"Unknown event type: {detail_type}", correlation_id)
        return {"status": "ignored", "reason": "unknown_event_type"}
    
    # Extract regional context
    region = event.get('region', os.environ.get('AWS_REGION', 'us-east-1'))
    regional_context = event.get('regional_context', {})

    # Build context for agents
    incident_context = {
        'correlation_id': correlation_id,
        'event_name': event_name,
        'resource_type': resource_type,
        'resource_id': resource_id,
        'region': region,
        'regional_context': regional_context,
        'user_identity': user_identity,
        'event_details': detail,
        'event_time': detail.get('eventTime', datetime.utcnow().isoformat())
    }
    
    # Create incident record
    create_incident_record(correlation_id, incident_context)
    
    # Configure agents
    agent_config = {
        AgentType.TRIAGE: {
            'incident_table': INCIDENT_TABLE
        },
        AgentType.TELEMETRY: {
            'incident_table': INCIDENT_TABLE
        },
        AgentType.REMEDIATION: {
            'incident_table': INCIDENT_TABLE,
            'codebuild_project': CODEBUILD_PROJECT
        },
        AgentType.RISK: {
            'incident_table': INCIDENT_TABLE,
            'blocked_windows': [
                {'day': 4, 'start_hour': 16, 'end_hour': 23}  # Friday 4pm-11pm
            ]
        },
        AgentType.COMMUNICATIONS: {
            'incident_table': INCIDENT_TABLE,
            'default_email': DEFAULT_EMAIL,
            'sender_email': SENDER_EMAIL,
            'sns_topic_arn': SNS_TOPIC_ARN
        }
    }
    
    # Create coordinator
    coordinator = AgentCoordinator(correlation_id, agent_registry)
    
    # Define agent execution order (by priority)
    agent_types = [
        AgentType.TRIAGE,       # Priority: CRITICAL
        AgentType.TELEMETRY,    # Priority: HIGH
        AgentType.RISK,         # Priority: HIGH
        AgentType.REMEDIATION,  # Priority: MEDIUM
        AgentType.COMMUNICATIONS # Priority: LOW
    ]
    
    # Update workflow state
    update_workflow_state(correlation_id, 'ANALYZING')
    
    # Orchestrate agents
    try:
        results = coordinator.orchestrate(
            context=incident_context,
            agent_types=agent_types,
            config=agent_config
        )
        
        structured_log("INFO", "Agent orchestration complete", correlation_id, results=results)
        
        # Update final workflow state
        final_state = 'COMPLETED' if results['successful_agents'] == results['total_agents'] else 'FAILED'
        update_workflow_state(
            correlation_id,
            final_state,
            {
                'agent_results': json.dumps(results, default=str),
                'total_duration_seconds': (datetime.utcnow() - start_time).total_seconds()
            }
        )
        
        return {
            'status': 'success',
            'correlation_id': correlation_id,
            'results': results
        }
        
    except Exception as e:
        structured_log("ERROR", f"Agent orchestration failed: {e}", correlation_id)
        update_workflow_state(correlation_id, 'FAILED', {'error': str(e)})
        
        return {
            'status': 'error',
            'correlation_id': correlation_id,
            'error': str(e)
        }
