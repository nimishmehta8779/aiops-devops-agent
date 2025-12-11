import json
import boto3
import os

bedrock = boto3.client('bedrock-runtime')
codebuild = boto3.client('codebuild')
sns = boto3.client('sns')

SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']
MODEL_ID = "amazon.titan-text-express-v1"

# Map of resource types to their CodeBuild projects
RESOURCE_RECOVERY_MAP = {
    "ec2": "aiops-devops-agent-apply",
    "lambda": "aiops-devops-agent-apply",
    "dynamodb": "aiops-devops-agent-apply",
    "s3": "aiops-devops-agent-apply",
    "rds": "aiops-devops-agent-apply",
    # All use the same project for now, but can be split later
}

def detect_resource_type(event_detail):
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

def extract_resource_identifier(event_detail, resource_type):
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

def handler(event, context):
    print("Event:", json.dumps(event))
    
    # Detect event type: Real-time vs CloudTrail
    detail_type = event.get('detail-type', '')
    detail = event.get('detail', {})
    
    # Handle Real-time EC2 State Change events
    if detail_type == 'EC2 Instance State-change Notification':
        event_name = 'EC2StateChange'
        resource_type = 'ec2'
        resource_id = detail.get('instance-id', 'unknown')
        state = detail.get('state', 'unknown')
        user_identity = 'System'
        
        print(f"Real-time EC2 event detected: {resource_id} -> {state}")
        
    # Handle CloudTrail API Call events
    elif detail_type == 'AWS API Call via CloudTrail':
        event_name = detail.get('eventName', 'Unknown')
        user_identity = detail.get('userIdentity', {}).get('arn', 'Unknown')
        
        # Detect resource type
        resource_type = detect_resource_type(detail)
        resource_id = extract_resource_identifier(detail, resource_type)
        
        print(f"CloudTrail event detected: {event_name} on {resource_type}/{resource_id}")
        
    else:
        print(f"Unknown event type: {detail_type}")
        return {"status": "ignored"}
    
    print(f"Detected resource type: {resource_type}, ID: {resource_id}")
    
    # Enhanced prompt with resource-specific context
    if detail_type == 'EC2 Instance State-change Notification':
        # For real-time events, use simpler prompt
        prompt = f"""
        You are a DevOps Agent. An EC2 instance changed state.
        
        Instance ID: {resource_id}
        New State: {state}
        
        If the state is "terminated", "stopped", or "stopping", this is a FAILURE.
        Otherwise, it is NORMAL.
        
        Classification:"""
    else:
        # For CloudTrail events, use detailed prompt
        prompt = f"""
        You are a DevOps Agent analyzing AWS infrastructure events.
        
        Event Details:
        - Event Name: {event_name}
        - Resource Type: {resource_type}
        - Resource ID: {resource_id}
        - User: {user_identity}
        - Full Details: {json.dumps(detail)}
        
        Analysis Instructions:
        1. If this is a DELETE, TERMINATE, or STOP event for critical resources, classify as FAILURE
        2. If this is unauthorized configuration change (like SSM parameter tampering), classify as TAMPERING
        3. If this is routine maintenance or expected change, classify as NORMAL
        
        Critical Resource Types: ec2, lambda, dynamodb, s3, rds
        
        Respond with ONE of these classifications:
        - FAILURE (for deletions/terminations of critical resources)
        - TAMPERING (for unauthorized config changes)
        - NORMAL (for expected operations)
        
        Classification:"""
    
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 512,
            "stopSequences": [],
            "temperature": 0,
            "topP": 1
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
        llm_output = response_body.get('results')[0].get('outputText')
        print("LLM Output:", llm_output)
        print(f"DEBUG: Checking condition - 'RECOVER' in output: {'RECOVER' in llm_output}, 'TAMPERING' in output: {'TAMPERING' in llm_output}, 'FAILURE' in output: {'FAILURE' in llm_output}")
        
        if "RECOVER" in llm_output or "TAMPERING" in llm_output or "FAILURE" in llm_output:
            print("DEBUG: Condition matched! Triggering recovery...")
            
            # Determine which CodeBuild project to use
            codebuild_project = RESOURCE_RECOVERY_MAP.get(resource_type, "aiops-devops-agent-apply")
            
            # Trigger Recovery
            cb_resp = codebuild.start_build(projectName=codebuild_project)
            build_id = cb_resp['build']['id']
            print(f"DEBUG: CodeBuild started: {build_id}")
            
            # Enhanced Notification with resource details
            msg = f"""
╔══════════════════════════════════════════════════════════════════════╗
║              DevOps Agent - Auto-Recovery Triggered                  ║
╚══════════════════════════════════════════════════════════════════════╝

🔴 INCIDENT DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Event: {event_name}
Resource Type: {resource_type.upper()}
Resource ID: {resource_id}
User: {user_identity}

🤖 AI ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{llm_output}

🔄 RECOVERY ACTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CodeBuild Project: {codebuild_project}
Build ID: {build_id}
Recovery Method: Infrastructure as Code (Terraform)

⏱️ TIMELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Detection: Immediate
Analysis: ~2 seconds
Recovery Started: Now
Expected Completion: 2-5 minutes

📧 You will receive a final status report once recovery is complete.
            """
            
            sns.publish(
                TopicArn=SNS_TOPIC_ARN, 
                Subject=f"🚨 DevOps Agent: {resource_type.upper()} Recovery Started - {resource_id}", 
                Message=msg
            )
            print("DEBUG: Notification sent")
        else:
            print("DEBUG: Condition NOT matched - no recovery triggered")
            
    except Exception as e:
        print(f"Error: {e}")
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject="DevOps Agent Error", Message=str(e))
        
    return {"status": "ok"}
