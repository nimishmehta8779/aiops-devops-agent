# Phase 9: Kubernetes Support

## Overview

This phase adds comprehensive Kubernetes/EKS support to the AIOps system.

## Features

### 1. Pod Failure Detection
- Detects pods in `Failed` or `Unknown` state
- Identifies `CrashLoopBackOff`, `ImagePullBackOff`, `ErrImagePull`
- Container-level failure detection

### 2. Automated Recovery
- **Pod Restart**: Delete failed pods (K8s recreates them)
- **Deployment Rollback**: Rollback to previous revision
- **Scaling**: Scale deployments up/down

### 3. HPA Monitoring
- Monitor Horizontal Pod Autoscaler status
- Track current vs desired replicas
- Alert on scaling issues

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    EKS Cluster                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Pod 1     │  │   Pod 2     │  │   Pod 3     │         │
│  │  (Running)  │  │  (Failed)   │  │ (CrashLoop) │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              K8s Agent Lambda                                │
│  - Detect failures via kubectl                              │
│  - Restart pods                                              │
│  - Rollback deployments                                      │
│  - Scale workloads                                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│           Kubectl Layer Lambda                               │
│  - Execute kubectl commands                                  │
│  - Authenticate with EKS                                     │
└─────────────────────────────────────────────────────────────┘
```

## Deployment

```bash
cd phase-9-kubernetes

# Set your EKS cluster name
terraform apply -var="eks_cluster_name=my-cluster"
```

## Usage

### Detect Pod Failures
```python
import boto3
lambda_client = boto3.client('lambda')

response = lambda_client.invoke(
    FunctionName='aiops-kubernetes-agent',
    Payload=json.dumps({
        'action': 'detect_failures',
        'cluster_name': 'my-eks-cluster',
        'namespace': 'production'
    })
)
```

### Restart Failed Pod
```python
response = lambda_client.invoke(
    FunctionName='aiops-kubernetes-agent',
    Payload=json.dumps({
        'action': 'restart_pod',
        'cluster_name': 'my-eks-cluster',
        'pod_name': 'my-app-abc123',
        'namespace': 'production'
    })
)
```

### Rollback Deployment
```python
response = lambda_client.invoke(
    FunctionName='aiops-kubernetes-agent',
    Payload=json.dumps({
        'action': 'rollback_deployment',
        'cluster_name': 'my-eks-cluster',
        'deployment_name': 'my-app',
        'namespace': 'production'
    })
)
```

### Scale Deployment
```python
response = lambda_client.invoke(
    FunctionName='aiops-kubernetes-agent',
    Payload=json.dumps({
        'action': 'scale_deployment',
        'cluster_name': 'my-eks-cluster',
        'deployment_name': 'my-app',
        'replicas': 5,
        'namespace': 'production'
    })
)
```

## Integration with Multi-Agent System

The K8s agent can be integrated into the Remediation Agent:

```python
# In remediation_agent.py
def _execute_k8s_runbook(self, runbook: Dict) -> Dict:
    """Execute Kubernetes runbook"""
    k8s_lambda = os.environ.get('K8S_AGENT_ARN')
    
    response = lambda_client.invoke(
        FunctionName=k8s_lambda,
        Payload=json.dumps(runbook)
    )
    
    return json.loads(response['Payload'].read())
```

## Prerequisites

- **EKS Cluster**: Must have an existing EKS cluster
- **IAM Permissions**: Lambda needs `eks:DescribeCluster` permission
- **kubectl**: Included in Lambda layer (or use AWS-provided layer)

## Security

- Uses AWS IAM for EKS authentication
- No kubeconfig stored permanently
- Temporary credentials generated per invocation
- Namespace-aware operations

## Future Enhancements

- **Helm Integration**: Deploy/upgrade Helm charts
- **Custom Resource Definitions**: Support CRDs
- **Multi-Cluster**: Support multiple EKS clusters
- **GitOps Integration**: Integrate with ArgoCD/Flux
