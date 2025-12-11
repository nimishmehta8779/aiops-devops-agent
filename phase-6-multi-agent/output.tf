output "lambda_function_name" {
  description = "Name of the multi-agent orchestrator Lambda function"
  value       = aws_lambda_function.multi_agent_orchestrator.function_name
}

output "lambda_function_arn" {
  description = "ARN of the multi-agent orchestrator Lambda function"
  value       = aws_lambda_function.multi_agent_orchestrator.arn
}

output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule"
  value       = aws_cloudwatch_event_rule.cloudtrail_events.name
}

output "log_group_name" {
  description = "CloudWatch Log Group name"
  value       = aws_cloudwatch_log_group.multi_agent_lambda.name
}
