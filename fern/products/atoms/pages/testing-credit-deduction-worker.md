# Credit Deduction Worker - Testing Guide

## Overview

The credit deduction worker processes usage events from RabbitMQ and reports them to Stigg.

**Design Philosophy: Validate Before Reporting**

- ✅ **Entitlement check** - Verify feature is in customer's plan (via sidecar cache)
- ✅ **No planId in payload** - Stigg knows the customer's plan automatically
- ✅ **Stigg handles overage** - Usage beyond limits is handled by Stigg
- ✅ **Usage is never lost** - Events retry and go to DLQ for manual review
- ❌ **NO auto-provisioning** - Subscriptions must exist beforehand

---

## Queue Names

- **Main Queue**: `credit-deduction-queue`
- **Dead Letter Queue**: `credit-deduction-dlq`

---

## Message Format

**IMPORTANT:** Messages must be wrapped in a `WorkerTask` structure:

```json
{
  "taskId": "unique-task-id",
  "taskType": "REPORT_USAGE",
  "payload": {
    // Your actual data here
  },
  "createdAt": "2026-01-22T12:00:00.000Z"
}
```

| Field          | Type         | Required | Description                  |
| -------------- | ------------ | -------- | ---------------------------- |
| `taskId`       | string       | ✅       | Unique task identifier       |
| `taskType`     | string       | ✅       | Task type (`REPORT_USAGE`)   |
| `payload`      | object       | ✅       | The actual usage report data |
| `createdAt`    | ISO datetime | ✅       | When the task was created    |
| `attemptCount` | number       | ❌       | Retry count (default: 0)     |
| `priority`     | number       | ❌       | Message priority             |

---

## Validation Checks

**Optimized Flow (single sidecar call):**

1. Validate payload fields (sync, instant)
2. **Entitlement check** (Stigg Sidecar cache - <1ms!) - covers ALL checks
3. Report usage to Stigg

| Check                   | Error Code               | Retryable? | Description                                                   |
| ----------------------- | ------------------------ | ---------- | ------------------------------------------------------------- |
| Basic payload           | `INVALID_PAYLOAD`        | ❌ No      | Missing customerId, featureId, eventId, or invalid usageValue |
| Customer not found      | `ENTITLEMENT_DENIED`     | ❌ No      | Customer doesn't exist in Stigg                               |
| No subscription         | `NO_ACTIVE_SUBSCRIPTION` | ✅ Yes     | Customer has no subscription                                  |
| Subscription expired    | `NO_ACTIVE_SUBSCRIPTION` | ✅ Yes     | Customer's subscription expired                               |
| Feature not found       | `ENTITLEMENT_DENIED`     | ❌ No      | Feature doesn't exist in Stigg                                |
| **Feature not in plan** | `ENTITLEMENT_DENIED`     | ❌ No      | Feature not included in customer's plan                       |
| Usage limit exceeded    | ⚠️ Allowed               | N/A        | Stigg handles overage automatically                           |
| Sidecar errors          | `STIGG_ERROR`            | ✅ Yes     | Network/API errors when calling Stigg                         |

**What we DON'T block on:**

- ❌ planId in payload - Stigg applies usage to customer's active subscription
- ❌ Usage limits - Stigg handles overage automatically

---

## Your Stigg Customers (Dev)

| Name             | Customer ID (use this in `customerId`) |
| ---------------- | -------------------------------------- |
| Test PAYG User 1 | `test-payg-user-1`                     |
| Test PAYG User 2 | `test-payg-user-2`                     |
| Test PAYG User 3 | `test-payg-user-3`                     |

---

## Available Features (plan-payg)

| Feature Name                | Feature ID                    | Type                           |
| --------------------------- | ----------------------------- | ------------------------------ |
| Create with AI (Raw Events) | `feature-create-ai-agent-raw` | Metered (0.5 credits/creation) |
| TTS V2 Access               | `feature-tts-v2-access`       | Boolean                        |

---

## Test Scenarios

### Scenario 1: Happy Path - Customer with Active Subscription

Test a customer who has an active subscription and reports usage.
**Prerequisite:** Customer must have an active subscription in Stigg!

```json
{
  "taskId": "test-task-001",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-ai-agent-raw",
    "usageValue": 10,
    "eventTimestamp": "2026-01-22T12:00:00.000Z",
    "source": "manual-test"
  },
  "createdAt": "2026-01-22T12:00:00.000Z"
}
```

**Expected Behavior:**

- `getEntitlement` returns `hasAccess: true`
- Usage reported to Stigg (10 creations × 0.5 credits = 5 credits)
- ClickHouse audit log with `status: success`
- New Relic event: `UsageReportEvent` with `status: success`

---

### Scenario 2: No Active Subscription (Failure Case)

Test a customer who has NO active subscription - should fail and retry.

```json
{
  "taskId": "test-task-002",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-002",
    "customerId": "test-payg-user-2",
    "featureId": "feature-create-ai-agent-raw",
    "usageValue": 5,
    "eventTimestamp": "2026-01-22T12:05:00.000Z",
    "source": "manual-test"
  },
  "createdAt": "2026-01-22T12:05:00.000Z"
}
```

**Expected Behavior (when customer has NO subscription):**

- Validation fails with `NO_ACTIVE_SUBSCRIPTION` error code
- Message retries 3 times (2s, 4s, 8s exponential backoff)
- After retries exhausted → goes to DLQ
- New Relic event: `UsageValidationFailed` with `errorCode: NO_ACTIVE_SUBSCRIPTION`
- ClickHouse audit log with `status: failed`

**To make this test pass:** First create a subscription for the customer in Stigg!

---

### Scenario 3: Multiple Usage Reports (Same Customer)

Report multiple usage events for the same customer:

**First Event:**

```json
{
  "taskId": "test-task-003a",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-003a",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-ai-agent-raw",
    "usageValue": 1,
    "eventTimestamp": "2026-01-22T12:10:00.000Z",
    "source": "manual-test"
  },
  "createdAt": "2026-01-22T12:10:00.000Z"
}
```

**Second Event:**

```json
{
  "taskId": "test-task-003b",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-003b",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-ai-agent-raw",
    "usageValue": 2,
    "eventTimestamp": "2026-01-22T12:11:00.000Z",
    "source": "manual-test"
  },
  "createdAt": "2026-01-22T12:11:00.000Z"
}
```

**Expected Behavior:**

- Both events processed successfully
- Total usage: 3 creations = 1.5 credits consumed

---

### Scenario 4: Idempotency Test (Same Event ID)

Send the **same message twice** to verify Stigg's deduplication:

```json
{
  "taskId": "test-task-004",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-004-duplicate",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-ai-agent-raw",
    "usageValue": 100,
    "eventTimestamp": "2026-01-22T12:15:00.000Z",
    "source": "manual-test-idempotency"
  },
  "createdAt": "2026-01-22T12:15:00.000Z"
}
```

**Expected Behavior:**

- First message: Usage deducted (100 creations = 50 credits)
- Second message: Stigg returns cached result, NO double deduction
- ClickHouse will have 2 entries (audit only), but Stigg only charged once

---

### Scenario 5: Invalid Customer (Failure Case)

Test with a non-existent customer to trigger retry/DLQ:

```json
{
  "taskId": "test-task-005",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-005",
    "customerId": "invalid_customer_xyz",
    "featureId": "feature-create-ai-agent-raw",
    "usageValue": 10,
    "eventTimestamp": "2026-01-22T12:20:00.000Z",
    "source": "manual-test-failure"
  },
  "createdAt": "2026-01-22T12:20:00.000Z"
}
```

**Expected Behavior:**

- Will retry 3 times with exponential backoff (2s, 4s, 8s)
- After max retries, sent to DLQ: `credit-deduction-dlq`
- New Relic event: `UsageReportDLQ`
- ClickHouse logs with `status: failed`

---

### Scenario 6: Invalid Feature ID (Feature Doesn't Exist in Stigg)

Test with a non-existent feature - Stigg will return an error:

```json
{
  "taskId": "test-task-006",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-006",
    "customerId": "test-payg-user-1",
    "featureId": "feature-does-not-exist",
    "usageValue": 10,
    "eventTimestamp": "2026-01-22T12:25:00.000Z",
    "source": "manual-test-invalid-feature"
  },
  "createdAt": "2026-01-22T12:25:00.000Z"
}
```

**Expected Behavior:**

- Entitlement check fails: `hasAccess: false`, `accessDeniedReason: FEATURE_NOT_FOUND (4)`
- Validation fails with `ENTITLEMENT_DENIED` error code
- Message goes to DLQ (not retryable)
- ClickHouse logs with `status: failed`

---

### Scenario 7: Feature NOT in Customer's Plan (Critical!)

Test with a feature that **exists in Stigg** but is **NOT in the customer's plan**:

```json
{
  "taskId": "test-task-007",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-007",
    "customerId": "test-payg-user-1",
    "featureId": "feature-enterprise-only",
    "usageValue": 10,
    "eventTimestamp": "2026-01-22T12:27:00.000Z",
    "source": "manual-test-feature-not-in-plan"
  },
  "createdAt": "2026-01-22T12:27:00.000Z"
}
```

**Expected Behavior:**

- Entitlement check fails: `hasAccess: false`, `accessDeniedReason: NO_FEATURE_ENTITLEMENT (2)`
- Validation fails with `ENTITLEMENT_DENIED` error code
- Message goes to DLQ (not retryable - feature won't magically appear in plan)
- New Relic event: `UsageValidationFailed` with details
- ClickHouse logs with `status: failed`

**⚠️ Why This Matters:** Without this check, usage would be reported to Stigg even for features not in the plan!

---

### Scenario 8: Usage Limit Exceeded (Overage)

Test when customer has exceeded their usage quota:

```json
{
  "taskId": "test-task-008",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-008",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-ai-agent-raw",
    "usageValue": 999999,
    "eventTimestamp": "2026-01-22T12:28:00.000Z",
    "source": "manual-test-overage"
  },
  "createdAt": "2026-01-22T12:28:00.000Z"
}
```

**Expected Behavior (depends on plan configuration):**

- If plan allows overage: ✅ Success, Stigg tracks overage
- If plan blocks overage: Entitlement check fails with `accessDeniedReason: USAGE_LIMIT_EXCEEDED (3)`
- Check Stigg dashboard for overage webhook

---

### Scenario 9: Invalid Payload (Missing Required Fields)

Test with missing required fields:

```json
{
  "taskId": "test-task-009",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-009",
    "customerId": "",
    "featureId": "feature-create-ai-agent-raw",
    "usageValue": -5,
    "eventTimestamp": "2026-01-22T12:29:00.000Z"
  },
  "createdAt": "2026-01-22T12:29:00.000Z"
}
```

**Expected Behavior:**

- Validation fails immediately with `INVALID_PAYLOAD` error
- NOT retryable (bad data won't fix itself)
- Goes to DLQ immediately
- ClickHouse logs with error details

---

### Scenario 10: Resource-Specific Usage

Test with a resource ID (e.g., per-agent usage):

```json
{
  "taskId": "test-task-010",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "test-evt-010",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-ai-agent-raw",
    "usageValue": 5,
    "resourceId": "agent_abc123",
    "eventTimestamp": "2026-01-22T12:30:00.000Z",
    "source": "manual-test",
    "metadata": {
      "agentName": "Sales Bot",
      "callId": "call_xyz"
    }
  },
  "createdAt": "2026-01-22T12:30:00.000Z"
}
```

**Expected Behavior:**

- Entitlement check passes
- Usage reported to Stigg with resource ID
- ClickHouse audit includes `resource_id`

---

## Publishing Messages to RabbitMQ

### Via RabbitMQ Management Console

1. Go to RabbitMQ Management UI (usually port 15672)
2. Navigate to **Queues** → `credit-deduction-queue`
3. Click **Publish message**
4. Set **Properties**: `content_type: application/json`
5. Paste the JSON payload

### Via CLI

```bash
rabbitmqadmin publish exchange=amq.default routing_key=credit-deduction-queue \
  payload='{"eventId":"test-001","customerId":"cust1","featureId":"api-calls","usageValue":10,"eventTimestamp":"2026-01-21T12:00:00.000Z"}'
```

---

## New Relic Queries (NRQL)

### All Usage Report Events

```sql
SELECT * FROM UsageReportEvent
WHERE appName = 'console-backend'
SINCE 1 hour ago
```

### Success vs Failure Rate

```sql
SELECT count(*) FROM UsageReportEvent
FACET status
SINCE 1 hour ago
```

### Auto-Provisioned Subscriptions

```sql
SELECT * FROM SubscriptionProvisioned
WHERE appName = 'console-backend'
SINCE 1 hour ago
```

### DLQ Messages (Failed after retries)

```sql
SELECT * FROM UsageReportDLQ
WHERE appName = 'console-backend'
SINCE 1 hour ago
```

### Stigg API Health

```sql
SELECT average(duration), percentage(count(*), WHERE success = true) as 'Success Rate'
FROM StiggApiCall
FACET operation
SINCE 1 hour ago TIMESERIES
```

### Processing Latency by Feature

```sql
SELECT average(duration), percentile(duration, 95)
FROM UsageReportEvent
WHERE status = 'success'
FACET featureId
SINCE 1 hour ago
```

### Worker Heartbeat (Health Check)

```sql
SELECT latest(timestamp) FROM WorkerHeartbeat
WHERE workerName = 'CreditDeductionWorker'
SINCE 5 minutes ago
```

### Usage by Customer

```sql
SELECT sum(usageValue) FROM UsageReportEvent
WHERE status = 'success'
FACET customerId
SINCE 1 hour ago
```

---

## ClickHouse Queries (Audit Logs)

### All Events

```sql
SELECT * FROM credit_audit
ORDER BY processed_at DESC
LIMIT 100;
```

### Success vs Failure

```sql
SELECT status, count(*)
FROM credit_audit
WHERE processed_at > now() - INTERVAL 1 HOUR
GROUP BY status;
```

### Auto-provisioned Subscriptions

```sql
SELECT * FROM credit_audit
WHERE JSONExtractBool(metadata, 'wasProvisioned') = true
ORDER BY processed_at DESC;
```

### Failed Events by Customer

```sql
SELECT customer_id, count(*), max(error_message)
FROM credit_audit
WHERE status = 'failed'
GROUP BY customer_id;
```

---

## Test Checklist

| #   | Test                             | Task ID          | Expected                      | NR Event                                         |
| --- | -------------------------------- | ---------------- | ----------------------------- | ------------------------------------------------ |
| 1   | Happy path (active subscription) | test-task-001    | ✅ Success                    | `UsageReportEvent`                               |
| 2   | No active subscription           | test-task-002    | ❌ Fail → DLQ                 | `UsageValidationFailed` (NO_ACTIVE_SUBSCRIPTION) |
| 3   | Multiple usage reports           | test-task-003a/b | ✅ Success x2                 | `UsageReportEvent` x2                            |
| 4   | Idempotency (same eventId x2)    | test-task-004 x2 | ✅ Success (no double charge) | `UsageReportEvent` x2                            |
| 5   | Invalid customer                 | test-task-005    | ❌ Fail → DLQ                 | `UsageValidationFailed` (NO_ACTIVE_SUBSCRIPTION) |
| 6   | Feature doesn't exist in Stigg   | test-task-006    | ❌ Fail → DLQ                 | `UsageValidationFailed` (ENTITLEMENT_DENIED)     |
| 7   | **Feature NOT in plan**          | test-task-007    | ❌ Fail → DLQ                 | `UsageValidationFailed` (ENTITLEMENT_DENIED)     |
| 8   | Usage limit exceeded             | test-task-008    | ⚠️ Depends on plan            | `UsageReportEvent` or `UsageValidationFailed`    |
| 9   | Invalid payload                  | test-task-009    | ❌ Fail → DLQ                 | `UsageValidationFailed` (INVALID_PAYLOAD)        |
| 10  | With resource ID                 | test-task-010    | ✅ Success                    | `UsageReportEvent`                               |

**AccessDeniedReason Codes (from Stigg):**
| Code | Reason | Retryable? |
|------|--------|------------|
| 1 | NO_SUBSCRIPTION | ✅ Yes |
| 2 | NO_FEATURE_ENTITLEMENT | ❌ No |
| 3 | USAGE_LIMIT_EXCEEDED | ❌ No |
| 4 | FEATURE_NOT_FOUND | ❌ No |
| 5 | SUBSCRIPTION_EXPIRED | ✅ Yes |
| 8 | CUSTOMER_NOT_FOUND | ❌ No |

---

## Troubleshooting

### Queues Not Created

- Check pod is running: `kubectl get pods -n dev`
- Check logs: `kubectl logs -f deployment/console-backend -n dev`
- Verify RabbitMQ URL in secrets

### Messages Not Processing

- Check worker started: Look for `[CreditDeductionWorker] Started successfully` in logs
- Check Stigg sidecar connectivity
- Verify ClickHouse connectivity

### DLQ Building Up

- Check New Relic for `UsageReportDLQ` events
- Review error messages in ClickHouse
- Common issues: Invalid customer, Stigg API errors, network issues

---

## Message Payload Schema

```typescript
{
  // Required fields
  eventId: string;           // Unique ID - used as Stigg idempotency key
  customerId: string;        // Customer/Organization ID
  featureId: string;         // Feature ID (e.g., 'api-calls', 'tts-characters')
  usageValue: number;        // Raw usage value (positive number)
  eventTimestamp: string;    // ISO 8601 datetime

  // Optional fields
  subscriptionId?: string;   // Subscription ID (if known)
  source?: string;           // Event source (e.g., 'atoms-backend', 'waves-backend')
  resourceId?: string;       // Resource ID for per-resource tracking
  metadata?: object;         // Additional metadata
}
```

---

## Architecture

```
┌─────────────────┐      ┌──────────────────────┐      ┌─────────────────┐
│  atoms-backend  │─────▶│  credit-deduction    │─────▶│  Stigg Sidecar  │
│  waves-backend  │      │  queue (RabbitMQ)    │      │  (gRPC)         │
└─────────────────┘      └──────────────────────┘      └─────────────────┘
                                   │                           │
                                   ▼                           │
                         ┌──────────────────┐                  │
                         │  CreditDeduction │◀─────────────────┘
                         │  Worker          │
                         └──────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
            ┌─────────────┐ ┌──────────┐ ┌──────────────┐
            │ ClickHouse  │ │ New Relic│ │ Stigg Backend│
            │ (Audit Log) │ │ (Metrics)│ │ (Provision)  │
            └─────────────┘ └──────────┘ └──────────────┘
```

# Trigger build
