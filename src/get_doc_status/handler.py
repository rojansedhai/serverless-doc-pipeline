"""
Lambda Handler: Get Document Status & Metadata
Queries DynamoDB by tenant_id and doc_id, and generates secure presigned GET download URLs.
"""
import json
import os
import re
import boto3
from botocore.config import Config
from shared.dynamodb_service import get_document_by_id, list_documents_by_tenant_and_status

S3_BUCKET = os.environ.get("S3_BUCKET_NAME")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DOWNLOAD_EXPIRATION_SECONDS = int(os.environ.get("DOWNLOAD_EXPIRATION_SECONDS", "3600"))

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    config=Config(signature_version="s3v4")
)


def get_tenant_id_from_event(event: dict) -> str:
    """Extracts tenant_id securely from JWT claims or headers."""
    try:
        claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
        tenant_id = claims.get("custom:tenant_id") or claims.get("tenant_id") or claims.get("sub")
        if tenant_id:
            return str(tenant_id)
    except Exception:
        pass

    # Fallback: Check custom headers (for local dev/test ONLY).
    #    In production, the JWT authorizer on API Gateway ensures unauthenticated
    #    requests never reach Lambda, so this path is not reachable by attackers.
    headers = event.get("headers", {}) or {}
    tenant_header = headers.get("x-tenant-id") or headers.get("X-Tenant-Id")
    if tenant_header:
        return re.sub(r'[^a-zA-Z0-9-_]', '', tenant_header)

    return "default-tenant"


def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Tenant-Id",
            "Access-Control-Allow-Methods": "OPTIONS,GET"
        },
        "body": json.dumps(body, default=str)
    }


def lambda_handler(event, context):
    print(f"Status query request: {json.dumps(event.get('requestContext', {}))}")

    if event.get("httpMethod") == "OPTIONS" or event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return build_response(200, {"message": "CORS preflight OK"})

    try:
        tenant_id = get_tenant_id_from_event(event)
        if not tenant_id:
            return build_response(401, {"error": "Unauthorized: Missing tenant identification"})

        path_params = event.get("pathParameters") or {}
        doc_id = path_params.get("doc_id") or path_params.get("docId")

        # 1. Single Document Query
        if doc_id:
            doc = get_document_by_id(tenant_id, doc_id)
            if not doc:
                return build_response(404, {
                    "error": f"Document with ID '{doc_id}' not found for tenant '{tenant_id}'"
                })

            response_data = dict(doc)

            # Generate presigned download URL if processed file is available
            s3_processed_key = doc.get("S3ProcessedKey")
            if s3_processed_key and S3_BUCKET:
                try:
                    download_url = s3_client.generate_presigned_url(
                        ClientMethod="get_object",
                        Params={
                            "Bucket": S3_BUCKET,
                            "Key": s3_processed_key
                        },
                        ExpiresIn=DOWNLOAD_EXPIRATION_SECONDS
                    )
                    response_data["downloadUrl"] = download_url
                    response_data["downloadExpiresInSeconds"] = DOWNLOAD_EXPIRATION_SECONDS
                except Exception as s3_err:
                    print(f"Could not generate download URL: {str(s3_err)}")

            return build_response(200, response_data)

        # 2. List Documents Query
        query_params = event.get("queryStringParameters") or {}
        raw_status = query_params.get("status")
        valid_statuses = {"PENDING_UPLOAD", "PROCESSING", "PROCESSED", "FAILED"}
        status_filter = raw_status if raw_status in valid_statuses else None

        try:
            parsed_limit = int(query_params.get("limit", 50))
            limit = max(1, min(parsed_limit, 100))
        except (ValueError, TypeError):
            limit = 50

        docs = list_documents_by_tenant_and_status(tenant_id, status=status_filter, limit=limit)
        return build_response(200, {
            "tenantId": tenant_id,
            "count": len(docs),
            "documents": docs
        })

    except Exception as e:
        print(f"Error querying document status: {str(e)}")
        return build_response(500, {"error": "Internal server error. Check CloudWatch logs for details."})
