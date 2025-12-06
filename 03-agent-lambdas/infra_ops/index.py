import json
import boto3
import os

ec2 = boto3.client('ec2')
codebuild = boto3.client('codebuild')
cloudtrail = boto3.client('cloudtrail')
sns = boto3.client('sns')

# Hardcoded for simplicity in this demo, ideally passed via env vars
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:YOUR_AWS_ACCOUNT_ID:aiops-devops-agent-notifications"
CODEBUILD_PROJECT = "aiops-devops-agent-apply"

def get_infra_health():
    # Check EC2 instances
    resp = ec2.describe_instance_status(IncludeAllInstances=True)
    statuses = []
    for i in resp.get('InstanceStatuses', []):
        statuses.append({
            'InstanceId': i['InstanceId'],
            'State': i['InstanceState']['Name'],
            'Status': i['InstanceStatus']['Status'],
            'SystemStatus': i['SystemStatus']['Status']
        })
    return statuses

def check_cloudtrail_failures():
    # Look for recent errors
    resp = cloudtrail.lookup_events(
        LookupAttributes=[{'AttributeKey': 'EventName', 'AttributeValue': 'RunInstances'}], # Example
        MaxResults=5
    )
    # In a real agent, we'd filter for "Error" or specific "Delete" events
    return str(resp.get('Events', []))

def trigger_recovery():
    resp = codebuild.start_build(projectName=CODEBUILD_PROJECT)
    return f"Started CodeBuild recovery: {resp['build']['id']}"

def send_notification(message):
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject="DevOps Agent Notification",
        Message=message
    )
    return "Notification sent."

def handler(event, context):
    print("Received event:", json.dumps(event))
    
    actionGroup = event.get('actionGroup')
    apiPath = event.get('apiPath')
    httpMethod = event.get('httpMethod')
    parameters = event.get('parameters', [])
    
    response_body = {"message": "Unknown path"}
    
    if apiPath == '/health':
        health = get_infra_health()
        response_body = {"status": "checked", "details": health}
        
    elif apiPath == '/recover':
        res = trigger_recovery()
        response_body = {"status": "recovery_started", "details": res}
        
    elif apiPath == '/notify':
        # Extract message from request body if present, or parameters
        msg = "Default notification"
        # In OpenAPI, body is in requestBody
        req_body = event.get('requestBody', {})
        content = req_body.get('content', {}).get('application/json', {})
        properties = content.get('properties', [])
        
        # Bedrock sends properties as a list of {name, type, value}
        for p in properties:
            if p['name'] == 'message':
                msg = p['value']
                
        res = send_notification(msg)
        response_body = {"status": "sent", "details": res}

    action_response = {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': actionGroup,
            'apiPath': apiPath,
            'httpMethod': httpMethod,
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {
                    'body': json.dumps(response_body)
                }
            }
        }
    }
    
    return action_response
