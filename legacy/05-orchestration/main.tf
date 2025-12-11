provider "aws" {
  region = var.aws_region
}

# 1. Orchestrator Lambda Role
resource "aws_iam_role" "orchestrator_role" {
  name = "${var.project_name}-orchestrator-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "orchestrator_policy" {
  role = aws_iam_role.orchestrator_role.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "codebuild:StartBuild",
          "sns:Publish",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      # Phase 1: DynamoDB permissions for incident tracking
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          var.enable_incident_tracking ? aws_dynamodb_table.aiops_incidents[0].arn : "",
          var.enable_incident_tracking ? "${aws_dynamodb_table.aiops_incidents[0].arn}/index/*" : "",
          var.enable_pattern_recognition ? aws_dynamodb_table.aiops_patterns[0].arn : "",
          var.enable_pattern_recognition ? "${aws_dynamodb_table.aiops_patterns[0].arn}/index/*" : ""
        ]
      },
      # CloudWatch Metrics for monitoring
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

# 2. Orchestrator Lambda
data "archive_file" "orchestrator_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/orchestrator.zip"
}

resource "aws_lambda_function" "orchestrator" {
  function_name    = "${var.project_name}-orchestrator"
  filename         = data.archive_file.orchestrator_zip.output_path
  role             = aws_iam_role.orchestrator_role.arn
  handler          = var.enable_enhanced_lambda ? "index_enhanced.handler" : "index.handler"
  runtime          = "python3.11"
  source_code_hash = data.archive_file.orchestrator_zip.output_base64sha256
  timeout          = 60

  environment {
    variables = merge(
      {
        SNS_TOPIC_ARN = var.sns_topic_arn
      },
      # Phase 1: Incident tracking
      var.enable_incident_tracking ? {
        INCIDENT_TABLE = aws_dynamodb_table.aiops_incidents[0].name
      } : {},
      # Phase 1: Pattern recognition
      var.enable_pattern_recognition ? {
        PATTERNS_TABLE = aws_dynamodb_table.aiops_patterns[0].name
      } : {},
      # Phase 2: Enhanced features
      var.enable_enhanced_lambda ? {
        COOLDOWN_MINUTES     = tostring(var.cooldown_minutes)
        CONFIDENCE_THRESHOLD = tostring(var.confidence_threshold)
      } : {}
    )
  }

  tags = {
    Name        = "AIOps Orchestrator Lambda"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# 3. EventBridge Rule (Trigger on CloudTrail Error/Delete)
resource "aws_cloudwatch_event_rule" "infra_failure" {
  name        = "${var.project_name}-failure-rule"
  description = "Detects infrastructure failures or deletions"

  event_pattern = <<EOF
{
  "source": ["aws.ec2", "aws.ssm", "aws.lambda", "aws.dynamodb", "aws.s3"],
  "detail-type": ["AWS API Call via CloudTrail"],
  "detail": {
    "eventName": [
      "TerminateInstances",
      "StopInstances",
      "PutParameter",
      "DeleteParameter",
      "DeleteFunction",
      "UpdateFunctionConfiguration",
      "DeleteTable",
      "DeleteBucket",
      "PutBucketPolicy"
    ]
  }
}
EOF
}

resource "aws_cloudwatch_event_target" "target" {
  rule      = aws_cloudwatch_event_rule.infra_failure.name
  target_id = "SendToOrchestrator"
  arn       = aws_lambda_function.orchestrator.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.infra_failure.arn
}

# 4. Real-time EventBridge Rules (No CloudTrail delay - < 1 second detection)

# Real-time EC2 State Changes
resource "aws_cloudwatch_event_rule" "ec2_state_change" {
  name        = "${var.project_name}-ec2-state-realtime"
  description = "Capture EC2 instance state changes in real-time (< 1 sec)"

  event_pattern = <<EOF
{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Instance State-change Notification"],
  "detail": {
    "state": ["terminated", "stopped", "stopping"]
  }
}
EOF
}

resource "aws_cloudwatch_event_target" "ec2_state_to_orchestrator" {
  rule      = aws_cloudwatch_event_rule.ec2_state_change.name
  target_id = "SendToOrchestratorRealtime"
  arn       = aws_lambda_function.orchestrator.arn
}

resource "aws_lambda_permission" "allow_eventbridge_ec2_state" {
  statement_id  = "AllowExecutionFromEventBridgeEC2State"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ec2_state_change.arn
}
