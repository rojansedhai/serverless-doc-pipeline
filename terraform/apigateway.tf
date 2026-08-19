# -----------------------------------------------------------------------------
# Amazon API Gateway (HTTP API v2)
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_api" "http_api" {
  name          = "${var.project_name}-api-${var.environment}"
  protocol_type = "HTTP"

  # CORS: Wildcard origins are used intentionally for this demo/portfolio project.
  # For production, restrict allow_origins to your frontend domain.
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization", "X-Tenant-Id"]
    max_age       = 3600
  }

  tags = {
    Name = "${var.project_name}-api-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# JWT Authorizer (Amazon Cognito User Pool)
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_authorizer" "jwt_authorizer" {
  api_id           = aws_apigatewayv2_api.http_api.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-jwt-authorizer"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.client.id]
    issuer   = "https://${aws_cognito_user_pool.pool.endpoint}"
  }
}

# -----------------------------------------------------------------------------
# API Gateway Integrations
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_integration" "presigned_url_integration" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.get_presigned_url.arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "get_doc_status_integration" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.get_doc_status.arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# -----------------------------------------------------------------------------
# API Routes
# -----------------------------------------------------------------------------
# 1. Request Presigned Upload URL
resource "aws_apigatewayv2_route" "post_upload_url" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "POST /upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.presigned_url_integration.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt_authorizer.id
  authorization_type = "JWT"
}

# 2. Query Single Document Status & Metadata
resource "aws_apigatewayv2_route" "get_document_by_id" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "GET /documents/{doc_id}"
  target             = "integrations/${aws_apigatewayv2_integration.get_doc_status_integration.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt_authorizer.id
  authorization_type = "JWT"
}

# 3. List Documents by Tenant
resource "aws_apigatewayv2_route" "get_documents" {
  api_id             = aws_apigatewayv2_api.http_api.id
  route_key          = "GET /documents"
  target             = "integrations/${aws_apigatewayv2_integration.get_doc_status_integration.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt_authorizer.id
  authorization_type = "JWT"
}

# -----------------------------------------------------------------------------
# Default Stage with Auto-Deploy
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_stage" "default_stage" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_logs.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      jwtClaims      = "$context.authorizer.claims"
    })
  }

  tags = {
    Name = "${var.project_name}-api-default-stage"
  }
}

resource "aws_cloudwatch_log_group" "api_gateway_logs" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# Lambda Invocation Permissions for API Gateway
# -----------------------------------------------------------------------------
resource "aws_lambda_permission" "apigw_presigned_url" {
  statement_id  = "AllowAPIGatewayInvokePresignedUrl"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_presigned_url.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_get_doc_status" {
  statement_id  = "AllowAPIGatewayInvokeDocStatus"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_doc_status.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}
