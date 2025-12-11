# Phase 6: Multi-Agent AIOps System

## Overview

This phase implements a comprehensive multi-agent AIOps system with five specialized agents:

1. **Triage Agent** - Alert classification, deduplication, and prioritization
2. **Telemetry Agent** - Deep querying of metrics, logs, and traces
3. **Remediation Agent** - Runbook generation and execution
4. **Risk/Guardrail Agent** - Change safety validation and compliance
5. **Communications Agent** - Email notifications and incident summaries

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Multi-Agent Orchestrator                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Coordinator                            │
│  Manages execution order, context passing, and dependencies      │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│Triage Agent  │    │Telemetry     │    │Risk Agent    │
│Priority: 1   │───▶│Agent         │───▶│Priority: 2   │
│              │    │Priority: 2   │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
┌──────────────┐                          ┌──────────────┐
│Remediation   │                          │Communications│
│Agent         │                          │Agent         │
│Priority: 3   │                          │Priority: 4   │
└──────────────┘                          └──────────────┘
```

## Agent Responsibilities

### Triage Agent (Priority: CRITICAL)
- Classifies incidents (CRITICAL, HIGH, MEDIUM, LOW, INFO)
- Deduplicates similar incidents using fingerprinting
- Calculates severity scores (1-10)
- Assesses business impact using Bedrock
- Noise reduction (suppresses likely false positives)

### Telemetry Agent (Priority: HIGH)
- Queries CloudWatch Metrics for resource health
- Queries CloudWatch Logs for error patterns
- Queries X-Ray for distributed traces
- Detects anomalies in metrics
- Tracks correlation IDs across services

### Risk/Guardrail Agent (Priority: HIGH)
- Validates change windows (blocks Friday 4pm-11pm by default)
- Checks AWS Config compliance
- Validates SLO/error budget state
- Assesses blast radius (localized/regional/global)
- Calculates risk scores (0.0-1.0)

### Remediation Agent (Priority: MEDIUM)
- Generates recovery runbooks using Bedrock
- Executes Terraform via CodeBuild
- Executes SSM Automation documents
- Invokes Lambda runbooks
- Implements human-in-the-loop approval for high-risk changes

### Communications Agent (Priority: LOW)
- Sends email notifications via SES
- Sends SNS notifications
- Generates incident summaries using Bedrock
- Creates postmortem reports
- Formats human-readable updates

## Deployment

### Prerequisites

- AWS CLI configured
- Terraform >= 1.0
- Existing DynamoDB table from phase-4 (`aiops-incidents`)
- (Optional) SES email verification for sender and recipient

### Steps

1. **Configure Variables**

Create `terraform.tfvars`:

```hcl
aws_region         = "us-east-1"
project_name       = "aiops-multi-agent"
incident_table_name = "aiops-incidents"
default_email      = "nimish.mehta@gmail.com"
sender_email       = "noreply@aiops.example.com"
enable_ses         = false  # Set to true after SES verification
```

2. **Deploy Infrastructure**

```bash
cd phase-6-multi-agent
terraform init
terraform plan
terraform apply
```

3. **(Optional) Verify SES Emails**

If `enable_ses = true`, verify both sender and recipient emails:

```bash
# Check verification status
aws ses get-identity-verification-attributes \
  --identities noreply@aiops.example.com nimish.mehta@gmail.com
```

Click verification links in emails sent by AWS.

## Testing

### Test Multi-Agent System

```bash
# Trigger a test incident (EC2 termination)
aws ec2 terminate-instances --instance-ids i-1234567890abcdef0

# Check Lambda logs
aws logs tail /aws/lambda/aiops-multi-agent-orchestrator --follow

# Query incident in DynamoDB
aws dynamodb get-item \
  --table-name aiops-incidents \
  --key '{"incident_id": {"S": "incident-XXXXX"}}'
```

### Verify Agent Execution

Check CloudWatch Logs for structured logs from each agent:

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/aiops-multi-agent-orchestrator \
  --filter-pattern '{ $.agent_type = "triage" }'
```

### Check Email Notifications

If SES is enabled, check email at `nimish.mehta@gmail.com` for incident notifications.

## Configuration

### Change Windows

Modify blocked change windows in `variables.tf`:

```hcl
blocked_windows = [
  {
    day        = 4  # Friday
    start_hour = 16 # 4 PM
    end_hour   = 23 # 11 PM
  }
]
```

### Risk Thresholds

Risk scores are calculated based on:
- Change window compliance (0.3 if blocked)
- Policy compliance (0.4 if non-compliant)
- SLO budget (0.2 if exhausted)
- Blast radius (0.1-0.3 based on scope)

Approval is required if risk score > 0.5.

### Agent Configuration

Each agent can be configured via environment variables or the `agent_config` dict in `index.py`.

## Metrics

The system publishes CloudWatch metrics to these namespaces:

- `AIOps/Triage` - Classification, severity, noise scores
- `AIOps/Telemetry` - Anomalies detected, health scores
- `AIOps/Risk` - Risk scores, approval requirements
- `AIOps/Remediation` - Remediation attempts, success rates
- `AIOps/Communications` - Notifications sent/failed

## Cost Estimate

- Lambda invocations: $0 (free tier)
- Bedrock API calls: ~$3-5/month (5 agents × multiple calls)
- DynamoDB: $0.75/month (on-demand)
- SES emails: $0 (free tier for first 62,000 emails)
- CloudWatch Logs: $0 (free tier)

**Total: ~$4-6/month**

## Troubleshooting

### Agents Not Executing

Check IAM permissions for the Lambda role. Ensure all required permissions are granted.

### Email Not Sending

1. Verify SES email identities are verified
2. Check SES sending limits (sandbox mode limits to verified emails only)
3. Review Lambda logs for SES errors

### High Risk Scores

Review risk factors in DynamoDB incident records. Adjust change windows or SLO thresholds as needed.

## Next Steps

- Implement multi-region deployment (Phase 7)
- Add custom ML models for pattern recognition (Phase 8)
- Add Kubernetes support (Phase 9)
