# Phase 1 Deployment Summary

## Resources to be Created

### ✅ DynamoDB Tables (Phase 1 - Foundation)
1. **`aiops-devops-agent-incidents`**
   - Purpose: Store all incident records with full context
   - Billing: Pay-per-request (on-demand)
   - Features:
     - 3 Global Secondary Indexes for efficient querying
     - Point-in-time recovery enabled
     - TTL enabled for auto-cleanup
     - Server-side encryption

2. **`aiops-devops-agent-patterns`**
   - Purpose: Store log patterns for anomaly detection
   - Billing: Pay-per-request (on-demand)
   - Features:
     - 1 Global Secondary Index
     - Point-in-time recovery enabled
     - Server-side encryption

### ✅ IAM & Lambda (Updated)
3. **`orchestrator_role`** - IAM role for Lambda
4. **`orchestrator_policy`** - Updated with DynamoDB permissions
5. **`orchestrator` Lambda** - Updated environment variables:
   - `INCIDENT_TABLE`: aiops-devops-agent-incidents
   - `PATTERNS_TABLE`: aiops-devops-agent-patterns
   - `SNS_TOPIC_ARN`: (existing)

### ✅ EventBridge Rules (Existing - will be recreated)
6. **`infra_failure`** - CloudTrail API call monitoring
7. **`ec2_state_change`** - Real-time EC2 state changes
8. **EventBridge targets** - Connect rules to Lambda
9. **Lambda permissions** - Allow EventBridge to invoke Lambda

## Total Resources: 11

## Estimated Monthly Cost
- DynamoDB (on-demand): ~$1.25/month (assuming 1000 incidents/month)
- Lambda: $0 (within free tier)
- EventBridge: $0 (AWS events are free)
- **Total Phase 1 Cost: ~$1.25/month**

## What Happens After Deployment
1. ✅ All incidents will be logged to DynamoDB
2. ✅ Each incident gets a unique correlation ID
3. ✅ Foundation ready for Phase 2 (cooldown protection, historical context)
4. ✅ Complete audit trail for compliance

## Next Steps After Phase 1
- Test incident logging
- Verify DynamoDB records
- Move to Phase 2 (Enhanced Lambda)
