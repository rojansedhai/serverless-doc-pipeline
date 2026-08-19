resource "aws_s3_bucket" "doc_storage" {
  bucket        = "${var.project_name}-storage-${var.environment}-${random_string.bucket_suffix.result}"
  force_destroy = var.environment != "prod"

  tags = {
    Name        = "${var.project_name}-storage-${var.environment}"
    Tiering     = "GlacierInstantRetrieval"
  }
}

resource "aws_s3_bucket_versioning" "doc_storage" {
  bucket = aws_s3_bucket.doc_storage.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "doc_storage" {
  bucket = aws_s3_bucket.doc_storage.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.pipeline_key.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "doc_storage" {
  bucket = aws_s3_bucket.doc_storage.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_notification" "doc_storage_eventbridge" {
  bucket      = aws_s3_bucket.doc_storage.id
  eventbridge = true
}

resource "aws_s3_bucket_cors_configuration" "doc_storage_cors" {
  bucket = aws_s3_bucket.doc_storage.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "GET", "HEAD", "POST"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "doc_storage_lifecycle" {
  bucket = aws_s3_bucket.doc_storage.id

  # Rule 1: Auto-expire transient raw upload staging files after 7 days
  rule {
    id     = "expire-raw-uploads"
    status = "Enabled"

    filter {
      prefix = "uploads/"
    }

    expiration {
      days = var.s3_retention_days_raw
    }

    noncurrent_version_expiration {
      noncurrent_days = 3
    }
  }

  # Rule 2: Tier processed permanent invoices to Glacier Instant Retrieval after 30 days
  rule {
    id     = "tier-processed-to-glacier-ir"
    status = "Enabled"

    filter {
      prefix = "processed/"
    }

    transition {
      days          = var.s3_glacier_transition_days
      storage_class = "GLACIER_IR"
    }

    noncurrent_version_transition {
      noncurrent_days = var.s3_glacier_transition_days
      storage_class   = "GLACIER_IR"
    }
  }
}

resource "aws_s3_bucket_policy" "enforce_tls" {
  bucket = aws_s3_bucket.doc_storage.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.doc_storage.arn,
          "${aws_s3_bucket.doc_storage.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}
