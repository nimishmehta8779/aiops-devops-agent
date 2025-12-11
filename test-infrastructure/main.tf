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
  region = "us-east-1"
}

# Get default VPC
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security group for test resources
resource "aws_security_group" "test_sg" {
  name        = "aiops-test-sg"
  description = "Security group for AIOps test resources"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "aiops-test-sg"
  }
}

# Get latest Amazon Linux 2023 AMI
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# Test EC2 instance (t2.micro - free tier)
resource "aws_instance" "test_ec2" {
  ami           = data.aws_ami.amazon_linux_2023.id
  instance_type = "t2.micro"

  vpc_security_group_ids = [aws_security_group.test_sg.id]

  tags = {
    Name        = "aiops-test-instance"
    Environment = "test"
    ManagedBy   = "aiops"
  }

  user_data = <<-EOF
              #!/bin/bash
              echo "AIOps Test Instance" > /tmp/test.txt
              EOF
}

# Test RDS instance (db.t3.micro - smallest)
resource "aws_db_instance" "test_rds" {
  identifier        = "aiops-test-db"
  engine            = "mysql"
  engine_version    = "8.0"
  instance_class    = "db.t3.micro"
  allocated_storage = 20

  db_name  = "testdb"
  username = "admin"
  password = "TestPassword123!" # Change in production

  vpc_security_group_ids = [aws_security_group.test_sg.id]
  db_subnet_group_name   = aws_db_subnet_group.test.name

  skip_final_snapshot = true
  publicly_accessible = false

  tags = {
    Name        = "aiops-test-rds"
    Environment = "test"
    ManagedBy   = "aiops"
  }
}

resource "aws_db_subnet_group" "test" {
  name       = "aiops-test-subnet-group"
  subnet_ids = data.aws_subnets.default.ids

  tags = {
    Name = "aiops-test-subnet-group"
  }
}

output "ec2_instance_id" {
  value = aws_instance.test_ec2.id
}

output "ec2_public_ip" {
  value = aws_instance.test_ec2.public_ip
}

output "rds_endpoint" {
  value = aws_db_instance.test_rds.endpoint
}

output "rds_instance_id" {
  value = aws_db_instance.test_rds.id
}
