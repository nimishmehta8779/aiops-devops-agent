# EventBridge rule for CloudTrail events
resource "aws_cloudwatch_event_rule" "cloudtrail_events" {
  name        = "${var.project_name}-cloudtrail-events"
  description = "Capture CloudTrail events for multi-agent AIOps"

  event_pattern = jsonencode({
    source      = ["aws.ec2", "aws.lambda", "aws.dynamodb", "aws.s3", "aws.rds", "aws.ssm"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = [
        # EC2
        "TerminateInstances",
        "StopInstances",
        # Lambda
        "DeleteFunction",
        "UpdateFunctionConfiguration",
        # DynamoDB
        "DeleteTable",
        # S3
        "DeleteBucket",
        "PutBucketPolicy",
        # RDS
        "DeleteDBInstance",
        # SSM
        "DeleteParameter",
        "PutParameter"
      ]
    }
  })

  tags = {
    Name        = "${var.project_name}-cloudtrail-rule"
    Environment = "production"
  }
}

# EventBridge target - Multi-Agent Lambda
resource "aws_cloudwatch_event_target" "multi_agent_lambda" {
  rule      = aws_cloudwatch_event_rule.cloudtrail_events.name
  target_id = "MultiAgentOrchestrator"
  arn       = aws_lambda_function.multi_agent_orchestrator.arn
}

# EventBridge rule for EC2 state changes (real-time)
resource "aws_cloudwatch_event_rule" "ec2_state_change" {
  name        = "${var.project_name}-ec2-state-change"
  description = "Capture EC2 instance state changes"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Instance State-change Notification"]
    detail = {
      state = ["terminated", "stopped"]
    }
  })

  tags = {
    Name        = "${var.project_name}-ec2-rule"
    Environment = "production"
  }
}

# EventBridge target for EC2 events
resource "aws_cloudwatch_event_target" "ec2_multi_agent_lambda" {
  rule      = aws_cloudwatch_event_rule.ec2_state_change.name
  target_id = "MultiAgentOrchestratorEC2"
  arn       = aws_lambda_function.multi_agent_orchestrator.arn
}

# Lambda permission for EC2 EventBridge rule
resource "aws_lambda_permission" "eventbridge_ec2" {
  statement_id  = "AllowExecutionFromEventBridgeEC2"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.multi_agent_orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ec2_state_change.arn
}
