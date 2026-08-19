output "api_endpoint" {
  description = "Base URL of the API Gateway HTTP API"
  value       = aws_apigatewayv2_api.http_api.api_endpoint
}

output "s3_bucket_name" {
  description = "Name of the secure S3 Document Storage Bucket"
  value       = aws_s3_bucket.doc_storage.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 Document Storage Bucket"
  value       = aws_s3_bucket.doc_storage.arn
}

output "dynamodb_table_name" {
  description = "Name of the Single-Table DynamoDB Table"
  value       = aws_dynamodb_table.doc_metadata.name
}

output "dynamodb_table_arn" {
  description = "ARN of the Single-Table DynamoDB Table"
  value       = aws_dynamodb_table.doc_metadata.arn
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID for Multi-Tenant Auth"
  value       = aws_cognito_user_pool.pool.id
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.client.id
}

output "kms_key_arn" {
  description = "ARN of the KMS Customer Managed Key"
  value       = aws_kms_key.pipeline_key.arn
}

output "kms_key_id" {
  description = "ID of the KMS Customer Managed Key"
  value       = aws_kms_key.pipeline_key.key_id
}

output "eventbridge_rule_arn" {
  description = "ARN of the S3 ObjectCreated EventBridge Rule"
  value       = aws_cloudwatch_event_rule.doc_upload_rule.arn
}
