#!/bin/bash

# AIOps Live Recovery Demo: ROLLBACK SCENARIO
# Shows automated rollback of a bad deployment

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

EKS_CLUSTER="aiops-eks-cluster"
REGION="us-east-1"

function print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE} $1 ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
}

function log() {
    echo -e "${GREEN}[$(date +%T)]${NC} $1"
}

# Ensure Kubeconfig
aws eks update-kubeconfig --name $EKS_CLUSTER --region $REGION > /dev/null

print_header "SETUP: DEPLOYING HEALTHY APP"

# Verify current state is healthy (assuming Terraform applied successfully)
log "Verifying initial state..."
kubectl rollout status deployment/crashing-app -n aiops-sample --timeout=60s
if [ $? -ne 0 ]; then
    echo -e "${RED}Initial state is not healthy. Waiting...${NC}"
    sleep 10
fi

# Get current revision
rev=$(kubectl rollout history deployment/crashing-app -n aiops-sample | tail -n 1 | awk '{print $1}')
log "Current Revision: $rev (Healthy)"


print_header "SCENARIO: BAD DEPLOYMENT SIMULATION"

log "Simulating a botched deployment (Bad Image + Crash Loop)..."

# Apply BAD configuration (Busybox with exit 1)
# Using kubectl patch to simulate CI/CD deployment
kubectl patch deployment crashing-app -n aiops-sample --type='json' -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/image", "value": "busybox"}, {"op": "add", "path": "/spec/template/spec/containers/0/command", "value": ["/bin/sh", "-c", "exit 1"]}]'

log "Bad configuration applied. Monitoring for failure..."

# Monitor for CrashLoopBackOff
for i in {1..20}; do
    pods=$(kubectl get po -n aiops-sample -l app=crashing-app)
    echo "$pods"
    if echo "$pods" | grep -q "CrashLoopBackOff"; then
        echo -e "${RED}⚠️  CrashLoopBackOff Detected!${NC}"
        
        # Trigger Agent (Simulation of EventBridge -> Lambda)
        # In real life, EventBridge triggers on Pod status. Here we force invoke for demo speed.
        log "Triggering AIOps Kubernetes Agent..."
        
        # Trigger Agent to Rollback
        log "Triggering AIOps Kubernetes Agent to ROLLBACK..."
        
        deployment_name="crashing-app"
        payload="{\"action\": \"rollback_deployment\", \"cluster_name\": \"$EKS_CLUSTER\", \"deployment_name\": \"$deployment_name\", \"namespace\": \"aiops-sample\"}"
        
        # Invoke Agent
        aws lambda invoke --function-name aiops-kubernetes-agent --payload "$payload" --cli-binary-format raw-in-base64-out k8s_rollback_response.json > /dev/null
        
        response=$(cat k8s_rollback_response.json)
        log "Agent Response: $response"
        
        break
    else
         # Check for Error state too
        if echo "$pods" | grep -q "Error"; then
             echo -e "${RED}⚠️  Pod in Error State!${NC}"
             
             log "Triggering AIOps Kubernetes Agent to ROLLBACK..."
             deployment_name="crashing-app"
             payload="{\"action\": \"rollback_deployment\", \"cluster_name\": \"$EKS_CLUSTER\", \"deployment_name\": \"$deployment_name\", \"namespace\": \"aiops-sample\"}"
             
             aws lambda invoke --function-name aiops-kubernetes-agent --payload "$payload" --cli-binary-format raw-in-base64-out k8s_rollback_response.json > /dev/null
             response=$(cat k8s_rollback_response.json)
             log "Agent Response: $response"
             
             break
        fi
    fi
    sleep 3
done

print_header "RECOVERY: AUTOMATED ROLLBACK"

log "Agent detected persistent failure. Initiating Rollback..."

# The agent might have returned "rollback" action or executed it.
# Check if rollback started.
for i in {1..20}; do
    status=$(kubectl rollout status deployment/crashing-app -n aiops-sample --timeout=5s 2>&1)
    echo "Rollout Status: $status"
    
    if [[ "$status" == *"successfully rolled out"* ]]; then
        echo -e "${GREEN}✅ ROLLBACK COMPLETE!${NC}"
        break
    fi
    sleep 3
done

# Verify image is back to Nginx
current_image=$(kubectl get deployment crashing-app -n aiops-sample -o jsonpath='{.spec.template.spec.containers[0].image}')
log "Current Image: $current_image"

if [[ "$current_image" == *"nginx"* ]]; then
    echo -e "${GREEN}SUCCESS: App restored to stable configuration.${NC}"
else
    echo -e "${RED}FAILURE: App is still on $current_image${NC}"
fi

print_header "DEMO COMPLETE"
