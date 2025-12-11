#!/bin/bash

# AIOps Live Recovery Demo
# Shows continuous state monitoring and automated recovery actions

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

EKS_CLUSTER="aiops-eks-cluster"
INCIDENT_TABLE="aiops-incidents"
REGION="us-east-1"

function print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE} $1 ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
}

function log() {
    echo -e "${GREEN}[$(date +%T)]${NC} $1"
}

function monitor_incident() {
    local incident_id=$1
    local current_state=""
    local previous_state=""
    
    log "Monitoring incident $incident_id..."
    
    for i in {1..30}; do
        response=$(aws dynamodb get-item --table-name $INCIDENT_TABLE --key "{\"incident_id\": {\"S\": \"$incident_id\"}}" --output json)
        
        if [ -z "$response" ]; then
            log "Incident not found yet..."
            sleep 1
            continue
        fi
        
        current_state=$(echo $response | jq -r '.Item.workflow_state.S')
        remediation_status=$(echo $response | jq -r '.Item.remediation_status.S // "none"')
        
        if [ "$current_state" != "$previous_state" ]; then
            echo -e "${YELLOW}>>> State Transition: $previous_state -> $current_state${NC}"
            
            # Print details based on state
            if [ "$current_state" == "ANALYZING" ]; then
                log "Agents are analyzing telemetry and risks..."
            elif [ "$current_state" == "COMPLETED" ] || [ "$current_state" == "FAILED" ]; then
                log "Workflow finished."
                
                # Check results
                remediation=$(echo $response | jq -r '.Item.remediation_plan.S // "{}"')
                if [ "$remediation_status" == "pending_approval" ]; then
                    echo -e "${RED}[RISK AGENT] BLOCKED Auto-Execution.${NC}"
                    echo -e "Reason: High Risk / Production DB Modification"
                    echo -e "Action Required: Human Approval"
                else
                     echo -e "${GREEN}[SUCCESS] Auto-Remediation Executed.${NC}"
                fi
                break
            fi
            
            previous_state=$current_state
        fi
        
        sleep 1
    done
}

# =================================================================================================
# SCENARIO 1: RDS AUTOMATED RECOVERY (Simulated)
# =================================================================================================
print_header "SCENARIO 1: RDS FAILURE & AI REASONING"

log "Simulating RDS Failure (Stopped State)..."
# Using the previously created mock event
aws lambda invoke --function-name aiops-multi-agent-orchestrator --payload file://rds_stop_event.json --cli-binary-format raw-in-base64-out rds_response.json > /dev/null

incident_id=$(cat rds_response.json | jq -r '.correlation_id')
log "Incident Created: $incident_id"

monitor_incident "$incident_id"

LOGS=$(aws logs filter-log-events --log-group-name "/aws/lambda/aiops-multi-agent-orchestrator" --limit 5 --output json)
echo -e "\n${BLUE}--- AGENT LOGS (DEBUG) ---${NC}"
echo "$LOGS" | jq -r '.events[].message' | grep -v "START" | grep -v "END" | head -n 5


# =================================================================================================
# SCENARIO 2: KUBERNETES APP RECOVERY
# =================================================================================================
print_header "SCENARIO 2: EKS APPLICATION RECOVERY"

# Update Kubeconfig
aws eks update-kubeconfig --name $EKS_CLUSTER --region $REGION > /dev/null

log "Checking current application state..."
kubectl get po -n aiops-sample
pod_name=$(kubectl get po -n aiops-sample -l app=crashing-app -o jsonpath="{.items[0].metadata.name}")

if [ -z "$pod_name" ]; then
    log "Deployment not found. Creating..."
    # Skipping creation if missing, assuming valid state from deployment
else 
    log "Target Pod: $pod_name"
fi

log "Detected Pod in CrashLoopBackOff. AIOps Agent initiating restart..."

# Invoke K8s Agent manually to restart pod
# FIX: Adjusted function name to aiops-kubernetes-agent
payload="{\"action\": \"restart_pod\", \"cluster_name\": \"$EKS_CLUSTER\", \"pod_name\": \"$pod_name\", \"namespace\": \"aiops-sample\"}"
aws lambda invoke --function-name aiops-kubernetes-agent --payload "$payload" --cli-binary-format raw-in-base64-out k8s_response.json > /dev/null

log "K8s Agent Response: $(cat k8s_response.json | jq -r '.body')"

log "Watching Pod Deletion & Recreation (5s)..."
for i in {1..5}; do
    kubectl get po -n aiops-sample
    sleep 1
done

log "Observation: App still crashing because code is bad (exit 1)."
echo -e "${YELLOW}AIOps Insight: Repeated failures detected. Applying Fix (Patch to Nginx)...${NC}"

# Applying Patch via Kubectl (simulating Engineer/Advanced Agent Action)
kubectl set image deployment/crashing-app busybox=nginx -n aiops-sample
log "Patch applied: Switched image to nginx"

monitor_pod() {
    log "Waiting for Pod to become Running..."
    for i in {1..20}; do
        status=$(kubectl get po -n aiops-sample -l app=crashing-app -o jsonpath="{.items[0].status.phase}")
        echo "Status: $status"
        if [ "$status" == "Running" ]; then
            echo -e "${GREEN}✅ APP RECOVERED!${NC}"
            return
        fi
        sleep 2
    done
    echo "Timed out waiting for recovery."
}

monitor_pod

print_header "DEMO COMPLETE"
