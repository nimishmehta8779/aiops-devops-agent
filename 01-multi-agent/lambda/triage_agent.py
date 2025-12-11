"""
Triage Agent - Alert Classification, Deduplication, and Prioritization
Analyzes CloudWatch alarms, DevOps Guru events, and historical patterns
"""

import json
import hashlib
from typing import Dict, List, Any
from datetime import datetime, timedelta
from agent_framework import BaseAgent, AgentType, AgentPriority, agent_registry


@agent_registry.register
class TriageAgent(BaseAgent):
    """
    Triage agent for incident classification and prioritization
    
    Responsibilities:
    - Classify alerts (CRITICAL, HIGH, MEDIUM, LOW, INFO)
    - Deduplicate similar incidents
    - Prioritize based on severity, blast radius, business impact
    - Noise reduction using ML-based filtering
    """
    
    @property
    def agent_type(self) -> AgentType:
        return AgentType.TRIAGE
    
    @property
    def priority(self) -> AgentPriority:
        return AgentPriority.CRITICAL  # Triage runs first
    
    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze and classify the incident
        
        Returns:
            {
                'classification': 'CRITICAL|HIGH|MEDIUM|LOW|INFO',
                'severity_score': 1-10,
                'is_duplicate': bool,
                'similar_incidents': [...],
                'noise_score': 0.0-1.0,
                'business_impact': {...}
            }
        """
        event_details = context.get('event_details', {})
        resource_type = context.get('resource_type', 'unknown')
        resource_id = context.get('resource_id', 'unknown')
        region = context.get('region', 'unknown')
        event_name = context.get('event_name', 'unknown')
        
        self.log("INFO", f"Analyzing incident for {resource_type}/{resource_id}")
        
        # Calculate fingerprint (including region)
        fingerprint = self._calculate_fingerprint(event_name, resource_type, resource_id, region)
        
        # Check for duplicates
        is_duplicate, similar_incidents = self._check_duplicates(fingerprint, resource_type)
        
        # Calculate severity score
        severity_score = self._calculate_severity(event_details, resource_type, similar_incidents)
        
        # Classify incident
        classification = self._classify_incident(severity_score, event_details)
        
        # Calculate noise score (likelihood this is a false positive)
        noise_score = self._calculate_noise_score(event_details, similar_incidents)
        
        # Assess business impact
        business_impact = self._assess_business_impact(
            resource_type,
            resource_id,
            severity_score,
            event_details
        )
        
        return {
            'fingerprint': fingerprint,
            'classification': classification,
            'severity_score': severity_score,
            'is_duplicate': is_duplicate,
            'similar_incidents': similar_incidents,
            'noise_score': noise_score,
            'business_impact': business_impact,
            'should_suppress': noise_score > 0.7,  # Suppress if likely noise
            'requires_immediate_action': classification in ['CRITICAL', 'HIGH'] and not is_duplicate
        }
    
    def execute(self, context: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute triage actions
        
        Actions:
        - Store incident classification in DynamoDB
        - Update incident priority
        - Create correlation with similar incidents
        """
        correlation_id = self.correlation_id
        
        # Store triage results
        self._store_triage_results(correlation_id, analysis)
        
        # If duplicate, link to original incident
        if analysis['is_duplicate'] and analysis['similar_incidents']:
            original_incident = analysis['similar_incidents'][0]
            self._link_duplicate_incident(correlation_id, original_incident['incident_id'])
        
        # Publish metrics
        self._publish_triage_metrics(analysis)
        
        return {
            'triage_complete': True,
            'classification': analysis['classification'],
            'action_required': analysis['requires_immediate_action'],
            'suppressed': analysis['should_suppress']
        }
    
    def _calculate_fingerprint(
        self,
        event_name: str,
        resource_type: str,
        resource_id: str,
        region: str = 'unknown'
    ) -> str:
        """Calculate SHA256 fingerprint for deduplication"""
        # Include region in fingerprint to distinguish same resource ID in different regions (unlikely but possible)
        raw_string = f"{event_name}:{resource_type}:{resource_id}:{region}"
        return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()
    
    def _check_duplicates(self, fingerprint: str, resource_type: str) -> tuple[bool, List[Dict]]:
        """
        Check for duplicate incidents in the last 24 hours
        
        Returns:
            (is_duplicate, similar_incidents)
        """
        try:
            cutoff_time = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            
            # Query DynamoDB for similar incidents
            response = self.dynamodb.scan(
                TableName=self.config.get('incident_table', 'aiops-incidents'),
                FilterExpression='fingerprint = :fp AND incident_timestamp > :cutoff',
                ExpressionAttributeValues={
                    ':fp': {'S': fingerprint},
                    ':cutoff': {'S': cutoff_time}
                },
                Limit=10
            )
            
            items = response.get('Items', [])
            
            similar_incidents = []
            for item in items:
                similar_incidents.append({
                    'incident_id': item.get('incident_id', {}).get('S', ''),
                    'timestamp': item.get('incident_timestamp', {}).get('S', ''),
                    'classification': item.get('event_classification', {}).get('S', ''),
                    'resolved': item.get('workflow_state', {}).get('S', '') == 'COMPLETED'
                })
            
            is_duplicate = len(similar_incidents) > 0
            
            return is_duplicate, similar_incidents
            
        except Exception as e:
            self.log("ERROR", f"Error checking duplicates: {e}")
            return False, []
    
    def _calculate_severity(
        self,
        event_details: Dict,
        resource_type: str,
        similar_incidents: List[Dict]
    ) -> int:
        """
        Calculate severity score (1-10)
        
        Factors:
        - Event type (delete = 10, modify = 5, read = 1)
        - Resource type criticality
        - Historical incident severity
        """
        event_name = event_details.get('eventName', '').lower()
        
        # Base severity from event type
        severity = 5  # Default medium
        
        if any(word in event_name for word in ['delete', 'terminate', 'destroy']):
            severity = 10
        elif any(word in event_name for word in ['stop', 'disable', 'detach']):
            severity = 8
        elif any(word in event_name for word in ['modify', 'update', 'change']):
            severity = 6
        elif any(word in event_name for word in ['create', 'start', 'enable']):
            severity = 3
        
        # Adjust based on resource type
        critical_resources = ['ec2', 'rds', 'dynamodb', 'lambda']
        if resource_type in critical_resources:
            severity = min(10, severity + 1)
        
        # Adjust based on historical incidents
        if similar_incidents:
            avg_historical_severity = sum(
                self._severity_from_classification(inc.get('classification', 'MEDIUM'))
                for inc in similar_incidents
            ) / len(similar_incidents)
            
            # Blend current and historical
            severity = int((severity + avg_historical_severity) / 2)
        
        return max(1, min(10, severity))
    
    def _severity_from_classification(self, classification: str) -> int:
        """Convert classification to severity score"""
        mapping = {
            'CRITICAL': 10,
            'HIGH': 8,
            'MEDIUM': 5,
            'LOW': 3,
            'INFO': 1
        }
        return mapping.get(classification, 5)
    
    def _classify_incident(self, severity_score: int, event_details: Dict) -> str:
        """
        Classify incident based on severity score
        
        Returns: CRITICAL|HIGH|MEDIUM|LOW|INFO
        """
        if severity_score >= 9:
            return 'CRITICAL'
        elif severity_score >= 7:
            return 'HIGH'
        elif severity_score >= 5:
            return 'MEDIUM'
        elif severity_score >= 3:
            return 'LOW'
        else:
            return 'INFO'
    
    def _calculate_noise_score(
        self,
        event_details: Dict,
        similar_incidents: List[Dict]
    ) -> float:
        """
        Calculate likelihood this is noise/false positive (0.0-1.0)
        
        Factors:
        - Frequency of similar incidents
        - Resolution rate of similar incidents
        - Event source reliability
        """
        noise_score = 0.0
        
        # High frequency of similar incidents suggests noise
        if len(similar_incidents) > 5:
            noise_score += 0.3
        
        # If most similar incidents were resolved quickly, might be noise
        if similar_incidents:
            resolved_count = sum(1 for inc in similar_incidents if inc.get('resolved'))
            resolution_rate = resolved_count / len(similar_incidents)
            
            if resolution_rate > 0.8:
                noise_score += 0.2
        
        # Certain event sources are noisier
        event_source = event_details.get('eventSource', '')
        noisy_sources = ['cloudtrail.amazonaws.com', 'config.amazonaws.com']
        if event_source in noisy_sources:
            noise_score += 0.1
        
        return min(1.0, noise_score)
    
    def _assess_business_impact(
        self,
        resource_type: str,
        resource_id: str,
        severity_score: int,
        event_details: Dict
    ) -> Dict[str, Any]:
        """
        Assess business impact of the incident
        
        Returns:
            {
                'affected_services': [...],
                'estimated_downtime_minutes': int,
                'blast_radius': 'localized|regional|global',
                'customer_impact': 'none|low|medium|high|critical'
            }
        """
        # Use Bedrock to assess business impact
        prompt = f"""Assess the business impact of this AWS infrastructure incident:

Resource Type: {resource_type}
Resource ID: {resource_id}
Severity Score: {severity_score}/10
Event: {event_details.get('eventName', 'Unknown')}

Provide a brief assessment of:
1. Which services might be affected
2. Estimated downtime in minutes
3. Blast radius (localized/regional/global)
4. Customer impact level (none/low/medium/high/critical)

Respond in JSON format:
{{
  "affected_services": ["service1", "service2"],
  "estimated_downtime_minutes": 5,
  "blast_radius": "localized",
  "customer_impact": "medium"
}}
"""
        
        try:
            response = self.invoke_bedrock(prompt, max_tokens=512)
            
            # Parse JSON response
            if '```json' in response:
                response = response.split('```json')[1].split('```')[0].strip()
            elif '```' in response:
                response = response.split('```')[1].split('```')[0].strip()
            
            impact = json.loads(response)
            return impact
            
        except Exception as e:
            self.log("ERROR", f"Error assessing business impact: {e}")
            
            # Fallback to simple heuristic
            return {
                'affected_services': [resource_type],
                'estimated_downtime_minutes': severity_score * 5,
                'blast_radius': 'localized' if severity_score < 7 else 'regional',
                'customer_impact': 'high' if severity_score >= 8 else 'medium'
            }
    
    def _store_triage_results(self, incident_id: str, analysis: Dict[str, Any]):
        """Store triage results in DynamoDB"""
        try:
            self.dynamodb.update_item(
                TableName=self.config.get('incident_table', 'aiops-incidents'),
                Key={'incident_id': {'S': incident_id}},
                UpdateExpression='SET triage_results = :results, fingerprint = :fp, updated_at = :updated',
                ExpressionAttributeValues={
                    ':results': {'S': json.dumps(analysis)},
                    ':fp': {'S': analysis['fingerprint']},
                    ':updated': {'S': datetime.utcnow().isoformat()}
                }
            )
        except Exception as e:
            self.log("ERROR", f"Error storing triage results: {e}")
    
    def _link_duplicate_incident(self, incident_id: str, original_incident_id: str):
        """Link duplicate incident to original"""
        try:
            self.dynamodb.update_item(
                TableName=self.config.get('incident_table', 'aiops-incidents'),
                Key={'incident_id': {'S': incident_id}},
                UpdateExpression='SET duplicate_of = :original',
                ExpressionAttributeValues={
                    ':original': {'S': original_incident_id}
                }
            )
        except Exception as e:
            self.log("ERROR", f"Error linking duplicate: {e}")
    
    def _publish_triage_metrics(self, analysis: Dict[str, Any]):
        """Publish triage metrics to CloudWatch"""
        try:
            self.cloudwatch.put_metric_data(
                Namespace='AIOps/Triage',
                MetricData=[
                    {
                        'MetricName': 'IncidentClassification',
                        'Value': 1,
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'Classification', 'Value': analysis['classification']}
                        ]
                    },
                    {
                        'MetricName': 'SeverityScore',
                        'Value': analysis['severity_score'],
                        'Unit': 'None'
                    },
                    {
                        'MetricName': 'NoiseScore',
                        'Value': analysis['noise_score'],
                        'Unit': 'None'
                    },
                    {
                        'MetricName': 'DuplicateIncidents',
                        'Value': 1 if analysis['is_duplicate'] else 0,
                        'Unit': 'Count'
                    }
                ]
            )
        except Exception as e:
            self.log("ERROR", f"Error publishing metrics: {e}")
