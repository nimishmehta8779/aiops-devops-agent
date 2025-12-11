variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "aiops-multi-agent"
}

variable "incident_table_name" {
  description = "DynamoDB table name for incidents"
  type        = string
  default     = "aiops-incidents"
}

variable "sns_topic_arn" {
  description = "SNS topic ARN for notifications"
  type        = string
  default     = ""
}

variable "codebuild_project" {
  description = "CodeBuild project name for Terraform execution"
  type        = string
  default     = "aiops-devops-agent-apply"
}

variable "default_email" {
  description = "Default email for notifications"
  type        = string
  default     = "nimish.mehta@gmail.com"
}

variable "sender_email" {
  description = "Sender email for SES notifications"
  type        = string
  default     = "noreply@aiops.example.com"
}

variable "enable_ses" {
  description = "Enable SES email notifications"
  type        = bool
  default     = false
}
