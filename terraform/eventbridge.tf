# -----------------------------------------------------------------------------
# EventBridge Rule for S3 ObjectCreated Notifications
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "doc_upload_rule" {
  name        = "${var.project_name}-s3-upload-rule-${var.environment}"
  description = "Routes S3 raw document uploads to the document processor Lambda"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = {
        name = [aws_s3_bucket.doc_storage.id]
      }
      object = {
        key = [{
          prefix = "uploads/"
        }]
      }
    }
  })

  tags = {
    Name = "${var.project_name}-s3-upload-rule-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# EventBridge Target -> Document Processor Lambda
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_event_target" "doc_processor_target" {
  rule      = aws_cloudwatch_event_rule.doc_upload_rule.name
  target_id = "DocProcessorLambdaTarget"
  arn       = aws_lambda_function.doc_processor.arn

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }
}

# -----------------------------------------------------------------------------
# Lambda Permission for EventBridge Invocation
# -----------------------------------------------------------------------------
resource "aws_lambda_permission" "allow_eventbridge_to_invoke_processor" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.doc_processor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.doc_upload_rule.arn
}
