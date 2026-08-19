# Building a $0-Idle-Cost Document Processor Using EventBridge and S3 Presigned URLs

*How modern serverless architecture eliminates idle infrastructure costs while scaling securely across multiple SaaS tenants.*

---

## The Challenge: The Idle Server Trap

Document and invoice processing (OCR, receipt metadata extraction, watermark stamping, format conversion) is inherently **bursty**. 

A typical SaaS product might ingest 50,000 invoices on the 1st of the month during billing runs, but only 200 documents a day throughout the rest of the cycle.

Traditional architectural approaches rely on:
1. **Always-on EC2/ECS Worker Clusters**: Dedicated VMs running Celery, BullMQ, or background worker pools. They incur 24/7 compute and licensing costs even when queue traffic drops to zero ($150–$600+/month minimum).
2. **Synchronous Upload Proxies**: Routing multi-megabyte binary payloads through application servers or API Gateways, resulting in memory spikes, network bottlenecks, and strict 29-second timeout limits.

In this article, we demonstrate how to build an **enterprise-grade, completely asynchronous, multi-tenant document pipeline** that incurs **$0 in idle costs** using Amazon S3 Presigned URLs, Amazon EventBridge, AWS Lambda, Amazon DynamoDB (Single-Table Design), and Amazon S3 Glacier Instant Retrieval.

---

## Architectural Blueprint

```
 +------------------+          +------------------------+
 |   Client App /   |  (1) JWT |   Amazon API Gateway   |
 |  Web / Mobile    |--------->|       (HTTP API)       |
 +------------------+          +------------------------+
         |                                 |
         | (2) Get Presigned URL           | Proxy to Lambda
         |                                 v
         |                     +------------------------+
         |                     |   Presigned URL Gen    |
         |                     |      AWS Lambda        |
         |                     +------------------------+
         |                                 | (3) Issue Scoped PUT URL
         v                                 v
+-------------------------------------------------------------+
|              Amazon S3 (Encrypted via AWS KMS)              |
|  Prefix: uploads/{tenant_id}/{doc_id}/{filename}            |
+-------------------------------------------------------------+
         |
         | (4) Direct S3 Event Notification (ObjectCreated)
         v
+-------------------------------------------------------------+
|                     Amazon EventBridge                      |
|  Rule Filter: detail.bucket.name & detail.object.key        |
+-------------------------------------------------------------+
         |
         | (5) Decoupled Event Routing
         v
+-------------------------------------------------------------+
|              Document Processor AWS Lambda                  |
|  - Extract OCR / Text / Metadata (Textract / PyPDF)         |
|  - Apply Security Watermarking                              |
|  - Save Artifact to processed/{tenant_id}/{doc_id}/         |
+-------------------------------------------------------------+
         |
         | (6) Atomic Status & Metadata Update
         v
+-------------------------------------------------------------+
|                    Amazon DynamoDB                          |
|         Single-Table Design with GSI for Tenancy            |
+-------------------------------------------------------------+
```

---

## Core Pillars of the Architecture

### 1. Direct-to-S3 Uploads via Presigned URLs
Instead of proxying large binaries through API Gateway and compute instances:
- The client authenticates via JWT (Amazon Cognito or OAuth2).
- The client sends a lightweight `POST /upload-url` request with the filename and content type.
- The `get_presigned_url` Lambda extracts the authenticated `tenant_id` from the JWT claims and issues a temporary (15-minute) presigned `PUT` URL scoped to:
  ```
  s3://<bucket>/uploads/{tenant_id}/{doc_id}/{sanitized_filename}
  ```
- The client uploads the binary directly to S3 with end-to-end KMS encryption.

**Benefits**:
- Zero memory pressure on compute layers.
- Bypass API Gateway 10MB payload limit.
- S3 handles high-bandwidth parallel uploads automatically.

---

### 2. S3 Event Notifications Native to EventBridge
Instead of managing SQS queues or polling mechanisms, we activate native EventBridge notifications on the S3 bucket:

```hcl
resource "aws_s3_bucket_notification" "doc_storage_eventbridge" {
  bucket      = aws_s3_bucket.doc_storage.id
  eventbridge = true
}
```

EventBridge filters events at the routing layer so only relevant `ObjectCreated` events in the `uploads/` prefix trigger the processor:

```json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "bucket": { "name": ["doc-pipeline-storage-prod-xyz"] },
    "object": { "key": [{ "prefix": "uploads/" }] }
  }
}
```

---

### 3. Multi-Tenant Isolation & IDOR Protection
Security in multi-tenant serverless applications requires strict partition boundaries across all layers:

1. **Storage Isolation**: Raw and processed files are partitioned under `{prefix}/{tenant_id}/{doc_id}/`.
2. **Authorizer Claim Validation**: The `tenant_id` is derived strictly from the cryptographically verified JWT claim (`custom:tenant_id` or `sub`). Client-provided path parameters cannot override this identity, eliminating Insecure Direct Object References (IDOR).
3. **Single-Table DynamoDB Schema**:
   - `PK`: `TENANT#<tenant_id>`
   - `SK`: `DOC#<doc_id>`
   - `GSI1PK`: `TENANT#<tenant_id>#STATUS#<status>`
   - `GSI1SK`: `CREATED#<timestamp>`

Because DynamoDB queries require partition key specification, cross-tenant data leakage is structurally impossible.

---

### 4. Storage Tiering: Glacier Instant Retrieval
Document storage costs compound over time. Invoices and receipts must be retained for years for regulatory compliance, yet they are rarely accessed after the initial processing week.

We configure automatic S3 Lifecycle rules:
- **Raw Staging Files (`uploads/`)**: Auto-deleted after 7 days once processed.
- **Processed Documents (`processed/`)**: Transitioned to **Glacier Instant Retrieval (GLACIER_IR)** after 30 days.

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "doc_storage_lifecycle" {
  bucket = aws_s3_bucket.doc_storage.id

  rule {
    id     = "tier-processed-to-glacier-ir"
    status = "Enabled"
    filter { prefix = "processed/" }
    transition {
      days          = 30
      storage_class = "GLACIER_IR"
    }
  }
}
```

*Savings*: S3 Standard costs ~$0.023/GB-month. Glacier Instant Retrieval costs ~$0.004/GB-month — an **immediate 68%–83% reduction in ongoing storage costs** while preserving millisecond retrieval latencies when a user requests a download.

---

## Cost Comparison: Always-On Cluster vs. Event-Driven Serverless

| Volume (Docs / Month) | 2x t3.medium ECS Cluster + ALB | Serverless Event Pipeline (This Architecture) | Monthly Savings |
| :--- | :--- | :--- | :--- |
| **0 (Idle Month)** | ~$72.50 / month | **$0.00 / month** | **100%** |
| **10,000 docs** | ~$74.20 / month | **$0.42 / month** | **99.4%** |
| **100,000 docs** | ~$82.10 / month | **$4.18 / month** | **94.9%** |
| **1,000,000 docs** | ~$180.00+ / month (scaling needed) | **$41.50 / month** | **76.9%** |

*(Calculated based on 512MB Lambda executing in 450ms, S3 PUT/GET calls, EventBridge events, and DynamoDB On-Demand capacity in us-east-1).*

---

## Summary & Key Takeaways

1. **True $0 Idle Cost**: By using API Gateway HTTP APIs, DynamoDB On-Demand, EventBridge, and Lambda (Arm64), your baseline infrastructure costs $0.00 when traffic is zero.
2. **Uncapped Scalability**: S3 presigned uploads absorb massive parallel document drops without choking backend servers.
3. **Built-in Security**: Multi-tenant boundaries, KMS encryption at rest, and JWT claims eliminate cross-tenant data leaks by design.
4. **Instant Long-Term Savings**: Automated lifecycle tiering to Glacier Instant Retrieval slashes storage overhead automatically as your data lake grows.
