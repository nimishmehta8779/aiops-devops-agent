provider "aws" {
  region = "us-east-1"
}

variable "project_name" {
  default = "aiops-devops-agent"
}

# 1. IAM Role for Action Group Lambdas
resource "aws_iam_role" "agent_lambda_role" {
  name = "${var.project_name}-action-group-role"

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

resource "aws_iam_role_policy" "agent_lambda_policy" {
  role = aws_iam_role.agent_lambda_role.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "codebuild:StartBuild",
          "codebuild:BatchGetBuilds",
          "cloudtrail:LookupEvents",
          "sns:Publish",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

# 2. Action Group Lambda: InfraOps
data "archive_file" "infra_ops_zip" {
  type        = "zip"
  source_dir  = "${path.module}/infra_ops"
  output_path = "${path.module}/infra_ops.zip"
}

resource "aws_lambda_function" "infra_ops" {
  function_name    = "${var.project_name}-infra-ops"
  filename         = data.archive_file.infra_ops_zip.output_path
  role             = aws_iam_role.agent_lambda_role.arn
  handler          = "index.handler"
  runtime          = "python3.11"
  source_code_hash = data.archive_file.infra_ops_zip.output_base64sha256
  timeout          = 60
}

# 3. Allow Bedrock to Invoke Lambda
resource "aws_lambda_permission" "allow_bedrock" {
  statement_id  = "AllowBedrockInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.infra_ops.function_name
  principal     = "bedrock.amazonaws.com"
}

output "infra_ops_lambda_arn" {
  value = aws_lambda_function.infra_ops.arn
}
