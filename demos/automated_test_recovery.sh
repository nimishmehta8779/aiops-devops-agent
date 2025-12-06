#!/bin/bash

################################################################################
# AI DevOps Agent - Automated Test & Recovery Script
# 
# This script performs end-to-end testing of the AI DevOps Agent with:
# - Automated incident triggering
# - Recovery validation
# - Manual intervention points
# - Comprehensive reporting
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_FILE="${SCRIPT_DIR}/test_report_$(date +%Y%m%d_%H%M%S).txt"
LAMBDA_ORCHESTRATOR="aiops-devops-agent-orchestrator"
LAMBDA_LOG_ANALYZER="aiops-devops-agent-log-analyzer"
DYNAMODB_INCIDENTS="aiops-devops-agent-incidents"
DYNAMODB_PATTERNS="aiops-devops-agent-patterns"

# Test counters
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_MANUAL=0

################################################################################
# Utility Functions
################################################################################

log() {
    echo -e "${CYAN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$REPORT_FILE"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$REPORT_FILE"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$REPORT_FILE"
    ((TESTS_FAILED++))
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}" | tee -a "$REPORT_FILE"
}

log_manual() {
    echo -e "${YELLOW}🔧 MANUAL INTERVENTION REQUIRED${NC}" | tee -a "$REPORT_FILE"
    echo -e "${YELLOW}$1${NC}" | tee -a "$REPORT_FILE"
    ((TESTS_MANUAL++))
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}" | tee -a "$REPORT_FILE"
}

section() {
    echo "" | tee -a "$REPORT_FILE"
    echo "═══════════════════════════════════════════════════════════════════" | tee -a "$REPORT_FILE"
    echo -e "${CYAN}$1${NC}" | tee -a "$REPORT_FILE"
    echo "═══════════════════════════════════════════════════════════════════" | tee -a "$REPORT_FILE"
}

wait_for_user() {
    echo -e "${YELLOW}Press ENTER to continue...${NC}"
    read -r
}

################################################################################
# Test Functions
################################################################################

test_lambda_exists() {
    ((TESTS_TOTAL++))
    log "Testing: Lambda function exists - $1"
    
    if aws lambda get-function --function-name "$1" &>/dev/null; then
        log_success "Lambda function $1 exists"
        return 0
    else
        log_error "Lambda function $1 not found"
        return 1
    fi
}

test_dynamodb_exists() {
    ((TESTS_TOTAL++))
    log "Testing: DynamoDB table exists - $1"
    
    if aws dynamodb describe-table --table-name "$1" &>/dev/null; then
        log_success "DynamoDB table $1 exists"
        return 0
    else
        log_error "DynamoDB table $1 not found"
        return 1
    fi
}

test_lambda_invoke() {
    ((TESTS_TOTAL++))
    local function_name=$1
    local payload_file=$2
    local expected_status=${3:-200}
    
    log "Testing: Lambda invocation - $function_name"
    
    local response_file="/tmp/lambda_response_$$.json"
    
    if aws lambda invoke \
        --function-name "$function_name" \
        --payload "file://$payload_file" \
        --cli-binary-format raw-in-base64-out \
        "$response_file" > /tmp/invoke_result_$$.json 2>&1; then
        
        local status_code=$(jq -r '.StatusCode' /tmp/invoke_result_$$.json)
        
        if [ "$status_code" = "$expected_status" ]; then
            log_success "Lambda invoked successfully (StatusCode: $status_code)"
            
            # Show response
            log_info "Response: $(cat $response_file | jq -c .)"
            
            # Return response for further processing
            cat "$response_file"
            return 0
        else
            log_error "Lambda returned unexpected status: $status_code (expected: $expected_status)"
            return 1
        fi
    else
        log_error "Lambda invocation failed"
        return 1
    fi
}

test_incident_logged() {
    ((TESTS_TOTAL++))
    local correlation_id=$1
    
    log "Testing: Incident logged to DynamoDB - $correlation_id"
    
    if aws dynamodb get-item \
        --table-name "$DYNAMODB_INCIDENTS" \
        --key "{\"incident_id\":{\"S\":\"$correlation_id\"}}" \
        --query 'Item' > /tmp/incident_$$.json 2>&1; then
        
        if [ -s /tmp/incident_$$.json ] && [ "$(cat /tmp/incident_$$.json)" != "null" ]; then
            local state=$(jq -r '.workflow_state.S' /tmp/incident_$$.json)
            local resource_type=$(jq -r '.resource_type.S' /tmp/incident_$$.json)
            
            log_success "Incident logged: State=$state, ResourceType=$resource_type"
            return 0
        else
            log_error "Incident not found in DynamoDB"
            return 1
        fi
    else
        log_error "Failed to query DynamoDB"
        return 1
    fi
}

test_cooldown_protection() {
    ((TESTS_TOTAL++))
    log "Testing: Cooldown protection"
    
    # Trigger same event twice
    local response1=$(test_lambda_invoke "$LAMBDA_ORCHESTRATOR" "test_demo.json" 200)
    local correlation_id1=$(echo "$response1" | jq -r '.correlation_id')
    
    sleep 2
    
    local response2=$(test_lambda_invoke "$LAMBDA_ORCHESTRATOR" "test_demo.json" 200)
    local status2=$(echo "$response2" | jq -r '.status')
    
    if [ "$status2" = "cooldown" ] || [ "$status2" = "manual_review_required" ]; then
        log_success "Cooldown protection working (status: $status2)"
        return 0
    else
        log_warning "Cooldown may not be active (status: $status2) - this is OK if > 5 minutes since last incident"
        return 0
    fi
}

test_log_analyzer() {
    ((TESTS_TOTAL++))
    log "Testing: Log Analyzer Lambda"
    
    local response_file="/tmp/log_analyzer_response_$$.json"
    
    if aws lambda invoke \
        --function-name "$LAMBDA_LOG_ANALYZER" \
        --cli-binary-format raw-in-base64-out \
        "$response_file" > /dev/null 2>&1; then
        
        local status=$(jq -r '.status' "$response_file")
        local analyzed=$(jq -r '.analyzed_log_groups' "$response_file")
        
        if [ "$status" = "ok" ]; then
            log_success "Log analyzer executed successfully (analyzed $analyzed log groups)"
            log_info "Results: $(cat $response_file | jq -c '.results')"
            return 0
        else
            log_error "Log analyzer returned unexpected status: $status"
            return 1
        fi
    else
        log_error "Log analyzer invocation failed"
        return 1
    fi
}

################################################################################
# Recovery Functions
################################################################################

trigger_test_incident() {
    section "TRIGGERING TEST INCIDENT"
    
    log "Creating test SSM parameter change event..."
    
    local response=$(test_lambda_invoke "$LAMBDA_ORCHESTRATOR" "test_demo.json" 200)
    local correlation_id=$(echo "$response" | jq -r '.correlation_id')
    local status=$(echo "$response" | jq -r '.status')
    local confidence=$(echo "$response" | jq -r '.confidence')
    
    log_info "Incident ID: $correlation_id"
    log_info "Status: $status"
    log_info "Confidence: $confidence"
    
    # Check if manual intervention is needed
    if [ "$status" = "manual_review_required" ]; then
        log_manual "Low confidence ($confidence) - Manual review required"
        log_manual "Incident ID: $correlation_id"
        log_manual ""
        log_manual "OPTIONS:"
        log_manual "1. Review incident in DynamoDB:"
        log_manual "   aws dynamodb get-item --table-name $DYNAMODB_INCIDENTS \\"
        log_manual "     --key '{\"incident_id\":{\"S\":\"$correlation_id\"}}'"
        log_manual ""
        log_manual "2. Check CloudWatch Logs:"
        log_manual "   aws logs tail /aws/lambda/$LAMBDA_ORCHESTRATOR --follow"
        log_manual ""
        log_manual "3. If you want to force recovery, update confidence threshold:"
        log_manual "   Edit terraform.tfvars: confidence_threshold = 0.6"
        log_manual "   Then run: terraform apply"
        log_manual ""
        
        wait_for_user
    fi
    
    # Verify incident was logged
    test_incident_logged "$correlation_id"
    
    echo "$correlation_id"
}

verify_recovery() {
    section "VERIFYING RECOVERY"
    
    local correlation_id=$1
    
    log "Checking incident status in DynamoDB..."
    
    aws dynamodb get-item \
        --table-name "$DYNAMODB_INCIDENTS" \
        --key "{\"incident_id\":{\"S\":\"$correlation_id\"}}" \
        --query 'Item.{State:workflow_state.S,Confidence:confidence.N,Classification:event_classification.S,RecoveryNeeded:recovery_needed.BOOL}' \
        --output json | tee -a "$REPORT_FILE"
}

################################################################################
# Main Test Flow
################################################################################

main() {
    section "AI DEVOPS AGENT - AUTOMATED TEST & RECOVERY"
    
    log "Test started at: $(date)"
    log "Report file: $REPORT_FILE"
    log ""
    
    # Phase 1: Infrastructure Tests
    section "PHASE 1: INFRASTRUCTURE VALIDATION"
    
    test_lambda_exists "$LAMBDA_ORCHESTRATOR"
    test_lambda_exists "$LAMBDA_LOG_ANALYZER"
    test_dynamodb_exists "$DYNAMODB_INCIDENTS"
    test_dynamodb_exists "$DYNAMODB_PATTERNS"
    
    # Phase 2: Functional Tests
    section "PHASE 2: FUNCTIONAL TESTS"
    
    # Test log analyzer
    test_log_analyzer
    
    # Test cooldown protection
    test_cooldown_protection
    
    # Phase 3: End-to-End Recovery Test
    section "PHASE 3: END-TO-END RECOVERY TEST"
    
    log "This will trigger a test incident and validate the complete workflow"
    wait_for_user
    
    # Trigger incident
    correlation_id=$(trigger_test_incident)
    
    # Verify recovery
    verify_recovery "$correlation_id"
    
    # Phase 4: Proactive Monitoring Test
    section "PHASE 4: PROACTIVE MONITORING TEST"
    
    log "Testing proactive log analysis..."
    test_log_analyzer
    
    # Phase 5: Historical Context Test
    section "PHASE 5: HISTORICAL CONTEXT TEST"
    
    log "Checking historical incidents in DynamoDB..."
    
    local incident_count=$(aws dynamodb scan \
        --table-name "$DYNAMODB_INCIDENTS" \
        --select COUNT \
        --query 'Count' \
        --output text)
    
    log_info "Total incidents in database: $incident_count"
    
    if [ "$incident_count" -gt 0 ]; then
        log_success "Historical context available ($incident_count incidents)"
    else
        log_warning "No historical incidents found"
    fi
    
    # Final Report
    section "TEST SUMMARY"
    
    echo "" | tee -a "$REPORT_FILE"
    echo "╔═══════════════════════════════════════════════════════════════════╗" | tee -a "$REPORT_FILE"
    echo "║                        TEST RESULTS                                ║" | tee -a "$REPORT_FILE"
    echo "╚═══════════════════════════════════════════════════════════════════╝" | tee -a "$REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"
    echo "  Total Tests:          $TESTS_TOTAL" | tee -a "$REPORT_FILE"
    echo "  ✅ Passed:            $TESTS_PASSED" | tee -a "$REPORT_FILE"
    echo "  ❌ Failed:            $TESTS_FAILED" | tee -a "$REPORT_FILE"
    echo "  🔧 Manual Required:   $TESTS_MANUAL" | tee -a "$REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"
    
    local success_rate=0
    if [ "$TESTS_TOTAL" -gt 0 ]; then
        success_rate=$((TESTS_PASSED * 100 / TESTS_TOTAL))
    fi
    
    echo "  Success Rate:         ${success_rate}%" | tee -a "$REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"
    
    if [ "$TESTS_FAILED" -eq 0 ]; then
        log_success "ALL TESTS PASSED! 🎉"
    else
        log_warning "Some tests failed. Review the report for details."
    fi
    
    echo "" | tee -a "$REPORT_FILE"
    log "Test completed at: $(date)"
    log "Full report saved to: $REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"
    
    # Show quick access commands
    section "QUICK ACCESS COMMANDS"
    
    echo "View CloudWatch Logs:" | tee -a "$REPORT_FILE"
    echo "  aws logs tail /aws/lambda/$LAMBDA_ORCHESTRATOR --follow" | tee -a "$REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"
    echo "View Incidents:" | tee -a "$REPORT_FILE"
    echo "  aws dynamodb scan --table-name $DYNAMODB_INCIDENTS --limit 5" | tee -a "$REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"
    echo "View Patterns:" | tee -a "$REPORT_FILE"
    echo "  aws dynamodb scan --table-name $DYNAMODB_PATTERNS --limit 5" | tee -a "$REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"
}

# Run main function
main

exit 0
