variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Prefix name for all resources in the pipeline"
  type        = string
  default     = "doc-pipeline"
}

variable "s3_retention_days_raw" {
  description = "Number of days before raw staging uploads are purged"
  type        = number
  default     = 7
}

variable "s3_glacier_transition_days" {
  description = "Days after which processed documents transition to Glacier Instant Retrieval"
  type        = number
  default     = 30
}

variable "dynamodb_ttl_days" {
  description = "Days after which transient metadata records expire via DynamoDB TTL"
  type        = number
  default     = 90
}

variable "enable_textract" {
  description = "Enable AWS Textract Expense Analysis for OCR processing"
  type        = bool
  default     = true
}

variable "url_expiration_seconds" {
  description = "TTL for S3 Presigned Upload URLs in seconds"
  type        = number
  default     = 900
}

variable "download_expiration_seconds" {
  description = "TTL for S3 Presigned Download URLs in seconds"
  type        = number
  default     = 3600
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}
