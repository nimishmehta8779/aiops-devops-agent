"""
Kubernetes Agent - EKS Event Detection and Pod Recovery
Handles K8s pod failures, deployment rollbacks, and HPA integration
"""

import json
import os
import boto3
from typing import Dict, List, Any
from datetime import datetime
import base64

# AWS clients
eks = boto3.client('eks')
ec2 = boto3.client('ec2')
dynamodb = boto3.client('dynamodb')
lambda_client = boto3.client('lambda')


class KubernetesAgent:
    """
    Kubernetes agent for EKS monitoring and recovery
    """
    
    def __init__(self, cluster_name: str, region: str = 'us-east-1'):
        self.cluster_name = cluster_name
        self.region = region
        self.kubectl_lambda = os.environ.get('KUBECTL_LAMBDA_ARN', '')
    
    def detect_pod_failures(self, namespace: str = 'default') -> List[Dict]:
        """
        Detect failed pods in EKS cluster
        Uses kubectl via Lambda layer
        """
        try:
            # Invoke kubectl Lambda to get pod status
            response = lambda_client.invoke(
                FunctionName=self.kubectl_lambda,
                Payload=json.dumps({
                    'cluster': self.cluster_name,
                    'command': f'get pods -n {namespace} -o json'
                })
            )
            
            result = json.loads(response['Payload'].read())
            pods_data = json.loads(result.get('body', '{}'))
            
            failed_pods = []
            for pod in pods_data.get('items', []):
                status = pod.get('status', {})
                phase = status.get('phase', '')
                
                # Check for failures
                if phase in ['Failed', 'Unknown']:
                    failed_pods.append({
                        'name': pod['metadata']['name'],
                        'namespace': pod['metadata']['namespace'],
                        'phase': phase,
                        'reason': status.get('reason', 'Unknown'),
                        'message': status.get('message', '')
                    })
                
                # Check container statuses
                container_statuses = status.get('containerStatuses', [])
                for container in container_statuses:
                    state = container.get('state', {})
                    
                    if 'waiting' in state:
                        waiting = state['waiting']
                        reason = waiting.get('reason', '')
                        
                        if reason in ['CrashLoopBackOff', 'ImagePullBackOff', 'ErrImagePull']:
                            failed_pods.append({
                                'name': pod['metadata']['name'],
                                'namespace': pod['metadata']['namespace'],
                                'container': container['name'],
                                'phase': 'ContainerFailure',
                                'reason': reason,
                                'message': waiting.get('message', '')
                            })
            
            return failed_pods
            
        except Exception as e:
            print(f"Error detecting pod failures: {e}")
            return []
    
    def restart_pod(self, pod_name: str, namespace: str = 'default') -> Dict:
        """
        Restart a failed pod by deleting it (K8s will recreate)
        """
        try:
            response = lambda_client.invoke(
                FunctionName=self.kubectl_lambda,
                Payload=json.dumps({
                    'cluster': self.cluster_name,
                    'command': f'delete pod {pod_name} -n {namespace}'
                })
            )
            
            result = json.loads(response['Payload'].read())
            
            return {
                'status': 'success',
                'pod': pod_name,
                'namespace': namespace,
                'action': 'deleted_for_restart'
            }
            
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def rollback_deployment(self, deployment_name: str, namespace: str = 'default') -> Dict:
        """
        Rollback a deployment to previous revision
        """
        try:
            response = lambda_client.invoke(
                FunctionName=self.kubectl_lambda,
                Payload=json.dumps({
                    'cluster': self.cluster_name,
                    'command': f'rollout undo deployment/{deployment_name} -n {namespace}'
                })
            )
            
            result = json.loads(response['Payload'].read())
            
            return {
                'status': 'success',
                'deployment': deployment_name,
                'namespace': namespace,
                'action': 'rolled_back'
            }
            
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def scale_deployment(self, deployment_name: str, replicas: int, namespace: str = 'default') -> Dict:
        """
        Scale a deployment
        """
        try:
            response = lambda_client.invoke(
                FunctionName=self.kubectl_lambda,
                Payload=json.dumps({
                    'cluster': self.cluster_name,
                    'command': f'scale deployment/{deployment_name} --replicas={replicas} -n {namespace}'
                })
            )
            
            result = json.loads(response['Payload'].read())
            
            return {
                'status': 'success',
                'deployment': deployment_name,
                'namespace': namespace,
                'replicas': replicas,
                'action': 'scaled'
            }
            
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def check_hpa_status(self, namespace: str = 'default') -> List[Dict]:
        """
        Check Horizontal Pod Autoscaler status
        """
        try:
            response = lambda_client.invoke(
                FunctionName=self.kubectl_lambda,
                Payload=json.dumps({
                    'cluster': self.cluster_name,
                    'command': f'get hpa -n {namespace} -o json'
                })
            )
            
            result = json.loads(response['Payload'].read())
            hpa_data = json.loads(result.get('body', '{}'))
            
            hpa_status = []
            for hpa in hpa_data.get('items', []):
                status = hpa.get('status', {})
                spec = hpa.get('spec', {})
                
                hpa_status.append({
                    'name': hpa['metadata']['name'],
                    'namespace': hpa['metadata']['namespace'],
                    'current_replicas': status.get('currentReplicas', 0),
                    'desired_replicas': status.get('desiredReplicas', 0),
                    'min_replicas': spec.get('minReplicas', 1),
                    'max_replicas': spec.get('maxReplicas', 10),
                    'target_cpu': spec.get('targetCPUUtilizationPercentage', 80)
                })
            
            return hpa_status
            
        except Exception as e:
            print(f"Error checking HPA status: {e}")
            return []


def handler(event, context):
    """
    Lambda handler for Kubernetes operations
    """
    cluster_name = event.get('cluster_name', os.environ.get('EKS_CLUSTER_NAME', ''))
    action = event.get('action', 'detect_failures')
    namespace = event.get('namespace', 'default')
    
    if not cluster_name:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'cluster_name required'})
        }
    
    k8s_agent = KubernetesAgent(cluster_name)
    
    if action == 'detect_failures':
        failed_pods = k8s_agent.detect_pod_failures(namespace)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'failed_pods': failed_pods,
                'count': len(failed_pods),
                'namespace': namespace
            })
        }
    
    elif action == 'restart_pod':
        pod_name = event.get('pod_name')
        if not pod_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'pod_name required'})
            }
        
        result = k8s_agent.restart_pod(pod_name, namespace)
        return {
            'statusCode': 200 if result['status'] == 'success' else 500,
            'body': json.dumps(result)
        }
    
    elif action == 'rollback_deployment':
        deployment_name = event.get('deployment_name')
        if not deployment_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'deployment_name required'})
            }
        
        result = k8s_agent.rollback_deployment(deployment_name, namespace)
        return {
            'statusCode': 200 if result['status'] == 'success' else 500,
            'body': json.dumps(result)
        }
    
    elif action == 'scale_deployment':
        deployment_name = event.get('deployment_name')
        replicas = event.get('replicas', 1)
        
        if not deployment_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'deployment_name required'})
            }
        
        result = k8s_agent.scale_deployment(deployment_name, replicas, namespace)
        return {
            'statusCode': 200 if result['status'] == 'success' else 500,
            'body': json.dumps(result)
        }
    
    elif action == 'check_hpa':
        hpa_status = k8s_agent.check_hpa_status(namespace)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'hpa_status': hpa_status,
                'count': len(hpa_status)
            })
        }
    
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Unknown action: {action}'})
        }
