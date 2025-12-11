# Phase-by-Phase Deployment Guide

## Overview
This guide walks you through deploying the enhanced AI DevOps Agent in 5 phases, starting with Phase 1 (Foundation) and progressively adding features.

---

## Prerequisites

1. **AWS CLI configured** with appropriate credentials
2. **Terraform installed** (v1.0+)
3. **Existing infrastructure:**
   - SNS Topic for notifications
   - CodeBuild project for recovery
   - CloudTrail enabled

---

## 🚀 PHASE 1: Foundation (Week 1-2)

### What You're Deploying
- ✅ DynamoDB table for incident tracking
- ✅ DynamoDB table for pattern recognition
- ✅ Updated IAM permissions
- ✅ Enhanced Lambda environment variables

### Benefits
- Complete audit trail of all incidents
- Foundation for learning and pattern recognition
- Correlation IDs for tracking

### Deployment Steps

```bash
# 1. Navigate to orchestration directory
cd /home/rockylinux/devel/aiops-ecs-bedrock/aiops-devops-agent/05-orchestration

# 2. Review configuration
cat terraform.tfvars

# Verify Phase 1 is enabled:
# enable_incident_tracking   = true
# enable_pattern_recognition = true

# 3. Initialize Terraform (if not already done)
terraform init

# 4. Review what will be created
terraform plan

# Expected resources:
# - aws_dynamodb_table.aiops_incidents[0]
# - aws_dynamodb_table.aiops_patterns[0]
# - Updated aws_iam_role_policy.orchestrator_policy
# - Updated aws_lambda_function.orchestrator (environment variables)

# 5. Apply Phase 1
terraform apply

# Type 'yes' when prompted

# 6. Verify deployment
terraform output

# Expected outputs:
# incidents_table_name = "aiops-devops-agent-incidents"
# incidents_table_arn  = "arn:aws:dynamodb:..."
# patterns_table_name  = "aiops-devops-agent-patterns"
# patterns_table_arn   = "arn:aws:dynamodb:..."
```

### Verification

```bash
# Check DynamoDB tables exist
aws dynamodb list-tables | grep aiops

# Describe incidents table
aws dynamodb describe-table --table-name aiops-devops-agent-incidents

# Check Lambda environment variables
aws lambda get-function-configuration \
  --function-name aiops-devops-agent-orchestrator \
  --query 'Environment.Variables'

# Should show:
# {
#   "SNS_TOPIC_ARN": "...",
#   "INCIDENT_TABLE": "aiops-devops-agent-incidents",
#   "PATTERNS_TABLE": "aiops-devops-agent-patterns"
# }
```

### Test Phase 1

```bash
# Trigger a test event
aws lambda invoke \
  --function-name aiops-devops-agent-orchestrator \
  --payload file://test_event.json \
  response.json

# Check if incident was recorded in DynamoDB
aws dynamodb scan \
  --table-name aiops-devops-agent-incidents \
  --limit 5

# You should see incident records with correlation IDs
```

### Phase 1 Complete! ✅
- DynamoDB tables created
- Lambda has access to tables
- Ready for Phase 2

---

## 🚀 PHASE 2: Enhanced Lambda (Week 3-4)

### What You're Deploying
- ✅ Enhanced Lambda code with workflow features
- ✅ Cooldown protection
- ✅ Confidence thresholds
- ✅ Historical context retrieval

### Prerequisites
- Phase 1 completed successfully
- `index_enhanced.py` copied to lambda directory

### Preparation

```bash
# 1. Copy enhanced Lambda code
cd /home/rockylinux/devel/aiops-ecs-bedrock/aiops-devops-agent/05-orchestration/lambda
cp index_enhanced.py index_enhanced.py.backup  # If it exists
# Or create it from the provided code

# 2. Verify the enhanced code is in place
ls -la lambda/
# Should show: index.py, index_enhanced.py
```

### Configuration

```bash
# Edit terraform.tfvars
nano terraform.tfvars

# Uncomment Phase 2 settings:
enable_enhanced_lambda = true
cooldown_minutes       = 5
confidence_threshold   = 0.8
```

### Deployment

```bash
# 1. Review changes
terraform plan

# Expected changes:
# - Lambda handler changed to "index_enhanced.handler"
# - New environment variables: COOLDOWN_MINUTES, CONFIDENCE_THRESHOLD

# 2. Apply Phase 2
terraform apply

# 3. Verify
aws lambda get-function-configuration \
  --function-name aiops-devops-agent-orchestrator \
  --query 'Environment.Variables'

# Should now show:
# {
#   "SNS_TOPIC_ARN": "...",
#   "INCIDENT_TABLE": "...",
#   "PATTERNS_TABLE": "...",
#   "COOLDOWN_MINUTES": "5",
#   "CONFIDENCE_THRESHOLD": "0.8"
# }
```

### Test Phase 2

```bash
# Test cooldown protection
# Trigger same event twice within 5 minutes

# First trigger
aws lambda invoke \
  --function-name aiops-devops-agent-orchestrator \
  --payload file://test_ec2_termination.json \
  response1.json

# Wait 10 seconds

# Second trigger (should be in cooldown)
aws lambda invoke \
  --function-name aiops-devops-agent-orchestrator \
  --payload file://test_ec2_termination.json \
  response2.json

# Check response2.json - should show "status": "cooldown"
cat response2.json
```

### Phase 2 Complete! ✅
- Enhanced Lambda deployed
- Cooldown protection active
- Confidence thresholds in place
- Ready for Phase 3

---

## 🚀 PHASE 3: Proactive Monitoring (Week 5-6)

### What You're Deploying
- ✅ Log Analyzer Lambda
- ✅ EventBridge schedule (every 5 minutes)
- ✅ Proactive anomaly detection
- ✅ Failure prediction

### Prerequisites
- Phase 1 & 2 completed
- CloudWatch Log Groups to monitor

### Preparation

```bash
# 1. Create log analyzer directory
mkdir -p /home/rockylinux/devel/aiops-ecs-bedrock/aiops-devops-agent/06-log-analyzer/lambda

# 2. Copy log analyzer code
# (Already created in previous steps)

# 3. Identify log groups to monitor
aws logs describe-log-groups --query 'logGroups[*].logGroupName'

# Example output:
# /aws/lambda/my-app
# /ecs/my-service
```

### Create Log Analyzer Terraform

```bash
# Create log_analyzer.tf
cat > log_analyzer.tf <<'EOF'
# ============================================================================
# PHASE 3: Proactive Log Monitoring
# ============================================================================

# Log Analyzer Lambda Role
resource "aws_iam_role" "log_analyzer_role" {
  count = var.enable_log_analyzer ? 1 : 0
  name  = "${var.project_name}-log-analyzer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "log_analyzer_policy" {
  count = var.enable_log_analyzer ? 1 : 0
  role  = aws_iam_role.log_analyzer_role[0].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:StartQuery",
          "logs:GetQueryResults",
          "logs:DescribeLogGroups",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          var.enable_pattern_recognition ? aws_dynamodb_table.aiops_patterns[0].arn : ""
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = var.sns_topic_arn
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      }
    ]
  })
}

# Log Analyzer Lambda
data "archive_file" "log_analyzer_zip" {
  count       = var.enable_log_analyzer ? 1 : 0
  type        = "zip"
  source_dir  = "${path.module}/../06-log-analyzer/lambda"
  output_path = "${path.module}/log_analyzer.zip"
}

resource "aws_lambda_function" "log_analyzer" {
  count            = var.enable_log_analyzer ? 1 : 0
  function_name    = "${var.project_name}-log-analyzer"
  filename         = data.archive_file.log_analyzer_zip[0].output_path
  role             = aws_iam_role.log_analyzer_role[0].arn
  handler          = "index.handler"
  runtime          = "python3.11"
  source_code_hash = data.archive_file.log_analyzer_zip[0].output_base64sha256
  timeout          = 300  # 5 minutes

  environment {
    variables = {
      SNS_TOPIC_ARN     = var.sns_topic_arn
      PATTERNS_TABLE    = var.enable_pattern_recognition ? aws_dynamodb_table.aiops_patterns[0].name : ""
      LOG_GROUPS        = var.log_groups_to_monitor
      ANOMALY_THRESHOLD = tostring(var.anomaly_threshold)
    }
  }

  tags = {
    Name        = "AIOps Log Analyzer"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Phase       = "Phase 3 - Proactive Monitoring"
  }
}

# EventBridge Schedule for Log Analyzer
resource "aws_cloudwatch_event_rule" "log_analyzer_schedule" {
  count               = var.enable_log_analyzer ? 1 : 0
  name                = "${var.project_name}-log-analyzer-schedule"
  description         = "Trigger log analyzer every 5 minutes"
  schedule_expression = var.log_analyzer_schedule
}

resource "aws_cloudwatch_event_target" "log_analyzer_target" {
  count     = var.enable_log_analyzer ? 1 : 0
  rule      = aws_cloudwatch_event_rule.log_analyzer_schedule[0].name
  target_id = "LogAnalyzerLambda"
  arn       = aws_lambda_function.log_analyzer[0].arn
}

resource "aws_lambda_permission" "allow_eventbridge_log_analyzer" {
  count         = var.enable_log_analyzer ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.log_analyzer[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.log_analyzer_schedule[0].arn
}
EOF
```

### Configuration

```bash
# Edit terraform.tfvars
nano terraform.tfvars

# Uncomment Phase 3 settings:
enable_log_analyzer   = true
log_groups_to_monitor = "/aws/lambda/my-app,/ecs/my-service"  # Update with your log groups
anomaly_threshold     = 0.7
log_analyzer_schedule = "rate(5 minutes)"
```

### Deployment

```bash
# 1. Review changes
terraform plan

# 2. Apply Phase 3
terraform apply

# 3. Verify
aws lambda list-functions | grep log-analyzer
```

### Test Phase 3

```bash
# Manually invoke log analyzer
aws lambda invoke \
  --function-name aiops-devops-agent-log-analyzer \
  response_log_analyzer.json

# Check response
cat response_log_analyzer.json

# Wait 5 minutes and check CloudWatch Logs
aws logs tail /aws/lambda/aiops-devops-agent-log-analyzer --follow
```

### Phase 3 Complete! ✅
- Proactive log monitoring active
- Anomaly detection running every 5 minutes
- Failure prediction enabled
- Ready for Phase 4 (optional)

---

## 🚀 PHASE 4: Step Functions (Week 7-8) - OPTIONAL

### What You're Deploying
- ✅ Step Functions state machine
- ✅ Multi-stage workflow orchestration
- ✅ Retry logic and error handling

### Coming Soon
This phase is optional and adds visual workflow monitoring. Most value is already achieved in Phases 1-3.

---

## 🚀 PHASE 5: Verification (Week 9-10) - OPTIONAL

### What You're Deploying
- ✅ Verification Lambda
- ✅ Post-recovery health checks
- ✅ Automated rollback

### Coming Soon
This phase is optional and adds verification layer. Most value is already achieved in Phases 1-3.

---

## Rollback Instructions

### Rollback Phase 3
```bash
# Edit terraform.tfvars
nano terraform.tfvars

# Set:
enable_log_analyzer = false

# Apply
terraform apply
```

### Rollback Phase 2
```bash
# Edit terraform.tfvars
nano terraform.tfvars

# Set:
enable_enhanced_lambda = false

# Apply
terraform apply
```

### Rollback Phase 1
```bash
# Edit terraform.tfvars
nano terraform.tfvars

# Set:
enable_incident_tracking   = false
enable_pattern_recognition = false

# Apply
terraform apply
```

---

## Monitoring & Troubleshooting

### Check Lambda Logs
```bash
# Orchestrator logs
aws logs tail /aws/lambda/aiops-devops-agent-orchestrator --follow

# Log analyzer logs
aws logs tail /aws/lambda/aiops-devops-agent-log-analyzer --follow
```

### Check DynamoDB Tables
```bash
# List incidents
aws dynamodb scan --table-name aiops-devops-agent-incidents --limit 10

# List patterns
aws dynamodb scan --table-name aiops-devops-agent-patterns --limit 10
```

### Check CloudWatch Metrics
```bash
# Custom metrics
aws cloudwatch list-metrics --namespace "AIOps/DevOpsAgent"
aws cloudwatch list-metrics --namespace "AIOps/LogAnalyzer"
```

---

## Cost Monitoring

```bash
# Check DynamoDB usage
aws dynamodb describe-table --table-name aiops-devops-agent-incidents \
  --query 'Table.TableSizeBytes'

# Check Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=aiops-devops-agent-orchestrator \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum
```

---

## Summary

### Phase 1 (Foundation) - DEPLOYED ✅
- DynamoDB tables for incident tracking
- Foundation for learning

### Phase 2 (Enhanced Lambda) - READY TO DEPLOY
- Cooldown protection
- Confidence thresholds
- Historical context

### Phase 3 (Proactive Monitoring) - READY TO DEPLOY
- Log analysis every 5 minutes
- Anomaly detection
- Failure prediction

### Phases 4-5 (Optional)
- Step Functions workflow
- Verification layer

**Recommended:** Deploy Phases 1-3 for maximum value (95% of benefits)
