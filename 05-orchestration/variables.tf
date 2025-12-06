variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "aiops-devops-agent"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "sns_topic_arn" {
  description = "SNS Topic ARN for notifications"
  type        = string
  default     = "arn:aws:sns:us-east-1:YOUR_AWS_ACCOUNT_ID:aiops-devops-agent-notifications"
}

variable "codebuild_project_name" {
  description = "CodeBuild project name for recovery"
  type        = string
  default     = "aiops-devops-agent-apply"
}

# Phase-specific variables

# Phase 1: Foundation
variable "enable_incident_tracking" {
  description = "Enable DynamoDB incident tracking (Phase 1)"
  type        = bool
  default     = true
}

variable "enable_pattern_recognition" {
  description = "Enable DynamoDB pattern recognition (Phase 1)"
  type        = bool
  default     = true
}

# Phase 2: Enhanced Lambda
variable "enable_enhanced_lambda" {
  description = "Use enhanced Lambda with workflow features (Phase 2)"
  type        = bool
  default     = false
}

variable "cooldown_minutes" {
  description = "Cooldown period in minutes to prevent recovery loops (Phase 2)"
  type        = number
  default     = 5
}

variable "confidence_threshold" {
  description = "Minimum confidence threshold for auto-recovery (Phase 2)"
  type        = number
  default     = 0.8
}

# Phase 3: Proactive Monitoring
variable "enable_log_analyzer" {
  description = "Enable proactive log analysis (Phase 3)"
  type        = bool
  default     = false
}

variable "log_groups_to_monitor" {
  description = "Comma-separated list of CloudWatch Log Groups to monitor (Phase 3)"
  type        = string
  default     = ""
}

variable "anomaly_threshold" {
  description = "Anomaly detection threshold for proactive alerts (Phase 3)"
  type        = number
  default     = 0.7
}

variable "log_analyzer_schedule" {
  description = "Schedule expression for log analyzer (Phase 3)"
  type        = string
  default     = "rate(5 minutes)"
}

# Phase 4: Step Functions
variable "enable_step_functions" {
  description = "Enable Step Functions workflow orchestration (Phase 4)"
  type        = bool
  default     = false
}

# Phase 5: Verification
variable "enable_verification" {
  description = "Enable verification Lambda (Phase 5)"
  type        = bool
  default     = false
}

variable "verification_retry_count" {
  description = "Number of verification retries (Phase 5)"
  type        = number
  default     = 3
}

variable "verification_retry_interval" {
  description = "Interval between verification retries in seconds (Phase 5)"
  type        = number
  default     = 30
}
