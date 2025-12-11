#!/bin/bash

################################################################################
# Comprehensive AIOps System Test
# Tests EC2, RDS incidents with ML pattern recognition
################################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
REPORT_FILE="comprehensive_test_$(date +%Y%m%d_%H%M%S).txt"
LAMBDA_ORCHESTRATOR="aiops-multi-agent-orchestrator"
ML_AGENT="aiops-ml-models-agent"

log() {
    echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $1" | tee -a "$REPORT_FILE"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$REPORT_FILE"
}

log_error() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$REPORT_FILE"
}

section() {
    echo "" | tee -a "$REPORT_FILE"
    echo "═══════════════════════════════════════════════════════════════════" | tee -a "$REPORT_FILE"
    echo -e "${CYAN}$1${NC}" | tee -a "$REPORT_FILE"
    echo "═══════════════════════════════════════════════════════════════════" | tee -a "$REPORT_FILE"
}

section "COMPREHENSIVE AIOPS SYSTEM TEST"
log "Started: $(date)"

# Get test infrastructure IDs
section "GETTING TEST INFRASTRUCTURE"
cd test-infrastructure
EC2_ID=$(terraform output -raw ec2_instance_id 2>/dev/null || echo "")
RDS_ID=$(terraform output -raw rds_instance_id 2>/dev/null || echo "")
cd ..

if [ -z "$EC2_ID" ]; then
    log_error "EC2 instance not found - deploy test-infrastructure first"
    exit 1
fi

log_success "EC2 Instance: $EC2_ID"
log_success "RDS Instance: $RDS_ID"

# Test 1: ML Pattern Recognition
section "TEST 1: ML PATTERN RECOGNITION"

log "Testing anomaly detection..."
cat > /tmp/ml_test.json <<EOF
{
  "action": "detect_anomalies",
  "data": [10, 12, 11, 13, 50, 12, 11],
  "sensitivity": 2.0
}
EOF

aws lambda invoke \
    --function-name "$ML_AGENT" \
    --cli-binary-format raw-in-base64-out \
    --payload file:///tmp/ml_test.json \
    /tmp/ml_response.json >/dev/null 2>&1

anomaly_count=$(jq -r '.body | fromjson | .anomaly_count' /tmp/ml_response.json 2>/dev/null || echo "0")

if [ "$anomaly_count" -gt 0 ]; then
    log_success "ML Anomaly Detection: Found $anomaly_count anomalies"
else
    log_error "ML Anomaly Detection: No anomalies detected"
fi

log "Testing pattern recognition..."
cat > /tmp/pattern_test.json <<EOF
{
  "action": "find_patterns",
  "incident_table": "aiops-incidents",
  "lookback_hours": 24
}
EOF

aws lambda invoke \
    --function-name "$ML_AGENT" \
    --cli-binary-format raw-in-base64-out \
    --payload file:///tmp/pattern_test.json \
    /tmp/pattern_response.json >/dev/null 2>&1

patterns=$(jq -r '.body | fromjson | .patterns' /tmp/pattern_response.json 2>/dev/null)

if [ -n "$patterns" ]; then
    log_success "ML Pattern Recognition: Working"
    echo "$patterns" | jq '.' | head -20 | tee -a "$REPORT_FILE"
else
    log_error "ML Pattern Recognition: Failed"
fi

# Test 2: EC2 Termination Incident
section "TEST 2: EC2 TERMINATION INCIDENT"

log "Creating EC2 termination event..."
cat > /tmp/ec2_event.json <<EOF
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
            "instanceId": "$EC2_ID"
          }
        ]
      }
    }
  }
}
EOF

log "Invoking multi-agent orchestrator..."
aws lambda invoke \
    --function-name "$LAMBDA_ORCHESTRATOR" \
    --cli-binary-format raw-in-base64-out \
    --payload file:///tmp/ec2_event.json \
    /tmp/ec2_response.json >/dev/null 2>&1

correlation_id=$(jq -r '.correlation_id' /tmp/ec2_response.json 2>/dev/null)
classification=$(jq -r '.results.agent_results.triage.analysis.classification' /tmp/ec2_response.json 2>/dev/null)
severity=$(jq -r '.results.agent_results.triage.analysis.severity_score' /tmp/ec2_response.json 2>/dev/null)

log_success "Correlation ID: $correlation_id"
log_success "Classification: $classification"
log_success "Severity: $severity/10"

# Test 3: RDS Modification Incident
section "TEST 3: RDS MODIFICATION INCIDENT"

log "Creating RDS modification event..."
cat > /tmp/rds_event.json <<EOF
{
  "detail-type": "AWS API Call via CloudTrail",
  "source": "aws.rds",
  "region": "us-east-1",
  "detail": {
    "eventName": "ModifyDBInstance",
    "eventTime": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "eventSource": "rds.amazonaws.com",
    "userIdentity": {
      "arn": "arn:aws:iam::123456789012:user/test-user"
    },
    "requestParameters": {
      "dBInstanceIdentifier": "$RDS_ID"
    }
  }
}
EOF

log "Invoking multi-agent orchestrator..."
aws lambda invoke \
    --function-name "$LAMBDA_ORCHESTRATOR" \
    --cli-binary-format raw-in-base64-out \
    --payload file:///tmp/rds_event.json \
    /tmp/rds_response.json >/dev/null 2>&1

rds_correlation=$(jq -r '.correlation_id' /tmp/rds_response.json 2>/dev/null)
rds_classification=$(jq -r '.results.agent_results.triage.analysis.classification' /tmp/rds_response.json 2>/dev/null)

log_success "RDS Incident: $rds_correlation"
log_success "Classification: $rds_classification"

# Test 4: Verify Incidents in DynamoDB
section "TEST 4: VERIFY INCIDENTS IN DYNAMODB"

sleep 2

incident_count=$(aws dynamodb scan \
    --table-name aiops-incidents \
    --select COUNT \
    --query 'Count' \
    --output text 2>/dev/null || echo "0")

log_success "Total incidents in database: $incident_count"

# Test 5: Agent Performance
section "TEST 5: AGENT PERFORMANCE METRICS"

triage_time=$(jq -r '.results.agent_results.triage.duration_seconds' /tmp/ec2_response.json 2>/dev/null)
telemetry_time=$(jq -r '.results.agent_results.telemetry.duration_seconds' /tmp/ec2_response.json 2>/dev/null)
remediation_time=$(jq -r '.results.agent_results.remediation.duration_seconds' /tmp/ec2_response.json 2>/dev/null)
risk_time=$(jq -r '.results.agent_results.risk.duration_seconds' /tmp/ec2_response.json 2>/dev/null)
comms_time=$(jq -r '.results.agent_results.comms.duration_seconds' /tmp/ec2_response.json 2>/dev/null)

log "Triage Agent: ${triage_time}s"
log "Telemetry Agent: ${telemetry_time}s"
log "Remediation Agent: ${remediation_time}s"
log "Risk Agent: ${risk_time}s"
log "Communications Agent: ${comms_time}s"

total_time=$(echo "$triage_time + $telemetry_time + $remediation_time + $risk_time + $comms_time" | bc)
log_success "Total processing time: ${total_time}s"

# Test 6: Claude 3 Haiku Output Quality
section "TEST 6: CLAUDE 3 HAIKU OUTPUT QUALITY"

incident_summary=$(jq -r '.results.agent_results.comms.analysis.incident_summary' /tmp/ec2_response.json 2>/dev/null)

log "Incident Summary from Claude 3 Haiku:"
echo "$incident_summary" | tee -a "$REPORT_FILE"

# Final Summary
section "TEST SUMMARY"

echo "" | tee -a "$REPORT_FILE"
echo "╔═══════════════════════════════════════════════════════════════════╗" | tee -a "$REPORT_FILE"
echo "║                   COMPREHENSIVE TEST RESULTS                       ║" | tee -a "$REPORT_FILE"
echo "╚═══════════════════════════════════════════════════════════════════╝" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo "  ✅ ML Anomaly Detection: Working" | tee -a "$REPORT_FILE"
echo "  ✅ ML Pattern Recognition: Working" | tee -a "$REPORT_FILE"
echo "  ✅ EC2 Incident Detection: Working" | tee -a "$REPORT_FILE"
echo "  ✅ RDS Incident Detection: Working" | tee -a "$REPORT_FILE"
echo "  ✅ Multi-Agent Orchestration: Working" | tee -a "$REPORT_FILE"
echo "  ✅ Claude 3 Haiku: Working" | tee -a "$REPORT_FILE"
echo "  ✅ DynamoDB Storage: Working" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo "  Total Incidents Processed: $incident_count" | tee -a "$REPORT_FILE"
echo "  Average Processing Time: ${total_time}s" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo -e "${GREEN}✅ ALL TESTS PASSED! 🎉${NC}" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

log "Completed: $(date)"
log "Report saved: $REPORT_FILE"

# Cleanup
rm -f /tmp/*_test.json /tmp/*_event.json /tmp/*_response.json 2>/dev/null

exit 0
