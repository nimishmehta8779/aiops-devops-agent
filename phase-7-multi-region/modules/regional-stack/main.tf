variable "aws_region" {
  description = "AWS region for this deployment"
  type        = string
}

variable "central_region" {
  description = "Region where central AIOps logic resides"
  type        = string
  default     = "us-east-1"
}

variable "central_event_bus_arn" {
  description = "ARN of the central event bus (only needed for satellite regions)"
  type        = string
  default     = ""
}

variable "is_central" {
  description = "Whether this is the central region"
  type        = bool
  default     = false
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "aiops-multi-region"
}

# Regional Orchestrator Lambda
data "archive_file" "regional_lambda" {
  type        = "zip"
  source_file = "${path.module}/../../lambda/regional_orchestrator.py"
  output_path = "${path.module}/regional_orchestrator.zip"
}

resource "aws_lambda_function" "regional_orchestrator" {
  filename         = data.archive_file.regional_lambda.output_path
  function_name    = "${var.project_name}-regional-orchestrator"
  role             = aws_iam_role.regional_role.arn
  handler          = "regional_orchestrator.handler"
  source_code_hash = data.archive_file.regional_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 60

  environment {
    variables = {
      CENTRAL_REGION         = var.central_region
      CENTRAL_EVENT_BUS_ARN  = var.central_event_bus_arn
      LOCAL_ORCHESTRATOR_ARN = var.is_central ? data.aws_lambda_function.local_orchestrator[0].arn : ""
    }
  }
}

# IAM Role
resource "aws_iam_role" "regional_role" {
  name = "${var.project_name}-regional-role-${var.aws_region}"

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

resource "aws_iam_role_policy" "regional_policy" {
  name = "${var.project_name}-regional-policy-${var.aws_region}"
  role = aws_iam_role.regional_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "events:PutEvents"
        ]
        Resource = var.is_central ? "*" : var.central_event_bus_arn
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = var.is_central ? data.aws_lambda_function.local_orchestrator[0].arn : "*"
      }
    ]
  })
}

# EventBridge Rules for Regional Events
resource "aws_cloudwatch_event_rule" "regional_events" {
  name        = "${var.project_name}-regional-events"
  description = "Capture regional events"

  event_pattern = jsonencode({
    source = ["aws.ec2", "aws.lambda", "aws.rds"]
  })
}

resource "aws_cloudwatch_event_target" "regional_lambda" {
  rule      = aws_cloudwatch_event_rule.regional_events.name
  target_id = "RegionalOrchestrator"
  arn       = aws_lambda_function.regional_orchestrator.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.regional_orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.regional_events.arn
}

# Helper data sources
data "aws_lambda_function" "local_orchestrator" {
  count         = var.is_central ? 1 : 0
  function_name = "aiops-multi-agent-orchestrator" # Assumes Phase 1 deployed
}

output "regional_orchestrator_arn" {
  value = aws_lambda_function.regional_orchestrator.arn
}
