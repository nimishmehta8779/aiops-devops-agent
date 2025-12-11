#!/bin/bash
# Test script for multi-agent AIOps system

set -e

echo "========================================="
echo "Multi-Agent AIOps System Test"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
LAMBDA_NAME="aiops-multi-agent-orchestrator"
LOG_GROUP="/aws/lambda/${LAMBDA_NAME}"
INCIDENT_TABLE="aiops-incidents"

# Test 1: Verify Lambda exists
echo -e "${YELLOW}Test 1: Verifying Lambda function exists...${NC}"
if aws lambda get-function --function-name "$LAMBDA_NAME" &>/dev/null; then
    echo -e "${GREEN}✓ Lambda function exists${NC}"
else
    echo -e "${RED}✗ Lambda function not found${NC}"
    exit 1
fi
echo ""

# Test 2: Verify DynamoDB table exists
echo -e "${YELLOW}Test 2: Verifying DynamoDB table exists...${NC}"
if aws dynamodb describe-table --table-name "$INCIDENT_TABLE" &>/dev/null; then
    echo -e "${GREEN}✓ DynamoDB table exists${NC}"
else
    echo -e "${RED}✗ DynamoDB table not found${NC}"
    exit 1
fi
echo ""

# Test 3: Verify EventBridge rules
echo -e "${YELLOW}Test 3: Verifying EventBridge rules...${NC}"
RULES=$(aws events list-rules --name-prefix "aiops-multi-agent" --query 'Rules[*].Name' --output text)
if [ -n "$RULES" ]; then
    echo -e "${GREEN}✓ EventBridge rules found: $RULES${NC}"
else
    echo -e "${RED}✗ No EventBridge rules found${NC}"
    exit 1
fi
echo ""

# Test 4: Test Lambda invocation with sample event
echo -e "${YELLOW}Test 4: Testing Lambda invocation...${NC}"

# Create test event
TEST_EVENT=$(cat <<EOF
{
  "version": "0",
  "id": "test-event-$(date +%s)",
  "detail-type": "AWS API Call via CloudTrail",
  "source": "aws.ec2",
  "account": "$(aws sts get-caller-identity --query Account --output text)",
  "time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "region": "us-east-1",
  "detail": {
    "eventVersion": "1.08",
    "eventTime": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "eventName": "TerminateInstances",
    "eventSource": "ec2.amazonaws.com",
    "userIdentity": {
      "type": "IAMUser",
      "arn": "arn:aws:iam::123456789012:user/test-user"
    },
    "requestParameters": {
      "instancesSet": {
        "items": [
          {
            "instanceId": "i-test123456"
          }
        ]
      }
    }
  }
}
EOF
)

# Invoke Lambda
echo "Invoking Lambda with test event..."
RESPONSE=$(aws lambda invoke \
    --function-name "$LAMBDA_NAME" \
    --payload "$TEST_EVENT" \
    --cli-binary-format raw-in-base64-out \
    /tmp/lambda-response.json 2>&1)

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Lambda invoked successfully${NC}"
    echo "Response:"
    cat /tmp/lambda-response.json | jq '.'
    
    # Extract correlation ID
    CORRELATION_ID=$(cat /tmp/lambda-response.json | jq -r '.correlation_id // empty')
    if [ -n "$CORRELATION_ID" ]; then
        echo -e "${GREEN}✓ Correlation ID: $CORRELATION_ID${NC}"
    fi
else
    echo -e "${RED}✗ Lambda invocation failed${NC}"
    echo "$RESPONSE"
    exit 1
fi
echo ""

# Test 5: Check CloudWatch Logs
echo -e "${YELLOW}Test 5: Checking CloudWatch Logs...${NC}"
echo "Waiting 5 seconds for logs to appear..."
sleep 5

RECENT_LOGS=$(aws logs tail "$LOG_GROUP" --since 1m --format short 2>/dev/null | head -20)
if [ -n "$RECENT_LOGS" ]; then
    echo -e "${GREEN}✓ CloudWatch logs found${NC}"
    echo "Recent logs:"
    echo "$RECENT_LOGS"
else
    echo -e "${YELLOW}⚠ No recent logs found (this may be normal)${NC}"
fi
echo ""

# Test 6: Verify incident in DynamoDB
if [ -n "$CORRELATION_ID" ]; then
    echo -e "${YELLOW}Test 6: Verifying incident in DynamoDB...${NC}"
    
    INCIDENT=$(aws dynamodb get-item \
        --table-name "$INCIDENT_TABLE" \
        --key "{\"incident_id\": {\"S\": \"$CORRELATION_ID\"}}" \
        --output json 2>/dev/null)
    
    if [ -n "$INCIDENT" ]; then
        echo -e "${GREEN}✓ Incident record found in DynamoDB${NC}"
        echo "Incident details:"
        echo "$INCIDENT" | jq '.Item | {
            incident_id: .incident_id.S,
            resource_type: .resource_type.S,
            resource_id: .resource_id.S,
            workflow_state: .workflow_state.S,
            created_at: .created_at.S
        }'
    else
        echo -e "${YELLOW}⚠ Incident record not found (may still be processing)${NC}"
    fi
    echo ""
fi

# Test 7: Check CloudWatch Metrics
echo -e "${YELLOW}Test 7: Checking CloudWatch Metrics...${NC}"
METRICS=$(aws cloudwatch list-metrics \
    --namespace "AIOps/Triage" \
    --query 'Metrics[*].MetricName' \
    --output text 2>/dev/null)

if [ -n "$METRICS" ]; then
    echo -e "${GREEN}✓ CloudWatch metrics found: $METRICS${NC}"
else
    echo -e "${YELLOW}⚠ No CloudWatch metrics found yet${NC}"
fi
echo ""

# Summary
echo "========================================="
echo -e "${GREEN}Multi-Agent System Test Complete!${NC}"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Review CloudWatch Logs for detailed agent execution"
echo "2. Check DynamoDB for incident records"
echo "3. Monitor CloudWatch Metrics for agent performance"
echo "4. Test email notifications (if SES is configured)"
echo ""
echo "To view logs in real-time:"
echo "  aws logs tail $LOG_GROUP --follow"
echo ""
echo "To query incidents:"
echo "  aws dynamodb scan --table-name $INCIDENT_TABLE --max-items 5"
