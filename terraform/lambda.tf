# -----------------------------------------------------------------------------
# Archive Packages for Lambda Functions
# -----------------------------------------------------------------------------
data "archive_file" "presigned_url_pkg" {
  type        = "zip"
  output_path = "${path.module}/.builds/get_presigned_url.zip"

  source {
    content  = file("${path.module}/../src/get_presigned_url/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${path.module}/../src/shared/dynamodb_service.py")
    filename = "shared/dynamodb_service.py"
  }
  source {
    content  = file("${path.module}/../src/shared/__init__.py")
    filename = "shared/__init__.py"
  }
}

data "archive_file" "doc_processor_pkg" {
  type        = "zip"
  output_path = "${path.module}/.builds/doc_processor.zip"

  source {
    content  = file("${path.module}/../src/doc_processor/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${path.module}/../src/shared/dynamodb_service.py")
    filename = "shared/dynamodb_service.py"
  }
  source {
    content  = file("${path.module}/../src/shared/__init__.py")
    filename = "shared/__init__.py"
  }
}

data "archive_file" "get_doc_status_pkg" {
  type        = "zip"
  output_path = "${path.module}/.builds/get_doc_status.zip"

  source {
    content  = file("${path.module}/../src/get_doc_status/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${path.module}/../src/shared/dynamodb_service.py")
    filename = "shared/dynamodb_service.py"
  }
  source {
    content  = file("${path.module}/../src/shared/__init__.py")
    filename = "shared/__init__.py"
  }
}

# -----------------------------------------------------------------------------
# 1. Presigned URL Generator Lambda
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "presigned_url_logs" {
  name              = "/aws/lambda/${var.project_name}-get-presigned-url-${var.environment}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "get_presigned_url" {
  function_name    = "${var.project_name}-get-presigned-url-${var.environment}"
  role             = aws_iam_role.presigned_url_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"] # Cost & Cold-start optimization
  memory_size      = 256
  timeout          = 15

  filename         = data.archive_file.presigned_url_pkg.output_path
  source_code_hash = data.archive_file.presigned_url_pkg.output_base64sha256

  environment {
    variables = {
      S3_BUCKET_NAME         = aws_s3_bucket.doc_storage.id
      DYNAMODB_TABLE_NAME    = aws_dynamodb_table.doc_metadata.name
      URL_EXPIRATION_SECONDS = var.url_expiration_seconds
      KMS_KEY_ID             = aws_kms_key.pipeline_key.key_id
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.presigned_url_logs,
    aws_iam_role_policy_attachment.presigned_url_attach
  ]

  tags = {
    Name = "${var.project_name}-get-presigned-url-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# 2. Document Processor Lambda (Event-Driven Worker)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "doc_processor_logs" {
  name              = "/aws/lambda/${var.project_name}-doc-processor-${var.environment}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "doc_processor" {
  function_name    = "${var.project_name}-doc-processor-${var.environment}"
  role             = aws_iam_role.doc_processor_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = 512
  timeout          = 60

  filename         = data.archive_file.doc_processor_pkg.output_path
  source_code_hash = data.archive_file.doc_processor_pkg.output_base64sha256

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.doc_metadata.name
      ENABLE_TEXTRACT     = tostring(var.enable_textract)
      PROCESSED_PREFIX    = "processed"
      KMS_KEY_ID          = aws_kms_key.pipeline_key.key_id
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.doc_processor_logs,
    aws_iam_role_policy_attachment.doc_processor_attach
  ]

  tags = {
    Name = "${var.project_name}-doc-processor-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# 3. Document Status Query Lambda
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "get_doc_status_logs" {
  name              = "/aws/lambda/${var.project_name}-get-doc-status-${var.environment}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "get_doc_status" {
  function_name    = "${var.project_name}-get-doc-status-${var.environment}"
  role             = aws_iam_role.get_doc_status_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = 256
  timeout          = 15

  filename         = data.archive_file.get_doc_status_pkg.output_path
  source_code_hash = data.archive_file.get_doc_status_pkg.output_base64sha256

  environment {
    variables = {
      S3_BUCKET_NAME              = aws_s3_bucket.doc_storage.id
      DYNAMODB_TABLE_NAME         = aws_dynamodb_table.doc_metadata.name
      DOWNLOAD_EXPIRATION_SECONDS = var.download_expiration_seconds
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.get_doc_status_logs,
    aws_iam_role_policy_attachment.get_doc_status_attach
  ]

  tags = {
    Name = "${var.project_name}-get-doc-status-${var.environment}"
  }
}
