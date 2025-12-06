provider "aws" {
  region = "us-east-1"
}

variable "project_name" {
  default = "aiops-devops-agent"
}

# 1. CodeCommit Repository
resource "aws_codecommit_repository" "infra_repo" {
  repository_name = "${var.project_name}-repo"
  description     = "Terraform infrastructure code for the application"
}

# 2. SNS Topic for Notifications
resource "aws_sns_topic" "notifications" {
  name = "${var.project_name}-notifications"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.notifications.arn
  protocol  = "email"
  endpoint  = "nimish.mehta@gmail.com"
}

# 3. S3 Bucket for Terraform State (for the app infra)
resource "aws_s3_bucket" "tf_state" {
  bucket        = "${var.project_name}-tfstate-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

# 4. CodeBuild Project (The Recovery Mechanism)
resource "aws_iam_role" "codebuild_role" {
  name = "${var.project_name}-codebuild-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "codebuild.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "codebuild_policy" {
  role = aws_iam_role.codebuild_role.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Resource = "*"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "s3:*",
          "ec2:*",
          "dynamodb:*",
          "iam:*",
          "sns:*",
          "codecommit:GitPull",
          "ssm:*",
          "apigateway:*",
          "lambda:*"
        ]
      }
    ]
  })
}

resource "aws_codebuild_project" "infra_apply" {
  name          = "${var.project_name}-apply"
  description   = "Applies Terraform to recover infrastructure"
  build_timeout = "15"
  service_role  = aws_iam_role.codebuild_role.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/amazonlinux2-x86_64-standard:4.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "TF_VERSION"
      value = "1.5.7"
    }
  }

  source {
    type            = "CODECOMMIT"
    location        = aws_codecommit_repository.infra_repo.clone_url_http
    git_clone_depth = 1
    buildspec       = "buildspec.yml"
  }
}

data "aws_caller_identity" "current" {}

output "repo_url" {
  value = aws_codecommit_repository.infra_repo.clone_url_http
}

output "codebuild_project_name" {
  value = aws_codebuild_project.infra_apply.name
}

output "sns_topic_arn" {
  value = aws_sns_topic.notifications.arn
}
