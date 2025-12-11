# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Reference existing DynamoDB table from phase-4
data "aws_dynamodb_table" "incidents" {
  name = var.incident_table_name
}

# Reference existing SNS topic if provided
data "aws_sns_topic" "notifications" {
  count = var.sns_topic_arn != "" ? 1 : 0
  name  = split(":", var.sns_topic_arn)[5]
}
