# Phase 00: Global Infrastructure

## Overview

This phase deploys the foundational global infrastructure required by all other phases.

## Components

### 1. **Terraform Remote State**
- **S3 Bucket**: Stores Terraform state files
- **DynamoDB Table**: Provides state locking
- **Versioning**: Enabled for state recovery
- **Encryption**: AES256 encryption at rest

### 2. **AIOps Incidents Database**
- **DynamoDB Table**: `aiops-incidents`
- **Billing**: Pay-per-request (cost-effective)
- **GSI**: ResourceIndex for querying by resource
- **Features**: Point-in-time recovery, encryption

### 3. **CodeBuild for Recovery**
- **Project**: `aiops-devops-agent-apply`
- **Purpose**: Executes Terraform for infrastructure recovery
- **Runtime**: AWS CodeBuild Standard 7.0 (includes Terraform)
- **Timeout**: 60 minutes

### 4. **Artifacts Storage**
- **S3 Bucket**: Stores CodeBuild artifacts and logs
- **Versioning**: Enabled

## Deployment

### Step 1: Deploy Global Infrastructure

```bash
cd 00-global-infra
terraform init
terraform apply
```

This creates:
- S3 bucket: `aiops-terraform-state-{account-id}`
- DynamoDB table: `aiops-terraform-locks`
- DynamoDB table: `aiops-incidents`
- CodeBuild project: `aiops-devops-agent-apply`
- S3 bucket: `aiops-codebuild-artifacts-{account-id}`

### Step 2: Configure Remote State for Other Phases

After deploying global infra, update other phases to use remote state:

Create `backend.tf` in each phase directory:

```hcl
terraform {
  backend "s3" {
    bucket         = "aiops-terraform-state-{your-account-id}"
    key            = "phase-6-multi-agent/terraform.tfstate"  # Change per phase
    region         = "us-east-1"
    dynamodb_table = "aiops-terraform-locks"
    encrypt        = true
  }
}
```

## Recovery Mechanism

### How Recovery Works

1. **Incident Detected** → Multi-agent system analyzes
2. **Remediation Agent** → Generates runbook with Terraform steps
3. **CodeBuild Triggered** → Starts `aiops-devops-agent-apply` project
4. **Terraform Executes** → Restores infrastructure from IaC
5. **Verification** → Confirms resource is healthy

### CodeBuild Buildspec

The CodeBuild project uses this buildspec (customizable):

```yaml
version: 0.2
phases:
  install:
    commands:
      - terraform --version
  pre_build:
    commands:
      - echo "Correlation ID: $CORRELATION_ID"
      - echo "Resource Type: $RESOURCE_TYPE"
  build:
    commands:
      - # Clone your IaC repository
      - # cd to appropriate directory
      - terraform init
      - terraform apply -auto-approve
  post_build:
    commands:
      - echo "Recovery complete"
```

### Environment Variables Passed

- `CORRELATION_ID`: Incident correlation ID
- `RESOURCE_TYPE`: Type of resource to recover (ec2, lambda, etc.)
- `TF_STATE_BUCKET`: S3 bucket for state
- `TF_LOCK_TABLE`: DynamoDB table for locking

## Cost Estimate

| Resource | Monthly Cost |
|----------|--------------|
| S3 (state + artifacts) | $0.02 |
| DynamoDB (on-demand) | $0.75 |
| CodeBuild (minimal usage) | $0 (free tier) |
| **Total** | **~$0.77/month** |

## Security

- ✅ S3 buckets encrypted (AES256)
- ✅ DynamoDB encrypted at rest
- ✅ Public access blocked on S3
- ✅ IAM least-privilege policies
- ✅ State locking prevents concurrent modifications
- ✅ Versioning enabled for recovery

## Next Steps

After deploying global infrastructure:

1. Note the output values (bucket names, table names)
2. Update `phase-6-multi-agent/variables.tf` with:
   - `incident_table_name = "aiops-incidents"`
   - `codebuild_project = "aiops-devops-agent-apply"`
3. Deploy phase-6-multi-agent
4. Test recovery by triggering an incident

## Outputs

```bash
terraform output
```

Returns:
- `terraform_state_bucket` - For remote state configuration
- `terraform_locks_table` - For state locking
- `incidents_table` - For multi-agent system
- `codebuild_project` - For recovery automation
- `codebuild_artifacts_bucket` - For build artifacts
