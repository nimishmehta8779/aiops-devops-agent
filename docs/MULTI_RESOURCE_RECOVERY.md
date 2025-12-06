# Multi-Resource Auto-Recovery System - Implementation Guide

## Overview
This system demonstrates production-ready auto-recovery for multiple AWS resource types using Amazon Bedrock AI and Infrastructure as Code.

## Supported Resources

### Currently Implemented:
1. **EC2 Instances** - Auto-restore terminated instances
2. **Lambda Functions** - Recreate deleted functions
3. **DynamoDB Tables** - Restore deleted tables
4. **S3 Buckets** - Recreate deleted buckets
5. **SSM Parameters** - Revert tampered configurations

### Architecture Components:

```
┌─────────────────────────────────────────────────────────────────┐
│                     AWS CloudTrail                               │
│          (Captures all API calls across services)                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Amazon EventBridge                             │
│   (Filters events: EC2, Lambda, DynamoDB, S3, SSM)              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Orchestrator Lambda Function                        │
│  • Detects resource type (ec2/lambda/dynamodb/s3/ssm)           │
│  • Extracts resource identifier                                  │
│  • Calls Amazon Bedrock for AI analysis                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Amazon Bedrock (Titan)                          │
│  Analyzes event and classifies as:                              │
│  • FAILURE (resource deletion/termination)                       │
│  • TAMPERING (unauthorized changes)                              │
│  • NORMAL (expected operations)                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS CodeBuild                                 │
│  • Clones Terraform code from CodeCommit                        │
│  • Runs `terraform apply`                                        │
│  • Detects drift and recreates missing resources                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Resource Restored                               │
│  • EC2 instance recreated with same config                      │
│  • Lambda function redeployed                                    │
│  • DynamoDB table restored                                       │
│  • S3 bucket recreated with versioning                          │
│  • SSM parameter reverted to secure value                       │
└─────────────────────────────────────────────────────────────────┘
```

## Resource Detection Logic

The system automatically detects resource types based on:

### 1. Event Source Matching
```python
def detect_resource_type(event_detail):
    event_source = event_detail.get('eventSource', '')
    
    if 'ec2' in event_source:
        return 'ec2'
    elif 'lambda' in event_source:
        return 'lambda'
    elif 'dynamodb' in event_source:
        return 'dynamodb'
    elif 's3' in event_source:
        return 's3'
    elif 'ssm' in event_source:
        return 'ssm'
```

### 2. Event Name Matching
```python
EVENT_PATTERNS = {
    'ec2': ['TerminateInstances', 'StopInstances'],
    'lambda': ['DeleteFunction', 'UpdateFunctionConfiguration'],
    'dynamodb': ['DeleteTable'],
    's3': ['DeleteBucket', 'PutBucketPolicy'],
    'ssm': ['PutParameter', 'DeleteParameter']
}
```

### 3. Resource Identifier Extraction
```python
def extract_resource_identifier(event_detail, resource_type):
    request_params = event_detail.get('requestParameters', {})
    
    if resource_type == 'ec2':
        return instances[0].get('instanceId')
    elif resource_type == 'lambda':
        return request_params.get('functionName')
    elif resource_type == 'dynamodb':
        return request_params.get('tableName')
    elif resource_type == 's3':
        return request_params.get('bucketName')
```

## AI-Powered Decision Making

### Bedrock Prompt Template:
```
You are a DevOps Agent analyzing AWS infrastructure events.

Event Details:
- Event Name: {event_name}
- Resource Type: {resource_type}
- Resource ID: {resource_id}
- User: {user_identity}

Analysis Instructions:
1. If this is a DELETE, TERMINATE, or STOP event for critical resources, classify as FAILURE
2. If this is unauthorized configuration change, classify as TAMPERING
3. If this is routine maintenance, classify as NORMAL

Critical Resource Types: ec2, lambda, dynamodb, s3, rds

Classification: [FAILURE/TAMPERING/NORMAL]
```

## Recovery Workflow

### For Each Resource Type:

#### EC2 Instance
1. **Detection**: `TerminateInstances` event captured
2. **Analysis**: Bedrock classifies as FAILURE
3. **Recovery**: Terraform recreates instance with:
   - Same AMI
   - Same instance type (t2.micro)
   - Same security groups
   - Same user data (web server config)
   - Same tags
4. **Verification**: New instance ID returned
5. **Notification**: Email with old/new instance IDs

#### Lambda Function
1. **Detection**: `DeleteFunction` event captured
2. **Analysis**: Bedrock classifies as FAILURE
3. **Recovery**: Terraform recreates function with:
   - Same runtime (python3.11)
   - Same handler
   - Same IAM role
   - Same code (from zip)
4. **Verification**: Function ARN returned
5. **Notification**: Email with function details

#### DynamoDB Table
1. **Detection**: `DeleteTable` event captured
2. **Analysis**: Bedrock classifies as FAILURE
3. **Recovery**: Terraform recreates table with:
   - Same table name
   - Same hash key
   - Same billing mode (PAY_PER_REQUEST)
   - Same tags
4. **Verification**: Table status = ACTIVE
5. **Notification**: Email with table details

#### S3 Bucket
1. **Detection**: `DeleteBucket` event captured
2. **Analysis**: Bedrock classifies as FAILURE
3. **Recovery**: Terraform recreates bucket with:
   - Same bucket name
   - Versioning enabled
   - Same tags
4. **Verification**: Bucket created
5. **Notification**: Email with bucket details

## Testing Scenarios

### Test 1: EC2 Termination
```bash
# Terminate instance
aws ec2 terminate-instances --instance-ids i-0e35eb936c3e975e8

# Expected: New instance created within 4 minutes
# Notification: Email with recovery details
```

### Test 2: Lambda Deletion
```bash
# Delete function
aws lambda delete-function --function-name aiops-monitored-function

# Expected: Function recreated within 2 minutes
# Notification: Email with function ARN
```

### Test 3: DynamoDB Deletion
```bash
# Delete table
aws dynamodb delete-table --table-name AiOpsDataTable

# Expected: Table recreated within 3 minutes
# Notification: Email with table status
```

### Test 4: S3 Bucket Deletion
```bash
# Delete bucket (must be empty first)
aws s3 rb s3://aiops-data-bucket-YOUR_AWS_ACCOUNT_ID --force

# Expected: Bucket recreated within 2 minutes
# Notification: Email with bucket details
```

### Test 5: SSM Parameter Tampering
```bash
# Change parameter value
aws ssm put-parameter --name "/myapp/config/mode" --value "hacked" --overwrite

# Expected: Parameter reverted to "secure-mode" within 2 minutes
# Notification: Email with tampering alert
```

## Email Notifications

Each recovery sends a detailed email with:

```
╔══════════════════════════════════════════════════════════════════════╗
║              DevOps Agent - Auto-Recovery Triggered                  ║
╚══════════════════════════════════════════════════════════════════════╝

🔴 INCIDENT DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Event: DeleteFunction
Resource Type: LAMBDA
Resource ID: aiops-monitored-function
User: arn:aws:iam::YOUR_AWS_ACCOUNT_ID:user/nimish

🤖 AI ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Classification: FAILURE
The event is a FAILURE.

🔄 RECOVERY ACTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CodeBuild Project: aiops-devops-agent-apply
Build ID: aiops-devops-agent-apply:xxxxx
Recovery Method: Infrastructure as Code (Terraform)

⏱️ TIMELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Detection: Immediate
Analysis: ~2 seconds
Recovery Started: Now
Expected Completion: 2-5 minutes
```

## Scaling to 50+ Resources

### Approach:

1. **Modular Terraform Structure**
   ```
   terraform/
   ├── modules/
   │   ├── ec2/
   │   ├── lambda/
   │   ├── dynamodb/
   │   ├── s3/
   │   ├── rds/
   │   └── eks/
   └── environments/
       └── production/
           └── main.tf (imports all modules)
   ```

2. **Resource-Specific CodeBuild Projects**
   ```python
   RESOURCE_RECOVERY_MAP = {
       "ec2": "aiops-ec2-recovery",
       "lambda": "aiops-lambda-recovery",
       "dynamodb": "aiops-dynamodb-recovery",
       "s3": "aiops-s3-recovery",
       "rds": "aiops-rds-recovery",
       "eks": "aiops-eks-recovery"
   }
   ```

3. **Parallel Recovery**
   - Multiple CodeBuild projects run in parallel
   - Each handles specific resource type
   - Faster recovery for multiple failures

4. **Dependency Management**
   - Terraform handles dependencies automatically
   - Resources created in correct order
   - Example: VPC → Subnet → EC2

5. **State Management**
   - Centralized S3 backend
   - State locking with DynamoDB
   - Prevents concurrent modification conflicts

## Cost Analysis

### Per Recovery Event:
- **Lambda Invocation**: $0.0000002 (< 1 cent)
- **Bedrock API Call**: ~$0.001
- **CodeBuild Minutes**: Free Tier (100 min/month)
- **SNS Notification**: Free Tier (1000/month)
- **Total per event**: < $0.01

### Monthly (assuming 100 events):
- **Total Cost**: < $1.00

## Production Recommendations

1. **Enable CloudTrail Data Events** for real-time detection
2. **Use AWS Secrets Manager** for sensitive parameters
3. **Implement approval workflow** for critical resources
4. **Add Slack/PagerDuty** integration for alerts
5. **Create resource-specific recovery strategies**
6. **Implement rollback mechanisms**
7. **Add compliance logging** to DynamoDB
8. **Use AWS Config** for drift detection
9. **Implement rate limiting** to prevent recovery loops
10. **Add manual approval** for production resources

## Next Steps

1. Test each resource type deletion
2. Verify recovery completeness
3. Check email notifications
4. Review CloudWatch logs
5. Validate Terraform state
6. Test concurrent failures
7. Measure recovery times
8. Document edge cases
