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
  default     = "aiops-observability"
}

variable "multi_agent_lambda_arn" {
  description = "ARN of the multi-agent orchestrator for routing insights"
  type        = string
  default     = "" # Pass this in or use data source
}

data "aws_caller_identity" "current" {}

# 1. DevOps Guru Integration
resource "aws_devopsguru_resource_collection" "aiops" {
  type = "AWS_TAGS"

  tags {
    app_boundary_key = "ManagedBy"
    tag_values       = ["aiops", "terraform"]
  }
}

resource "aws_cloudwatch_event_rule" "devops_guru" {
  name        = "capture-devops-guru-insights"
  description = "Capture DevOps Guru insights and route to AIOps agents"

  event_pattern = jsonencode({
    source      = ["aws.devops-guru"]
    detail-type = ["DevOps Guru New Insight Open"]
  })
}

# 3. CloudWatch Dashboard for AIOps Metrics
resource "aws_cloudwatch_dashboard" "aiops_main" {
  dashboard_name = "AIOps-Main-Dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AIOps/Telemetry", "HealthScore", "ServiceName", "aiops-orchestrator"],
            [".", "AnomaliesDetected", ".", "."]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "System Health & Anomalies"
        }
      },
      {
        type   = "log"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          query  = "SOURCE '/aws/lambda/aiops-multi-agent-orchestrator' | fields @timestamp, @message | filter @message like /CRITICAL/ | sort @timestamp desc"
          region = var.aws_region
          title  = "Recent Critical Incidents"
          view   = "table"
        }
      },
      {
        type   = "text"
        x      = 0
        y      = 6
        width  = 24
        height = 2
        properties = {
          markdown = "## Operational Insights"
        }
      }
    ]
  })
}

# 4. Outputs
output "dashboard_name" {
  value = aws_cloudwatch_dashboard.aiops_main.dashboard_name
}
