import boto3
import time
import json
import sys

# Configuration
AGENT_NAME = "aiops-devops-agent"
AGENT_ROLE_NAME = "aiops-devops-agent-role"
ACTION_GROUP_NAME = "InfraOpsActionGroup"
LAMBDA_FUNCTION_NAME = "aiops-devops-agent-infra-ops"
MODEL_ID = "amazon.titan-text-express-v1" # Cost-effective model

bedrock_agent = boto3.client('bedrock-agent')
iam = boto3.client('iam')
lambda_client = boto3.client('lambda')

def get_role_arn(role_name):
    try:
        return iam.get_role(RoleName=role_name)['Role']['Arn']
    except iam.exceptions.NoSuchEntityException:
        return None

def create_agent_role():
    role_name = AGENT_ROLE_NAME
    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy)
        )
        print(f"Created IAM Role: {role_name}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"IAM Role {role_name} already exists")

    # Attach Bedrock policy
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="BedrockAgentPolicy",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "bedrock:InvokeModel",
                    "Resource": f"arn:aws:bedrock:us-east-1::foundation-model/{MODEL_ID}"
                }
            ]
        })
    )
    return iam.get_role(RoleName=role_name)['Role']['Arn']

def create_agent(role_arn):
    instruction = """
    You are a DevOps Agent responsible for monitoring and recovering infrastructure.
    
    Your capabilities:
    1. Check Infrastructure Health: Use 'get_infra_health' to see the status of EC2 instances.
    2. Analyze Failures: If you suspect a failure, use 'get_infra_health' or ask the user for logs.
    3. Recover: If infrastructure is unhealthy or missing, use 'trigger_recovery' to run the CodeBuild pipeline.
    4. Notify: Always use 'send_notification' to inform the user (your-email@example.com) about failures and recovery actions.
    
    Workflow:
    - If you receive a failure alert, first check health.
    - If health is bad, trigger recovery.
    - Send a notification about the action taken.
    """
    
    try:
        response = bedrock_agent.create_agent(
            agentName=AGENT_NAME,
            agentResourceRoleArn=role_arn,
            instruction=instruction,
            foundationModel=MODEL_ID,
            description="DevOps Agent for Auto-Remediation"
        )
        print(f"Created Agent: {response['agent']['agentId']}")
        return response['agent']['agentId']
    except Exception as e:
        print(f"Error creating agent: {e}")
        # Try to find existing
        agents = bedrock_agent.list_agents()
        for a in agents['agentSummaries']:
            if a['agentName'] == AGENT_NAME:
                return a['agentId']
        raise e

def create_action_group(agent_id, lambda_arn):
    api_schema = {
        "openapi": "3.0.0",
        "info": {
            "title": "InfraOps API",
            "version": "1.0.0"
        },
        "paths": {
            "/health": {
                "get": {
                    "summary": "Get infrastructure health status",
                    "operationId": "get_infra_health",
                    "responses": {
                        "200": {
                            "description": "Health status",
                            "content": {"application/json": {"schema": {"type": "string"}}}
                        }
                    }
                }
            },
            "/recover": {
                "post": {
                    "summary": "Trigger infrastructure recovery pipeline",
                    "operationId": "trigger_recovery",
                    "responses": {
                        "200": {
                            "description": "Recovery started",
                            "content": {"application/json": {"schema": {"type": "string"}}}
                        }
                    }
                }
            },
            "/notify": {
                "post": {
                    "summary": "Send email notification",
                    "operationId": "send_notification",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "message": {"type": "string", "description": "The message to send"}
                                    },
                                    "required": ["message"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Notification sent",
                            "content": {"application/json": {"schema": {"type": "string"}}}
                        }
                    }
                }
            }
        }
    }

    try:
        bedrock_agent.create_agent_action_group(
            agentId=agent_id,
            agentVersion='DRAFT',
            actionGroupName=ACTION_GROUP_NAME,
            actionGroupExecutor={
                'lambda': lambda_arn
            },
            apiSchema={
                'payload': json.dumps(api_schema)
            },
            description="Actions for Infrastructure Operations"
        )
        print("Created Action Group")
    except Exception as e:
        print(f"Error creating action group (might exist): {e}")

def prepare_agent(agent_id):
    try:
        bedrock_agent.prepare_agent(agentId=agent_id)
        print("Agent Prepared")
        
        # Wait for preparation
        while True:
            resp = bedrock_agent.get_agent(agentId=agent_id)
            status = resp['agent']['agentStatus']
            if status == 'PREPARED':
                break
            print(f"Waiting for agent to be PREPARED... ({status})")
            time.sleep(2)
            
        # Create Alias
        try:
            bedrock_agent.create_agent_alias(
                agentId=agent_id,
                agentAliasName="prod",
                description="Production Alias"
            )
            print("Created Agent Alias: prod")
        except Exception as e:
            print(f"Alias might exist: {e}")
            
    except Exception as e:
        print(f"Error preparing agent: {e}")

def main():
    print("Setting up Bedrock Agent...")
    
    # 1. Role
    role_arn = create_agent_role()
    time.sleep(10) # Wait for IAM propagation
    
    # 2. Agent
    agent_id = create_agent(role_arn)
    
    # 3. Get Lambda ARN
    lambda_arn = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)['Configuration']['FunctionArn']
    
    # 4. Action Group
    create_action_group(agent_id, lambda_arn)
    
    # 5. Prepare
    prepare_agent(agent_id)
    
    print(f"SUCCESS: Agent {agent_id} is ready.")

if __name__ == "__main__":
    main()
