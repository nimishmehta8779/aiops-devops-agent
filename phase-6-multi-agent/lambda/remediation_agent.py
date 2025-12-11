"""
Remediation Agent - Propose and Execute Runbooks and Rollbacks
Executes SSM Automation, Lambda runbooks, deployment rollbacks
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from agent_framework import BaseAgent, AgentType, AgentPriority, agent_registry
import boto3


@agent_registry.register
class RemediationAgent(BaseAgent):
    """
    Remediation agent for proposing and executing recovery actions
    
    Responsibilities:
    - Generate recovery runbooks using Bedrock
    - Execute SSM Automation documents
    - Invoke Lambda runbooks
    - Trigger CodeDeploy/CodePipeline rollbacks
    - Execute Terraform-based recovery via CodeBuild
    """
    
    def __init__(self, correlation_id: str, config: Dict[str, Any] = None):
        super().__init__(correlation_id, config)
        self.ssm = boto3.client('ssm')
        self.codebuild = boto3.client('codebuild')
        self.codedeploy = boto3.client('codedeploy')
        self.lambda_client = boto3.client('lambda')
    
    @property
    def agent_type(self) -> AgentType:
        return AgentType.REMEDIATION
    
    @property
    def priority(self) -> AgentPriority:
        return AgentPriority.MEDIUM  # Remediation runs after telemetry
    
    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze and generate remediation plan
        
        Returns:
            {
                'runbook': {...},
                'estimated_duration': int,
                'risk_level': 'low|medium|high',
                'requires_approval': bool,
                'rollback_plan': {...}
            }
        """
        resource_type = context.get('resource_type', 'unknown')
        resource_id = context.get('resource_id', 'unknown')
        event_details = context.get('event_details', {})
        
        # Get triage results if available
        triage_results = context.get('previous_agent_results', {}).get('triage', {})
        classification = triage_results.get('analysis', {}).get('classification', 'MEDIUM')
        
        # Get telemetry results if available
        telemetry_results = context.get('previous_agent_results', {}).get('telemetry', {})
        
        self.log("INFO", f"Generating remediation plan for {resource_type}/{resource_id}")
        
        # Generate runbook using Bedrock
        runbook = self._generate_runbook(
            resource_type,
            resource_id,
            event_details,
            classification,
            telemetry_results
        )
        
        # Assess risk level
        risk_level = self._assess_risk_level(runbook, resource_type, classification)
        
        # Determine if approval is required
        requires_approval = risk_level in ['high', 'medium'] or classification == 'CRITICAL'
        
        # Generate rollback plan
        rollback_plan = self._generate_rollback_plan(runbook, resource_type)
        
        return {
            'runbook': runbook,
            'estimated_duration': runbook.get('estimated_duration_seconds', 300),
            'risk_level': risk_level,
            'requires_approval': requires_approval,
            'rollback_plan': rollback_plan,
            'auto_executable': not requires_approval
        }
    
    def execute(self, context: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute remediation actions
        
        Actions:
        - Execute runbook steps (if approved or low-risk)
        - Store remediation results
        - Publish metrics
        """
        runbook = analysis['runbook']
        requires_approval = analysis['requires_approval']
        
        # Check if approval is required
        if requires_approval:
            # Store pending approval state
            self._store_pending_approval(self.correlation_id, analysis)
            
            return {
                'status': 'pending_approval',
                'message': 'Remediation requires human approval',
                'runbook': runbook,
                'approval_required': True
            }
        
        # Execute runbook
        execution_result = self._execute_runbook(runbook, context)
        
        # Store remediation results
        self._store_remediation_results(self.correlation_id, execution_result)
        
        # Publish metrics
        self._publish_remediation_metrics(execution_result)
        
        return execution_result
    
    def _generate_runbook(
        self,
        resource_type: str,
        resource_id: str,
        event_details: Dict,
        classification: str,
        telemetry_results: Dict
    ) -> Dict[str, Any]:
        """Generate remediation runbook using Bedrock"""
        
        event_name = event_details.get('eventName', 'Unknown')
        
        # Build context for Bedrock
        telemetry_summary = ""
        if telemetry_results:
            analysis = telemetry_results.get('analysis', {})
            anomalies = analysis.get('anomalies', [])
            if anomalies:
                telemetry_summary = f"\n\nDetected Anomalies:\n"
                for anomaly in anomalies[:3]:
                    telemetry_summary += f"- {anomaly.get('description', 'Unknown')}\n"
        
        prompt = f"""You are a DevOps AI Agent creating a remediation runbook for an AWS infrastructure incident.

INCIDENT DETAILS:
- Resource Type: {resource_type}
- Resource ID: {resource_id}
- Event: {event_name}
- Classification: {classification}
{telemetry_summary}

CREATE A STEP-BY-STEP REMEDIATION RUNBOOK:

1. IMMEDIATE ACTIONS (< 1 minute)
   - Quick stabilization steps

2. PRIMARY RECOVERY (1-5 minutes)
   - Main restoration steps

3. VERIFICATION STEPS
   - How to confirm recovery success

For each step, specify:
- step_number: Sequential number
- action_type: "terraform" | "ssm" | "lambda" | "manual"
- description: What this step does
- timeout_seconds: Maximum time allowed
- command: Actual command or automation document name
- success_criteria: How to verify success

RESPOND IN VALID JSON FORMAT:
{{
  "steps": [
    {{
      "step_number": 1,
      "action_type": "terraform",
      "description": "Restore infrastructure using Terraform",
      "timeout_seconds": 300,
      "command": "terraform apply -auto-approve",
      "success_criteria": "Resource exists and is healthy"
    }}
  ],
  "estimated_duration_seconds": 300,
  "prerequisites": ["AWS credentials", "Terraform state access"]
}}
"""
        
        try:
            response = self.invoke_bedrock(prompt, max_tokens=2048, temperature=0.2)
            
            # Parse JSON response
            if '```json' in response:
                response = response.split('```json')[1].split('```')[0].strip()
            elif '```' in response:
                response = response.split('```')[1].split('```')[0].strip()
            
            runbook = json.loads(response)
            return runbook
            
        except Exception as e:
            self.log("ERROR", f"Error generating runbook: {e}")
            
            # Fallback to simple runbook
            return {
                'steps': [
                    {
                        'step_number': 1,
                        'action_type': 'terraform',
                        'description': f'Restore {resource_type} using Terraform',
                        'timeout_seconds': 300,
                        'command': 'terraform apply -auto-approve',
                        'success_criteria': 'Resource restored'
                    }
                ],
                'estimated_duration_seconds': 300,
                'prerequisites': []
            }
    
    def _assess_risk_level(self, runbook: Dict, resource_type: str, classification: str) -> str:
        """Assess risk level of remediation"""
        
        # High risk if critical classification
        if classification == 'CRITICAL':
            return 'high'
        
        # Check runbook steps
        steps = runbook.get('steps', [])
        
        # High risk if many steps or long duration
        if len(steps) > 5 or runbook.get('estimated_duration_seconds', 0) > 600:
            return 'high'
        
        # Medium risk for production resources
        critical_resources = ['rds', 'dynamodb', 'ec2']
        if resource_type in critical_resources:
            return 'medium'
        
        # Low risk for simple, fast operations
        return 'low'
    
    def _generate_rollback_plan(self, runbook: Dict, resource_type: str) -> Dict[str, Any]:
        """Generate rollback plan in case remediation fails"""
        return {
            'description': 'Rollback to previous state if remediation fails',
            'steps': [
                'Take snapshot of current state',
                'Alert on-call engineer',
                'Revert to last known good configuration'
            ],
            'automated': False
        }
    
    def _execute_runbook(self, runbook: Dict, context: Dict) -> Dict[str, Any]:
        """Execute the runbook steps"""
        
        resource_type = context.get('resource_type', 'unknown')
        steps = runbook.get('steps', [])
        
        execution_results = []
        overall_success = True
        
        for step in steps:
            step_num = step.get('step_number', 0)
            action_type = step.get('action_type', 'manual')
            
            self.log("INFO", f"Executing step {step_num}: {step.get('description', '')}")
            
            try:
                if action_type == 'terraform':
                    result = self._execute_terraform(step, resource_type)
                elif action_type == 'ssm':
                    result = self._execute_ssm(step)
                elif action_type == 'lambda':
                    result = self._execute_lambda(step)
                else:
                    result = {
                        'status': 'skipped',
                        'message': 'Manual step requires human intervention'
                    }
                
                execution_results.append({
                    'step_number': step_num,
                    'status': result.get('status', 'unknown'),
                    'result': result
                })
                
                if result.get('status') != 'success':
                    overall_success = False
                    
            except Exception as e:
                self.log("ERROR", f"Error executing step {step_num}: {e}")
                execution_results.append({
                    'step_number': step_num,
                    'status': 'failed',
                    'error': str(e)
                })
                overall_success = False
                break  # Stop on first failure
        
        return {
            'status': 'success' if overall_success else 'failed',
            'steps_executed': len(execution_results),
            'execution_results': execution_results,
            'overall_success': overall_success
        }
    
    def _execute_terraform(self, step: Dict, resource_type: str) -> Dict[str, Any]:
        """Execute Terraform via CodeBuild"""
        try:
            codebuild_project = self.config.get('codebuild_project', 'aiops-devops-agent-apply')
            
            response = self.codebuild.start_build(
                projectName=codebuild_project,
                environmentVariablesOverride=[
                    {
                        'name': 'CORRELATION_ID',
                        'value': self.correlation_id,
                        'type': 'PLAINTEXT'
                    },
                    {
                        'name': 'RESOURCE_TYPE',
                        'value': resource_type,
                        'type': 'PLAINTEXT'
                    }
                ]
            )
            
            build_id = response['build']['id']
            
            return {
                'status': 'success',
                'build_id': build_id,
                'message': f'CodeBuild started: {build_id}'
            }
            
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _execute_ssm(self, step: Dict) -> Dict[str, Any]:
        """Execute SSM Automation document"""
        try:
            document_name = step.get('command', '')
            
            if not document_name:
                return {'status': 'failed', 'error': 'No SSM document specified'}
            
            response = self.ssm.start_automation_execution(
                DocumentName=document_name,
                Parameters={}
            )
            
            execution_id = response['AutomationExecutionId']
            
            return {
                'status': 'success',
                'execution_id': execution_id,
                'message': f'SSM automation started: {execution_id}'
            }
            
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _execute_lambda(self, step: Dict) -> Dict[str, Any]:
        """Execute Lambda runbook"""
        try:
            function_name = step.get('command', '')
            
            if not function_name:
                return {'status': 'failed', 'error': 'No Lambda function specified'}
            
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'correlation_id': self.correlation_id,
                    'step': step
                })
            )
            
            return {
                'status': 'success',
                'response': json.loads(response['Payload'].read()),
                'message': f'Lambda executed: {function_name}'
            }
            
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _store_pending_approval(self, incident_id: str, analysis: Dict[str, Any]):
        """Store pending approval state"""
        try:
            self.dynamodb.update_item(
                TableName=self.config.get('incident_table', 'aiops-incidents'),
                Key={'incident_id': {'S': incident_id}},
                UpdateExpression='SET remediation_status = :status, remediation_plan = :plan, updated_at = :updated',
                ExpressionAttributeValues={
                    ':status': {'S': 'pending_approval'},
                    ':plan': {'S': json.dumps(analysis)},
                    ':updated': {'S': datetime.utcnow().isoformat()}
                }
            )
        except Exception as e:
            self.log("ERROR", f"Error storing pending approval: {e}")
    
    def _store_remediation_results(self, incident_id: str, result: Dict[str, Any]):
        """Store remediation results"""
        try:
            self.dynamodb.update_item(
                TableName=self.config.get('incident_table', 'aiops-incidents'),
                Key={'incident_id': {'S': incident_id}},
                UpdateExpression='SET remediation_results = :results, updated_at = :updated',
                ExpressionAttributeValues={
                    ':results': {'S': json.dumps(result)},
                    ':updated': {'S': datetime.utcnow().isoformat()}
                }
            )
        except Exception as e:
            self.log("ERROR", f"Error storing remediation results: {e}")
    
    def _publish_remediation_metrics(self, result: Dict[str, Any]):
        """Publish remediation metrics"""
        try:
            self.cloudwatch.put_metric_data(
                Namespace='AIOps/Remediation',
                MetricData=[
                    {
                        'MetricName': 'RemediationAttempts',
                        'Value': 1,
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'Status', 'Value': result.get('status', 'unknown')}
                        ]
                    },
                    {
                        'MetricName': 'StepsExecuted',
                        'Value': result.get('steps_executed', 0),
                        'Unit': 'Count'
                    }
                ]
            )
        except Exception as e:
            self.log("ERROR", f"Error publishing metrics: {e}")
