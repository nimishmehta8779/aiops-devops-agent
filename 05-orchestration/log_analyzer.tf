# ============================================================================
# PHASE 3: Proactive Log Monitoring
# ============================================================================
# This creates a Lambda that analyzes CloudWatch Logs to predict failures

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

  tags = {
    Name        = "AIOps Log Analyzer Role"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Phase       = "Phase 3 - Proactive Monitoring"
  }
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
        Resource = var.enable_pattern_recognition ? [
          aws_dynamodb_table.aiops_patterns[0].arn
        ] : []
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
  timeout          = 300 # 5 minutes

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
  description         = "Trigger log analyzer every 5 minutes for proactive monitoring"
  schedule_expression = var.log_analyzer_schedule

  tags = {
    Name        = "AIOps Log Analyzer Schedule"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Phase       = "Phase 3 - Proactive Monitoring"
  }
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

# Outputs for Phase 3
output "log_analyzer_function_name" {
  description = "Name of the log analyzer Lambda function"
  value       = var.enable_log_analyzer ? aws_lambda_function.log_analyzer[0].function_name : null
}

output "log_analyzer_function_arn" {
  description = "ARN of the log analyzer Lambda function"
  value       = var.enable_log_analyzer ? aws_lambda_function.log_analyzer[0].arn : null
}
