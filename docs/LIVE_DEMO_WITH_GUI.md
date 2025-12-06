# 🎬 LIVE DEMO WITH AWS CONSOLE GUI CHECKS

## Pre-Demo Setup

### AWS Console Tabs to Open

Open these tabs in your AWS Console (us-east-1 region):

1. **Lambda** - https://console.aws.amazon.com/lambda/home?region=us-east-1#/functions
2. **DynamoDB** - https://console.aws.amazon.com/dynamodbv2/home?region=us-east-1#tables
3. **CloudWatch Logs** - https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups
4. **EventBridge** - https://console.aws.amazon.com/events/home?region=us-east-1#/rules
5. **CodeBuild** - https://console.aws.amazon.com/codesuite/codebuild/projects?region=us-east-1
6. **CloudWatch Metrics** - https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#metricsV2:

---

## 🎯 PART 1: VERIFY SYSTEM (2 minutes)

### Step 1.1: Check Lambda Functions

**CLI:**
```bash
aws lambda list-functions --query 'Functions[?contains(FunctionName, `aiops`)].{Name:FunctionName,Handler:Handler,Runtime:Runtime}' --output table
```

**AWS Console - Lambda:**
✅ Navigate to: Lambda > Functions
✅ You should see:
   - `aiops-devops-agent-orchestrator` (Runtime: Python 3.11, Handler: index_enhanced.handler)
   - `aiops-devops-agent-log-analyzer` (Runtime: Python 3.11, Handler: index.handler)

**What to check:**
- [ ] Both functions show "Active" status (green checkmark)
- [ ] Last modified date is recent
- [ ] No errors in the function overview

**Screenshot this!** 📸

---

### Step 1.2: Check DynamoDB Tables

**CLI:**
```bash
aws dynamodb list-tables --query 'TableNames[?contains(@, `aiops`)]' --output table
```

**AWS Console - DynamoDB:**
✅ Navigate to: DynamoDB > Tables
✅ You should see:
   - `aiops-devops-agent-incidents` (Status: Active)
   - `aiops-devops-agent-patterns` (Status: Active)

**What to check:**
- [ ] Both tables show "Active" status
- [ ] Item count (may be 0 if no incidents yet)
- [ ] Table size

**Click on `aiops-devops-agent-incidents`:**
- [ ] Check "Indexes" tab - should show 3 GSIs:
  - `resource-type-index`
  - `resource-timestamp-index`
  - `workflow-state-index`

**Screenshot this!** 📸

---

### Step 1.3: Check EventBridge Rules

**CLI:**
```bash
aws events list-rules --query 'Rules[?contains(Name, `aiops`)].{Name:Name,State:State,Schedule:ScheduleExpression}' --output table
```

**AWS Console - EventBridge:**
✅ Navigate to: EventBridge > Rules
✅ You should see:
   - `aiops-devops-agent-failure-rule` (State: ENABLED)
   - `aiops-devops-agent-ec2-state-realtime` (State: ENABLED)
   - `aiops-devops-agent-log-analyzer-schedule` (State: ENABLED, Schedule: rate(5 minutes))

**What to check:**
- [ ] All rules show "Enabled" state
- [ ] Log analyzer schedule shows "rate(5 minutes)"
- [ ] Each rule has targets configured

**Screenshot this!** 📸

---

## 🎯 PART 2: REACTIVE RECOVERY DEMO (5 minutes)

### Step 2.1: Trigger a Test Event

**CLI:**
```bash
# Create test event
cat > test_demo.json <<'EOF'
{
  "detail-type": "AWS API Call via CloudTrail",
  "source": "aws.ssm",
  "detail": {
    "eventName": "PutParameter",
    "eventSource": "ssm.amazonaws.com",
    "userIdentity": {
      "arn": "arn:aws:iam::YOUR_AWS_ACCOUNT_ID:user/demo-user"
    },
    "requestParameters": {
      "name": "/demo/config/setting",
      "value": "test-value-changed",
      "type": "String"
    }
  }
}
EOF

# Invoke orchestrator
aws lambda invoke \
  --function-name aiops-devops-agent-orchestrator \
  --payload file://test_demo.json \
  --cli-binary-format raw-in-base64-out \
  response_demo.json

# Show response
cat response_demo.json | jq .
```

**AWS Console - Lambda:**
✅ Navigate to: Lambda > Functions > aiops-devops-agent-orchestrator
✅ Click "Monitor" tab
✅ Click "View CloudWatch logs"

**What to check in CloudWatch Logs:**
- [ ] New log stream created (timestamp-based)
- [ ] Log shows: "Handler invoked"
- [ ] Log shows: "correlation_id" generated
- [ ] Log shows: "Invoking Bedrock for enhanced analysis"
- [ ] Log shows: "Analysis complete: NORMAL" (or FAILURE/TAMPERING)

**Screenshot the logs!** 📸

---

### Step 2.2: Check Incident Record in DynamoDB

**CLI:**
```bash
# Query latest incident
aws dynamodb scan \
  --table-name aiops-devops-agent-incidents \
  --limit 1 \
  --scan-index-forward false \
  --query 'Items[0]' \
  --output json | jq .
```

**AWS Console - DynamoDB:**
✅ Navigate to: DynamoDB > Tables > aiops-devops-agent-incidents
✅ Click "Explore table items"
✅ Click "Scan" (or "Run")

**What to check:**
- [ ] New item appears with recent timestamp
- [ ] `incident_id` starts with "incident-"
- [ ] `resource_type` = "ssm"
- [ ] `resource_id` = "/demo/config/setting"
- [ ] `workflow_state` = "COMPLETED" (or other state)
- [ ] `event_details` contains full event JSON

**Click on the item to see full details:**
- [ ] Check all attributes
- [ ] Note the `correlation_id`

**Screenshot this!** 📸

---

### Step 2.3: Test Cooldown Protection

**CLI:**
```bash
# Invoke again immediately (should be in cooldown)
aws lambda invoke \
  --function-name aiops-devops-agent-orchestrator \
  --payload file://test_demo.json \
  --cli-binary-format raw-in-base64-out \
  response_cooldown.json

# Show response
cat response_cooldown.json | jq .
```

**Expected Response:**
```json
{
  "status": "cooldown",
  "correlation_id": "incident-xxx-yyy",
  "last_incident": "incident-abc-def"
}
```

**AWS Console - CloudWatch Logs:**
✅ Refresh the log stream
✅ Look for new log entry

**What to check:**
- [ ] Log shows: "Resource in cooldown period"
- [ ] Log shows: "last incident: incident-xxx"
- [ ] No new CodeBuild triggered
- [ ] No new DynamoDB item created (same count as before)

**Screenshot this!** 📸

---

## 🎯 PART 3: PROACTIVE MONITORING DEMO (5 minutes)

### Step 3.1: Check Log Analyzer Configuration

**CLI:**
```bash
aws lambda get-function-configuration \
  --function-name aiops-devops-agent-log-analyzer \
  --query 'Environment.Variables' \
  --output json | jq .
```

**AWS Console - Lambda:**
✅ Navigate to: Lambda > Functions > aiops-devops-agent-log-analyzer
✅ Click "Configuration" tab
✅ Click "Environment variables"

**What to check:**
- [ ] `ANOMALY_THRESHOLD` = "0.7"
- [ ] `LOG_GROUPS` = "/aws/lambda/aiops-devops-agent-orchestrator"
- [ ] `PATTERNS_TABLE` = "aiops-devops-agent-patterns"
- [ ] `SNS_TOPIC_ARN` = (your SNS topic)

**Screenshot this!** 📸

---

### Step 3.2: Manually Trigger Log Analyzer

**CLI:**
```bash
# Invoke log analyzer
aws lambda invoke \
  --function-name aiops-devops-agent-log-analyzer \
  --cli-binary-format raw-in-base64-out \
  response_log_analyzer.json

# Show results
cat response_log_analyzer.json | jq .
```

**Expected Response:**
```json
{
  "status": "ok",
  "analyzed_log_groups": 1,
  "results": [{
    "log_group": "/aws/lambda/aiops-devops-agent-orchestrator",
    "anomaly_count": 0,
    "failure_probability": 0.0,
    "urgency": "LOW"
  }]
}
```

**AWS Console - Lambda:**
✅ Navigate to: Lambda > Functions > aiops-devops-agent-log-analyzer
✅ Click "Monitor" tab
✅ Click "View CloudWatch logs"

**What to check in logs:**
- [ ] Log shows: "Analyzing log group: /aws/lambda/..."
- [ ] Log shows: "Extracted X error patterns"
- [ ] Log shows: "Anomaly count: 0" (if system healthy)
- [ ] Log shows: "Failure probability: 0.0"

**Screenshot this!** 📸

---

### Step 3.3: Check Pattern Baseline in DynamoDB

**CLI:**
```bash
aws dynamodb scan \
  --table-name aiops-devops-agent-patterns \
  --limit 5 \
  --output json | jq '.Items[] | {pattern_id, resource_type, occurrence_count}'
```

**AWS Console - DynamoDB:**
✅ Navigate to: DynamoDB > Tables > aiops-devops-agent-patterns
✅ Click "Explore table items"
✅ Click "Scan"

**What to check:**
- [ ] Items may be empty initially (patterns learned over time)
- [ ] If items exist, check `pattern_id`, `resource_type`, `occurrence_count`
- [ ] Note the baseline values

**Screenshot this!** 📸

---

### Step 3.4: Check EventBridge Schedule

**AWS Console - EventBridge:**
✅ Navigate to: EventBridge > Rules
✅ Click on `aiops-devops-agent-log-analyzer-schedule`

**What to check:**
- [ ] State: "Enabled"
- [ ] Schedule expression: "rate(5 minutes)"
- [ ] Target: Lambda function `aiops-devops-agent-log-analyzer`
- [ ] Next scheduled time (should be within 5 minutes)

**Click "Monitoring" tab:**
- [ ] Check "Invocations" graph (should show activity every 5 minutes)
- [ ] Check "Failed invocations" (should be 0)

**Screenshot this!** 📸

---

## 🎯 PART 4: CLOUDWATCH METRICS (3 minutes)

### Step 4.1: Check Custom Metrics

**CLI:**
```bash
aws cloudwatch list-metrics \
  --namespace "AIOps/DevOpsAgent" \
  --output table
```

**AWS Console - CloudWatch:**
✅ Navigate to: CloudWatch > Metrics > All metrics
✅ Search for namespace: "AIOps/DevOpsAgent"

**What to check:**
- [ ] Metrics exist for:
  - `IncidentCount` (by ResourceType, Classification)
  - `RecoveryDuration` (by ResourceType, Success)
- [ ] Click on a metric to see the graph

**If no metrics yet:**
- This is normal if no incidents have occurred
- Metrics will appear after first incident

**Screenshot this!** 📸

---

### Step 4.2: Check Lambda Metrics

**AWS Console - CloudWatch:**
✅ Navigate to: CloudWatch > Metrics > All metrics
✅ Click "Lambda" namespace
✅ Select "By Function Name"

**What to check for orchestrator:**
- [ ] Invocations (should show recent activity)
- [ ] Duration (should be ~3-5 seconds)
- [ ] Errors (should be 0)
- [ ] Throttles (should be 0)

**What to check for log analyzer:**
- [ ] Invocations (should show activity every 5 minutes)
- [ ] Duration (should be ~10-30 seconds)
- [ ] Errors (should be 0)

**Screenshot this!** 📸

---

## 🎯 PART 5: COMPLETE AUDIT TRAIL (2 minutes)

### Step 5.1: Query All Incidents

**CLI:**
```bash
aws dynamodb scan \
  --table-name aiops-devops-agent-incidents \
  --query 'Items[*].{ID:incident_id.S,Type:resource_type.S,State:workflow_state.S,Time:incident_timestamp.S}' \
  --output table
```

**AWS Console - DynamoDB:**
✅ Navigate to: DynamoDB > Tables > aiops-devops-agent-incidents
✅ Click "Explore table items"
✅ Click "Scan"
✅ Sort by "incident_timestamp" (descending)

**What to check:**
- [ ] All incidents listed chronologically
- [ ] Each has unique `incident_id`
- [ ] `workflow_state` progression visible
- [ ] `resource_type` and `resource_id` captured

**Click on an incident to see full details:**
- [ ] `event_details` (full event JSON)
- [ ] `llm_analysis` (AI analysis if available)
- [ ] `recovery_actions` (if recovery was triggered)
- [ ] `success` (true/false)
- [ ] `recovery_duration_seconds`

**Screenshot this!** 📸

---

### Step 5.2: Check CloudWatch Logs Insights

**AWS Console - CloudWatch:**
✅ Navigate to: CloudWatch > Logs > Insights
✅ Select log group: `/aws/lambda/aiops-devops-agent-orchestrator`
✅ Run this query:

```
fields @timestamp, correlation_id, level, message
| filter correlation_id like /incident/
| sort @timestamp desc
| limit 20
```

**What to check:**
- [ ] All log entries with correlation IDs
- [ ] Structured JSON format
- [ ] Complete workflow visible (DETECTING → ANALYZING → EXECUTING → COMPLETED)
- [ ] Timestamps show progression

**Try this query for errors:**
```
fields @timestamp, correlation_id, level, message
| filter level = "ERROR"
| sort @timestamp desc
| limit 20
```

**Screenshot this!** 📸

---

## 🎯 BONUS: ADVANCED CHECKS

### Check IAM Permissions

**AWS Console - IAM:**
✅ Navigate to: IAM > Roles
✅ Search for: "aiops-devops-agent"
✅ Click on `aiops-devops-agent-orchestrator-role`

**What to check:**
- [ ] Trust relationship allows Lambda service
- [ ] Policy includes:
  - Bedrock: InvokeModel
  - CodeBuild: StartBuild
  - DynamoDB: PutItem, GetItem, UpdateItem, Query
  - SNS: Publish
  - CloudWatch: PutMetricData

---

### Check CodeBuild Projects

**AWS Console - CodeBuild:**
✅ Navigate to: CodeBuild > Build projects
✅ Look for: `aiops-devops-agent-apply`

**What to check:**
- [ ] Project exists
- [ ] Source: Your Terraform repository
- [ ] Environment: Linux, standard image
- [ ] Buildspec: Uses Terraform commands

**Click "Build history":**
- [ ] Check if any builds were triggered by the agent
- [ ] Check build status (should be "Succeeded")

---

## 📊 DEMO SUMMARY CHECKLIST

After completing the demo, you should have verified:

### Infrastructure ✅
- [ ] 2 Lambda functions deployed and active
- [ ] 2 DynamoDB tables created with GSIs
- [ ] 3 EventBridge rules enabled
- [ ] 1 CodeBuild project configured

### Functionality ✅
- [ ] Incident detection working
- [ ] Incident logging to DynamoDB
- [ ] Correlation IDs generated
- [ ] Cooldown protection working
- [ ] Log analyzer running every 5 minutes
- [ ] Anomaly detection functional

### Observability ✅
- [ ] CloudWatch Logs showing structured logs
- [ ] CloudWatch Metrics (if incidents occurred)
- [ ] DynamoDB audit trail complete
- [ ] EventBridge invocations visible

### Screenshots Taken 📸
- [ ] Lambda functions list
- [ ] DynamoDB tables and items
- [ ] EventBridge rules
- [ ] CloudWatch Logs
- [ ] CloudWatch Metrics
- [ ] Incident details in DynamoDB

---

## 🎬 DEMO PRESENTATION TIPS

### For Each Step:
1. **Show CLI output first** (terminal)
2. **Then show AWS Console** (GUI verification)
3. **Explain what's happening** (narration)
4. **Highlight key points** (correlation IDs, AI analysis, etc.)

### Key Talking Points:
- ✅ "Detection happens in < 1 second"
- ✅ "AI analyzes with historical context"
- ✅ "Cooldown prevents recovery loops"
- ✅ "Complete audit trail for compliance"
- ✅ "Proactive monitoring prevents failures"
- ✅ "All for just $2.75/month!"

---

## 🚀 NEXT STEPS AFTER DEMO

1. **Share screenshots** with stakeholders
2. **Publish blog post** from `BLOG_POST.md`
3. **Create presentation** using screenshots
4. **Schedule technical deep-dive** for interested teams
5. **Plan production deployment**

---

**Demo Duration:** 15-20 minutes  
**Preparation Time:** 5 minutes  
**Wow Factor:** 🌟🌟🌟🌟🌟

**You're ready to impress!** 🎉
