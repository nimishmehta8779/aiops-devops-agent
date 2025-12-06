#!/bin/bash

################################################################################
# AI DevOps Agent - Quick Automated Test (Non-Interactive)
# 
# This script performs automated testing without user prompts
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
LAMBDA_ORCHESTRATOR="aiops-devops-agent-orchestrator"
LAMBDA_LOG_ANALYZER="aiops-devops-agent-log-analyzer"
DYNAMODB_INCIDENTS="aiops-devops-agent-incidents"

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

section "AI DEVOPS AGENT - QUICK AUTOMATED TEST"
log "Started: $(date)"

# Test 1: Lambda Functions
section "TEST 1: LAMBDA FUNCTIONS"
((TESTS_TOTAL++))

if aws lambda get-function --function-name "$LAMBDA_ORCHESTRATOR" &>/dev/null; then
    log_success "Orchestrator Lambda exists"
else
    log_error "Orchestrator Lambda not found"
fi

((TESTS_TOTAL++))
if aws lambda get-function --function-name "$LAMBDA_LOG_ANALYZER" &>/dev/null; then
    log_success "Log Analyzer Lambda exists"
else
    log_error "Log Analyzer Lambda not found"
fi

# Test 2: DynamoDB
section "TEST 2: DYNAMODB TABLES"
((TESTS_TOTAL++))

if aws dynamodb describe-table --table-name "$DYNAMODB_INCIDENTS" &>/dev/null; then
    log_success "Incidents table exists"
else
    log_error "Incidents table not found"
fi

# Test 3: Trigger Incident
section "TEST 3: TRIGGER TEST INCIDENT"
((TESTS_TOTAL++))

log "Invoking orchestrator Lambda..."
response_file="/tmp/test_response_$$.json"

if aws lambda invoke \
    --function-name "$LAMBDA_ORCHESTRATOR" \
    --payload file://test_demo.json \
    --cli-binary-format raw-in-base64-out \
    "$response_file" > /tmp/invoke_$$.json 2>&1; then
    
    status_code=$(jq -r '.StatusCode' /tmp/invoke_$$.json 2>/dev/null || echo "unknown")
    
    if [ "$status_code" = "200" ]; then
        log_success "Lambda invoked successfully"
        
        # Parse response
        correlation_id=$(jq -r '.correlation_id' "$response_file" 2>/dev/null)
        status=$(jq -r '.status' "$response_file" 2>/dev/null)
        confidence=$(jq -r '.confidence' "$response_file" 2>/dev/null)
        
        log "  Correlation ID: $correlation_id"
        log "  Status: $status"
        log "  Confidence: $confidence"
        
        # Test 4: Verify in DynamoDB
        section "TEST 4: VERIFY INCIDENT IN DYNAMODB"
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
    else
        log_error "Lambda returned status: $status_code"
    fi
else
    log_error "Lambda invocation failed"
fi

# Test 5: Log Analyzer
section "TEST 5: LOG ANALYZER"
((TESTS_TOTAL++))

log "Invoking log analyzer..."
analyzer_response="/tmp/analyzer_$$.json"

if aws lambda invoke \
    --function-name "$LAMBDA_LOG_ANALYZER" \
    --cli-binary-format raw-in-base64-out \
    "$analyzer_response" > /dev/null 2>&1; then
    
    analyzer_status=$(jq -r '.status' "$analyzer_response" 2>/dev/null)
    
    if [ "$analyzer_status" = "ok" ]; then
        log_success "Log analyzer executed successfully"
        analyzed=$(jq -r '.analyzed_log_groups' "$analyzer_response" 2>/dev/null)
        log "  Analyzed log groups: $analyzed"
    else
        log_error "Log analyzer returned: $analyzer_status"
    fi
else
    log_error "Log analyzer invocation failed"
fi

# Test 6: Historical Data
section "TEST 6: HISTORICAL DATA"
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
else
    echo -e "${YELLOW}⚠️  Some tests failed${NC}" | tee -a "$REPORT_FILE"
fi

echo "" | tee -a "$REPORT_FILE"
log "Completed: $(date)"
log "Report saved: $REPORT_FILE"

# Cleanup
rm -f /tmp/*_$$.json /tmp/*_$$.txt 2>/dev/null

exit 0
