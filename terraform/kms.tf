resource "aws_kms_key" "pipeline_key" {
  description             = "Customer Managed Key for ${var.project_name} S3 & DynamoDB encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "pipeline-kms-policy"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow S3 and DynamoDB Services"
        Effect = "Allow"
        Principal = {
          Service = [
            "s3.amazonaws.com",
            "dynamodb.amazonaws.com",
            "lambda.amazonaws.com"
          ]
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-kms-key-${var.environment}"
  }
}

resource "aws_kms_alias" "pipeline_key_alias" {
  name          = "alias/${var.project_name}-${var.environment}"
  target_key_id = aws_kms_key.pipeline_key.key_id
}
