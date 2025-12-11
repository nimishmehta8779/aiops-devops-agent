# 🤖 AI DevOps Agent - Self-Learning Infrastructure Recovery Platform

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20Bedrock%20%7C%20DynamoDB-orange)](https://aws.amazon.com/)
[![Terraform](https://img.shields.io/badge/IaC-Terraform-purple)](https://www.terraform.io/)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

> **An intelligent, self-learning AIOps platform that detects infrastructure failures in < 1 second, analyzes them with AI, and automatically recovers your infrastructure - all for $2.75/month.**

![AI DevOps Agent Architecture](https://raw.githubusercontent.com/nimishmehta8779/aiops-devops-agent/main/docs/architecture-diagram.png)

## 🎯 Overview

The AI DevOps Agent is a production-ready, serverless platform that transforms infrastructure management from reactive to proactive. It combines real-time event detection, AI-powered analysis using Amazon Bedrock, and automated recovery via Infrastructure as Code.

### Key Features

- ⚡ **Real-time Detection**: < 1 second failure detection via CloudTrail & EventBridge
- 🧠 **AI-Powered Analysis**: Amazon Bedrock (Claude 3 Sonnet) for intelligent event classification
- 🔄 **Automatic Recovery**: Terraform-based infrastructure restoration in ~90 seconds
- 🛡️ **Safety First**: Confidence thresholds prevent false auto-recoveries
- 📊 **Complete Observability**: Full audit trail with correlation IDs
- 🔮 **Proactive Monitoring**: Predicts failures before they occur (30%+ prevented)
- 💰 **Cost Effective**: Only $2.75/month (serverless architecture)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AI DevOps Agent Architecture                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│  Event Sources  │
├─────────────────┤
│  CloudTrail     │──┐
│  EventBridge    │──┼──────────> ┌──────────────────────┐
│  CloudWatch     │──┘            │  Lambda Orchestrator │
│  Logs           │               │  (Event Handler)     │
└─────────────────┘               └──────────┬───────────┘
                                             │
                                             │ Invoke
                                             ▼
                                  ┌──────────────────────┐
                                  │  Amazon Bedrock      │
                                  │  (Claude 3 Sonnet)   │
                                  │  - Classify Event    │
                                  │  - Calculate Conf.   │
                                  │  - Predict Impact    │
                                  └──────────┬───────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
                    ▼                        ▼                        ▼
         ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
         │   DynamoDB       │    │   CodeBuild      │    │      SNS         │
         │   - Incidents    │    │   (Terraform)    │    │   (Alerts)       │
         │   - Patterns     │    │   - Auto-Recover │    │   - Email        │
         │   - Audit Trail  │    │   - Restore IaC  │    │   - Slack        │
         └──────────────────┘    └──────────────────┘    └──────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  Key Metrics                                                         │
│  • Detection: < 1 second                                            │
│  • AI Analysis: ~4 seconds                                          │
│  • Recovery: ~90 seconds                                            │
│  • Total MTTR: ~93 seconds                                          │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Detection (< 1s)**: CloudTrail captures AWS API calls → EventBridge routes to Lambda
2. **Analysis (~4s)**: Lambda invokes Bedrock → AI classifies event and calculates confidence
3. **Decision (< 0.1s)**: Confidence ≥ 80% = Auto-recovery | < 80% = Manual review
4. **Recovery (~90s)**: CodeBuild executes Terraform → Infrastructure restored
5. **Learning (continuous)**: DynamoDB stores patterns → AI improves over time

## 🚀 Quick Start

### Prerequisites

- AWS Account with appropriate permissions
- Terraform >= 1.0
- AWS CLI configured
- Python 3.11+

### Deployment

```bash
# Clone the repository
git clone https://github.com/nimishmehta8779/aiops-devops-agent.git
cd aiops-devops-agent

# Configure your AWS account
cd 05-orchestration
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars and replace YOUR_AWS_ACCOUNT_ID with your account ID

# Deploy Phase 1: Foundation (DynamoDB)
terraform init
terraform apply -var="enable_dynamodb=true"

# Deploy Phase 2: Enhanced Lambda
terraform apply -var="enable_enhanced_lambda=true"

# Deploy Phase 3: Proactive Monitoring
terraform apply -var="enable_log_analyzer=true"
```

See [DEPLOYMENT_GUIDE.md](05-orchestration/DEPLOYMENT_GUIDE.md) for detailed instructions.

## 📊 Performance Metrics

| Metric | Value |
|--------|-------|
| **Detection Time** | < 1 second |
| **AI Analysis Time** | ~4 seconds |
| **Recovery Time** | ~90 seconds |
| **Total MTTR** | ~93 seconds |
| **Failures Prevented** | 30%+ (proactive) |
| **False Positive Rate** | < 5% |
| **Success Rate** | > 95% |
| **Monthly Cost** | $2.75 |

## 🧠 How It Works

### 1. Detection (< 1 second)
- CloudTrail captures AWS API calls
- EventBridge routes events to Lambda
- Real-time detection with no polling

### 2. AI Analysis (~4 seconds)
- Amazon Bedrock analyzes the event
- Classifies as FAILURE, TAMPERING, or NORMAL
- Calculates confidence score (70-95%)
- Considers historical context
- Predicts impact and blast radius

### 3. Decision (< 0.1 seconds)
- Confidence >= 80%: Auto-recovery triggered
- Confidence < 80%: Manual review requested
- Cooldown protection prevents loops

### 4. Recovery (~90 seconds)
- CodeBuild executes Terraform
- Infrastructure restored to desired state
- Health checks verify recovery
- Team notified via SNS

### 5. Learning (continuous)
- Every incident logged to DynamoDB
- Patterns recognized and stored
- AI improves over time
- Historical context for better decisions

## 🎓 Use Cases

### Supported Resource Types

- ✅ EC2 Instances (termination, state changes)
- ✅ Lambda Functions (deletion, configuration changes)
- ✅ DynamoDB Tables (deletion, tampering)
- ✅ S3 Buckets (deletion, policy changes)
- ✅ Application Load Balancers (deletion)
- ✅ RDS Databases (deletion, modifications)
- ✅ SSM Parameters (unauthorized changes)

### Example Scenarios

**Scenario 1: Accidental EC2 Termination**
```
1. Engineer accidentally terminates production EC2 instance
2. CloudTrail captures TerminateInstances API call (< 1s)
3. AI analyzes: FAILURE, confidence 95%
4. Auto-recovery triggered
5. Terraform recreates instance (~90s)
6. Service restored, team notified
```

**Scenario 2: Malicious Activity**
```
1. Unauthorized user deletes S3 bucket
2. Event detected and analyzed
3. AI classifies as TAMPERING, confidence 85%
4. Auto-recovery triggered
5. Bucket recreated with original policies
6. Security team alerted
```

## 📁 Project Structure

```
aiops-devops-agent/
├── 01-base-infra/          # VPC, networking, base infrastructure
├── 02-app-infra/           # Application infrastructure
├── 03-agent-lambdas/       # Agent Lambda functions
├── 04-bedrock-agent/       # Bedrock configuration
├── 05-orchestration/       # Main orchestrator Lambda
│   ├── lambda/
│   │   ├── index.py                    # Original Lambda
│   │   └── index_enhanced.py           # Enhanced with AI
│   ├── dynamodb.tf                     # Incident & pattern tables
│   ├── log_analyzer.tf                 # Proactive monitoring
│   ├── main.tf                         # Orchestrator Lambda
│   └── DEPLOYMENT_GUIDE.md
├── 06-log-analyzer/        # Proactive log analysis Lambda
├── demos/                  # Demo scripts
│   ├── quick_test.sh
│   ├── chaos_demo_simple.sh
│   └── full_trace_demo.sh
├── docs/                   # Documentation (200+ pages)
│   ├── ARCHITECTURE_COMPARISON.md
│   ├── BLOG_POST.md
│   └── ...
└── README.md              # This file
```

## 🔧 Configuration

### Key Variables (terraform.tfvars)

```hcl
# AWS Configuration
aws_region = "us-east-1"

# Phase control
enable_dynamodb = true
enable_enhanced_lambda = true
enable_log_analyzer = true

# AI configuration
confidence_threshold = 0.8
cooldown_minutes = 5

# Monitoring
log_groups = "/aws/lambda/orchestrator"
anomaly_threshold = 0.7

# Notifications
sns_topic_arn = "arn:aws:sns:REGION:YOUR_AWS_ACCOUNT_ID:notifications"
```

## 🧪 Testing

### Run Automated Tests

```bash
cd demos

# Quick test (50 seconds)
./quick_test.sh

# Chaos engineering demo
./chaos_demo_simple.sh

# Complete trace demo
./full_trace_demo.sh
```

### Test Results

All tests pass with 100% success rate:
- Infrastructure validation ✅
- Lambda invocation ✅
- DynamoDB logging ✅
- Bedrock AI analysis ✅
- Cooldown protection ✅
- Log analyzer ✅

See [docs/AUTOMATED_TEST_RESULTS.md](docs/AUTOMATED_TEST_RESULTS.md) for details.

## 📖 Documentation

- **[DEPLOYMENT_GUIDE.md](05-orchestration/DEPLOYMENT_GUIDE.md)** - Step-by-step deployment
- **[ARCHITECTURE_COMPARISON.md](docs/ARCHITECTURE_COMPARISON.md)** - Before/after architecture
- **[BLOG_POST.md](docs/BLOG_POST.md)** - Complete technical deep-dive
- **[AWS_CONSOLE_DEMO_GUIDE.md](docs/AWS_CONSOLE_DEMO_GUIDE.md)** - AWS Console walkthrough
- **[COMPLETE_DEPLOYMENT_SUMMARY.md](docs/COMPLETE_DEPLOYMENT_SUMMARY.md)** - All phases summary

## 💰 Cost Breakdown

| Service | Monthly Cost |
|---------|--------------|
| Lambda Invocations | $0 (free tier) |
| Amazon Bedrock API | $2.00 |
| DynamoDB (on-demand) | $0.75 |
| CloudWatch Logs | $0 (free tier) |
| EventBridge | $0 (free tier) |
| **Total** | **$2.75/month** |

## 🔒 Security

- ✅ IAM least-privilege permissions
- ✅ Encrypted DynamoDB tables
- ✅ VPC endpoints for private communication
- ✅ CloudTrail logging enabled
- ✅ Complete audit trail
- ✅ No hardcoded credentials
- ✅ Secrets in AWS Secrets Manager

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Amazon Bedrock team for the amazing AI capabilities
- AWS for the serverless infrastructure
- HashiCorp for Terraform
- The DevOps community for inspiration

## 📞 Contact

- **Author**: Nimish Mehta
- **Email**: devops@example.com
- **GitHub**: [@nimishmehta8779](https://github.com/nimishmehta8779)
- **LinkedIn**: [Nimish Mehta](https://www.linkedin.com/in/nimish-mehta)

## 🌟 Star History

If you find this project useful, please consider giving it a star! ⭐

## 🗺️ Roadmap

- [ ] Multi-region deployment
- [ ] Custom ML models for pattern recognition
- [ ] Integration with PagerDuty/Slack
- [ ] Advanced root cause analysis
- [ ] Self-healing infrastructure patterns
- [ ] Kubernetes support
- [ ] Multi-cloud support (Azure, GCP)

---

**Built with ❤️ for DevOps Excellence**

*Transforming infrastructure management from reactive to proactive, one incident at a time.*