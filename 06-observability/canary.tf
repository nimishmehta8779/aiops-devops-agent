# CloudWatch Synthetics Canary
resource "aws_synthetics_canary" "api_canary" {
  name                 = "aiops-api-canary"
  artifact_s3_location = "s3://${aws_s3_bucket.canary.bucket}/"
  execution_role_arn   = aws_iam_role.canary.arn
  handler              = "pageLoadBlueprint.handler"
  zip_file             = data.archive_file.canary.output_path
  runtime_version      = "syn-nodejs-puppeteer-9.1"

  schedule {
    expression = "rate(5 minutes)"
  }

  run_config {
    timeout_in_seconds = 60
  }

  tags = {
    Environment = "production"
    ManagedBy   = "aiops"
  }
}

# S3 Bucket for Canary Artifacts
resource "aws_s3_bucket" "canary" {
  bucket        = "aiops-canary-artifacts-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

# IAM Role for Canary
resource "aws_iam_role" "canary" {
  name = "aiops-canary-role"

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

resource "aws_iam_role_policy_attachment" "canary" {
  role       = aws_iam_role.canary.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Simple canary script
data "archive_file" "canary" {
  type        = "zip"
  output_path = "${path.module}/canary.zip"

  source {
    content  = <<EOF
var synthetics = require('Synthetics');
const log = require('SyntheticsLogger');

const pageLoadBlueprint = async function () {
    // INSERT URL here
    const url = "https://www.google.com";

    let page = await synthetics.getPage();
    const response = await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 30000});
    if (!response) {
        throw "Failed to load page!";
    }
    await page.waitForTimeout(15000);
    await synthetics.takeScreenshot('loaded', 'loaded');
    let pageTitle = await page.title();
    log.info('Page title: ' + pageTitle);
};

exports.handler = async () => {
    return await pageLoadBlueprint();
};
EOF
    filename = "nodejs/node_modules/pageLoadBlueprint.js"
  }
}
