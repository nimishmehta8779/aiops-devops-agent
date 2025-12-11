"""
Kubectl Lambda Layer
Executes kubectl commands against EKS cluster
"""

import json
import os
import subprocess
import boto3
import base64

eks = boto3.client('eks')


def get_cluster_credentials(cluster_name: str, region: str = 'us-east-1'):
    """Get EKS cluster credentials"""
    try:
        response = eks.describe_cluster(name=cluster_name)
        cluster = response['cluster']
        
        # Get cluster endpoint and CA
        endpoint = cluster['endpoint']
        ca_data = cluster['certificateAuthority']['data']
        
        # Write kubeconfig
        kubeconfig = {
            'apiVersion': 'v1',
            'kind': 'Config',
            'clusters': [{
                'name': cluster_name,
                'cluster': {
                    'server': endpoint,
                    'certificate-authority-data': ca_data
                }
            }],
            'contexts': [{
                'name': cluster_name,
                'context': {
                    'cluster': cluster_name,
                    'user': cluster_name
                }
            }],
            'current-context': cluster_name,
            'users': [{
                'name': cluster_name,
                'user': {
                    'exec': {
                        'apiVersion': 'client.authentication.k8s.io/v1beta1',
                        'command': 'aws',
                        'args': [
                            'eks', 'get-token',
                            '--cluster-name', cluster_name,
                            '--region', region
                        ]
                    }
                }
            }]
        }
        
        return kubeconfig
        
    except Exception as e:
        print(f"Error getting cluster credentials: {e}")
        return None


def handler(event, context):
    """
    Execute kubectl command
    """
    cluster_name = event.get('cluster', '')
    command = event.get('command', 'get pods')
    
    if not cluster_name:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'cluster name required'})
        }
    
    # Get cluster credentials
    kubeconfig = get_cluster_credentials(cluster_name)
    if not kubeconfig:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Failed to get cluster credentials'})
        }
    
    # Write kubeconfig to /tmp
    kubeconfig_path = '/tmp/kubeconfig'
    with open(kubeconfig_path, 'w') as f:
        json.dump(kubeconfig, f)
    
    # Execute kubectl command
    try:
        result = subprocess.run(
            f'kubectl --kubeconfig={kubeconfig_path} {command}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return {
                'statusCode': 200,
                'body': result.stdout
            }
        else:
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': result.stderr,
                    'returncode': result.returncode
                })
            }
            
    except subprocess.TimeoutExpired:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Command timeout'})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
