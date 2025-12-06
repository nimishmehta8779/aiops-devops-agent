provider "aws" {
  region = "us-east-1"
}

terraform {
  backend "s3" {
    bucket = "aiops-devops-agent-tfstate-415703161648"
    key    = "multi-resource-infra/terraform.tfstate"
    region = "us-east-1"
  }
}

locals {
  project_name = "aiops-multi-resource"
  environment  = "production"
}

# Get default VPC for simplicity
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "allow_all" {
  name        = "${local.project_name}-sg"
  description = "Allow all traffic for demo"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 1. EC2 Web Server
resource "aws_instance" "web_server" {
  ami                    = "ami-0c7217cdde317cfec"
  instance_type          = "t2.micro"
  subnet_id              = tolist(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.allow_all.id]

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              yum install -y httpd
              systemctl start httpd
              systemctl enable httpd
              echo "<h1>Multi-Resource Web Server</h1>" > /var/www/html/index.html
              EOF

  tags = {
    Name         = "aiops-web-server"
    Environment  = local.environment
    ManagedBy    = "terraform"
    ResourceType = "ec2"
  }
}

# 2. Lambda Function
data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/lambda_function.zip"

  source {
    content  = <<-EOF
def handler(event, context):
    return {
        'statusCode': 200,
        'body': 'Hello from monitored Lambda!'
    }
    EOF
    filename = "index.py"
  }
}

resource "aws_iam_role" "lambda_role" {
  name = "${local.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "app_function" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "aiops-monitored-function"
  role             = aws_iam_role.lambda_role.arn
  handler          = "index.handler"
  runtime          = "python3.11"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  tags = {
    Name         = "aiops-monitored-lambda"
    Environment  = local.environment
    ManagedBy    = "terraform"
    ResourceType = "lambda"
  }
}

# 3. DynamoDB Table
resource "aws_dynamodb_table" "data_table" {
  name         = "AiOpsDataTable"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  tags = {
    Name         = "aiops-data-table"
    Environment  = local.environment
    ManagedBy    = "terraform"
    ResourceType = "dynamodb"
  }
}

# 4. S3 Bucket
resource "aws_s3_bucket" "data_bucket" {
  bucket        = "aiops-data-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Name         = "aiops-data-bucket"
    Environment  = local.environment
    ManagedBy    = "terraform"
    ResourceType = "s3"
  }
}

resource "aws_s3_bucket_versioning" "data_bucket_versioning" {
  bucket = aws_s3_bucket.data_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

data "aws_caller_identity" "current" {}

# Outputs
output "ec2_instance_id" {
  value = aws_instance.web_server.id
}

output "lambda_function_name" {
  value = aws_lambda_function.app_function.function_name
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.data_table.name
}

output "s3_bucket_name" {
  value = aws_s3_bucket.data_bucket.id
}

output "resources_summary" {
  value = {
    ec2      = aws_instance.web_server.id
    lambda   = aws_lambda_function.app_function.function_name
    dynamodb = aws_dynamodb_table.data_table.name
    s3       = aws_s3_bucket.data_bucket.id
  }
}
