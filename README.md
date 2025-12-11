# AIOps Multi-Agent DevOps Automation Platform

An intelligent, event-driven DevOps automation platform that uses multiple AI agents to detect, analyze, and automatically remediate infrastructure failures across AWS services.

## 🎯 Overview

This platform implements a sophisticated multi-agent system that provides:
- **Real-time Failure Detection**: Sub-second detection via EventBridge
- **Intelligent Triage**: AI-powered incident classification and deduplication
- **Risk Assessment**: Automated safety validation before remediation
- **Autonomous Recovery**: Self-healing infrastructure with rollback capabilities
- **Human-in-the-Loop**: Approval workflows for high-risk changes

## 🏗️ Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        EVENT SOURCES                             │
├─────────────────────────────────────────────────────────────────┤
│  CloudTrail │ EventBridge │ CloudWatch │ EKS Events │ Custom    │
└──────┬──────────────┬──────────┬──────────┬──────────┬──────────┘
       │              │          │          │          │
       └──────────────┴──────────┴──────────┴──────────┘
                              │
                    ┌─────────▼─────────┐
                    │  EventBridge Rule │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   ORCHESTRATOR    │
                    │   Lambda Function │
                    └─────────┬─────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
   │ TRIAGE  │          │  RISK   │          │REMEDIATE│
   │  Agent  │─────────▶│  Agent  │─────────▶│  Agent  │
   └────┬────┘          └────┬────┘          └────┬────┘
        │                    │                     │
        │              ┌─────▼─────┐               │
        │              │ TELEMETRY │               │
        │              │   Agent   │               │
        │              └───────────┘               │
        │                                          │
        └──────────────────┬───────────────────────┘
                           │
                    ┌──────▼──────┐
                    │    COMMS    │
                    │    Agent    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Notifications│
                    │ (Email/SNS) │
                    └─────────────┘
```

### Agent Workflow & Decision Making

#### 1. **Triage Agent** (First Responder)
**Purpose**: Classify and prioritize incidents

**Decision Process**:
```python
1. Calculate Fingerprint
   ├─ Hash(event_name + resource_type + resource_id + region)
   └─ Check DynamoDB for duplicates (24h window)

2. Classify Severity
   ├─ CRITICAL: Production failures, data loss
   ├─ HIGH: Service degradation, security events
   ├─ MEDIUM: Performance issues, warnings
   └─ LOW: Informational, routine changes

3. Assess Business Impact
   ├─ Affected Services: Parse event details
   ├─ Blast Radius: localized | regional | global
   ├─ Estimated Downtime: Based on resource type
   └─ Customer Impact: Severity mapping

4. Noise Filtering
   ├─ Duplicate Detection: Suppress if seen recently
   ├─ Noise Score: 0.0 (unique) to 1.0 (spam)
   └─ Action Required: severity >= MEDIUM && !duplicate
```

**Output**: Classification, deduplication status, priority

---

#### 2. **Telemetry Agent** (Data Collector)
**Purpose**: Gather contextual metrics and logs

**Decision Process**:
```python
1. Collect Metrics (CloudWatch)
   ├─ EC2: CPU, Network, Disk
   ├─ RDS: Connections, IOPS, Latency
   ├─ Lambda: Invocations, Errors, Duration
   └─ EKS: Pod metrics, Node health

2. Retrieve Logs (CloudWatch Logs)
   ├─ Last 15 minutes of application logs
   ├─ Error pattern detection
   └─ Correlation with event timestamp

3. Trace Analysis (X-Ray)
   ├─ Distributed trace collection
   ├─ Error identification
   └─ Performance bottleneck detection

4. Anomaly Detection
   ├─ Compare current vs baseline metrics
   ├─ Statistical deviation analysis
   └─ Flag abnormal patterns

5. Health Score Calculation
   └─ 0.0 (critical) to 1.0 (healthy)
```

**Output**: Metrics, logs, traces, anomalies, health score

---

#### 3. **Risk Agent** (Safety Validator)
**Purpose**: Validate change safety and compliance

**Decision Process**:
```python
1. Check Change Window
   ├─ Current Time vs Blocked Windows
   ├─ Default: Block Friday 4PM-11PM
   └─ Allow 24/7 except blocked periods

2. Validate Policy Compliance (AWS Config)
   ├─ Query compliance status for resource
   ├─ Check security group rules
   ├─ Verify encryption settings
   └─ Validate backup policies

3. Check SLO/Error Budget
   ├─ Query recent error rates
   ├─ Calculate budget consumption
   └─ Block if budget exhausted

4. Assess Blast Radius
   ├─ EC2: localized (single instance)
   ├─ RDS: regional (database cluster)
   ├─ DynamoDB: critical (data store)
   └─ S3: critical (storage layer)

5. Calculate Risk Score
   risk_score = (
       0.3 * (1 if !change_window_ok else 0) +
       0.3 * (1 if !policy_compliant else 0) +
       0.2 * (1 if !slo_budget_ok else 0) +
       0.2 * blast_radius_weight
   )

6. Approval Decision
   approval_required = (
       risk_score > 0.5 OR
       !change_window_ok OR
       !policy_compliant
   )
```

**Output**: Risk score, approval requirement, safety validation

---

#### 4. **Remediation Agent** (Action Executor)
**Purpose**: Generate and execute recovery plans

**Decision Process**:
```python
1. Generate Runbook (Bedrock AI)
   ├─ Query Knowledge Base for similar incidents
   ├─ Construct prompt with context
   ├─ Invoke Bedrock (Amazon Titan)
   └─ Parse JSON runbook response

2. Fallback Logic (if Bedrock fails)
   ├─ EC2: SSM Automation → AWS-StartEC2Instance
   ├─ RDS: SSM Automation → AWS-StartRdsInstance
   ├─ EKS: Lambda Invoke → aiops-kubernetes-agent
   └─ Lambda: Terraform → redeploy function

3. Assess Remediation Risk
   ├─ Check Risk Agent approval status
   ├─ Evaluate runbook complexity
   └─ Determine auto-executability

4. Execute or Queue
   IF approval_required:
       ├─ Store in DynamoDB (pending_approval)
       ├─ Send notification to approvers
       └─ Wait for manual approval
   ELSE:
       ├─ Execute runbook steps sequentially
       ├─ Monitor execution status
       └─ Rollback on failure

5. Execution Methods
   ├─ SSM: start_automation_execution()
   ├─ Lambda: invoke() with payload
   ├─ Terraform: trigger CodeBuild project
   └─ Manual: human intervention required
```

**Output**: Runbook, execution results, approval status

---

#### 5. **Communications Agent** (Notifier)
**Purpose**: Human-readable updates and notifications

**Decision Process**:
```python
1. Generate Incident Summary (Bedrock AI)
   ├─ Aggregate all agent results
   ├─ Create human-readable narrative
   └─ Include impact, status, next steps

2. Determine Recipients
   ├─ CRITICAL/HIGH: Escalation list + on-call
   ├─ MEDIUM: DevOps team
   └─ LOW: Monitoring dashboard only

3. Select Notification Channels
   ├─ Email (SES): All severities
   ├─ SNS: CRITICAL/HIGH only
   └─ Slack/PagerDuty: Future integration

4. Send Notifications
   ├─ Format email with incident details
   ├─ Include approval link (if required)
   └─ Track delivery status

5. Store Communication Log
   └─ Update DynamoDB incident record
```

**Output**: Notifications sent, delivery status

---

## 🔄 End-to-End Workflow Example

### Scenario: EC2 Instance Stopped

```
1. EVENT DETECTION (t=0ms)
   ├─ EventBridge detects EC2 state change
   ├─ Event: {"detail-type": "EC2 Instance State-change Notification"}
   └─ Trigger: Orchestrator Lambda

2. ORCHESTRATOR (t=50ms)
   ├─ Parse event → resource_type='ec2', resource_id='i-xxx'
   ├─ Create incident record in DynamoDB
   └─ Initialize agent coordination

3. TRIAGE AGENT (t=100ms)
   ├─ Fingerprint: hash('EC2StateChange-ec2-i-xxx-us-east-1')
   ├─ Duplicate check: NOT FOUND
   ├─ Classification: MEDIUM (unplanned stop)
   ├─ Business Impact: localized, 30min downtime
   └─ Decision: PROCEED (requires_immediate_action=True)

4. TELEMETRY AGENT (t=300ms)
   ├─ CloudWatch Metrics: CPU=0% (stopped)
   ├─ Logs: Last entry 2min ago (normal shutdown)
   ├─ X-Ray: No active traces
   ├─ Health Score: 0.0 (instance down)
   └─ Decision: UNHEALTHY

5. RISK AGENT (t=500ms)
   ├─ Change Window: OK (Thursday 11PM)
   ├─ Policy Compliance: OK (no violations)
   ├─ SLO Budget: OK (99.9% uptime)
   ├─ Blast Radius: localized (0.1 weight)
   ├─ Risk Score: 0.1 (LOW)
   └─ Decision: SAFE TO PROCEED (approval_required=False)

6. REMEDIATION AGENT (t=1000ms)
   ├─ Bedrock Query: "How to recover stopped EC2?"
   ├─ Fallback: SSM Automation (AWS-StartEC2Instance)
   ├─ Runbook: [{"action": "ssm", "params": {"InstanceId": "i-xxx"}}]
   ├─ Risk Check: approval_required=False
   ├─ Execute: ssm.start_automation_execution()
   └─ Result: Execution ID: abc-123 (SUCCESS)

7. COMMUNICATIONS AGENT (t=1500ms)
   ├─ Summary: "EC2 instance i-xxx stopped unexpectedly. 
   │            Automated recovery initiated via SSM.
   │            Expected recovery time: 2 minutes."
   ├─ Recipients: devops@example.com
   ├─ Send Email: SUCCESS
   └─ Update DynamoDB: workflow_state=COMPLETED

8. VERIFICATION (t=120s)
   ├─ SSM Automation completes
   ├─ Instance state: running
   └─ Health check: PASS
```

**Total Time to Recovery**: ~2 minutes (fully automated)

---

## 📦 Supported Resources

| Resource | Detection | Remediation | Method |
|----------|-----------|-------------|--------|
| **EC2** | EventBridge (real-time) | Start instance | SSM Automation |
| **RDS** | EventBridge (real-time) | Start DB instance | SSM Automation |
| **EKS** | CloudWatch Schedule (1min) | Restart pod/rollback | Lambda (K8s Agent) |
| **Lambda** | CloudWatch Logs | Redeploy function | Terraform/CodeBuild |
| **DynamoDB** | CloudTrail (15min) | Restore table | Terraform |
| **S3** | CloudTrail (15min) | Recreate bucket | Terraform |

---

## 🚀 Deployment

### Prerequisites
- AWS Account with appropriate permissions
- Terraform >= 1.0
- AWS CLI configured
- Python 3.9+

### Quick Start

```bash
# 1. Clone repository
git clone <repository-url>
cd aiops-devops-agent

# 2. Configure variables
cp 01-multi-agent/terraform.tfvars.example 01-multi-agent/terraform.tfvars
# Edit terraform.tfvars with your AWS account details

# 3. Deploy infrastructure (in order)
cd 01-multi-agent && terraform init && terraform apply
cd ../03-ml-models && terraform init && terraform apply
cd ../04-kubernetes && terraform init && terraform apply
cd ../05-knowledge-base && terraform init && terraform apply

# 4. Deploy test infrastructure (optional)
cd ../test-infrastructure && terraform init && terraform apply
```

### Module Deployment Order

1. **01-multi-agent**: Core orchestrator and agents
2. **03-ml-models**: ML-based pattern analysis
3. **04-kubernetes**: EKS cluster and K8s agent
4. **05-knowledge-base**: Bedrock KB for runbook storage
5. **test-infrastructure**: Test EC2/RDS resources

---

## 🧪 Testing

### Run Automated Recovery Demo

```bash
# EC2 Recovery Demo
./demos/scripts/live_recovery_demo.sh

# EKS Rollback Demo
./demos/scripts/live_recovery_demo_rollback.sh

# Comprehensive Test
./demos/scripts/comprehensive_test.sh
```

### Manual Testing

```bash
# Trigger EC2 failure
aws ec2 stop-instances --instance-ids i-xxx

# Monitor orchestrator logs
aws logs tail /aws/lambda/aiops-multi-agent-orchestrator --follow

# Check incident status
aws dynamodb get-item --table-name aiops-incidents \
  --key '{"incident_id": {"S": "incident-xxx"}}'
```

---

## 📊 Monitoring & Observability

### CloudWatch Dashboards
- **Agent Performance**: Execution times, success rates
- **Incident Metrics**: Detection latency, recovery time
- **Resource Health**: Service availability, error rates

### Key Metrics
- `AIOps/Triage/IncidentsClassified`
- `AIOps/Risk/ApprovalRequired`
- `AIOps/Remediation/RemediationAttempts`
- `AIOps/Communications/NotificationsSent`

### Logs
- `/aws/lambda/aiops-multi-agent-orchestrator`
- `/aws/lambda/aiops-kubernetes-agent`
- `/aws/lambda/aiops-ml-models-agent`

---

## 🔐 Security

### IAM Permissions
- **Orchestrator**: Read CloudWatch, DynamoDB, invoke Bedrock
- **Remediation**: SSM automation, Lambda invoke, EC2/RDS start
- **K8s Agent**: EKS cluster access, kubectl operations

### Data Protection
- All logs encrypted at rest (KMS)
- Secrets managed via AWS Secrets Manager
- Network isolation via VPC security groups

### Compliance
- AWS Config integration for policy validation
- Change window enforcement
- Approval workflows for high-risk actions

---

## 🛠️ Configuration

### Environment Variables

**Orchestrator Lambda**:
```bash
INCIDENT_TABLE=aiops-incidents
BEDROCK_MODEL_ID=amazon.titan-text-express-v1
KNOWLEDGE_BASE_ID=<kb-id>
```

**Risk Agent**:
```bash
BLOCKED_WINDOWS='[{"day": 4, "start_hour": 16, "end_hour": 23}]'
SLO_ERROR_BUDGET_THRESHOLD=0.001
```

### Terraform Variables

```hcl
# 01-multi-agent/terraform.tfvars
project_name = "aiops"
aws_region = "us-east-1"
default_email = "devops@example.com"
enable_ses = true
```

---

## 📈 Cost Optimization

### Estimated Monthly Costs (us-east-1)

| Service | Usage | Cost |
|---------|-------|------|
| Lambda | 10K invocations/month | $0.20 |
| DynamoDB | 1GB storage, 100 WCU/RCU | $1.50 |
| CloudWatch | 10GB logs, 100 metrics | $5.00 |
| Bedrock | 1M tokens/month | $3.00 |
| EKS | 1 cluster (control plane) | $73.00 |
| **Total** | | **~$83/month** |

### Cost Reduction Tips
- Use Lambda reserved concurrency
- Enable DynamoDB auto-scaling
- Set CloudWatch log retention to 7 days
- Use Bedrock on-demand pricing

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🆘 Troubleshooting

### Common Issues

**Issue**: Orchestrator not triggering
- **Check**: EventBridge rule is enabled
- **Check**: Lambda has EventBridge permissions
- **Fix**: `aws events enable-rule --name aiops-multi-agent-cloudtrail-events`

**Issue**: Remediation fails with AccessDenied
- **Check**: Lambda IAM role has `ec2:StartInstances`, `rds:StartDBInstance`
- **Fix**: Update `01-multi-agent/iam.tf` and redeploy

**Issue**: Bedrock returns "Error generating response"
- **Check**: Model access enabled in Bedrock console
- **Check**: IAM permissions for `bedrock:InvokeModel`
- **Fix**: Enable model access or switch to fallback logic

---

## 📚 Additional Resources

- [Architecture Deep Dive](docs/ARCHITECTURE.md)
- [Agent Framework Guide](docs/AGENT_FRAMEWORK.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [API Reference](docs/API_REFERENCE.md)

---

## 🎓 Learn More

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [Multi-Agent Systems](https://en.wikipedia.org/wiki/Multi-agent_system)
- [Site Reliability Engineering](https://sre.google/)

---

**Built with ❤️ for DevOps Engineers**