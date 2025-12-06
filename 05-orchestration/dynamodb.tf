# ============================================================================
# PHASE 1: Foundation - DynamoDB Tables for Incident Tracking
# ============================================================================
# This creates the foundation for workflow state management and learning

# DynamoDB Table for Incident Tracking
# This table stores all incidents with full context for learning and pattern recognition
resource "aws_dynamodb_table" "aiops_incidents" {
  count = var.enable_incident_tracking ? 1 : 0

  name         = "${var.project_name}-incidents"
  billing_mode = "PAY_PER_REQUEST" # On-demand pricing for cost efficiency
  hash_key     = "incident_id"

  # Primary key
  attribute {
    name = "incident_id"
    type = "S"
  }

  # GSI 1: Query by resource type and timestamp
  attribute {
    name = "resource_type"
    type = "S"
  }

  attribute {
    name = "incident_timestamp"
    type = "S"
  }

  # GSI 2: Query by resource key (type#id) for cooldown checks
  attribute {
    name = "resource_key"
    type = "S"
  }

  # GSI 3: Query by workflow state
  attribute {
    name = "workflow_state"
    type = "S"
  }

  # Global Secondary Index 1: Resource Type + Timestamp
  global_secondary_index {
    name            = "resource-type-index"
    hash_key        = "resource_type"
    range_key       = "incident_timestamp"
    projection_type = "ALL"
  }

  # Global Secondary Index 2: Resource Key + Timestamp (for cooldown)
  global_secondary_index {
    name            = "resource-timestamp-index"
    hash_key        = "resource_key"
    range_key       = "incident_timestamp"
    projection_type = "ALL"
  }

  # Global Secondary Index 3: Workflow State
  global_secondary_index {
    name            = "workflow-state-index"
    hash_key        = "workflow_state"
    range_key       = "incident_timestamp"
    projection_type = "ALL"
  }

  # Enable point-in-time recovery for data protection
  point_in_time_recovery {
    enabled = true
  }

  # Enable TTL to auto-delete old incidents (optional - 90 days)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Server-side encryption
  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "AIOps Incident Tracking"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Purpose     = "AI DevOps Agent - Incident History and Pattern Recognition"
    Phase       = "Phase 1 - Foundation"
  }
}

# DynamoDB Table for Pattern Recognition (Optional - for advanced use cases)
resource "aws_dynamodb_table" "aiops_patterns" {
  count = var.enable_pattern_recognition ? 1 : 0

  name         = "${var.project_name}-patterns"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pattern_id"

  attribute {
    name = "pattern_id"
    type = "S"
  }

  attribute {
    name = "resource_type"
    type = "S"
  }

  attribute {
    name = "occurrence_count"
    type = "N"
  }

  # GSI for querying patterns by resource type
  global_secondary_index {
    name            = "resource-pattern-index"
    hash_key        = "resource_type"
    range_key       = "occurrence_count"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "AIOps Pattern Recognition"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Phase       = "Phase 1 - Foundation"
  }
}


# ============================================================================
# Outputs
# ============================================================================

# Phase 1 Outputs
output "incidents_table_name" {
  description = "Name of the incidents DynamoDB table"
  value       = var.enable_incident_tracking ? aws_dynamodb_table.aiops_incidents[0].name : null
}

output "incidents_table_arn" {
  description = "ARN of the incidents DynamoDB table"
  value       = var.enable_incident_tracking ? aws_dynamodb_table.aiops_incidents[0].arn : null
}

output "patterns_table_name" {
  description = "Name of the patterns DynamoDB table"
  value       = var.enable_pattern_recognition ? aws_dynamodb_table.aiops_patterns[0].name : null
}

output "patterns_table_arn" {
  description = "ARN of the patterns DynamoDB table"
  value       = var.enable_pattern_recognition ? aws_dynamodb_table.aiops_patterns[0].arn : null
}

