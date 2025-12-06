# ============================================================================
# Terraform Variables Configuration
# ============================================================================
# This file controls which phases are enabled
# Uncomment phases as you progress through implementation

# Basic Configuration
project_name = "aiops-devops-agent"
environment  = "dev"
aws_region   = "us-east-1"

# SNS Topic (update with your actual ARN)
sns_topic_arn = "arn:aws:sns:us-east-1:415703161648:aiops-devops-agent-notifications"

# CodeBuild Project (update with your actual project name)
codebuild_project_name = "aiops-devops-agent-apply"

# ============================================================================
# PHASE 1: Foundation (Week 1-2)
# ============================================================================
# Enable DynamoDB tables for incident tracking and pattern recognition
enable_incident_tracking   = true
enable_pattern_recognition = true

# ============================================================================
# PHASE 2: Enhanced Lambda (Week 3-4)
# ============================================================================
# Enable enhanced Lambda with workflow features
enable_enhanced_lambda = true
cooldown_minutes       = 5
confidence_threshold   = 0.8

# ============================================================================
# PHASE 3: Proactive Monitoring (Week 5-6)
# ============================================================================
# Enable proactive log analysis
enable_log_analyzer   = true
log_groups_to_monitor = "/aws/lambda/aiops-devops-agent-orchestrator"
anomaly_threshold     = 0.7
log_analyzer_schedule = "rate(5 minutes)"

# ============================================================================
# PHASE 4: Step Functions (Week 7-8)
# ============================================================================
# Enable Step Functions workflow orchestration
enable_step_functions = true

# ============================================================================
# PHASE 5: Verification (Week 9-10)
# ============================================================================
# Uncomment to enable verification Lambda
# enable_verification         = true
# verification_retry_count    = 3
# verification_retry_interval = 30
