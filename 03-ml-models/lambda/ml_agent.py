"""
ML Pattern Recognition Agent
Uses custom ML models for anomaly detection and pattern recognition
"""

import json
import os
import numpy as np
from typing import Dict, List, Any
from datetime import datetime, timedelta
import boto3

# AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb')
cloudwatch = boto3.client('cloudwatch')


class AnomalyDetector:
    """
    Simple anomaly detection using statistical methods
    Can be extended with SageMaker models
    """
    
    def __init__(self, sensitivity: float = 2.0):
        self.sensitivity = sensitivity  # Number of standard deviations
    
    def detect_anomalies(self, data: List[float]) -> List[Dict]:
        """
        Detect anomalies using Z-score method
        
        Returns list of anomaly indices and scores
        """
        if len(data) < 3:
            return []
        
        data_array = np.array(data)
        mean = np.mean(data_array)
        std = np.std(data_array)
        
        if std == 0:
            return []
        
        z_scores = np.abs((data_array - mean) / std)
        
        anomalies = []
        for i, z_score in enumerate(z_scores):
            if z_score > self.sensitivity:
                anomalies.append({
                    'index': i,
                    'value': float(data[i]),
                    'z_score': float(z_score),
                    'severity': 'high' if z_score > 3 else 'medium'
                })
        
        return anomalies


class PatternRecognizer:
    """
    Pattern recognition for incident patterns
    """
    
    def __init__(self, incident_table: str):
        self.incident_table = incident_table
    
    def find_patterns(self, lookback_hours: int = 24) -> Dict[str, Any]:
        """
        Find recurring patterns in incidents
        """
        cutoff_time = (datetime.utcnow() - timedelta(hours=lookback_hours)).isoformat()
        
        try:
            # Query recent incidents
            response = dynamodb.scan(
                TableName=self.incident_table,
                FilterExpression='incident_timestamp > :cutoff',
                ExpressionAttributeValues={
                    ':cutoff': {'S': cutoff_time}
                }
            )
            
            incidents = response.get('Items', [])
            
            # Analyze patterns
            patterns = {
                'resource_type_distribution': self._analyze_resource_types(incidents),
                'time_of_day_pattern': self._analyze_time_patterns(incidents),
                'severity_trend': self._analyze_severity_trend(incidents),
                'common_error_patterns': self._analyze_error_patterns(incidents)
            }
            
            return patterns
            
        except Exception as e:
            print(f"Error finding patterns: {e}")
            return {}
    
    def _analyze_resource_types(self, incidents: List[Dict]) -> Dict[str, int]:
        """Count incidents by resource type"""
        distribution = {}
        for incident in incidents:
            resource_type = incident.get('resource_type', {}).get('S', 'unknown')
            distribution[resource_type] = distribution.get(resource_type, 0) + 1
        return distribution
    
    def _analyze_time_patterns(self, incidents: List[Dict]) -> Dict[str, int]:
        """Analyze incidents by hour of day"""
        hourly_distribution = {str(h): 0 for h in range(24)}
        
        for incident in incidents:
            timestamp_str = incident.get('incident_timestamp', {}).get('S', '')
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    hour = str(timestamp.hour)
                    hourly_distribution[hour] += 1
                except:
                    pass
        
        return hourly_distribution
    
    def _analyze_severity_trend(self, incidents: List[Dict]) -> Dict[str, Any]:
        """Analyze severity trends over time"""
        severity_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'INFO': 0}
        
        for incident in incidents:
            triage_results = incident.get('triage_results', {}).get('S', '{}')
            try:
                triage = json.loads(triage_results)
                classification = triage.get('classification', 'MEDIUM')
                severity_counts[classification] = severity_counts.get(classification, 0) + 1
            except:
                pass
        
        return severity_counts
    
    def _analyze_error_patterns(self, incidents: List[Dict]) -> List[str]:
        """Find common error patterns"""
        error_patterns = {}
        
        for incident in incidents:
            event_details = incident.get('event_details', {}).get('S', '{}')
            try:
                details = json.loads(event_details)
                event_name = details.get('eventName', 'Unknown')
                error_patterns[event_name] = error_patterns.get(event_name, 0) + 1
            except:
                pass
        
        # Return top 5 patterns
        sorted_patterns = sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)
        return [f"{pattern}: {count}" for pattern, count in sorted_patterns[:5]]


class ThresholdOptimizer:
    """
    Optimize alert thresholds based on historical data
    """
    
    def __init__(self):
        self.default_thresholds = {
            'cpu_utilization': 80.0,
            'error_rate': 5.0,
            'latency_ms': 1000.0
        }
    
    def optimize_thresholds(self, metric_history: Dict[str, List[float]]) -> Dict[str, float]:
        """
        Optimize thresholds based on historical data
        Uses percentile-based approach
        """
        optimized = {}
        
        for metric_name, values in metric_history.items():
            if len(values) < 10:
                optimized[metric_name] = self.default_thresholds.get(metric_name, 100.0)
                continue
            
            # Use 95th percentile as threshold
            threshold = np.percentile(values, 95)
            optimized[metric_name] = float(threshold)
        
        return optimized


def handler(event, context):
    """
    Lambda handler for ML pattern recognition
    """
    action = event.get('action', 'detect_anomalies')
    
    if action == 'detect_anomalies':
        data = event.get('data', [])
        detector = AnomalyDetector(sensitivity=event.get('sensitivity', 2.0))
        anomalies = detector.detect_anomalies(data)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'anomalies': anomalies,
                'total_points': len(data),
                'anomaly_count': len(anomalies)
            })
        }
    
    elif action == 'find_patterns':
        incident_table = event.get('incident_table', 'aiops-incidents')
        lookback_hours = event.get('lookback_hours', 24)
        
        recognizer = PatternRecognizer(incident_table)
        patterns = recognizer.find_patterns(lookback_hours)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'patterns': patterns,
                'lookback_hours': lookback_hours
            })
        }
    
    elif action == 'optimize_thresholds':
        metric_history = event.get('metric_history', {})
        optimizer = ThresholdOptimizer()
        thresholds = optimizer.optimize_thresholds(metric_history)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'optimized_thresholds': thresholds
            })
        }
    
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Unknown action: {action}'})
        }
