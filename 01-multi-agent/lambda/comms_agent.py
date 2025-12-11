"""
Communications Agent - Human-Readable Updates and Notifications
Sends emails, creates incident summaries, generates postmortems
"""

import json
from typing import Dict, List, Any
from datetime import datetime
from agent_framework import BaseAgent, AgentType, AgentPriority, agent_registry
import boto3


@agent_registry.register
class CommunicationsAgent(BaseAgent):
    """
    Communications agent for human-readable updates
    
    Responsibilities:
    - Send email notifications via SES
    - Generate incident summaries using Bedrock
    - Create postmortem reports
    - Format human-readable updates
    - Track notification preferences
    """
    
    def __init__(self, correlation_id: str, config: Dict[str, Any] = None):
        super().__init__(correlation_id, config)
        self.ses = boto3.client('ses')
        self.sns = boto3.client('sns')
    
    @property
    def agent_type(self) -> AgentType:
        return AgentType.COMMUNICATIONS
    
    @property
    def priority(self) -> AgentPriority:
        return AgentPriority.LOW  # Communications runs last
    
    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze and prepare communications
        
        Returns:
            {
                'incident_summary': str,
                'postmortem': str,
                'notification_type': 'email|sns|both',
                'recipients': [...],
                'severity': 'critical|high|medium|low'
            }
        """
        resource_type = context.get('resource_type', 'unknown')
        resource_id = context.get('resource_id', 'unknown')
        event_details = context.get('event_details', {})
        
        # Get all previous agent results
        previous_results = context.get('previous_agent_results', {})
        
        self.log("INFO", f"Preparing communications for {resource_type}/{resource_id}")
        
        # Generate incident summary
        incident_summary = self._generate_incident_summary(
            resource_type,
            resource_id,
            event_details,
            previous_results
        )
        
        # Determine severity for notification
        triage_results = previous_results.get('triage', {})
        classification = triage_results.get('analysis', {}).get('classification', 'MEDIUM')
        
        # Get recipients based on severity
        recipients = self._get_recipients(classification)
        
        # Determine notification type
        notification_type = 'both' if classification in ['CRITICAL', 'HIGH'] else 'email'
        
        return {
            'incident_summary': incident_summary,
            'notification_type': notification_type,
            'recipients': recipients,
            'severity': classification.lower(),
            'should_notify': True
        }
    
    def execute(self, context: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute communications actions
        
        Actions:
        - Send email notifications
        - Send SNS notifications
        - Store communication log
        """
        if not analysis['should_notify']:
            return {'status': 'skipped', 'reason': 'No notification required'}
        
        notification_results = []
        
        # Send email notifications
        if analysis['notification_type'] in ['email', 'both']:
            email_result = self._send_email_notification(
                analysis['recipients'],
                analysis['incident_summary'],
                analysis['severity']
            )
            notification_results.append(email_result)
        
        # Send SNS notifications
        if analysis['notification_type'] in ['sns', 'both']:
            sns_result = self._send_sns_notification(
                analysis['incident_summary'],
                analysis['severity']
            )
            notification_results.append(sns_result)
        
        # Store communication log
        self._store_communication_log(self.correlation_id, notification_results)
        
        # Publish metrics
        self._publish_communication_metrics(notification_results)
        
        return {
            'notifications_sent': len(notification_results),
            'notification_results': notification_results,
            'recipients': analysis['recipients']
        }
    
    def _generate_incident_summary(
        self,
        resource_type: str,
        resource_id: str,
        event_details: Dict,
        previous_results: Dict
    ) -> str:
        """Generate human-readable incident summary using Bedrock"""
        
        # Extract key information from previous agents
        triage = previous_results.get('triage', {}).get('analysis', {})
        telemetry = previous_results.get('telemetry', {}).get('analysis', {})
        remediation = previous_results.get('remediation', {}).get('analysis', {})
        risk = previous_results.get('risk', {}).get('analysis', {})
        
        prompt = f"""Generate a concise, human-readable incident summary for a DevOps team.

INCIDENT DETAILS:
- Resource: {resource_type} / {resource_id}
- Event: {event_details.get('eventName', 'Unknown')}
- Time: {event_details.get('eventTime', 'Unknown')}

TRIAGE ANALYSIS:
- Classification: {triage.get('classification', 'Unknown')}
- Severity: {triage.get('severity_score', 0)}/10
- Business Impact: {json.dumps(triage.get('business_impact', {}))}

TELEMETRY:
- Anomalies Detected: {len(telemetry.get('anomalies', []))}
- Health Score: {telemetry.get('telemetry_health_score', 0.5)}

REMEDIATION:
- Status: {remediation.get('auto_executable', False) and 'Automated' or 'Requires Approval'}
- Estimated Duration: {remediation.get('estimated_duration', 0)}s

RISK ASSESSMENT:
- Risk Score: {risk.get('risk_score', 0.5)}
- Safe to Proceed: {risk.get('safe_to_proceed', False)}

Generate a summary in this format:

**INCIDENT SUMMARY**

[Brief 2-3 sentence description of what happened]

**IMPACT**
- Affected Services: [list]
- Severity: [level]
- Estimated Downtime: [time]

**CURRENT STATUS**
[What's happening now - automated recovery, pending approval, etc.]

**NEXT STEPS**
[What will happen next or what action is required]

Keep it concise and actionable. Use bullet points.
"""
        
        try:
            response = self.invoke_bedrock(prompt, max_tokens=1024, temperature=0.3)
            return response
            
        except Exception as e:
            self.log("ERROR", f"Error generating summary: {e}")
            
            # Fallback to simple summary
            return f"""**INCIDENT SUMMARY**

{resource_type.upper()} resource {resource_id} experienced a {event_details.get('eventName', 'failure')} event.

**IMPACT**
- Classification: {triage.get('classification', 'UNKNOWN')}
- Severity: {triage.get('severity_score', 0)}/10

**CURRENT STATUS**
Incident detected and being processed by AIOps system.

**NEXT STEPS**
Automated remediation in progress.
"""
    
    def _get_recipients(self, classification: str) -> List[str]:
        """Get email recipients based on severity"""
        
        # Default recipient from config
        default_email = self.config.get('default_email', 'nimish.mehta@gmail.com')
        
        recipients = [default_email]
        
        # Add escalation recipients for critical incidents
        if classification == 'CRITICAL':
            escalation_emails = self.config.get('escalation_emails', [])
            recipients.extend(escalation_emails)
        
        return list(set(recipients))  # Remove duplicates
    
    def _send_email_notification(
        self,
        recipients: List[str],
        summary: str,
        severity: str
    ) -> Dict[str, Any]:
        """Send email notification via SES"""
        
        try:
            # Format email subject
            subject = f"🚨 AIOps Alert [{severity.upper()}] - Incident {self.correlation_id[:8]}"
            
            # Format email body
            body = f"""
{summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**INCIDENT ID:** {self.correlation_id}

**TIMESTAMP:** {datetime.utcnow().isoformat()}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is an automated notification from the AIOps DevOps Agent.
Full incident details are stored in DynamoDB.

To approve pending remediation actions, reply to this email with "APPROVE {self.correlation_id[:8]}"
"""
            
            # Send via SES
            response = self.ses.send_email(
                Source=self.config.get('sender_email', 'noreply@aiops.example.com'),
                Destination={'ToAddresses': recipients},
                Message={
                    'Subject': {'Data': subject},
                    'Body': {'Text': {'Data': body}}
                }
            )
            
            message_id = response['MessageId']
            
            self.log("INFO", f"Email sent: {message_id}")
            
            return {
                'type': 'email',
                'status': 'success',
                'message_id': message_id,
                'recipients': recipients
            }
            
        except Exception as e:
            self.log("ERROR", f"Error sending email: {e}")
            
            # Fallback to SNS if SES fails
            try:
                return self._send_sns_notification(summary, severity)
            except:
                return {
                    'type': 'email',
                    'status': 'failed',
                    'error': str(e)
                }
    
    def _send_sns_notification(self, summary: str, severity: str) -> Dict[str, Any]:
        """Send SNS notification"""
        
        try:
            sns_topic = self.config.get('sns_topic_arn')
            
            if not sns_topic:
                return {
                    'type': 'sns',
                    'status': 'skipped',
                    'reason': 'No SNS topic configured'
                }
            
            response = self.sns.publish(
                TopicArn=sns_topic,
                Subject=f"AIOps Alert [{severity.upper()}]",
                Message=summary
            )
            
            message_id = response['MessageId']
            
            self.log("INFO", f"SNS notification sent: {message_id}")
            
            return {
                'type': 'sns',
                'status': 'success',
                'message_id': message_id
            }
            
        except Exception as e:
            self.log("ERROR", f"Error sending SNS: {e}")
            return {
                'type': 'sns',
                'status': 'failed',
                'error': str(e)
            }
    
    def generate_postmortem(
        self,
        incident_id: str,
        context: Dict,
        previous_results: Dict
    ) -> str:
        """Generate postmortem report using Bedrock"""
        
        prompt = f"""Generate a detailed postmortem report for this incident.

INCIDENT ID: {incident_id}

CONTEXT:
{json.dumps(context, indent=2, default=str)}

AGENT RESULTS:
{json.dumps(previous_results, indent=2, default=str)}

Generate a postmortem in this format:

# Incident Postmortem

## Summary
[Brief overview]

## Timeline
[Chronological sequence of events]

## Root Cause
[What caused the incident]

## Impact
[What was affected and how]

## Resolution
[How it was resolved]

## Lessons Learned
[What we learned]

## Action Items
[Preventive measures for the future]

Be specific and actionable.
"""
        
        try:
            response = self.invoke_bedrock(prompt, max_tokens=2048, temperature=0.2)
            return response
            
        except Exception as e:
            self.log("ERROR", f"Error generating postmortem: {e}")
            return f"# Incident Postmortem\n\nIncident ID: {incident_id}\n\nPostmortem generation failed: {e}"
    
    def _store_communication_log(self, incident_id: str, results: List[Dict]):
        """Store communication log in DynamoDB"""
        try:
            self.dynamodb.update_item(
                TableName=self.config.get('incident_table', 'aiops-incidents'),
                Key={'incident_id': {'S': incident_id}},
                UpdateExpression='SET communication_log = :log, updated_at = :updated',
                ExpressionAttributeValues={
                    ':log': {'S': json.dumps(results)},
                    ':updated': {'S': datetime.utcnow().isoformat()}
                }
            )
        except Exception as e:
            self.log("ERROR", f"Error storing communication log: {e}")
    
    def _publish_communication_metrics(self, results: List[Dict]):
        """Publish communication metrics"""
        try:
            successful = sum(1 for r in results if r.get('status') == 'success')
            failed = sum(1 for r in results if r.get('status') == 'failed')
            
            self.cloudwatch.put_metric_data(
                Namespace='AIOps/Communications',
                MetricData=[
                    {
                        'MetricName': 'NotificationsSent',
                        'Value': successful,
                        'Unit': 'Count'
                    },
                    {
                        'MetricName': 'NotificationsFailed',
                        'Value': failed,
                        'Unit': 'Count'
                    }
                ]
            )
        except Exception as e:
            self.log("ERROR", f"Error publishing metrics: {e}")
