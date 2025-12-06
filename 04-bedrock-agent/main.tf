provider "aws" {
  region = "us-east-1"
}

variable "project_name" {
  default = "aiops-devops-agent"
}

# 1. IAM Role for Bedrock Agent
resource "aws_iam_role" "bedrock_agent_role" {
  name = "${var.project_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "bedrock_agent_policy" {
  role = aws_iam_role.bedrock_agent_role.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2:1"
      }
    ]
  })
}

# 2. Bedrock Agent
resource "aws_bedrockagent_agent" "devops_agent" {
  agent_name                  = var.project_name
  agent_resource_role_arn     = aws_iam_role.bedrock_agent_role.arn
  idle_session_ttl_in_seconds = 1800
  foundation_model            = "anthropic.claude-v2:1"
  instruction                 = <<EOF
You are a DevOps Agent responsible for monitoring and recovering infrastructure.

Your capabilities:
1. Check Infrastructure Health: Use 'get_infra_health' to see the status of EC2 instances.
2. Analyze Failures: If you suspect a failure, use 'get_infra_health' or ask the user for logs.
3. Recover: If infrastructure is unhealthy, missing, or TAMPERED with (e.g., SSM Parameter changes), use 'trigger_recovery' to run the CodeBuild pipeline.
4. Notify: Always use 'send_notification' to inform the user (your-email@example.com) about failures and recovery actions.

Workflow:
- If you receive a 'PutParameter' event for '/myapp/config/mode', this is a TAMPERING attempt.
- You MUST trigger recovery immediately to revert the parameter to its secure state.
- Send a notification: "Tampering detected on SSM Parameter. Reverting to secure state."
EOF
}

# 3. Action Group
# We need the Lambda ARN from Phase 3. Using remote state or data source would be best, 
# but for simplicity in this flow, I'll use a variable or data source.
# Let's use data "aws_lambda_function" to look it up by name.

data "aws_lambda_function" "infra_ops" {
  function_name = "${var.project_name}-infra-ops"
}

resource "aws_bedrockagent_agent_action_group" "infra_ops_group" {
  agent_id          = aws_bedrockagent_agent.devops_agent.id
  agent_version     = "DRAFT"
  action_group_name = "InfraOpsActionGroup"
  description       = "Actions for Infrastructure Operations"

  action_group_executor {
    lambda = data.aws_lambda_function.infra_ops.arn
  }

  api_schema {
    payload = jsonencode({
      "openapi" : "3.0.1",
      "info" : {
        "title" : "InfraOps API",
        "version" : "1.0.0"
      },
      "paths" : {
        "/health" : {
          "get" : {
            "summary" : "Get infrastructure health",
            "description" : "Returns the status of EC2 instances",
            "operationId" : "get_infra_health",
            "responses" : {
              "200" : {
                "description" : "Health status",
                "content" : {
                  "application/json" : {
                    "schema" : {
                      "type" : "string"
                    }
                  }
                }
              }
            }
          }
        },
        "/recover" : {
          "post" : {
            "summary" : "Trigger recovery",
            "description" : "Starts the CodeBuild pipeline to recover infrastructure",
            "operationId" : "trigger_recovery",
            "responses" : {
              "200" : {
                "description" : "Recovery started",
                "content" : {
                  "application/json" : {
                    "schema" : {
                      "type" : "string"
                    }
                  }
                }
              }
            }
          }
        },
        "/notify" : {
          "post" : {
            "summary" : "Send notification",
            "description" : "Sends an email notification via SNS",
            "operationId" : "send_notification",
            "requestBody" : {
              "required" : true,
              "content" : {
                "application/json" : {
                  "schema" : {
                    "type" : "object",
                    "properties" : {
                      "message" : {
                        "type" : "string",
                        "description" : "The message to send"
                      }
                    },
                    "required" : ["message"]
                  }
                }
              }
            },
            "responses" : {
              "200" : {
                "description" : "Notification sent",
                "content" : {
                  "application/json" : {
                    "schema" : {
                      "type" : "string"
                    }
                  }
                }
              }
            }
          }
        }
      }
    })
  }
}

# 4. Agent Alias (Deploys the Agent)
# Note: Creating an alias triggers preparation.
resource "aws_bedrockagent_agent_alias" "prod" {
  agent_id         = aws_bedrockagent_agent.devops_agent.id
  agent_alias_name = "prod"
  description      = "Production Alias"

  # Dependent on Action Group being created
  depends_on = [aws_bedrockagent_agent_action_group.infra_ops_group]
}

output "agent_id" {
  value = aws_bedrockagent_agent.devops_agent.id
}

output "agent_alias_id" {
  value = aws_bedrockagent_agent_alias.prod.agent_alias_id
}
