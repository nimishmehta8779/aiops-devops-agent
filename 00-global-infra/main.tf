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
  default     = "aiops"
}

data "aws_caller_identity" "current" {}

# S3 Bucket for Terraform Remote State
resource "aws_s3_bucket" "terraform_state" {
  bucket = "${var.project_name}-terraform-state-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name        = "${var.project_name}-terraform-state"
    Environment = "global"
    ManagedBy   = "terraform"
  }
}

# Enable versioning for state bucket
resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Enable encryption for state bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access to state bucket
resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB table for Terraform state locking
resource "aws_dynamodb_table" "terraform_locks" {
  name         = "${var.project_name}-terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Name        = "${var.project_name}-terraform-locks"
    Environment = "global"
    ManagedBy   = "terraform"
  }
}

# DynamoDB table for AIOps incidents
resource "aws_dynamodb_table" "incidents" {
  name         = "${var.project_name}-incidents"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "incident_id"

  attribute {
    name = "incident_id"
    type = "S"
  }

  attribute {
    name = "resource_key"
    type = "S"
  }

  attribute {
    name = "incident_timestamp"
    type = "S"
  }

  # GSI for querying by resource
  global_secondary_index {
    name            = "ResourceIndex"
    hash_key        = "resource_key"
    range_key       = "incident_timestamp"
    projection_type = "ALL"
  }

  # Enable point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }

  # Enable encryption at rest
  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "${var.project_name}-incidents"
    Environment = "global"
    ManagedBy   = "terraform"
  }
}

# S3 Bucket for CodeBuild artifacts
resource "aws_s3_bucket" "codebuild_artifacts" {
  bucket = "${var.project_name}-codebuild-artifacts-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name        = "${var.project_name}-codebuild-artifacts"
    Environment = "global"
    ManagedBy   = "terraform"
  }
}

# Enable versioning for artifacts bucket
resource "aws_s3_bucket_versioning" "codebuild_artifacts" {
  bucket = aws_s3_bucket.codebuild_artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

# CodeBuild IAM Role
resource "aws_iam_role" "codebuild" {
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

# CodeBuild IAM Policy
resource "aws_iam_role_policy" "codebuild" {
  name = "${var.project_name}-codebuild-policy"
  role = aws_iam_role.codebuild.id

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
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = [
          "${aws_s3_bucket.codebuild_artifacts.arn}/*",
          "${aws_s3_bucket.terraform_state.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.codebuild_artifacts.arn,
          aws_s3_bucket.terraform_state.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem"
        ]
        Resource = aws_dynamodb_table.terraform_locks.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:*",
          "lambda:*",
          "dynamodb:*",
          "s3:*",
          "rds:*",
          "ssm:*",
          "iam:GetRole",
          "iam:PassRole"
        ]
        Resource = "*"
      }
    ]
  })
}

# CodeBuild Project for Terraform Apply
resource "aws_codebuild_project" "terraform_apply" {
  name          = "${var.project_name}-devops-agent-apply"
  description   = "Execute Terraform apply for infrastructure recovery"
  build_timeout = 60
  service_role  = aws_iam_role.codebuild.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = false

    environment_variable {
      name  = "TF_STATE_BUCKET"
      value = aws_s3_bucket.terraform_state.bucket
    }

    environment_variable {
      name  = "TF_LOCK_TABLE"
      value = aws_dynamodb_table.terraform_locks.name
    }
  }

  source {
    type      = "NO_SOURCE"
    buildspec = <<-EOT
      version: 0.2
      phases:
        install:
          commands:
            - echo "Installing Terraform..."
            - wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
            - unzip terraform_1.6.0_linux_amd64.zip
            - mv terraform /usr/local/bin/
            - terraform --version
        pre_build:
          commands:
            - echo "Correlation ID - $CORRELATION_ID"
            - echo "Resource Type - $RESOURCE_TYPE"
        build:
          commands:
            - echo "Executing Terraform apply for recovery..."
            - echo "This would restore infrastructure based on resource type"
            - echo "In production, clone your IaC repo and run terraform apply"
        post_build:
          commands:
            - echo "Recovery complete"
    EOT
  }

  logs_config {
    cloudwatch_logs {
      group_name = "/aws/codebuild/${var.project_name}-terraform-apply"
    }
  }

  tags = {
    Name        = "${var.project_name}-terraform-apply"
    Environment = "global"
    ManagedBy   = "terraform"
  }
}

# Outputs
output "terraform_state_bucket" {
  description = "S3 bucket for Terraform remote state"
  value       = aws_s3_bucket.terraform_state.bucket
}

output "terraform_locks_table" {
  description = "DynamoDB table for Terraform state locking"
  value       = aws_dynamodb_table.terraform_locks.name
}

output "incidents_table" {
  description = "DynamoDB table for AIOps incidents"
  value       = aws_dynamodb_table.incidents.name
}

output "codebuild_project" {
  description = "CodeBuild project for Terraform execution"
  value       = aws_codebuild_project.terraform_apply.name
}

output "codebuild_artifacts_bucket" {
  description = "S3 bucket for CodeBuild artifacts"
  value       = aws_s3_bucket.codebuild_artifacts.bucket
}
