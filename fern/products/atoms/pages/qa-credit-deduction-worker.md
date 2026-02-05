# Credit Deduction Worker - QA Testing Document

## Document Information

| Field        | Value                   |
| ------------ | ----------------------- |
| Feature      | Credit Deduction Worker |
| Version      | 1.0                     |
| Last Updated | January 2026            |
| PR           | #328                    |

---

## 1. Feature Overview

### What is the Credit Deduction Worker?

The Credit Deduction Worker is a background service that processes usage events and reports them to Stigg for billing. It runs as part of `console-backend` and consumes messages from RabbitMQ.

### Key Responsibilities

1. **Consume usage events** from RabbitMQ queue (`credit-deduction-queue`)
2. **Validate customer entitlements** via Stigg Sidecar cache (sub-millisecond latency)
3. **Report usage to Stigg** for billing and credit deduction
4. **Log all transactions** to ClickHouse for audit trail
5. **Handle failures** with retry logic and Dead Letter Queue (DLQ)

### Design Philosophy

| Principle                 | Description                                                    |
| ------------------------- | -------------------------------------------------------------- |
| Validate Before Reporting | Verify entitlements before reporting usage to Stigg            |
| No planId Required        | Stigg automatically knows customer's active plan               |
| Stigg Handles Overage     | Usage beyond limits is allowed - Stigg manages overage billing |
| Never Lose Data           | Failed events retry, then go to DLQ for manual review          |
| No Auto-Provisioning      | Subscriptions must exist before usage can be reported          |

---

## 2. Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EVENT PRODUCERS                                 │
│                                                                              │
│     ┌──────────────────┐              ┌──────────────────┐                  │
│     │  atoms-backend   │              │  waves-backend   │                  │
│     │  (AI Agents)     │              │  (Voice Calls)   │                  │
│     └────────┬─────────┘              └────────┬─────────┘                  │
│              │                                  │                            │
└──────────────┼──────────────────────────────────┼────────────────────────────┘
               │                                  │
               ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               RABBITMQ                                       │
│                                                                              │
│     ┌────────────────────────────┐      ┌────────────────────────────┐      │
│     │  credit-deduction-queue    │      │  credit-deduction-dlq      │      │
│     │  (Main Queue)              │      │  (Dead Letter Queue)       │      │
│     └─────────────┬──────────────┘      └────────────────────────────┘      │
│                   │                              ▲                           │
└───────────────────┼──────────────────────────────┼───────────────────────────┘
                    │                              │
                    ▼                              │ (failed after 2 retries)
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CONSOLE-BACKEND                                   │
│                                                                              │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │                    CreditDeductionWorker                         │     │
│     │                                                                  │     │
│     │  1. Parse & Validate Payload (Zod)                              │     │
│     │  2. Check Entitlement (Stigg Sidecar)                           │     │
│     │  3. Report Usage (Stigg)                                        │     │
│     │  4. Log to ClickHouse                                           │     │
│     │  5. Emit Metrics (New Relic)                                    │     │
│     └──────────────────────┬──────────────────────────────────────────┘     │
│                            │                                                 │
└────────────────────────────┼─────────────────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   stigg-proxy    │ │    ClickHouse    │ │    New Relic     │
│   (HTTP → gRPC)  │ │   (Audit Logs)   │ │    (Metrics)     │
└────────┬─────────┘ └──────────────────┘ └──────────────────┘
         │
         ▼
┌──────────────────┐
│  stigg-sidecar   │
│  (gRPC, Cache)   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   Stigg Cloud    │
│   (Billing)      │
└──────────────────┘
```

### Queue Configuration

| Queue                    | Purpose                           | TTL    |
| ------------------------ | --------------------------------- | ------ |
| `credit-deduction-queue` | Main processing queue             | None   |
| `credit-deduction-dlq`   | Failed messages for manual review | 7 days |

---

## 3. Processing Flow

### Step-by-Step Flow

```
Message Received
       │
       ▼
┌──────────────────┐
│ 1. Parse JSON    │───► Invalid JSON? ───► DLQ (unparseable)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 2. Validate      │───► Invalid payload? ───► DLQ (not retryable)
│    Payload (Zod) │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 3. Check         │───► No access? ─┬─► Retryable? ───► Retry (max 2)
│    Entitlement   │                 │
│    (Sidecar)     │                 └─► Not retryable? ───► DLQ
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 4. Report Usage  │───► API error? ───► Retry (max 2) ───► DLQ
│    (Stigg)       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 5. Log to        │───► ClickHouse down? ───► Log to console (fallback)
│    ClickHouse    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 6. ACK Message   │
│    (Success!)    │
└──────────────────┘
```

### Retry Behavior

| Attempt   | Delay       | Total Wait |
| --------- | ----------- | ---------- |
| 1st retry | 2 seconds   | 2s         |
| 2nd retry | 4 seconds   | 6s         |
| After 2nd | Send to DLQ | -          |

> **Note:** `maxRetries: 3` means 3 total attempts (initial + 2 retries), not 3 retries.

---

## 4. Message Format

### WorkerTask Wrapper (Required)

All messages must be wrapped in a `WorkerTask` structure:

```json
{
  "taskId": "unique-task-id",
  "taskType": "REPORT_USAGE",
  "payload": {
    // Actual usage data here
  },
  "createdAt": "2026-01-22T12:00:00.000Z"
}
```

### Payload Fields

| Field            | Type   | Required | Validation              | Description                                     |
| ---------------- | ------ | -------- | ----------------------- | ----------------------------------------------- |
| `eventId`        | string | Yes      | Non-empty, trimmed      | Unique event ID (used as idempotency key)       |
| `customerId`     | string | Yes      | Non-empty, trimmed      | Customer/Organization ID in Stigg               |
| `featureId`      | string | Yes      | Non-empty, trimmed      | Feature ID (e.g., `feature-create-with-ai-raw`) |
| `usageValue`     | number | Yes      | Positive, max 1 billion | Raw usage value                                 |
| `eventTimestamp` | string | Yes      | ISO 8601 datetime       | When the usage occurred                         |
| `subscriptionId` | string | No       | -                       | Subscription ID (optional)                      |
| `source`         | string | No       | -                       | Event source (e.g., `atoms-backend`)            |
| `resourceId`     | string | No       | Max 50 chars            | Resource ID for per-resource tracking           |
| `metadata`       | object | No       | -                       | Additional metadata for debugging               |

### Sample Complete Message

```json
{
  "taskId": "task-20260128-001",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "evt-20260128-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:00:00.000Z",
    "source": "atoms-backend",
    "resourceId": "agent_abc123",
    "metadata": {
      "agentName": "Sales Bot",
      "callId": "call_xyz"
    }
  },
  "createdAt": "2026-01-28T10:00:00.000Z"
}
```

---

## 5. Error Codes and Handling

### Worker Error Codes

| Error Code               | Description                               | Retryable | Action                  |
| ------------------------ | ----------------------------------------- | --------- | ----------------------- |
| `INVALID_PAYLOAD`        | Missing or invalid fields in payload      | No        | Sent to DLQ immediately |
| `NO_ACTIVE_SUBSCRIPTION` | Customer has no subscription or expired   | Yes       | Retry 2 times, then DLQ |
| `ENTITLEMENT_DENIED`     | Customer/feature not found or not in plan | No        | Sent to DLQ immediately |
| `STIGG_ERROR`            | Network/API error calling Stigg           | Yes       | Retry 2 times, then DLQ |

### Stigg AccessDeniedReason Codes

| Code | Name                   | Meaning                                | Retryable |
| ---- | ---------------------- | -------------------------------------- | --------- |
| 0    | UNSPECIFIED            | Unknown reason                         | Yes       |
| 1    | NO_SUBSCRIPTION        | Customer has no subscription           | Yes       |
| 2    | NO_FEATURE_ENTITLEMENT | Feature not in customer's plan         | No        |
| 3    | USAGE_LIMIT_EXCEEDED   | Usage exceeded limit (allowed through) | N/A       |
| 4    | FEATURE_NOT_FOUND      | Feature doesn't exist in Stigg         | No        |
| 5    | SUBSCRIPTION_EXPIRED   | Customer's subscription expired        | Yes       |
| 6    | NOT_IN_TRIAL           | Customer not in trial period           | Yes       |
| 7    | TRIAL_EXPIRED          | Trial period expired                   | Yes       |
| 8    | CUSTOMER_NOT_FOUND     | Customer doesn't exist in Stigg        | No        |
| 9    | UNKNOWN                | Unknown error                          | Yes       |

---

## 6. Test Environment Setup

### Test Customers (Dev Environment)

| Customer Name    | Customer ID        | Has Subscription |
| ---------------- | ------------------ | ---------------- |
| Test PAYG User 1 | `test-payg-user-1` | Yes (active)     |
| Test PAYG User 2 | `test-payg-user-2` | No               |
| Test PAYG User 3 | `test-payg-user-3` | Expired          |

### Available Features

| Feature Name                | Feature ID                   | Type    | Credits/Unit |
| --------------------------- | ---------------------------- | ------- | ------------ |
| Create with AI (Raw Events) | `feature-create-with-ai-raw` | Metered | 0.5 credits  |
| TTS V2 Usage (Raw)          | `feature-tts-v2-usage-raw`   | Metered | N/A          |
| TTS V3 Usage (Raw)          | `feature-tts-v3-usage-raw`   | Metered | N/A          |
| STT Usage (Raw)             | `feature-stt-usage-raw`      | Metered | N/A          |
| Atoms Voice V2 (Raw)        | `feature-atoms-voice-v2-raw` | Metered | N/A          |
| Atoms Voice V3 (Raw)        | `feature-atoms-voice-v3-raw` | Metered | N/A          |

### Access Points

| Service             | Dev URL                   | Port  |
| ------------------- | ------------------------- | ----- |
| RabbitMQ Management | http://rabbitmq-dev:15672 | 15672 |
| ClickHouse          | https://clickhouse-dev    | 8443  |
| New Relic           | https://one.newrelic.com  | -     |
| Stigg Dashboard     | https://app.stigg.io      | -     |

---

## 7. Test Cases

### Category A: Happy Path Tests

#### TC-A01: Basic Usage Report (Active Subscription)

| Field             | Value                                               |
| ----------------- | --------------------------------------------------- |
| **Test ID**       | TC-A01                                              |
| **Priority**      | P0 - Critical                                       |
| **Prerequisites** | Customer `test-payg-user-1` has active subscription |

**Test Message:**

```json
{
  "taskId": "tc-a01-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-a01-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:00:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:00:00.000Z"
}
```

**Expected Results:**

- Message processed successfully
- Usage reported to Stigg (10 units = 5 credits)
- ClickHouse audit log: `status = 'success'`
- New Relic: `EventProcessed` with `success = true`

**Verification:**

```sql
-- ClickHouse
SELECT * FROM credit_audit WHERE event_id = 'tc-a01-evt-001';
```

---

#### TC-A02: Multiple Usage Reports (Same Customer)

| Field             | Value                                               |
| ----------------- | --------------------------------------------------- |
| **Test ID**       | TC-A02                                              |
| **Priority**      | P0 - Critical                                       |
| **Prerequisites** | Customer `test-payg-user-1` has active subscription |

**Test Messages (send both):**

Message 1:

```json
{
  "taskId": "tc-a02-task-1",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-a02-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 5,
    "eventTimestamp": "2026-01-28T10:01:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:01:00.000Z"
}
```

Message 2:

```json
{
  "taskId": "tc-a02-task-2",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-a02-evt-002",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 3,
    "eventTimestamp": "2026-01-28T10:02:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:02:00.000Z"
}
```

**Expected Results:**

- Both messages processed successfully
- Total usage: 8 units = 4 credits deducted
- 2 entries in ClickHouse with `status = 'success'`

---

#### TC-A03: Usage with Resource ID

| Field             | Value                                               |
| ----------------- | --------------------------------------------------- |
| **Test ID**       | TC-A03                                              |
| **Priority**      | P1 - High                                           |
| **Prerequisites** | Customer `test-payg-user-1` has active subscription |

**Test Message:**

```json
{
  "taskId": "tc-a03-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-a03-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 1,
    "resourceId": "agent_sales_bot_001",
    "eventTimestamp": "2026-01-28T10:03:00.000Z",
    "source": "qa-test",
    "metadata": {
      "agentName": "Sales Bot",
      "department": "Sales"
    }
  },
  "createdAt": "2026-01-28T10:03:00.000Z"
}
```

**Expected Results:**

- Message processed successfully
- ClickHouse audit includes `resource_id = 'agent_sales_bot_001'`
- Metadata preserved in audit log

---

#### TC-A04: Usage with Subscription ID

| Field             | Value                              |
| ----------------- | ---------------------------------- |
| **Test ID**       | TC-A04                             |
| **Priority**      | P2 - Medium                        |
| **Prerequisites** | Customer has known subscription ID |

**Test Message:**

```json
{
  "taskId": "tc-a04-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-a04-evt-001",
    "customerId": "test-payg-user-1",
    "subscriptionId": "sub_12345",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 2,
    "eventTimestamp": "2026-01-28T10:04:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:04:00.000Z"
}
```

**Expected Results:**

- Message processed successfully
- Subscription ID included in ClickHouse audit

---

### Category B: Validation Failure Tests

#### TC-B01: Missing customerId

| Field             | Value     |
| ----------------- | --------- |
| **Test ID**       | TC-B01    |
| **Priority**      | P1 - High |
| **Prerequisites** | None      |

**Test Message:**

```json
{
  "taskId": "tc-b01-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-b01-evt-001",
    "customerId": "",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:05:00.000Z"
  },
  "createdAt": "2026-01-28T10:05:00.000Z"
}
```

**Expected Results:**

- Validation fails immediately
- Message sent to DLQ (no retries)
- Error: `INVALID_PAYLOAD`

---

#### TC-B02: Missing featureId

| Field             | Value     |
| ----------------- | --------- |
| **Test ID**       | TC-B02    |
| **Priority**      | P1 - High |
| **Prerequisites** | None      |

**Test Message:**

```json
{
  "taskId": "tc-b02-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-b02-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:06:00.000Z"
  },
  "createdAt": "2026-01-28T10:06:00.000Z"
}
```

**Expected Results:**

- Validation fails immediately
- Message sent to DLQ (no retries)

---

#### TC-B03: Invalid usageValue (Negative)

| Field             | Value     |
| ----------------- | --------- |
| **Test ID**       | TC-B03    |
| **Priority**      | P1 - High |
| **Prerequisites** | None      |

**Test Message:**

```json
{
  "taskId": "tc-b03-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-b03-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": -5,
    "eventTimestamp": "2026-01-28T10:07:00.000Z"
  },
  "createdAt": "2026-01-28T10:07:00.000Z"
}
```

**Expected Results:**

- Validation fails (usageValue must be positive)
- Message sent to DLQ

---

#### TC-B04: Invalid usageValue (Zero)

| Field             | Value     |
| ----------------- | --------- |
| **Test ID**       | TC-B04    |
| **Priority**      | P1 - High |
| **Prerequisites** | None      |

**Test Message:**

```json
{
  "taskId": "tc-b04-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-b04-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 0,
    "eventTimestamp": "2026-01-28T10:08:00.000Z"
  },
  "createdAt": "2026-01-28T10:08:00.000Z"
}
```

**Expected Results:**

- Validation fails (usageValue must be positive)
- Message sent to DLQ

---

#### TC-B05: Invalid eventTimestamp Format

| Field             | Value       |
| ----------------- | ----------- |
| **Test ID**       | TC-B05      |
| **Priority**      | P2 - Medium |
| **Prerequisites** | None        |

**Test Message:**

```json
{
  "taskId": "tc-b05-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-b05-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 10,
    "eventTimestamp": "2026/01/28 10:00:00"
  },
  "createdAt": "2026-01-28T10:09:00.000Z"
}
```

**Expected Results:**

- Validation fails (must be ISO 8601)
- Message sent to DLQ

---

### Category C: Entitlement Failure Tests

#### TC-C01: Customer Not Found in Stigg

| Field             | Value                        |
| ----------------- | ---------------------------- |
| **Test ID**       | TC-C01                       |
| **Priority**      | P0 - Critical                |
| **Prerequisites** | Use non-existent customer ID |

**Test Message:**

```json
{
  "taskId": "tc-c01-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-c01-evt-001",
    "customerId": "customer-does-not-exist-xyz",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:10:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:10:00.000Z"
}
```

**Expected Results:**

- Entitlement check fails: `CUSTOMER_NOT_FOUND`
- Message sent to DLQ (not retryable)
- Error code: `ENTITLEMENT_DENIED`

---

#### TC-C02: Customer Has No Subscription

| Field             | Value                                                      |
| ----------------- | ---------------------------------------------------------- |
| **Test ID**       | TC-C02                                                     |
| **Priority**      | P0 - Critical                                              |
| **Prerequisites** | Customer `test-payg-user-2` exists but has no subscription |

**Test Message:**

```json
{
  "taskId": "tc-c02-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-c02-evt-001",
    "customerId": "test-payg-user-2",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:11:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:11:00.000Z"
}
```

**Expected Results:**

- Entitlement check fails: `NO_SUBSCRIPTION`
- Retries 2 times with exponential backoff (2s, 4s)
- After retries (3 total attempts), sent to DLQ
- Error code: `NO_ACTIVE_SUBSCRIPTION`

---

#### TC-C03: Feature Not Found in Stigg

| Field             | Value                       |
| ----------------- | --------------------------- |
| **Test ID**       | TC-C03                      |
| **Priority**      | P1 - High                   |
| **Prerequisites** | Use non-existent feature ID |

**Test Message:**

```json
{
  "taskId": "tc-c03-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-c03-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-does-not-exist",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:12:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:12:00.000Z"
}
```

**Expected Results:**

- Entitlement check fails: `FEATURE_NOT_FOUND`
- Message sent to DLQ (not retryable)
- Error code: `ENTITLEMENT_DENIED`

---

#### TC-C04: Feature Not In Customer's Plan

| Field             | Value                                     |
| ----------------- | ----------------------------------------- |
| **Test ID**       | TC-C04                                    |
| **Priority**      | P0 - Critical                             |
| **Prerequisites** | Feature exists but not in customer's plan |

**Test Message:**

```json
{
  "taskId": "tc-c04-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-c04-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-enterprise-only",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:13:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:13:00.000Z"
}
```

**Expected Results:**

- Entitlement check fails: `NO_FEATURE_ENTITLEMENT`
- Message sent to DLQ (not retryable)
- Error code: `ENTITLEMENT_DENIED`

---

#### TC-C05: Subscription Expired

| Field             | Value                                                |
| ----------------- | ---------------------------------------------------- |
| **Test ID**       | TC-C05                                               |
| **Priority**      | P1 - High                                            |
| **Prerequisites** | Customer `test-payg-user-3` has expired subscription |

**Test Message:**

```json
{
  "taskId": "tc-c05-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-c05-evt-001",
    "customerId": "test-payg-user-3",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:14:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:14:00.000Z"
}
```

**Expected Results:**

- Entitlement check fails: `SUBSCRIPTION_EXPIRED`
- Retries 2 times with exponential backoff (2s, 4s)
- After retries (3 total attempts), sent to DLQ
- Error code: `NO_ACTIVE_SUBSCRIPTION`

---

### Category D: Idempotency Tests

#### TC-D01: Duplicate eventId (Same Message Twice)

| Field             | Value                            |
| ----------------- | -------------------------------- |
| **Test ID**       | TC-D01                           |
| **Priority**      | P0 - Critical                    |
| **Prerequisites** | Customer has active subscription |

**Test Message (send TWICE with same eventId):**

```json
{
  "taskId": "tc-d01-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-d01-idempotent-event",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 100,
    "eventTimestamp": "2026-01-28T10:15:00.000Z",
    "source": "qa-test-idempotency"
  },
  "createdAt": "2026-01-28T10:15:00.000Z"
}
```

**Expected Results:**

- First message: Usage deducted (100 units)
- Second message: Stigg returns cached result, NO double deduction
- ClickHouse has 2 audit entries (both `status = 'success'`)
- Stigg dashboard shows only 100 units consumed (not 200)

---

#### TC-D02: Same eventId with Different usageValue

| Field             | Value                            |
| ----------------- | -------------------------------- |
| **Test ID**       | TC-D02                           |
| **Priority**      | P1 - High                        |
| **Prerequisites** | Customer has active subscription |

**Message 1:**

```json
{
  "taskId": "tc-d02-task-1",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-d02-same-event-id",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 50,
    "eventTimestamp": "2026-01-28T10:16:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:16:00.000Z"
}
```

**Message 2 (same eventId, different usageValue):**

```json
{
  "taskId": "tc-d02-task-2",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-d02-same-event-id",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 75,
    "eventTimestamp": "2026-01-28T10:17:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:17:00.000Z"
}
```

**Expected Results:**

- First message's value (50) is used
- Second message is deduplicated by Stigg (ignored)
- Only 50 units charged to customer

---

### Category E: Edge Cases

#### TC-E01: Maximum usageValue

| Field             | Value                            |
| ----------------- | -------------------------------- |
| **Test ID**       | TC-E01                           |
| **Priority**      | P2 - Medium                      |
| **Prerequisites** | Customer has active subscription |

**Test Message:**

```json
{
  "taskId": "tc-e01-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-e01-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 999999999,
    "eventTimestamp": "2026-01-28T10:18:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:18:00.000Z"
}
```

**Expected Results:**

- Message processed successfully (if within limit)
- Large usage value recorded correctly

---

#### TC-E02: Exceeds Maximum usageValue

| Field             | Value       |
| ----------------- | ----------- |
| **Test ID**       | TC-E02      |
| **Priority**      | P2 - Medium |
| **Prerequisites** | None        |

**Test Message:**

```json
{
  "taskId": "tc-e02-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-e02-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 1000000001,
    "eventTimestamp": "2026-01-28T10:19:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:19:00.000Z"
}
```

**Expected Results:**

- Validation fails (exceeds 1 billion limit)
- Message sent to DLQ

---

#### TC-E03: Maximum resourceId Length

| Field             | Value                            |
| ----------------- | -------------------------------- |
| **Test ID**       | TC-E03                           |
| **Priority**      | P2 - Medium                      |
| **Prerequisites** | Customer has active subscription |

**Test Message:**

```json
{
  "taskId": "tc-e03-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-e03-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 1,
    "resourceId": "12345678901234567890123456789012345678901234567890",
    "eventTimestamp": "2026-01-28T10:20:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:20:00.000Z"
}
```

**Expected Results:**

- Message processed successfully (exactly 50 chars)

---

#### TC-E04: Exceeds resourceId Length

| Field             | Value       |
| ----------------- | ----------- |
| **Test ID**       | TC-E04      |
| **Priority**      | P2 - Medium |
| **Prerequisites** | None        |

**Test Message:**

```json
{
  "taskId": "tc-e04-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-e04-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 1,
    "resourceId": "123456789012345678901234567890123456789012345678901",
    "eventTimestamp": "2026-01-28T10:21:00.000Z",
    "source": "qa-test"
  },
  "createdAt": "2026-01-28T10:21:00.000Z"
}
```

**Expected Results:**

- Validation fails (exceeds 50 char limit)
- Message sent to DLQ

---

### Category F: Usage Limit Tests

#### TC-F01: Usage Limit Exceeded (Overage Allowed)

| Field             | Value                             |
| ----------------- | --------------------------------- |
| **Test ID**       | TC-F01                            |
| **Priority**      | P1 - High                         |
| **Prerequisites** | Customer has used all their quota |

**Test Message:**

```json
{
  "taskId": "tc-f01-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-f01-evt-001",
    "customerId": "test-payg-user-1",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 999999,
    "eventTimestamp": "2026-01-28T10:22:00.000Z",
    "source": "qa-test-overage"
  },
  "createdAt": "2026-01-28T10:22:00.000Z"
}
```

**Expected Results:**

- Entitlement check may return `USAGE_LIMIT_EXCEEDED`
- Worker allows this through (Stigg handles overage)
- Usage is reported and logged
- Check Stigg dashboard for overage billing

---

### Category G: Retry and DLQ Tests

#### TC-G01: Verify Retry Behavior

| Field             | Value                                              |
| ----------------- | -------------------------------------------------- |
| **Test ID**       | TC-G01                                             |
| **Priority**      | P1 - High                                          |
| **Prerequisites** | Customer without subscription (to trigger retries) |

**Test Message:**

```json
{
  "taskId": "tc-g01-task",
  "taskType": "REPORT_USAGE",
  "payload": {
    "eventId": "tc-g01-evt-001",
    "customerId": "test-payg-user-2",
    "featureId": "feature-create-with-ai-raw",
    "usageValue": 10,
    "eventTimestamp": "2026-01-28T10:23:00.000Z",
    "source": "qa-test-retry"
  },
  "createdAt": "2026-01-28T10:23:00.000Z"
}
```

**Expected Results:**

- First attempt fails
- Retry after 2 seconds
- Retry after 4 seconds (6s total)
- Sent to DLQ after 2 retries (3 total attempts)
- Total time: ~6 seconds

**Verification:**

- Watch logs for retry messages
- Check DLQ after ~10 seconds

---

#### TC-G02: Verify DLQ Message Format

| Field             | Value                             |
| ----------------- | --------------------------------- |
| **Test ID**       | TC-G02                            |
| **Priority**      | P1 - High                         |
| **Prerequisites** | Message in DLQ from previous test |

**Steps:**

1. Go to RabbitMQ Management UI
2. Navigate to `credit-deduction-dlq`
3. Get message from queue

**Expected DLQ Message Headers:**

- `x-dlq-failure-reason`: Error description
- `x-dlq-failed-at`: ISO timestamp
- `x-dlq-worker`: `CreditDeductionWorker`

**Expected DLQ Message Body:**

- Original message preserved exactly (can be replayed)

---

#### TC-G03: DLQ Message Replay

| Field             | Value                                     |
| ----------------- | ----------------------------------------- |
| **Test ID**       | TC-G03                                    |
| **Priority**      | P2 - Medium                               |
| **Prerequisites** | Message in DLQ, cause of failure resolved |

**Steps:**

1. Get message from `credit-deduction-dlq`
2. Update `attemptCount` to 0 (or remove it)
3. Publish to `credit-deduction-queue`
4. Verify message processes successfully

---

## 8. Verification Queries

### New Relic NRQL Queries

#### All Usage Events (Last Hour)

```sql
SELECT * FROM EventProcessed
WHERE workerName = 'credit-deduction'
SINCE 1 hour ago
```

#### Success vs Failure Rate

```sql
SELECT count(*) FROM EventProcessed
WHERE workerName = 'credit-deduction'
FACET success
SINCE 1 hour ago
```

#### Failed Events by Reason

```sql
SELECT count(*) FROM EventProcessed
WHERE workerName = 'credit-deduction' AND success = false
FACET failureReason
SINCE 1 hour ago
```

#### External API Latency

```sql
SELECT average(latencyMs), percentile(latencyMs, 95)
FROM ExternalApiCall
FACET service, operation
SINCE 1 hour ago TIMESERIES
```

#### Worker Heartbeat (Health Check)

```sql
SELECT latest(timestamp) FROM WorkerHeartbeat
WHERE workerName = 'CreditDeductionWorker'
SINCE 5 minutes ago
```

### ClickHouse SQL Queries

#### All Audit Entries (Recent)

```sql
SELECT * FROM credit_audit
ORDER BY processed_at DESC
LIMIT 100;
```

#### Events by Status

```sql
SELECT status, count(*) as count
FROM credit_audit
WHERE processed_at > now() - INTERVAL 1 HOUR
GROUP BY status;
```

#### Failed Events with Errors

```sql
SELECT event_id, customer_id, feature_id, error_message, processed_at
FROM credit_audit
WHERE status = 'failed'
ORDER BY processed_at DESC
LIMIT 50;
```

#### Usage by Customer

```sql
SELECT customer_id, sum(usage_value) as total_usage, count(*) as event_count
FROM credit_audit
WHERE status = 'success'
GROUP BY customer_id
ORDER BY total_usage DESC;
```

#### Specific Event Lookup

```sql
SELECT * FROM credit_audit
WHERE event_id = 'YOUR_EVENT_ID_HERE';
```

---

## 9. How to Publish Test Messages

### Option 1: RabbitMQ Management UI

1. Open RabbitMQ Management UI (port 15672)
2. Navigate to **Queues** tab
3. Click on `credit-deduction-queue`
4. Expand **Publish message** section
5. Set **Properties**:
   - `content_type: application/json`
6. Paste JSON message in **Payload**
7. Click **Publish message**

### Option 2: Command Line (rabbitmqadmin)

```bash
rabbitmqadmin publish \
  exchange=amq.default \
  routing_key=credit-deduction-queue \
  properties='{"content_type":"application/json"}' \
  payload='<YOUR_JSON_MESSAGE>'
```

### Option 3: Port Forward to Local

```bash
# Port forward RabbitMQ
kubectl port-forward svc/rabbitmq 15672:15672 -n smallest-dev-aps1

# Access at http://localhost:15672
```

---

## 10. Test Execution Checklist

### Pre-Test Setup

| Step | Action                               | Status |
| ---- | ------------------------------------ | ------ |
| 1    | Verify console-backend is running    | [ ]    |
| 2    | Verify RabbitMQ is accessible        | [ ]    |
| 3    | Verify ClickHouse is accessible      | [ ]    |
| 4    | Verify Stigg sidecar is running      | [ ]    |
| 5    | Verify test customers exist in Stigg | [ ]    |
| 6    | Clear any old test data (optional)   | [ ]    |

### Test Execution

| Test ID | Test Name                     | Priority | Status | Notes |
| ------- | ----------------------------- | -------- | ------ | ----- |
| TC-A01  | Basic Usage Report            | P0       | [ ]    |       |
| TC-A02  | Multiple Usage Reports        | P0       | [ ]    |       |
| TC-A03  | Usage with Resource ID        | P1       | [ ]    |       |
| TC-A04  | Usage with Subscription ID    | P2       | [ ]    |       |
| TC-B01  | Missing customerId            | P1       | [ ]    |       |
| TC-B02  | Missing featureId             | P1       | [ ]    |       |
| TC-B03  | Invalid usageValue (Negative) | P1       | [ ]    |       |
| TC-B04  | Invalid usageValue (Zero)     | P1       | [ ]    |       |
| TC-B05  | Invalid eventTimestamp        | P2       | [ ]    |       |
| TC-C01  | Customer Not Found            | P0       | [ ]    |       |
| TC-C02  | No Subscription               | P0       | [ ]    |       |
| TC-C03  | Feature Not Found             | P1       | [ ]    |       |
| TC-C04  | Feature Not In Plan           | P0       | [ ]    |       |
| TC-C05  | Subscription Expired          | P1       | [ ]    |       |
| TC-D01  | Duplicate eventId             | P0       | [ ]    |       |
| TC-D02  | Same eventId, Different Value | P1       | [ ]    |       |
| TC-E01  | Maximum usageValue            | P2       | [ ]    |       |
| TC-E02  | Exceeds Maximum usageValue    | P2       | [ ]    |       |
| TC-E03  | Maximum resourceId Length     | P2       | [ ]    |       |
| TC-E04  | Exceeds resourceId Length     | P2       | [ ]    |       |
| TC-F01  | Usage Limit Exceeded          | P1       | [ ]    |       |
| TC-G01  | Verify Retry Behavior         | P1       | [ ]    |       |
| TC-G02  | Verify DLQ Message Format     | P1       | [ ]    |       |
| TC-G03  | DLQ Message Replay            | P2       | [ ]    |       |

### Post-Test Verification

| Step | Action                                       | Status |
| ---- | -------------------------------------------- | ------ |
| 1    | Verify all expected ClickHouse entries       | [ ]    |
| 2    | Verify New Relic metrics                     | [ ]    |
| 3    | Verify Stigg usage in dashboard              | [ ]    |
| 4    | Verify DLQ contains expected failed messages | [ ]    |
| 5    | Clean up test data                           | [ ]    |

---

## 11. Troubleshooting

### Messages Not Being Processed

1. Check if worker is running:
   ```bash
   kubectl logs -f deployment/console-backend -n smallest-dev-aps1 | grep CreditDeductionWorker
   ```
2. Look for "Started successfully" message
3. Verify queue has consumers in RabbitMQ UI

### Messages Going to DLQ Unexpectedly

1. Check DLQ message headers for `x-dlq-failure-reason`
2. Look up error code in Error Codes table
3. Verify customer exists in Stigg
4. Verify feature is in customer's plan

### ClickHouse Not Receiving Logs

1. Check for "CLICKHOUSE_AUDIT_FALLBACK" in console logs
2. Verify ClickHouse connectivity
3. Check console-backend logs for ClickHouse errors

### Stigg API Errors

1. Check stigg-proxy logs:
   ```bash
   kubectl logs -f deployment/stigg-proxy -n smallest-dev-aps1
   ```
2. Verify stigg-sidecar is running
3. Check API key configuration

---

## 12. Contact

| Role          | Name      | Contact               |
| ------------- | --------- | --------------------- |
| Feature Owner | Pratiksha | pratiksha@smallest.ai |
| Backend Team  | -         | #backend-team         |
| DevOps        | -         | #devops               |
