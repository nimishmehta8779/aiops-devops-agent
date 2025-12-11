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

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    # This requires the awscli to be installed locally where Terraform is executed
    args = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }
}

data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "aiops-kubernetes"
}

variable "eks_cluster_name" {
  description = "EKS cluster name to monitor"
  type        = string
  default     = ""
}

# Package kubectl layer Lambda
data "archive_file" "kubectl_layer" {
  type        = "zip"
  source_file = "${path.module}/lambda/kubectl_layer.py"
  output_path = "${path.module}/kubectl_layer.zip"
}

# Package K8s agent Lambda
data "archive_file" "k8s_agent" {
  type        = "zip"
  source_file = "${path.module}/lambda/k8s_agent.py"
  output_path = "${path.module}/k8s_agent.zip"
}

# Kubectl Layer Lambda (executes kubectl commands)
resource "aws_lambda_function" "kubectl_layer" {
  filename         = data.archive_file.kubectl_layer.output_path
  function_name    = "${var.project_name}-kubectl-layer"
  role             = aws_iam_role.k8s_lambda.arn
  handler          = "kubectl_layer.handler"
  source_code_hash = data.archive_file.kubectl_layer.output_base64sha256
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      # AWS_REGION is reserved and automatically provided
    }
  }
}

# K8s Agent Lambda
resource "aws_lambda_function" "k8s_agent" {
  filename         = data.archive_file.k8s_agent.output_path
  function_name    = "${var.project_name}-agent"
  role             = aws_iam_role.k8s_lambda.arn
  handler          = "k8s_agent.handler"
  source_code_hash = data.archive_file.k8s_agent.output_base64sha256
  runtime          = "python3.11"
  timeout          = 300
  memory_size      = 512

  environment {
    variables = {
      CLUSTER_NAME       = module.eks.cluster_name
      KUBECTL_LAMBDA_ARN = aws_lambda_function.kubectl_layer.arn
    }
  }
}

# IAM Role
resource "aws_iam_role" "k8s_lambda" {
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

resource "aws_iam_role_policy" "k8s_lambda" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.k8s_lambda.id

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
          "eks:DescribeCluster",
          "eks:ListClusters"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = aws_lambda_function.kubectl_layer.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:*:table/aiops-incidents"
      }
    ]
  })
}

# EventBridge rule for EKS events (if available)
resource "aws_cloudwatch_event_rule" "eks_events" {
  count       = var.eks_cluster_name != "" ? 1 : 0
  name        = "${var.project_name}-eks-events"
  description = "Capture EKS cluster events"

  event_pattern = jsonencode({
    source      = ["aws.eks"]
    detail-type = ["EKS Cluster State Change"]
  })
}

resource "aws_cloudwatch_event_target" "k8s_agent" {
  count     = var.eks_cluster_name != "" ? 1 : 0
  rule      = aws_cloudwatch_event_rule.eks_events[0].name
  target_id = "K8sAgent"
  arn       = aws_lambda_function.k8s_agent.arn
}

resource "aws_lambda_permission" "eventbridge" {
  count         = var.eks_cluster_name != "" ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.k8s_agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.eks_events[0].arn
}

output "k8s_agent_arn" {
  value = aws_lambda_function.k8s_agent.arn
}

output "kubectl_layer_arn" {
  value = aws_lambda_function.kubectl_layer.arn
}
