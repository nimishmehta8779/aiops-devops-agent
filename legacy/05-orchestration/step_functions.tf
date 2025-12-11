# ============================================================================
# PHASE 4: Step Functions Workflow Orchestration
# ============================================================================
# This creates a visual workflow for multi-stage recovery with retry logic

# Step Functions IAM Role
resource "aws_iam_role" "step_functions_role" {
  count = var.enable_step_functions ? 1 : 0
  name  = "${var.project_name}-step-functions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "states.amazonaws.com"
      }
    }]
  })

  tags = {
    Name        = "AIOps Step Functions Role"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Phase       = "Phase 4 - Step Functions"
  }
}

resource "aws_iam_role_policy" "step_functions_policy" {
  count = var.enable_step_functions ? 1 : 0
  role  = aws_iam_role.step_functions_role[0].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          aws_lambda_function.orchestrator.arn,
          "${aws_lambda_function.orchestrator.arn}:*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "codebuild:StartBuild",
          "codebuild:BatchGetBuilds"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem"
        ]
        Resource = var.enable_incident_tracking ? [
          aws_dynamodb_table.aiops_incidents[0].arn
        ] : []
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = var.sns_topic_arn
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      }
    ]
  })
}

# Step Functions State Machine
resource "aws_sfn_state_machine" "aiops_recovery_workflow" {
  count    = var.enable_step_functions ? 1 : 0
  name     = "${var.project_name}-recovery-workflow"
  role_arn = aws_iam_role.step_functions_role[0].arn

  definition = templatefile("${path.module}/workflow_state_machine_simple.json", {
    orchestrator_lambda_arn = aws_lambda_function.orchestrator.arn
    sns_topic_arn           = var.sns_topic_arn
    incident_table          = var.enable_incident_tracking ? aws_dynamodb_table.aiops_incidents[0].name : ""
    region                  = var.aws_region
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_functions_logs[0].arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tags = {
    Name        = "AIOps Recovery Workflow"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Phase       = "Phase 4 - Step Functions"
  }
}

# CloudWatch Log Group for Step Functions
resource "aws_cloudwatch_log_group" "step_functions_logs" {
  count             = var.enable_step_functions ? 1 : 0
  name              = "/aws/states/${var.project_name}-recovery-workflow"
  retention_in_days = 7

  tags = {
    Name        = "AIOps Step Functions Logs"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Phase       = "Phase 4 - Step Functions"
  }
}

# Update Lambda to add STATE_MACHINE_ARN environment variable
# This is handled in main.tf with conditional merge

# Outputs for Phase 4
output "step_functions_arn" {
  description = "ARN of the Step Functions state machine"
  value       = var.enable_step_functions ? aws_sfn_state_machine.aiops_recovery_workflow[0].arn : null
}

output "step_functions_name" {
  description = "Name of the Step Functions state machine"
  value       = var.enable_step_functions ? aws_sfn_state_machine.aiops_recovery_workflow[0].name : null
}
