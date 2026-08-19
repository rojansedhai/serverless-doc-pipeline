# Multi-Tenant Event-Driven Document & Invoicing Pipeline

[![Terraform](https://img.shields.io/badge/IaC-Terraform-623CE4.svg)](https://www.terraform.io/)
[![AWS Serverless](https://img.shields.io/badge/AWS-Serverless-FF9900.svg)](https://aws.amazon.com/serverless/)
[![Architecture](https://img.shields.io/badge/Architecture-Event--Driven-00C7B7.svg)]()
[![License](https://img.shields.io/badge/License-MIT-blue.svg)]()

An enterprise-grade, secure, multi-tenant document and invoice processing pipeline built on AWS. Designed for **$0 idle infrastructure cost**, sub-second response times, and automated lifecycle tiering.

---

## 🏗️ System Architecture

```
 +------------------+          +------------------------+
 |   Client App /   |  (1) JWT |   Amazon API Gateway   |
 |  Web / Postman   |--------->|       (HTTP API)       |
 +------------------+          +------------------------+
         |                                 |
         | (2) Get Presigned URL           | Proxy to Lambda
         |                                 v
         |                     +------------------------+
         |                     |   Presigned URL Gen    |
         |                     |      AWS Lambda        |
         |                     +------------------------+
         |                                 | (3) Validate Tenant ID & Issue
         v                                 v
+-------------------------------------------------------------+
|              Amazon S3 (Encrypted via AWS KMS)              |
|  Prefix: uploads/{tenant_id}/{doc_id}/{filename}            |
+-------------------------------------------------------------+
         |
         | (4) S3 Event Notification (ObjectCreated)
         v
+-------------------------------------------------------------+
|                     Amazon EventBridge                      |
|  Rule Filter: detail.bucket.name & detail.object.key        |
+-------------------------------------------------------------+
         |
         | (5) Event-Driven Worker Trigger
         v
+-------------------------------------------------------------+
|              Document Processor AWS Lambda                  |
|  - Extract OCR / Text / Metadata (Textract / PyPDF)         |
|  - Apply Security Watermarking                              |
|  - Store output to processed/{tenant_id}/{doc_id}/          |
+-------------------------------------------------------------+
         |
         | (6) Record Metadata, Status & Metrics
         v
+-------------------------------------------------------------+
|                    Amazon DynamoDB                          |
|         Single-Table Design with GSI for Tenancy            |
+-------------------------------------------------------------+
```

---

## 🔒 Multi-Tenant Security & Isolation Highlights

1. **Cryptographic Identity Propagation (No IDOR)**:
   - Client requests carry a verified Cognito / OAuth2 JWT.
   - The `tenant_id` is extracted strictly from verified token claims (`custom:tenant_id` or `sub`).
   - S3 partition paths and DynamoDB query keys are enforced by the serverless compute layer.
2. **KMS Customer Managed Key (CMK)**:
   - Dedicated KMS key with automatic rotation encrypting both S3 storage and DynamoDB metadata at rest.
   - S3 Bucket Policy denies unencrypted and non-TLS requests (`aws:SecureTransport = false`).
3. **Least-Privilege IAM Scoping**:
   - Distinct execution roles per Lambda.
   - Presigned URL Lambda can only write to `uploads/*`.
   - Processor Lambda can only read from `uploads/*` and write to `processed/*`.
4. **Storage Tiering to Glacier Instant Retrieval**:
   - Transient `uploads/` are purged after 7 days.
   - Permanent `processed/` documents transition to `GLACIER_IR` (Glacier Instant Retrieval) after 30 days for 68%+ cost savings while retaining millisecond retrieval speed.

---

## 📂 Repository Structure

```
serverless-doc-pipeline/
├── terraform/                      # Infrastructure as Code (Terraform)
│   ├── main.tf                    # Provider setup and global resources
│   ├── variables.tf               # Configurable variables
│   ├── outputs.tf                 # API endpoints, S3 bucket names, pool IDs
│   ├── kms.tf                     # KMS CMK encryption configuration
│   ├── cognito.tf                 # Cognito User Pool & App Client
│   ├── s3.tf                      # S3 bucket, lifecycle rules & EventBridge enable
│   ├── dynamodb.tf                # Single-table schema (PK, SK, GSI1, TTL)
│   ├── iam.tf                     # Scoped least-privilege IAM roles & policies
│   ├── lambda.tf                  # Lambda functions, packaging & log groups
│   ├── eventbridge.tf             # S3 ObjectCreated EventBridge routing rule
│   ├── apigateway.tf              # HTTP API v2, JWT authorizer & routes
│   └── terraform.tfvars.example   # Example variables
├── src/                           # Lambda Function Source Code
│   ├── shared/
│   │   └── dynamodb_service.py    # Reusable Single-Table DynamoDB client
│   ├── get_presigned_url/
│   │   ├── handler.py             # Tenant-scoped PUT URL generator
│   │   └── requirements.txt
│   ├── doc_processor/
│   │   ├── handler.py             # EventBridge OCR & invoice processor
│   │   └── requirements.txt
│   └── get_doc_status/
│       ├── handler.py             # Document status & presigned GET downloader
│       └── requirements.txt
├── scripts/
│   ├── build.py                   # Packages Lambdas into zip archives
│   ├── deploy.ps1 / deploy.sh     # One-click deployment scripts
│   └── test_pipeline.py           # Automated end-to-end and security test suite
├── docs/
│   ├── blog_zero_idle_cost_doc_processor.md # Ready-to-publish blog post
│   └── deep_dive_cold_start_benchmark.md    # Technical benchmark whitepaper
└── README.md                      # Project documentation
```

---

## 🚀 Step-by-Step Deployment Guide

### Prerequisites
- [AWS CLI](https://aws.amazon.com/cli/) configured with deployment credentials.
- [Terraform](https://www.terraform.io/) (>= 1.5.0).
- [Python](https://www.python.org/) (3.10+).

---

### Step 1: Package Lambda Artifacts
Run the build script to package the Lambda handlers and shared single-table modules:

```bash
python scripts/build.py
```

---

### Step 2: Configure & Deploy Infrastructure with Terraform

```bash
cd terraform

# 1. Initialize Terraform providers
terraform init

# 2. Review execution plan
terraform plan

# 3. Deploy infrastructure
terraform apply -auto-approve
```

Upon completion, Terraform will output your live endpoints:
```
Outputs:
api_endpoint               = "https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com"
cognito_user_pool_id       = "us-east-1_xxxxxxxxx"
cognito_user_pool_client_id = "xxxxxxxxxxxxxxxxxxxxxxxxxx"
dynamodb_table_name        = "doc-pipeline-metadata-prod"
s3_bucket_name             = "doc-pipeline-storage-prod-abc12345"
```

---

### Step 3: Run Automated End-to-End & Security Tests

Run the included verification script against your deployed API Gateway endpoint:

```bash
python scripts/test_pipeline.py --api-url "https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com"
```

This automated test executes:
1. `POST /upload-url`: Obtains S3 Presigned PUT URL for `tenant-alpha`.
2. Direct S3 Upload: Sends a sample invoice PDF payload.
3. Asynchronous Event Routing: EventBridge triggers `doc_processor` Lambda.
4. Polling & Status Verification: Verifies status transitions to `PROCESSED` with extracted metadata (Vendor, Total, Invoice Number).
5. Multi-Tenant IDOR Security Test: Verifies `tenant-beta` is strictly denied from accessing `tenant-alpha`'s document (`HTTP 404/403`).
6. Presigned GET Download: Verifies processed artifact download with watermark signature.

---

## 📊 API Specification

### 1. Request Presigned Upload URL
`POST /upload-url`
- **Headers**: `Authorization: Bearer <JWT>` or `X-Tenant-Id: <tenant_id>`
- **Body**:
  ```json
  {
    "filename": "invoice_2026_08.pdf",
    "contentType": "application/pdf"
  }
  ```
- **Response** (HTTP 200):
  ```json
  {
    "message": "Presigned upload URL generated successfully",
    "docId": "550e8400-e29b-41d4-a716-446655440000",
    "tenantId": "tenant-alpha",
    "s3Key": "uploads/tenant-alpha/550e8400-e29b-41d4-a716-446655440000/invoice_2026_08.pdf",
    "uploadUrl": "https://doc-pipeline-storage...s3.amazonaws.com/uploads/...",
    "expiresInSeconds": 900
  }
  ```

---

### 2. Query Document Status & Extracted Metadata
`GET /documents/{doc_id}`
- **Headers**: `Authorization: Bearer <JWT>` or `X-Tenant-Id: <tenant_id>`
- **Response** (HTTP 200):
  ```json
  {
    "DocId": "550e8400-e29b-41d4-a716-446655440000",
    "TenantId": "tenant-alpha",
    "Status": "PROCESSED",
    "CreatedAt": "2026-08-17T15:20:00Z",
    "UpdatedAt": "2026-08-17T15:20:02Z",
    "ExtractedMetadata": {
      "vendor_name": "Acme Cloud Services LLC",
      "invoice_number": "INV-98231",
      "total_amount": "1420.50",
      "currency": "USD",
      "processing_duration_ms": 342.5
    },
    "S3ProcessedKey": "processed/tenant-alpha/550e8400-e29b-41d4-a716-446655440000/processed_invoice_2026_08.pdf",
    "downloadUrl": "https://doc-pipeline-storage...s3.amazonaws.com/processed/..."
  }
  ```

---

### 3. List Tenant Documents
`GET /documents?status=PROCESSED&limit=20`
- **Headers**: `Authorization: Bearer <JWT>` or `X-Tenant-Id: <tenant_id>`

---

## 🧹 Teardown

To destroy all cloud resources and avoid any ongoing storage fees:

```bash
cd terraform
terraform destroy -auto-approve
```

---

## 📖 Published Content Artifacts

- **Blog Article**: [Stop Paying for Idle Clusters: How I Built a Cheap Document Processing Pipeline on AWS](https://medium.com/@rojansedhai01/stop-paying-for-idle-clusters-how-i-built-a-cheap-document-processing-pipeline-on-aws-54471ff8be24?sharedUserId=rojansedhai01)
- **Technical Whitepaper**: [Comparative Benchmark: Lambda Cold-Start Tuning with Container Images vs. Lambda Layers](https://github.com/rojansedhai/serverless-doc-pipeline/blob/main/docs/deep_dive_cold_start_benchmark.md)
