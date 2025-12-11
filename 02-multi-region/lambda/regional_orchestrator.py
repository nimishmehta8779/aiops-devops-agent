"""
Regional Orchestrator Lambda
Routes events to local agents or central reasoning layer
"""

import json
import os
import boto3
from datetime import datetime
from typing import Dict, Any

# AWS clients
events = boto3.client('events')
lambda_client = boto3.client('lambda')

# Environment variables
CENTRAL_REGION = os.environ.get('CENTRAL_REGION', 'us-east-1')
CURRENT_REGION = os.environ.get('AWS_REGION', 'us-east-1')
CENTRAL_EVENT_BUS_ARN = os.environ.get('CENTRAL_EVENT_BUS_ARN', '')
LOCAL_ORCHESTRATOR_ARN = os.environ.get('LOCAL_ORCHESTRATOR_ARN', '')


def log(level: str, message: str, **kwargs):
    """Structured logging"""
    print(json.dumps({
        'timestamp': datetime.utcnow().isoformat(),
        'level': level,
        'message': message,
        'region': CURRENT_REGION,
        **kwargs
    }))


def handler(event, context):
    """
    Regional handler - acts as a proxy
    1. Annotate event with regional context
    2. If central region: Process locally
    3. If remote region: Forward to central event bus
    """
    try:
        log("INFO", "Regional orchestrator invoked", event=event)
        
        # Add regional context
        event['region'] = CURRENT_REGION
        event['regional_context'] = {
            'forwarded_from': CURRENT_REGION,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # If we are in the central region, process normally
        if CURRENT_REGION == CENTRAL_REGION:
            log("INFO", "Processing in central region")
            # Invoke local multi-agent orchestrator
            response = lambda_client.invoke(
                FunctionName=LOCAL_ORCHESTRATOR_ARN,
                InvocationType='Event',  # Async
                Payload=json.dumps(event)
            )
            return {'status': 'processing_locally', 'region': CURRENT_REGION}
            
        else:
            # We are in a satellite region - forward to central
            log("INFO", f"Forwarding to central region: {CENTRAL_REGION}")
            
            # Put event to central event bus
            response = events.put_events(
                Entries=[
                    {
                        'Source': event.get('source', 'aws.aiops'),
                        'DetailType': event.get('detail-type', 'Regional Event'),
                        'Detail': json.dumps(event.get('detail', {})),
                        'EventBusName': CENTRAL_EVENT_BUS_ARN,
                        'Resources': event.get('resources', [])
                    }
                ]
            )
            
            return {
                'status': 'forwarded',
                'target_region': CENTRAL_REGION,
                'event_id': response['Entries'][0].get('EventId')
            }
            
    except Exception as e:
        log("ERROR", f"Regional processing failed: {e}")
        raise
