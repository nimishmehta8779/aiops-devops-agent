#!/bin/bash

################################################################################
# Multi-Agent AIOps System - Automated Test
# Tests the deployed infrastructure and multi-agent orchestration
################################################################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
REPORT_FILE="test_report_$(date +%Y%m%d_%H%M%S).txt"
LAMBDA_ORCHESTRATOR="aiops-multi-agent-orchestrator"
DYNAMODB_INCIDENTS="aiops-incidents"
DYNAMODB_LOCKS="aiops-terraform-locks"
CODEBUILD_PROJECT="aiops-devops-agent-apply"

# Counters
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

log() {
    echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $1" | tee -a "$REPORT_FILE"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$REPORT_FILE"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$REPORT_FILE"
    ((TESTS_FAILED++))
}

section() {
    echo "" | tee -a "$REPORT_FILE"
    echo "═══════════════════════════════════════════════════════════════════" | tee -a "$REPORT_FILE"
    echo -e "${CYAN}$1${NC}" | tee -a "$REPORT_FILE"
    echo "═══════════════════════════════════════════════════════════════════" | tee -a "$REPORT_FILE"
}

################################################################################
# Main Tests
################################################################################

section "MULTI-AGENT AIOPS SYSTEM - AUTOMATED TEST"
log "Started: $(date)"

# Test 1: Global Infrastructure
section "TEST 1: GLOBAL INFRASTRUCTURE"

((TESTS_TOTAL++))
if aws dynamodb describe-table --table-name "$DYNAMODB_INCIDENTS" &>/dev/null; then
    log_success "Incidents table exists"
else
    log_error "Incidents table not found"
fi

((TESTS_TOTAL++))
if aws dynamodb describe-table --table-name "$DYNAMODB_LOCKS" &>/dev/null; then
    log_success "Terraform locks table exists"
else
    log_error "Terraform locks table not found"
fi

((TESTS_TOTAL++))
if aws codebuild batch-get-projects --names "$CODEBUILD_PROJECT" &>/dev/null; then
    log_success "CodeBuild project exists"
else
    log_error "CodeBuild project not found"
fi

# Test 2: Multi-Agent Lambda
section "TEST 2: MULTI-AGENT LAMBDA"
((TESTS_TOTAL++))

if aws lambda get-function --function-name "$LAMBDA_ORCHESTRATOR" &>/dev/null; then
    log_success "Multi-agent orchestrator Lambda exists"
else
    log_error "Multi-agent orchestrator Lambda not found"
fi

# Test 3: EventBridge Rules
section "TEST 3: EVENTBRIDGE RULES"
((TESTS_TOTAL++))

if aws events describe-rule --name "aiops-multi-agent-cloudtrail-events" &>/dev/null; then
    log_success "CloudTrail EventBridge rule exists"
else
    log_error "CloudTrail EventBridge rule not found"
fi

((TESTS_TOTAL++))
if aws events describe-rule --name "aiops-multi-agent-ec2-state-change" &>/dev/null; then
    log_success "EC2 state change EventBridge rule exists"
else
    log_error "EC2 state change EventBridge rule not found"
fi

# Test 4: Trigger Test Incident
section "TEST 4: TRIGGER TEST INCIDENT (EC2 TERMINATION)"
((TESTS_TOTAL++))

log "Creating test event payload..."
cat > /tmp/test_event.json <<EOF
{
  "detail-type": "AWS API Call via CloudTrail",
  "source": "aws.ec2",
  "region": "us-east-1",
  "detail": {
    "eventName": "TerminateInstances",
    "eventTime": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "eventSource": "ec2.amazonaws.com",
    "userIdentity": {
      "arn": "arn:aws:iam::123456789012:user/test-user"
    },
    "requestParameters": {
      "instancesSet": {
        "items": [
          {
            "instanceId": "i-test123456789"
          }
        ]
      }
    }
  }
}
EOF

log "Invoking multi-agent orchestrator..."
response_file="/tmp/test_response_$$.json"

if aws lambda invoke \
    --function-name "$LAMBDA_ORCHESTRATOR" \
    --payload file:///tmp/test_event.json \
    --cli-binary-format raw-in-base64-out \
    "$response_file" > /tmp/invoke_$$.json 2>&1; then
    
    status_code=$(jq -r '.StatusCode' /tmp/invoke_$$.json 2>/dev/null || echo "unknown")
    
    if [ "$status_code" = "200" ]; then
        log_success "Lambda invoked successfully"
        
        # Parse response
        correlation_id=$(jq -r '.correlation_id' "$response_file" 2>/dev/null)
        status=$(jq -r '.status' "$response_file" 2>/dev/null)
        total_agents=$(jq -r '.results.total_agents' "$response_file" 2>/dev/null)
        successful_agents=$(jq -r '.results.successful_agents' "$response_file" 2>/dev/null)
        
        log "  Correlation ID: $correlation_id"
        log "  Status: $status"
        log "  Total Agents: $total_agents"
        log "  Successful Agents: $successful_agents"
        
        # Test 5: Verify Agent Execution
        section "TEST 5: VERIFY AGENT EXECUTION"
        
        ((TESTS_TOTAL++))
        if [ "$total_agents" = "5" ]; then
            log_success "All 5 agents executed"
        else
            log_error "Expected 5 agents, got $total_agents"
        fi
        
        ((TESTS_TOTAL++))
        if [ "$successful_agents" = "5" ]; then
            log_success "All agents completed successfully"
        else
            log_error "Only $successful_agents agents succeeded"
        fi
        
        # Test 6: Verify in DynamoDB
        section "TEST 6: VERIFY INCIDENT IN DYNAMODB"
        ((TESTS_TOTAL++))
        
        sleep 2  # Give DynamoDB time to update
        
        if aws dynamodb get-item \
            --table-name "$DYNAMODB_INCIDENTS" \
            --key "{\"incident_id\":{\"S\":\"$correlation_id\"}}" \
            --query 'Item.workflow_state.S' \
            --output text > /tmp/state_$$.txt 2>&1; then
            
            state=$(cat /tmp/state_$$.txt)
            if [ -n "$state" ] && [ "$state" != "None" ]; then
                log_success "Incident logged to DynamoDB (State: $state)"
            else
                log_error "Incident not found in DynamoDB"
            fi
        else
            log_error "Failed to query DynamoDB"
        fi
        
        # Test 7: Verify Agent Results
        section "TEST 7: VERIFY AGENT RESULTS"
        
        ((TESTS_TOTAL++))
        triage_status=$(jq -r '.results.agent_results.triage.status' "$response_file" 2>/dev/null)
        if [ "$triage_status" = "success" ]; then
            classification=$(jq -r '.results.agent_results.triage.analysis.classification' "$response_file" 2>/dev/null)
            log_success "Triage Agent: $triage_status (Classification: $classification)"
        else
            log_error "Triage Agent failed"
        fi
        
        ((TESTS_TOTAL++))
        remediation_status=$(jq -r '.results.agent_results.remediation.status' "$response_file" 2>/dev/null)
        if [ "$remediation_status" = "success" ]; then
            approval_required=$(jq -r '.results.agent_results.remediation.execution.approval_required' "$response_file" 2>/dev/null)
            log_success "Remediation Agent: $remediation_status (Approval Required: $approval_required)"
        else
            log_error "Remediation Agent failed"
        fi
        
    else
        log_error "Lambda returned status: $status_code"
    fi
else
    log_error "Lambda invocation failed"
fi

# Test 8: CloudWatch Logs
section "TEST 8: CLOUDWATCH LOGS"
((TESTS_TOTAL++))

log_group="/aws/lambda/$LAMBDA_ORCHESTRATOR"
if aws logs describe-log-groups --log-group-name-prefix "$log_group" | grep -q "$log_group"; then
    log_success "CloudWatch log group exists"
    
    # Get latest log stream
    latest_stream=$(aws logs describe-log-streams \
        --log-group-name "$log_group" \
        --order-by LastEventTime \
        --descending \
        --max-items 1 \
        --query 'logStreams[0].logStreamName' \
        --output text 2>/dev/null)
    
    if [ -n "$latest_stream" ] && [ "$latest_stream" != "None" ]; then
        log "  Latest log stream: $latest_stream"
    fi
else
    log_error "CloudWatch log group not found"
fi

# Test 9: Historical Data
section "TEST 9: HISTORICAL DATA"
((TESTS_TOTAL++))

incident_count=$(aws dynamodb scan \
    --table-name "$DYNAMODB_INCIDENTS" \
    --select COUNT \
    --query 'Count' \
    --output text 2>/dev/null || echo "0")

if [ "$incident_count" -gt 0 ]; then
    log_success "Historical incidents available: $incident_count"
else
    log_error "No historical incidents found"
fi

# Final Report
section "TEST SUMMARY"

echo "" | tee -a "$REPORT_FILE"
echo "╔═══════════════════════════════════════════════════════════════════╗" | tee -a "$REPORT_FILE"
echo "║                        TEST RESULTS                                ║" | tee -a "$REPORT_FILE"
echo "╚═══════════════════════════════════════════════════════════════════╝" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo "  Total Tests:    $TESTS_TOTAL" | tee -a "$REPORT_FILE"
echo "  ✅ Passed:      $TESTS_PASSED" | tee -a "$REPORT_FILE"
echo "  ❌ Failed:      $TESTS_FAILED" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

success_rate=0
if [ "$TESTS_TOTAL" -gt 0 ]; then
    success_rate=$((TESTS_PASSED * 100 / TESTS_TOTAL))
fi

echo "  Success Rate:   ${success_rate}%" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED! 🎉${NC}" | tee -a "$REPORT_FILE"
    exit_code=0
else
    echo -e "${YELLOW}⚠️  Some tests failed${NC}" | tee -a "$REPORT_FILE"
    exit_code=1
fi

echo "" | tee -a "$REPORT_FILE"
log "Completed: $(date)"
log "Report saved: $REPORT_FILE"

# Cleanup
rm -f /tmp/*_$$.json /tmp/*_$$.txt /tmp/test_event.json 2>/dev/null

exit $exit_code
