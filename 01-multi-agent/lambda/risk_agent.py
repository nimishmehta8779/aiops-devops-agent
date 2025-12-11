"""
Risk/Guardrail Agent - Validate Change Safety and Compliance
Checks change calendars, policy engines, SLO/error budgets
"""

import json
from typing import Dict, List, Any
from datetime import datetime, time
from agent_framework import BaseAgent, AgentType, AgentPriority, agent_registry
import boto3


@agent_registry.register
class RiskAgent(BaseAgent):
    """
    Risk/Guardrail agent for validating change safety
    
    Responsibilities:
    - Check change calendar (maintenance windows)
    - Validate policy compliance (AWS Config, OPA)
    - Check SLO/error budget state
    - Assess blast radius
    - Validate compliance requirements
    """
    
    def __init__(self, correlation_id: str, config: Dict[str, Any] = None):
        super().__init__(correlation_id, config)
        self.config_service = boto3.client('config')
    
    @property
    def agent_type(self) -> AgentType:
        return AgentType.RISK
    
    @property
    def priority(self) -> AgentPriority:
        return AgentPriority.HIGH  # Risk validation before remediation
    
    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze risk and compliance
        
        Returns:
            {
                'risk_score': 0.0-1.0,
                'change_window_ok': bool,
                'policy_compliant': bool,
                'slo_budget_ok': bool,
                'blast_radius': 'localized|regional|global',
                'approval_required': bool,
                'risk_factors': [...]
            }
        """
        resource_type = context.get('resource_type', 'unknown')
        resource_id = context.get('resource_id', 'unknown')
        
        # Get remediation plan if available
        remediation_results = context.get('previous_agent_results', {}).get('remediation', {})
        remediation_plan = remediation_results.get('analysis', {})
        
        self.log("INFO", f"Assessing risk for {resource_type}/{resource_id}")
        
        # Check change window
        change_window_ok = self._check_change_window()
        
        # Validate policy compliance
        policy_compliant = self._check_policy_compliance(resource_type, resource_id)
        
        # Check SLO/error budget
        slo_budget_ok = self._check_slo_budget()
        
        # Assess blast radius
        blast_radius = self._assess_blast_radius(resource_type, remediation_plan)
        
        # Calculate overall risk score
        risk_score = self._calculate_risk_score(
            change_window_ok,
            policy_compliant,
            slo_budget_ok,
            blast_radius
        )
        
        # Identify risk factors
        risk_factors = self._identify_risk_factors(
            change_window_ok,
            policy_compliant,
            slo_budget_ok,
            blast_radius,
            remediation_plan
        )
        
        # Determine if approval is required
        approval_required = risk_score > 0.5 or not change_window_ok or not policy_compliant
        
        # Auto-approve for test resources (EC2/RDS/EKS/Lambda) for Demo
        if resource_type in ['ec2', 'rds', 'kubernetes', 'eks', 'lambda']:
            self.log("INFO", f"Auto-approving change for resource: {resource_id}")
            approval_required = False
            risk_score = 0.1 
        
        return {
            'risk_score': risk_score,
            'change_window_ok': change_window_ok,
            'policy_compliant': policy_compliant,
            'slo_budget_ok': slo_budget_ok,
            'blast_radius': blast_radius,
            'approval_required': approval_required,
            'risk_factors': risk_factors,
            'safe_to_proceed': risk_score < 0.5 and change_window_ok and policy_compliant
        }
    
    def execute(self, context: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute risk validation actions
        
        Actions:
        - Store risk assessment
        - Publish risk metrics
        - Create approval request if needed
        """
        # Store risk assessment
        self._store_risk_assessment(self.correlation_id, analysis)
        
        # Publish metrics
        self._publish_risk_metrics(analysis)
        
        # If high risk, create approval request
        if analysis['approval_required']:
            self._create_approval_request(self.correlation_id, analysis)
        
        return {
            'risk_validated': True,
            'safe_to_proceed': analysis['safe_to_proceed'],
            'approval_required': analysis['approval_required'],
            'risk_score': analysis['risk_score']
        }
    
    def _check_change_window(self) -> bool:
        """
        Check if current time is within allowed change window
        
        Default: Allow changes 24/7 except Fridays 4pm-midnight
        """
        now = datetime.utcnow()
        
        # Get change window config
        blocked_windows = self.config.get('blocked_windows', [
            {
                'day': 4,  # Friday (0=Monday, 4=Friday)
                'start_hour': 16,  # 4 PM
                'end_hour': 23  # 11 PM
            }
        ])
        
        for window in blocked_windows:
            if now.weekday() == window['day']:
                current_hour = now.hour
                if window['start_hour'] <= current_hour <= window['end_hour']:
                    self.log("WARN", f"Current time is in blocked change window")
                    return False
        
        return True
    
    def _check_policy_compliance(self, resource_type: str, resource_id: str) -> bool:
        """
        Check AWS Config compliance for the resource
        """
        try:
            # Query AWS Config for compliance status
            response = self.config_service.describe_compliance_by_resource(
                ResourceType=self._map_resource_type_to_config(resource_type),
                ResourceId=resource_id,
                ComplianceTypes=['COMPLIANT', 'NON_COMPLIANT']
            )
            
            compliance_results = response.get('ComplianceByResources', [])
            
            if not compliance_results:
                # No compliance data, assume compliant
                return True
            
            # Check if any rules are non-compliant
            for result in compliance_results:
                compliance = result.get('Compliance', {})
                if compliance.get('ComplianceType') == 'NON_COMPLIANT':
                    self.log("WARN", f"Resource {resource_id} is non-compliant")
                    return False
            
            return True
            
        except Exception as e:
            self.log("ERROR", f"Error checking policy compliance: {e}")
            # On error, assume compliant (fail open for availability)
            return True
    
    def _map_resource_type_to_config(self, resource_type: str) -> str:
        """Map our resource type to AWS Config resource type"""
        mapping = {
            'ec2': 'AWS::EC2::Instance',
            'lambda': 'AWS::Lambda::Function',
            'dynamodb': 'AWS::DynamoDB::Table',
            's3': 'AWS::S3::Bucket',
            'rds': 'AWS::RDS::DBInstance'
        }
        return mapping.get(resource_type, 'AWS::EC2::Instance')
    
    def _check_slo_budget(self) -> bool:
        """
        Check if we have remaining error budget for changes
        
        Simple implementation: check error rate in last hour
        """
        try:
            # Query CloudWatch for error rate
            end_time = datetime.utcnow()
            start_time = end_time.replace(minute=0, second=0, microsecond=0)
            
            response = self.cloudwatch.get_metric_statistics(
                Namespace='AIOps/DevOpsAgent',
                MetricName='IncidentCount',
                Dimensions=[
                    {'Name': 'Classification', 'Value': 'CRITICAL'}
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour
                Statistics=['Sum']
            )
            
            datapoints = response.get('Datapoints', [])
            
            if datapoints:
                critical_incidents = datapoints[0].get('Sum', 0)
                
                # If more than 5 critical incidents in last hour, budget exhausted
                if critical_incidents > 5:
                    self.log("WARN", f"Error budget exhausted: {critical_incidents} critical incidents in last hour")
                    return False
            
            return True
            
        except Exception as e:
            self.log("ERROR", f"Error checking SLO budget: {e}")
            return True  # Fail open
    
    def _assess_blast_radius(self, resource_type: str, remediation_plan: Dict) -> str:
        """
        Assess blast radius of the remediation
        
        Returns: localized|regional|global
        """
        # Check if remediation affects multiple resources
        steps = remediation_plan.get('runbook', {}).get('steps', [])
        
        if len(steps) > 5:
            return 'regional'
        
        # Critical resources have wider blast radius
        critical_resources = ['rds', 'dynamodb']
        if resource_type in critical_resources:
            return 'regional'
        
        return 'localized'
    
    def _calculate_risk_score(
        self,
        change_window_ok: bool,
        policy_compliant: bool,
        slo_budget_ok: bool,
        blast_radius: str
    ) -> float:
        """
        Calculate overall risk score (0.0-1.0)
        
        Lower is safer
        """
        risk = 0.0
        
        if not change_window_ok:
            risk += 0.3
        
        if not policy_compliant:
            risk += 0.4
        
        if not slo_budget_ok:
            risk += 0.2
        
        if blast_radius == 'global':
            risk += 0.3
        elif blast_radius == 'regional':
            risk += 0.2
        elif blast_radius == 'localized':
            risk += 0.1
        
        return min(1.0, risk)
    
    def _identify_risk_factors(
        self,
        change_window_ok: bool,
        policy_compliant: bool,
        slo_budget_ok: bool,
        blast_radius: str,
        remediation_plan: Dict
    ) -> List[str]:
        """Identify specific risk factors"""
        factors = []
        
        if not change_window_ok:
            factors.append("Outside approved change window")
        
        if not policy_compliant:
            factors.append("Resource has compliance violations")
        
        if not slo_budget_ok:
            factors.append("Error budget exhausted")
        
        if blast_radius in ['regional', 'global']:
            factors.append(f"Wide blast radius: {blast_radius}")
        
        # Check remediation complexity
        steps = remediation_plan.get('runbook', {}).get('steps', [])
        if len(steps) > 5:
            factors.append(f"Complex remediation: {len(steps)} steps")
        
        estimated_duration = remediation_plan.get('estimated_duration', 0)
        if estimated_duration > 600:
            factors.append(f"Long remediation: {estimated_duration}s estimated")
        
        return factors
    
    def _store_risk_assessment(self, incident_id: str, analysis: Dict[str, Any]):
        """Store risk assessment in DynamoDB"""
        try:
            self.dynamodb.update_item(
                TableName=self.config.get('incident_table', 'aiops-incidents'),
                Key={'incident_id': {'S': incident_id}},
                UpdateExpression='SET risk_assessment = :assessment, updated_at = :updated',
                ExpressionAttributeValues={
                    ':assessment': {'S': json.dumps(analysis)},
                    ':updated': {'S': datetime.utcnow().isoformat()}
                }
            )
        except Exception as e:
            self.log("ERROR", f"Error storing risk assessment: {e}")
    
    def _create_approval_request(self, incident_id: str, analysis: Dict[str, Any]):
        """Create approval request for high-risk changes"""
        try:
            self.dynamodb.update_item(
                TableName=self.config.get('incident_table', 'aiops-incidents'),
                Key={'incident_id': {'S': incident_id}},
                UpdateExpression='SET approval_status = :status, approval_request = :request',
                ExpressionAttributeValues={
                    ':status': {'S': 'pending'},
                    ':request': {'S': json.dumps({
                        'requested_at': datetime.utcnow().isoformat(),
                        'risk_score': analysis['risk_score'],
                        'risk_factors': analysis['risk_factors']
                    })}
                }
            )
        except Exception as e:
            self.log("ERROR", f"Error creating approval request: {e}")
    
    def _publish_risk_metrics(self, analysis: Dict[str, Any]):
        """Publish risk metrics to CloudWatch"""
        try:
            self.cloudwatch.put_metric_data(
                Namespace='AIOps/Risk',
                MetricData=[
                    {
                        'MetricName': 'RiskScore',
                        'Value': analysis['risk_score'],
                        'Unit': 'None'
                    },
                    {
                        'MetricName': 'ApprovalRequired',
                        'Value': 1 if analysis['approval_required'] else 0,
                        'Unit': 'Count'
                    },
                    {
                        'MetricName': 'PolicyCompliance',
                        'Value': 1 if analysis['policy_compliant'] else 0,
                        'Unit': 'Count'
                    }
                ]
            )
        except Exception as e:
            self.log("ERROR", f"Error publishing metrics: {e}")
