# Building a $0-Idle-Cost Document & Invoicing Pipeline on AWS (With Multi-Tenant IDOR Protection & S3 Tiering)

*How modern event-driven serverless architecture eliminates 24/7 cluster costs, handles bursty traffic spikes, and enforces cryptographic tenant isolation.*

---

[![GitHub Repo](https://img.shields.io/badge/GitHub-rojansedhai%2Fserverless--doc--pipeline-181717?style=for-the-badge&logo=github)](https://github.com/rojansedhai/serverless-doc-pipeline)
[![Terraform](https://img.shields.io/badge/IaC-Terraform-623CE4?style=for-the-badge&logo=terraform)](https://github.com/rojansedhai/serverless-doc-pipeline/tree/main/terraform)
[![AWS Serverless](https://img.shields.io/badge/AWS-Serverless-FF9900?style=for-the-badge&logo=amazonaws)](https://github.com/rojansedhai/serverless-doc-pipeline)

> 🔗 **Full Open-Source Codebase**: All Terraform configurations, Lambda handlers, and the interactive frontend demo portal are available on GitHub: [**github.com/rojansedhai/serverless-doc-pipeline**](https://github.com/rojansedhai/serverless-doc-pipeline).

---

## 1. The Challenge: The "Idle Server" Trap

Document and invoice processing (OCR, receipt metadata extraction, watermark stamping, PDF format conversions) is inherently **bursty**:

* A B2B SaaS platform might ingest **50,000 invoices on the 1st of every month** during customer billing runs.
* For the remaining 29 days, traffic drops to just **a few hundred files a day**.

```
Traffic
  ▲
  │       ┌─┐ Billing Spike (50,000 docs/day)
  │       │ │
  │       │ │
  │       │ │
  │───────┘ └───────────────────────── Normal Traffic (~200 docs/day)
  └───────────────────────────────────► Time
```

### Traditional Approaches & Why They Fail:
1. **Always-On ECS/EC2 Worker Clusters**: Running background workers (Celery, BullMQ, Sidekiq) on 2x `t3.medium` instances with an ALB costs **$70 to $200+/month** minimum — even when processing zero documents.
2. **Synchronous Upload Proxies**: Streaming multi-megabyte binary PDFs through API Gateway or monolithic web servers introduces high memory pressure, network bottlenecks, and strict 29-second timeout limits.

In this article, we'll build an **enterprise-grade, completely asynchronous, multi-tenant document pipeline** that incurs **$0 in idle costs** using:
* **Amazon S3 Presigned URLs** (Direct browser-to-storage uploads)
* **Amazon EventBridge** (Native decoupled event routing)
* **AWS Lambda (Arm64 Graviton3)** (Zero-idle on-demand compute)
* **Amazon DynamoDB** (Single-Table Design with GSI isolation)
* **Amazon S3 Glacier Instant Retrieval** (Automated lifecycle tiering)
* **Amazon Cognito & API Gateway HTTP API (v2)** (Cryptographic IDOR defense)

---

## 2. Architectural Blueprint

Here is how data flows from the browser to cold storage without a single byte blocking the web server:

```
 +--------------------+          +--------------------------+
 |  Web App / Client  |  (1) JWT |    Amazon API Gateway    |
 | (Interactive SaaS) |--------->|     (HTTP API + CORS)    |
 +--------------------+          +--------------------------+
          │                                   │
          │ (2) POST /upload-url              │ Proxy to Lambda
          │                                   ▼
          │                       +-------------------------+
          │                       |    Presigned URL Gen    |
          │                       |  AWS Lambda (Python 3.12|
          │                       +-------------------------+
          │                                   │ (3) Issue Scoped PUT URL
          ▼                                   ▼
+---------------------------------------------------------------+
|               Amazon S3 Storage (Encrypted via KMS)           |
|   Key: uploads/{tenant_id}/{doc_id}/{sanitized_filename}      |
+---------------------------------------------------------------+
          │
          │ (4) Native Event Notification (ObjectCreated)
          ▼
+---------------------------------------------------------------+
|                      Amazon EventBridge                       |
|   Rule Filter: detail.bucket.name & detail.object.key         |
+---------------------------------------------------------------+
          │
          │ (5) Asynchronous Event Trigger
          ▼
+---------------------------------------------------------------+
|                 Document Processor AWS Lambda                 |
|   - Extract Invoice Fields (Textract AnalyzeExpense / OCR)   |
|   - Apply Cryptographic Security Watermark                    |
|   - Save Output to processed/{tenant_id}/{doc_id}/            |
+---------------------------------------------------------------+
          │
          │ (6) Atomic Record Update
          ▼
+---------------------------------------------------------------+
|                       Amazon DynamoDB                         |
|   Single-Table Design: PK: TENANT#{id} | SK: DOC#{id}         |
+---------------------------------------------------------------+
```

---

## 3. Core Architectural Pillars

### Pillar 1: Direct S3 Ingestion via Scoped Presigned URLs
Instead of forcing large binary PDFs through backend servers, the client requests a short-lived (15-minute) presigned `PUT` URL.

The Lambda function extracts the verified tenant identity from the JWT claims and binds the upload destination strictly to the tenant's partition:

```python
# From src/get_presigned_url/handler.py
s3_key = f"uploads/{tenant_id}/{doc_id}/{sanitized_filename}"

presigned_url = s3_client.generate_presigned_url(
    ClientMethod="put_object",
    Params={
        "Bucket": S3_BUCKET,
        "Key": s3_key,
        "ContentType": content_type
    },
    ExpiresIn=900,
    HttpMethod="PUT"
)
```

👉 *Inspect the full implementation in [`src/get_presigned_url/handler.py`](https://github.com/rojansedhai/serverless-doc-pipeline/blob/main/src/get_presigned_url/handler.py).*

---

### Pillar 2: Decoupled Event Routing via Amazon EventBridge
Instead of managing SQS queues or polling loops, we enable native EventBridge notifications directly on the S3 bucket:

```hcl
# From terraform/s3.tf & terraform/eventbridge.tf
resource "aws_s3_bucket_notification" "doc_storage_eventbridge" {
  bucket      = aws_s3_bucket.doc_storage.id
  eventbridge = true
}

resource "aws_cloudwatch_event_rule" "doc_upload_rule" {
  name        = "doc-pipeline-s3-upload-rule-prod"
  description = "Routes S3 raw document uploads to the document processor Lambda"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [aws_s3_bucket.doc_storage.id] }
      object = { key  = [{ prefix = "uploads/" }] }
    }
  })
}
```

> **Why this matters**: Because the EventBridge rule filters strictly on `uploads/`, when the processor writes the transformed PDF to `processed/`, it does **not** trigger the rule again — preventing recursive processing loops.

👉 *Check the IaC definitions in [`terraform/eventbridge.tf`](https://github.com/rojansedhai/serverless-doc-pipeline/blob/main/terraform/eventbridge.tf).*

---

### Pillar 3: Multi-Tenant Zero-Trust Isolation (IDOR Defense)
Insecure Direct Object References (IDOR) happen when backend services trust user-supplied tenant IDs from the URL query or request body.

In this pipeline, tenant identity is derived **exclusively** from cryptographically verified Cognito JWT claims:

```
[Incoming Request]
       │
       ▼
[API Gateway JWT Authorizer]  ──► Validates RS256 signature & User Pool Client ID
       │
       ▼
[Lambda Execution Context]    ──► Reads claims["custom:tenant_id"]
       │
       ▼
[DynamoDB Single-Table Query] ──► PK: TENANT#{claims["custom:tenant_id"]}
```

Even if `tenant-beta` discovers a valid document UUID belonging to `tenant-alpha`, querying `/documents/{doc_id}` with `tenant-beta`'s token fails at the DynamoDB partition level with an immediate `HTTP 404/403`:

```python
# From src/shared/dynamodb_service.py
def get_document_by_id(tenant_id: str, doc_id: str):
    response = table.get_item(
        Key={
            "PK": f"TENANT#{tenant_id}",  # Tenant boundary enforced at database key
            "SK": f"DOC#{doc_id}"
        }
    )
    return response.get("Item")
```

👉 *Review the Single-Table DynamoDB schema in [`src/shared/dynamodb_service.py`](https://github.com/rojansedhai/serverless-doc-pipeline/blob/main/src/shared/dynamodb_service.py).*

---

### Pillar 4: Storage Tiering with Glacier Instant Retrieval
Document storage costs compound over time. While compliance requires retaining invoices for 7+ years, files are rarely accessed after the first 30 days.

We configured S3 Lifecycle rules to automate tiering:
1. **Raw uploads (`uploads/`)**: Purged after 7 days once processed.
2. **Processed documents (`processed/`)**: Transitioned to **Glacier Instant Retrieval (`GLACIER_IR`)** after 30 days.

```hcl
# From terraform/s3.tf
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

* **S3 Standard**: ~$0.023 / GB-month
* **S3 Glacier Instant Retrieval**: ~$0.004 / GB-month
* **Result**: **~83% cost reduction** with millisecond retrieval speed when a user requests a download.

---

## 4. Cost Comparison: Always-On Cluster vs. Serverless

| Monthly Volume | 2x t3.medium ECS Cluster + ALB | Serverless Event Pipeline (This Architecture) | Monthly Savings |
| :--- | :--- | :--- | :--- |
| **0 docs (Idle Month)** | ~$72.50 / month | **$0.00 / month** | **100%** |
| **10,000 docs** | ~$74.20 / month | **$0.42 / month** | **99.4%** |
| **100,000 docs** | ~$82.10 / month | **$4.18 / month** | **94.9%** |
| **1,000,000 docs** | ~$180.00+ / month | **$41.50 / month** | **76.9%** |

*(Calculated on AWS us-east-1 pricing: Arm64 512MB Lambda executing in ~450ms, S3 PUT/GET, DynamoDB On-Demand capacity, and EventBridge events).*

---

## 5. Live SaaS Dashboard & Interactive Testing

To test and demonstrate the pipeline end-to-end, the project includes a standalone **Enterprise SaaS Dashboard** built with vanilla ES6 modules and CSS (located in [`frontend/`](https://github.com/rojansedhai/serverless-doc-pipeline/tree/main/frontend)):

*(Insert screenshot of Document Ingestion & Live Pipeline Tracker)*

### Key Features of the Demo Portal:
1. **Context Switcher**: Instant switching between `Tenant Alpha (Enterprise)` and `Tenant Beta (Logistics)`.
2. **Preset Ingestion**: 1-Click synthetic invoice generator testing compute charges, line items, and totals.
3. **Live 5-Step Pipeline Tracker**: Real-time visual feedback across JWT validation, S3 PUT upload, EventBridge trigger, OCR extraction, and DynamoDB commit.
4. **Interactive IDOR Security Benchmark**: Live cross-tenant exploit simulator attempting unauthorized access to verify partition barriers.

*(Insert screenshot of IDOR Security Benchmark Exploit Test)*

---

## 6. How to Deploy in Under 5 Minutes

You can deploy the complete infrastructure to your AWS account in 3 commands:

### Prerequisites:
* [AWS CLI](https://aws.amazon.com/cli/) configured
* [Terraform >= 1.5.0](https://www.terraform.io/)
* [Python 3.10+](https://www.python.org/)

```bash
# 1. Clone the GitHub repository
git clone https://github.com/rojansedhai/serverless-doc-pipeline.git
cd serverless-doc-pipeline

# 2. Package Lambda artifacts
python scripts/build.py

# 3. Deploy full infrastructure with Terraform
cd terraform
terraform init
terraform apply -auto-approve
```

### Run the Automated Security & E2E Test Suite:
```bash
python scripts/test_pipeline.py --api-url "<YOUR_API_GATEWAY_URL>"
```

👉 *Find step-by-step setup guides in the [Project README](https://github.com/rojansedhai/serverless-doc-pipeline#readme).*

---

## 7. Key Takeaways

1. **Eliminate Idle Waste**: If your workload is bursty, serverless event-driven architecture drops baseline operational expenses to **$0.00**.
2. **Offload Heavy I/O**: Direct-to-S3 presigned uploads protect backend compute from memory spikes and network saturation.
3. **Enforce Security at Key Boundaries**: Multi-tenancy must rely on cryptographically verified JWT claims mapped directly to DynamoDB partition keys (`PK: TENANT#<id>`), eliminating IDOR vulnerabilities.
4. **Automate Storage Tiering**: Transitioning older documents to Glacier Instant Retrieval saves 80%+ on compounding storage bills without adding retrieval delays.

---

### 📚 Links & References
* 💻 **GitHub Repository**: [rojansedhai/serverless-doc-pipeline](https://github.com/rojansedhai/serverless-doc-pipeline)
* 📑 **Cold-Start Benchmark Whitepaper**: [Lambda Cold-Start Tuning for Headless PDF & OCR](https://github.com/rojansedhai/serverless-doc-pipeline/blob/main/docs/deep_dive_cold_start_benchmark.md)
* 🛠️ **Terraform Infrastructure Code**: [`/terraform` directory](https://github.com/rojansedhai/serverless-doc-pipeline/tree/main/terraform)
