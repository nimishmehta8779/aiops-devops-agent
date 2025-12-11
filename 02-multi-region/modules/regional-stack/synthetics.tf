resource "aws_synthetics_canary" "multi_region_heartbeat" {
  name                 = "${var.project_name}-heartbeat-${var.aws_region}"
  artifact_s3_location = "s3://${aws_s3_bucket.canary_bucket.bucket}/"
  execution_role_arn   = aws_iam_role.canary_role.arn
  handler              = "heartbeat.handler"
  zip_file             = "heartbeat.zip"
  runtime_version      = "syn-python-selenium-1.0"

  schedule {
    expression = "rate(5 minutes)"
  }
}

resource "aws_s3_bucket" "canary_bucket" {
  bucket = "${var.project_name}-canary-${var.aws_region}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_iam_role" "canary_role" {
  name = "${var.project_name}-canary-role-${var.aws_region}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}
