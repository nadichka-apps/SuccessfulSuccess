# AWS Event-Driven Weekly Meetings Report Lab

## 1. System Architecture & Component Overview

This lab implements an event-driven, decoupled, serverless pipeline that generates and delivers weekly meeting report summaries as structured CSV files.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          AWS Cloud                                          │
│                                                                                             │
│  [EventBridge Scheduler]                                                                    │
│  Schedule: Every Monday at 07:00 Europe/Kyiv                                                │
│  FlexibleTimeWindow: OFF                                                                    │
│         │                                                                                   │
│         ▼                                                                                   │
│  [SQS WeeklyReportQueue] ────(After 3 fails)────▶ [SQS WeeklyReportDLQ]                     │
│  VisibilityTimeout: 360s                                                                    │
│         │                                                                                   │
│         ▼ (BatchSize: 1)                                                                    │
│  ┌───────────────────────── Default VPC ─────────────────────────┐                          │
│  │                                                               │                          │
│  │  [Report Builder Lambda] ──Port 5432──▶ [Aurora Serverless]   │                          │
│  │  (In VPC, reuses backend image,         (PostgreSQL 17)       │                          │
│  │   Timeout: 60s)                                               │                          │
│  │         │                                                     │                          │
│  │         ▼                                                     │                          │
│  │  [S3 Gateway VPC Endpoint] (Route Tables attached, $0 cost)   │                          │
│  └─────────┬─────────────────────────────────────────────────────┘                          │
│            │                                                                                │
│            ▼ (s3:PutObject)                                                                 │
│  [Private Encrypted S3 Bucket] (90-day lifecycle expiration)                                │
│  s3://successfulsuccess-reports-${AWS::AccountId}/reports/{week}.csv                         │
│            │                                                                                │
│            ▼ Notification (Prefix: "reports/", Suffix: ".csv")                              │
│  [Mailer Lambda] (Outside VPC, direct internet routing to SES)                              │
│  (Read-only S3 access: s3:GetObject only, NO PutObject)                                     │
│         │                                                                                   │
│         ├─── Check & Record Dedup ───▶ [DynamoDB ReportsDedupTable]                         │
│         │                              (Conditional write: attribute_not_exists)            │
│         ▼                                                                                   │
│  [Amazon SES] (MIME attachment: text/csv; charset=utf-8)                                    │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Architectural Highlights
1. **Decoupled Invocation via SQS**: EventBridge Scheduler pushes messages into an SQS queue with an attached Dead-Letter Queue (DLQ). The queue absorbs scheduling spikes, buffers execution, and provides automated retries.
2. **VPC Network Isolation & S3 Gateway Endpoint**: The Report Builder Lambda runs inside the application VPC to access private Aurora Serverless v2 PostgreSQL. Instead of requiring an expensive NAT Gateway ($32+/month), traffic to S3 routes privately and without charge through an **S3 Gateway VPC Endpoint**.
3. **Dual Network Separation**:
   * **Report Builder Lambda (Inside VPC)**: Queries PostgreSQL, compiles report metrics, and uploads the CSV to S3.
   * **Mailer Lambda (Outside VPC)**: Triggered by S3 ObjectCreated events, runs in the standard AWS Lambda execution environment with direct internet access to call Amazon SES without NAT Gateway overhead.
4. **Idempotent S3 Key Design**: For any given ISO week (e.g., `2026-W40`), the object key is strictly `reports/{week}.csv`. Subsequent runs for the same week cleanly overwrite the existing artifact.
5. **Least-Privilege Security**: The Mailer Lambda has read-only S3 permissions (`s3:GetObject` on `reports/*.csv`). It is strictly prohibited from writing or deleting S3 objects, eliminating infinite trigger loops.
6. **Persistent Deduplication**: DynamoDB provides atomic conditional locking to suppress duplicate emails during S3 or SQS event replays.

---

## 2. Answers to the 13 Core Discussion Questions

### Question 1: Event-Driven Architecture vs. Polling / Monolithic Cron
**Answer:**
In traditional monolithic architectures, scheduled reporting relies on an in-process cron scheduler (e.g., Celery beat, APScheduler) or an operating system cron daemon running on a web server. This approach couples scheduled batch workloads directly to the web API's compute resources, introducing significant downsides:
* **Resource Contention**: Heavy report aggregation queries consume database connections, memory, and CPU cycles, degrading web API responsiveness for interactive users.
* **Failure Blast Radius**: If the batch reporting job crashes or runs out of memory, it can bring down the entire API container or instance.
* **Inefficient Resource Provisioning**: Servers must be over-provisioned 24/7 to handle periodic morning traffic spikes that only occur once a week.

An event-driven serverless architecture decouples trigger emission (EventBridge Scheduler), buffering (SQS), computation (Report Builder Lambda), storage (S3), and delivery (Mailer Lambda). Compute resources spin up on demand, execute, and scale back to zero. If the report fails, the main web API remains 100% operational, and SQS handles retries independently.

---

### Question 2: EventBridge Scheduler vs. Legacy CloudWatch Events / EventBridge Rules
**Answer:**
Amazon EventBridge Scheduler is the modern, dedicated scheduling capability that supersedes legacy CloudWatch Events / EventBridge Rules for scheduled jobs:
1. **Timezone Support**: EventBridge Scheduler natively supports `ScheduleExpressionTimezone: "Europe/Kyiv"`. Legacy CloudWatch Events only support UTC, requiring brittle manual cron adjustments across Daylight Saving Time (EET to EEST transitions).
2. **Flexible Time Windows**: Scheduler offers configurable invocation windows (`FlexibleTimeWindow`). We explicitly set `Mode: "OFF"` to guarantee punctuality at 07:00:00.
3. **Native Dead-Letter Queues (DLQ) & Target Retry Policies**: Scheduler allows configuring target-level retries and DLQs directly on the schedule resource itself.
4. **Direct Target Integrations**: Scheduler integrates directly with over 270 AWS services and thousands of API actions without requiring boilerplate Lambda proxies.

---

### Question 3: Buffer Queue (SQS) Between Scheduler and Builder
**Answer:**
Placing Amazon SQS between EventBridge Scheduler and Report Builder provides four critical operational benefits:
1. **Concurrency Control & Throttling**: Lambda event source mappings allow strict concurrency regulation (`BatchSize: 1`, configurable maximum concurrency). This prevents simultaneous batch runs from overwhelming Aurora Serverless v2 PostgreSQL connection limits.
2. **Backpressure Decoupling**: If Aurora is asleep (paused at 0 ACU), the database takes ~15 seconds to resume. SQS absorbs the trigger event without dropping it, giving Aurora time to wake up.
3. **Resilience & Asynchronous Retries**: SQS provides message retention (up to 14 days) and granular redrive control. If the Report Builder fails, the message remains on the queue until the visibility timeout expires, allowing automated retry attempts.
4. **Auditability & Observability**: Operators can inspect pending, in-flight, and dead-lettered messages in SQS to verify schedule health.

---

### Question 4: Dead-Letter Queue (DLQ) & The 6x Visibility Timeout Rule
**Answer:**
* **Purpose of the DLQ**: The DLQ (`WeeklyReportDLQ`) isolates persistent "poison-pill" messages (e.g., corrupted payloads, unrecoverable database errors) after `maxReceiveCount: 3` failures. This prevents poison pills from endlessly cycling through the consumer and consuming resources.
* **The 6x Visibility Timeout Rule**:
  * AWS Lambda's SQS integration requires that the queue's `VisibilityTimeout` be set to **at least 6 times the Lambda function timeout**:
    $$\text{VisibilityTimeout} \ge 6 \times \text{Lambda Timeout}$$
  * In our configuration, the Report Builder Lambda timeout is 60 seconds; the queue visibility timeout is configured to **360 seconds** ($6 \times 60$).
  * **Why**: When Lambda receives a message batch, SQS hides the message for the duration of the visibility timeout. If Lambda fails or the execution environment is recycled, the message becomes visible again. If the visibility timeout were equal to or shorter than the function timeout, SQS could make the message visible to another Lambda instance while the first invocation is still running, causing race conditions, redundant executions, and false DLQ transitions.
* **Alerting**: A CloudWatch Alarm on `ApproximateNumberOfMessagesVisible > 0` on the DLQ alerts on-call engineers to inspect and remediate failures before using the SQS redrive API.

---

### Question 5: Private Networking & S3 Gateway VPC Endpoint vs. NAT Gateway
**Answer:**
* **Why the Builder Needs a VPC**: The Report Builder Lambda connects to Aurora Serverless v2 PostgreSQL, which sits inside private VPC subnets with no public IP address. Therefore, the Builder must attach to the VPC.
* **The S3 Gateway VPC Endpoint**:
  * AWS EC2 provides Gateway Endpoints for Amazon S3 (`com.amazonaws.us-east-1.s3`) that inject prefix-list routes directly into the VPC Route Tables.
  * Traffic between the Lambda function in the VPC and Amazon S3 routes entirely within the AWS internal network fabric.
* **Cost Comparison**:
  * **NAT Gateway**: Costs ~$0.045 per hour (~$32.40/month per AZ) plus $0.045 per GB of data processing.
  * **S3 Gateway Endpoint**: **$0.00 / month (completely free)**, with zero data processing charges.
* **Security**: The S3 Gateway Endpoint ensures data never traverses the public internet, satisfying zero-trust network requirements.

---

### Question 6: Network Separation: In-VPC Builder vs. Out-of-VPC Mailer
**Answer:**
The architecture splits report generation and email delivery across two distinct Lambda functions:
1. **Report Builder Lambda (Inside VPC)**:
   * Holds database credentials and network access to PostgreSQL (Port 5432).
   * Generates the CSV report and writes it to S3 through the free S3 Gateway VPC Endpoint.
   * Has **no internet access** and cannot reach public AWS HTTPS APIs.
2. **Mailer Lambda (Outside VPC)**:
   * Runs in the standard AWS Lambda utility VPC with direct outbound internet access to AWS public APIs.
   * Calls Amazon SES (`ses:SendRawEmail`) without requiring an expensive NAT Gateway or specialized VPC endpoints.
   * Has **zero database credentials** and **zero access** to the internal VPC network.
* **Security & Architectural Win**:
  * Adheres to the principle of least privilege: the mailer cannot compromise the database, and the builder cannot leak data via outbound internet.
  * Eliminates 100% of NAT Gateway costs.

---

### Question 7: S3 Event Notification Filtering & Idempotent Keys
**Answer:**
* **Notification Filtering**:
  * S3 is configured to emit `s3:ObjectCreated:*` notifications strictly for keys with prefix `reports/` and suffix `.csv`.
  * Non-report files, temporary upload parts, and metadata files do not trigger the Mailer Lambda.
* **Preventing Infinite Loops**:
  * In event-driven architectures where S3 triggers Lambda, a common failure mode is an **infinite loop**: Lambda triggered by an S3 upload writes back to the same bucket, triggering itself indefinitely.
  * We eliminate this risk in two ways:
    1. The Mailer Lambda has **read-only permissions** (`s3:GetObject` only; `s3:PutObject` is explicitly denied in IAM).
    2. S3 notifications are scoped exclusively to `reports/*.csv`.
* **Idempotent S3 Key**:
  * The key is deterministic: `reports/{week}.csv` (e.g. `reports/2026-W40.csv`).
  * Re-running report generation for the same week overwrites the file in place, keeping bucket storage clean and predictable.

---

### Question 8: Why "Exactly-Once" Delivery Cannot Be Guaranteed
**Answer:**
In distributed systems, claiming "exactly-once" delivery across independent network services is technically incorrect due to the fundamental nature of consensus and network partitions:
1. **At-Least-Once Messaging**: Amazon SQS and Amazon S3 Event Notifications provide at-least-once delivery. In rare network retries or component restarts, duplicate messages can be dispatched.
2. **Dual-Write / Non-Atomic Commit Boundary**:
   * The Mailer Lambda interacts with two distinct external systems: Amazon SES and Amazon DynamoDB.
   * Amazon SES does not support two-phase commit (2PC) or distributed transactions with DynamoDB.
3. **The Unavoidable Crash-After-Send Failure**:
   * If the Mailer Lambda successfully calls `ses.send_raw_email(...)` and SES accepts the message, but the Lambda container crashes immediately (e.g., container host crash, out-of-memory kill, network timeout before writing DynamoDB state):
   * DynamoDB never receives the `SENT` status.
   * S3 or SQS will redeliver the event upon retry, resulting in a duplicate email delivery.
4. **Honest Engineering Guarantee**:
   * The architecture guarantees **effectively-once / idempotent delivery under all normal execution and retry conditions**, with an atomic conditional lock in DynamoDB.
   * However, under catastrophic crash-after-send conditions, duplicate delivery remains theoretically possible.

---

### Question 9: Concurrency-Safe Persistent Deduplication Mechanism
**Answer:**
To achieve robust idempotency, the Mailer uses Amazon DynamoDB (`ReportsDedupTable`):
* **Primary Key**: `report_key` (e.g. `reports/2026-W40.csv#recipient@example.com`).
* **Attributes**: `status` (`PENDING` | `SENT` | `FAILED`), `lock_expiry` (epoch seconds), `message_id`, `ttl`.
* **Lock Acquisition**:
  ```python
  ConditionExpression=(
      "attribute_not_exists(report_key) OR "
      "#st = :failed OR "
      "(#st = :pending AND lock_expiry < :now)"
  )
  ```
* **Handling Retries & Stale Locks**:
  * When a delivery begins, it writes `status: "PENDING"` with a `lock_expiry` set to 5 minutes in the future.
  * If a concurrent execution attempts delivery, DynamoDB throws `ConditionalCheckFailedException`, and the duplicate is suppressed.
  * If a Lambda execution crashes mid-flight without updating status, the lock expires after 300 seconds, allowing the subsequent SQS/S3 retry to reclaim the lock and complete delivery.
  * On success, status is updated to `SENT`. On SES rejection, status is updated to `FAILED`, allowing immediate retry.

---

### Question 10: Presigned URLs vs. Direct MIME Attachments
**Answer:**
| Consideration | Direct MIME Attachment (Implemented) | S3 Presigned URL |
| :--- | :--- | :--- |
| **User Experience** | Instant access directly in email client. Works offline on mobile/desktop without browser redirect. | Recipient must click link, open browser, and download the file. |
| **File Size Constraints** | Amazon SES imposes a **10 MB total message size limit** (including base64 overhead, ~7.5 MB raw file). | Can handle files up to **5 TB** in Amazon S3. |
| **Expiration & Revocation**| Attachment persists permanently in the recipient's mailbox. | Presigned URLs expire (max 7 days; typically 24 hours). Link can be revoked or rotated. |
| **Security & Access** | Data is stored in recipient's mail provider. | S3 bucket remains private; access is time-limited to holders of the signed query string. |
| **Fit for this Lab** | **Ideal**: Weekly meetings CSV files are compact (<500 KB) and recipients benefit from direct attachments without expiring links. |

---

### Question 11: Least-Privilege IAM & Security Controls
**Answer:**
Each component is isolated with a dedicated IAM role following least-privilege principles:
1. **`SchedulerRole`**:
   * Can only assume `scheduler.amazonaws.com`.
   * Action: `sqs:SendMessage` strictly restricted to `WeeklyReportQueue.Arn`.
2. **`ReportBuilderRole`**:
   * Attaches `AWSLambdaVPCAccessExecutionRole` to create elastic network interfaces (ENIs) in the VPC.
   * Action: `s3:PutObject` restricted to `arn:aws:s3:::<reports-bucket>/reports/*.csv`.
   * Action: `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on `WeeklyReportQueue.Arn`.
   * **No SES permissions; no broad S3 permissions**.
3. **`MailerRole`**:
   * Attaches `AWSLambdaBasicExecutionRole` (writes CloudWatch logs).
   * Action: `s3:GetObject` strictly restricted to `arn:aws:s3:::<reports-bucket>/reports/*.csv`.
   * **Explicitly no `s3:PutObject` or `s3:DeleteObject`**.
   * Action: `dynamodb:PutItem`, `dynamodb:UpdateItem`, `dynamodb:GetItem` restricted to `DedupTable.Arn`.
   * Action: `ses:SendEmail`, `ses:SendRawEmail`.
   * **No VPC configuration; no database access**.

---

### Question 12: Observability, CloudWatch Metrics, & Failure Verification
**Answer:**
* **Key CloudWatch Metrics**:
  * `AWS/SQS ApproximateNumberOfMessagesVisible`: Queue backlog.
  * `AWS/SQS NumberOfMessagesSentToDLQ`: Dead-lettered failures requiring human intervention.
  * `AWS/Lambda Errors` & `Throttles`: Failures in Report Builder or Mailer.
  * `AWS/Lambda Duration`: Monitoring cold starts (especially Aurora 15s wake-up time).
* **Failure / DLQ Verification Procedure**:
  1. **Simulate a Failure**: Send a malformed payload to SQS:
     ```bash
     aws sqs send-message --queue-url <WeeklyReportQueueUrl> --message-body '{"week":"INVALID-WEEK"}'
     ```
  2. **Observe Retries**: The Report Builder Lambda rejects the invalid week with `ValueError`.
  3. **Verify Visibility Timeout & Redrive**: Lambda fails 3 times (`maxReceiveCount: 3`).
  4. **Verify DLQ Arrival**: SQS moves the poison pill to `WeeklyReportDLQ`.
  5. **Inspect DLQ Attributes**:
     ```bash
     aws sqs get-queue-attributes --queue-url <WeeklyReportDLQUrl> --attribute-names ApproximateNumberOfMessages
     ```
  6. **Inspect CloudWatch Logs**: Verify clear structured logs without exposed credentials.

---

### Question 13: Total Cost of Ownership (TCO): Serverless vs. Always-On EC2/ECS
**Answer:**
| Resource | Serverless Event-Driven Pipeline | Always-On Worker (EC2 `t4g.small` + NAT Gateway) |
| :--- | :--- | :--- |
| **Compute** | EventBridge ($0) + Lambda (~4 runs/mo, <2 min compute: $0 within Free Tier). | EC2 `t4g.small`: ~$12.50/month. |
| **VPC Egress** | S3 Gateway Endpoint: **$0.00 / month**. | NAT Gateway: **~$32.40 / month** ($0.045/hr) + data transfer. |
| **Queue / DB** | SQS (Free Tier: 1M req/mo) + DynamoDB Pay-Per-Request ($0.00). | Self-hosted queue or container overhead. |
| **Email** | SES (First 62,000 emails/mo free, then $0.10 / 1,000). | Same SES cost. |
| **Storage** | S3 (~5 MB storage with 90-day lifecycle: <$0.01). | EBS volume ($1.60/month). |
| **Total Monthly Cost** | **<$0.01 / month** (virtually 100% free under normal workloads) | **~$46.50 – $60.00 / month** |

The event-driven serverless architecture provides a **99.9% cost reduction**, eliminating idle compute and NAT Gateway overhead while scaling automatically.

---

## 3. Deployment Instructions

### Prerequisites
1. Fill `.env` with AWS credentials and database password:
   ```bash
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=...
   AWS_REGION=us-east-1
   PROJECT_NAME=successfulsuccess
   AWS_DB_PASSWORD=...
   REPORTS_SENDER_EMAIL=your-verified-email@example.com
   REPORTS_RECIPIENT_EMAIL=your-recipient@example.com
   ```
2. Verify AWS identity:
   ```bash
   make aws-whoami
   ```

### Step 1: Deploy Auth, Backend, and Database Stacks (if not already deployed)
```bash
make aws-deploy-auth
make aws-deploy-backend
```

### Step 2: Deploy the Reports Pipeline Stack
Deploy the dedicated `infra/reports.yml` CloudFormation stack:
```bash
make aws-deploy-reports
```
This automatically queries the default VPC, subnets, route tables, security group, ECR image, and database connection, provisioning:
* EventBridge Scheduler (`cron(0 7 ? * MON *)` in `Europe/Kyiv`)
* SQS Queue + DLQ
* Encrypted Reports S3 Bucket + S3 Gateway VPC Endpoint
* DynamoDB Deduplication Table
* Report Builder Lambda (in VPC)
* Mailer Lambda (outside VPC)

---

## 4. Amazon SES Setup Guide

AWS accounts start in the **Amazon SES Sandbox** by default. To receive report emails:

1. **Verify Sender Email Identity**:
   ```bash
   aws ses verify-email-identity --email-address "$REPORTS_SENDER_EMAIL"
   ```
   * Open the confirmation email sent by Amazon Web Services and click the verification link.
2. **Verify Recipient Email Identity (if in Sandbox)**:
   * While in SES Sandbox, you can only send emails to verified addresses.
   ```bash
   aws ses verify-email-identity --email-address "$REPORTS_RECIPIENT_EMAIL"
   ```
   * Click the verification link in the recipient mailbox.
3. **Verify Identity Status**:
   ```bash
   aws ses get-identity-verification-attributes --identities "$REPORTS_SENDER_EMAIL" "$REPORTS_RECIPIENT_EMAIL"
   ```
   Ensure `VerificationStatus` reports `Success`.

---

## 5. Evidence-Capture Checklist & Operational Commands

When submitting the lab assignment, run the following verification commands and record their output:

### 1. Run All Automated Tests
```bash
make test-reports
```
*Expected: 34 passed tests covering report generation, CSV structure, ISO week edge cases, DynamoDB deduplication, builder SQS dispatching, and mailer SES delivery.*

### 2. Check Reports Infrastructure Status
```bash
make aws-reports-status
```
*Captures CloudFormation stack outputs, queue attributes, and DLQ message counts.*

### 3. Trigger an On-Demand Report Run
```bash
make aws-trigger-report week=2026-W40
```

### 4. Check Generated S3 Object
```bash
aws s3 ls s3://successfulsuccess-reports-<ACCOUNT_ID>/reports/
```
*Expected: `reports/2026-W40.csv` present.*

### 5. Check CloudWatch Logs for Report Builder & Mailer
```bash
aws logs tail /aws/lambda/successfulsuccess-report-builder --since 10m
aws logs tail /aws/lambda/successfulsuccess-report-mailer --since 10m
```
*Verify: Log lines indicate trigger type, ISO week `2026-W40`, S3 upload, and SES message ID without logging database secrets.*

### 6. Verify Email Deduplication
Trigger the same week report a second time:
```bash
make aws-trigger-report week=2026-W40
```
Inspect Mailer logs:
```bash
aws logs tail /aws/lambda/successfulsuccess-report-mailer --since 5m
```
*Verify: Log confirms `Deduplication check: reports/2026-W40.csv already delivered or currently locked... duplicate_suppressed`.*

### 7. Clean Teardown
When finished evaluating the assignment, all stacks (including the reports stack and S3 reports bucket) can be deleted cleanly:
```bash
make aws-destroy
```
