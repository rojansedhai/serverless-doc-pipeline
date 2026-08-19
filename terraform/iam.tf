# -----------------------------------------------------------------------------
# Base Assume Role Policy for Lambda
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# -----------------------------------------------------------------------------
# 1. Presigned URL Generator Lambda Role & Policy
# -----------------------------------------------------------------------------
resource "aws_iam_role" "presigned_url_role" {
  name               = "${var.project_name}-presigned-url-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_policy" "presigned_url_policy" {
  name        = "${var.project_name}-presigned-url-policy-${var.environment}"
  description = "Permissions for generating presigned upload URLs and recording pending docs"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-get-presigned-url-*"
      },
      {
        Sid    = "S3PutPresignedScoped"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectTagging"
        ]
        Resource = "${aws_s3_bucket.doc_storage.arn}/uploads/*"
      },
      {
        Sid    = "DynamoDBPutPending"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem"
        ]
        Resource = aws_dynamodb_table.doc_metadata.arn
      },
      {
        Sid    = "KMSAccess"
        Effect = "Allow"
        Action = [
          "kms:GenerateDataKey*",
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.pipeline_key.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "presigned_url_attach" {
  role       = aws_iam_role.presigned_url_role.name
  policy_arn = aws_iam_policy.presigned_url_policy.arn
}

# -----------------------------------------------------------------------------
# 2. Document Processor Lambda Role & Policy
# -----------------------------------------------------------------------------
resource "aws_iam_role" "doc_processor_role" {
  name               = "${var.project_name}-doc-processor-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_policy" "doc_processor_policy" {
  name        = "${var.project_name}-doc-processor-policy-${var.environment}"
  description = "Permissions for OCR processing, watermarking, DynamoDB updates, and S3 tiering"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-doc-processor-*"
      },
      {
        Sid    = "S3RawReadAndProcessedWrite"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectTagging",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.doc_storage.arn}/uploads/*"
      },
      {
        Sid    = "S3ProcessedWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectTagging"
        ]
        Resource = "${aws_s3_bucket.doc_storage.arn}/processed/*"
      },
      {
        Sid    = "DynamoDBUpdateStatus"
        Effect = "Allow"
        Action = [
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:PutItem"
        ]
        Resource = aws_dynamodb_table.doc_metadata.arn
      },
      {
        Sid    = "TextractExtraction"
        Effect = "Allow"
        Action = [
          "textract:AnalyzeExpense",
          "textract:DetectDocumentText"
        ]
        Resource = "*"
      },
      {
        Sid    = "KMSOperations"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.pipeline_key.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "doc_processor_attach" {
  role       = aws_iam_role.doc_processor_role.name
  policy_arn = aws_iam_policy.doc_processor_policy.arn
}

# -----------------------------------------------------------------------------
# 3. Document Status Query Lambda Role & Policy
# -----------------------------------------------------------------------------
resource "aws_iam_role" "get_doc_status_role" {
  name               = "${var.project_name}-doc-status-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_policy" "get_doc_status_policy" {
  name        = "${var.project_name}-doc-status-policy-${var.environment}"
  description = "Permissions for querying document metadata and issuing presigned GET URLs"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-get-doc-status-*"
      },
      {
        Sid    = "DynamoDBQuery"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.doc_metadata.arn,
          "${aws_dynamodb_table.doc_metadata.arn}/index/*"
        ]
      },
      {
        Sid    = "S3DownloadPresigned"
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.doc_storage.arn}/processed/*"
      },
      {
        Sid    = "KMSDecrypt"
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = aws_kms_key.pipeline_key.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "get_doc_status_attach" {
  role       = aws_iam_role.get_doc_status_role.name
  policy_arn = aws_iam_policy.get_doc_status_policy.arn
}
