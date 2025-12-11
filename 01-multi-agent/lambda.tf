# Package Lambda function
data "archive_file" "multi_agent_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/multi_agent.zip"
}

# Multi-Agent Orchestrator Lambda
resource "aws_lambda_function" "multi_agent_orchestrator" {
  filename         = data.archive_file.multi_agent_lambda.output_path
  function_name    = "${var.project_name}-orchestrator"
  role             = aws_iam_role.multi_agent_lambda.arn
  handler          = "index.handler"
  source_code_hash = data.archive_file.multi_agent_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 300 # 5 minutes
  memory_size      = 512

  environment {
    variables = {
      INCIDENT_TABLE    = var.incident_table_name
      SNS_TOPIC_ARN     = var.sns_topic_arn
      CODEBUILD_PROJECT = var.codebuild_project
      DEFAULT_EMAIL     = var.default_email
      SENDER_EMAIL      = var.sender_email
    }
  }

  tags = {
    Name        = "${var.project_name}-orchestrator"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "multi_agent_lambda" {
  name              = "/aws/lambda/${aws_lambda_function.multi_agent_orchestrator.function_name}"
  retention_in_days = 7

  tags = {
    Name        = "${var.project_name}-logs"
    Environment = "production"
  }
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.multi_agent_orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cloudtrail_events.arn
}
