terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "aiops-ml-models"
}

variable "incident_table_name" {
  description = "DynamoDB table name for incidents"
  type        = string
  default     = "aiops-incidents"
}

# Package Lambda
data "archive_file" "ml_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/ml_agent.zip"
}

# ML Agent Lambda
resource "aws_lambda_function" "ml_agent" {
  filename         = data.archive_file.ml_lambda.output_path
  function_name    = "${var.project_name}-agent"
  role             = aws_iam_role.ml_lambda.arn
  handler          = "ml_agent.handler"
  source_code_hash = data.archive_file.ml_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 300
  memory_size      = 1024

  environment {
    variables = {
      INCIDENT_TABLE = var.incident_table_name
    }
  }
}

# IAM Role
resource "aws_iam_role" "ml_lambda" {
  name = "${var.project_name}-lambda-role"

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

resource "aws_iam_role_policy" "ml_lambda" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.ml_lambda.id

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
          "dynamodb:Scan",
          "dynamodb:Query",
          "dynamodb:GetItem"
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:*:table/${var.incident_table_name}"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "cloudwatch:GetMetricStatistics"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.ml_models.arn}/*"
      }
    ]
  })
}

# S3 bucket for ML models
resource "aws_s3_bucket" "ml_models" {
  bucket = "${var.project_name}-models-${data.aws_caller_identity.current.account_id}"
}

# EventBridge rule to trigger pattern analysis daily
resource "aws_cloudwatch_event_rule" "daily_pattern_analysis" {
  name                = "${var.project_name}-daily-analysis"
  description         = "Trigger ML pattern analysis daily"
  schedule_expression = "rate(1 day)"
}

resource "aws_cloudwatch_event_target" "ml_lambda" {
  rule      = aws_cloudwatch_event_rule.daily_pattern_analysis.name
  target_id = "MLAgent"
  arn       = aws_lambda_function.ml_agent.arn

  input = jsonencode({
    action         = "find_patterns"
    incident_table = var.incident_table_name
    lookback_hours = 24
  })
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ml_agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_pattern_analysis.arn
}

data "aws_caller_identity" "current" {}

output "ml_agent_arn" {
  value = aws_lambda_function.ml_agent.arn
}

output "ml_models_bucket" {
  value = aws_s3_bucket.ml_models.bucket
}
