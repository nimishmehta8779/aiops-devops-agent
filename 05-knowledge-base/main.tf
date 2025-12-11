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
  default     = "aiops-knowledge"
}

data "aws_caller_identity" "current" {}

# S3 bucket for incident postmortems and runbooks
resource "aws_s3_bucket" "knowledge_base" {
  bucket = "${var.project_name}-kb-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "${var.project_name}-knowledge-base"
  }
}

resource "aws_s3_bucket_versioning" "knowledge_base" {
  bucket = aws_s3_bucket.knowledge_base.id

  versioning_configuration {
    status = "Enabled"
  }
}

# OpenSearch Serverless for vector search
resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "aiops-kb-enc-policy"
  type = "encryption"
  policy = jsonencode({
    Rules = [
      {
        Resource = [
          "collection/${var.project_name}-collection"
        ]
        ResourceType = "collection"
      }
    ]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_security_policy" "network" {
  name = "aiops-kb-net-policy"
  type = "network"
  policy = jsonencode([
    {
      Rules = [
        {
          Resource = [
            "collection/${var.project_name}-collection"
          ]
          ResourceType = "collection"
        }
      ]
      AllowFromPublic = true
    }
  ])
}

resource "aws_opensearchserverless_access_policy" "data_access" {
  name = "${var.project_name}-data-access"
  type = "data"
  policy = jsonencode([
    {
      Rules = [
        {
          Resource = [
            "collection/${var.project_name}-collection"
          ]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:DeleteCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems"
          ]
          ResourceType = "collection"
        },
        {
          Resource = [
            "index/${var.project_name}-collection/*"
          ]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument"
          ]
          ResourceType = "index"
        }
      ]
      Principal = [
        aws_iam_role.bedrock_kb.arn,
        data.aws_caller_identity.current.arn
      ]
    }
  ])
}

resource "aws_opensearchserverless_collection" "knowledge_base" {
  name = "${var.project_name}-collection"
  type = "VECTORSEARCH"

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network
  ]
}

# Create Index
resource "null_resource" "create_index" {
  triggers = {
    endpoint = aws_opensearchserverless_collection.knowledge_base.collection_endpoint
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/create_index.py ${aws_opensearchserverless_collection.knowledge_base.collection_endpoint} ${var.aws_region}"
  }

  depends_on = [
    aws_opensearchserverless_collection.knowledge_base,
    aws_opensearchserverless_access_policy.data_access
  ]
}

# IAM role for Bedrock Knowledge Base
resource "aws_iam_role" "bedrock_kb" {
  name = "${var.project_name}-bedrock-kb-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:knowledge-base/*"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "bedrock_kb" {
  name = "${var.project_name}-bedrock-kb-policy"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.knowledge_base.arn,
          "${aws_s3_bucket.knowledge_base.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "aoss:APIAccessAll"
        ]
        Resource = aws_opensearchserverless_collection.knowledge_base.arn
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v1"
      }
    ]
  })
}

# Bedrock Knowledge Base
resource "aws_bedrockagent_knowledge_base" "aiops" {
  name     = "${var.project_name}-kb"
  role_arn = aws_iam_role.bedrock_kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v1"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.knowledge_base.arn
      vector_index_name = "aiops-incidents-index"
      field_mapping {
        vector_field   = "embedding"
        text_field     = "text"
        metadata_field = "metadata"
      }
    }
  }

  depends_on = [
    aws_iam_role_policy.bedrock_kb,
    aws_opensearchserverless_access_policy.data_access,
    null_resource.create_index
  ]
}

# Data source for S3
resource "aws_bedrockagent_data_source" "s3_incidents" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.aiops.id
  name              = "incident-postmortems"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = aws_s3_bucket.knowledge_base.arn
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 512
        overlap_percentage = 20
      }
    }
  }
}

# Lambda to sync incidents to Knowledge Base
resource "aws_lambda_function" "kb_sync" {
  filename      = "${path.module}/kb_sync.zip"
  function_name = "${var.project_name}-kb-sync"
  role          = aws_iam_role.kb_sync_lambda.arn
  handler       = "kb_sync.handler"
  runtime       = "python3.11"
  timeout       = 300

  environment {
    variables = {
      KNOWLEDGE_BASE_ID = aws_bedrockagent_knowledge_base.aiops.id
      DATA_SOURCE_ID    = aws_bedrockagent_data_source.s3_incidents.data_source_id
      S3_BUCKET         = aws_s3_bucket.knowledge_base.bucket
    }
  }
}

resource "aws_iam_role" "kb_sync_lambda" {
  name = "${var.project_name}-kb-sync-role"

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

resource "aws_iam_role_policy" "kb_sync_lambda" {
  name = "${var.project_name}-kb-sync-policy"
  role = aws_iam_role.kb_sync_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.knowledge_base.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:StartIngestionJob",
          "bedrock:GetIngestionJob"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:*:table/aiops-incidents"
      }
    ]
  })
}

# EventBridge rule to trigger KB sync daily
resource "aws_cloudwatch_event_rule" "kb_sync" {
  name                = "${var.project_name}-kb-sync"
  description         = "Sync incidents to Knowledge Base daily"
  schedule_expression = "rate(1 day)"
}

resource "aws_cloudwatch_event_target" "kb_sync" {
  rule      = aws_cloudwatch_event_rule.kb_sync.name
  target_id = "KBSync"
  arn       = aws_lambda_function.kb_sync.arn
}

resource "aws_lambda_permission" "kb_sync_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.kb_sync.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.kb_sync.arn
}

# Package Lambda
data "archive_file" "kb_sync" {
  type        = "zip"
  source_file = "${path.module}/lambda/kb_sync.py"
  output_path = "${path.module}/kb_sync.zip"
}

output "knowledge_base_id" {
  value = aws_bedrockagent_knowledge_base.aiops.id
}

output "knowledge_base_arn" {
  value = aws_bedrockagent_knowledge_base.aiops.arn
}

output "s3_bucket" {
  value = aws_s3_bucket.knowledge_base.bucket
}

output "opensearch_endpoint" {
  value = aws_opensearchserverless_collection.knowledge_base.collection_endpoint
}
