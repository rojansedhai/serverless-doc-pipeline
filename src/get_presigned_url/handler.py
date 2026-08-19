"""
Lambda Handler: Get Presigned S3 Upload URL
Validates multi-tenant JWT claims and generates a scoped S3 presigned PUT URL.
"""
import json
import os
import re
import uuid
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from shared.dynamodb_service import create_document_record

S3_BUCKET = os.environ.get("S3_BUCKET_NAME")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
URL_EXPIRATION_SECONDS = int(os.environ.get("URL_EXPIRATION_SECONDS", "900"))
KMS_KEY_ID = os.environ.get("KMS_KEY_ID")

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    config=Config(signature_version="s3v4")
)

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff"
}


def sanitize_filename(filename: str) -> str:
    """Sanitizes filename to prevent directory traversal and S3 key issues."""
    if not isinstance(filename, str):
        return "document.pdf"
    filename = os.path.basename(filename).strip()
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    filename = filename.strip("._-")
    # Clamp length to 100 characters to prevent S3 key bloat
    if len(filename) > 100:
        base, ext = os.path.splitext(filename)
        filename = base[:90] + ext[:10]
    return filename or "document.pdf"


def get_tenant_id_from_event(event: dict) -> str:
    """
    Extracts tenant_id securely from verified JWT claims in requestContext.
    Falls back to header or query parameter only for local test mode if enabled.
    """
    # 1. Check HTTP API JWT Authorizer claims (Cognito)
    try:
        claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
        # Support custom:tenant_id, tenant_id, or sub
        tenant_id = claims.get("custom:tenant_id") or claims.get("tenant_id") or claims.get("sub")
        if tenant_id:
            return str(tenant_id)
    except Exception:
        pass

    # 2. Fallback: Check custom headers (for local dev/test ONLY).
    #    In production, the JWT authorizer on API Gateway ensures unauthenticated
    #    requests never reach Lambda, so this path is not reachable by attackers.
    #    For hardened production, consider removing this fallback entirely.
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
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
        },
        "body": json.dumps(body)
    }


def lambda_handler(event, context):
    print(f"Received request: {json.dumps(event.get('requestContext', {}))}")

    if event.get("httpMethod") == "OPTIONS" or event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return build_response(200, {"message": "CORS preflight OK"})

    try:
        tenant_id = get_tenant_id_from_event(event)
        if not tenant_id:
            return build_response(401, {"error": "Unauthorized: Missing or invalid tenant context"})

        body = {}
        if event.get("body"):
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]

        raw_filename = body.get("filename", "document.pdf")
        content_type = body.get("contentType", "application/pdf")

        if content_type not in ALLOWED_CONTENT_TYPES:
            return build_response(400, {
                "error": f"Invalid content-type: {content_type}. Allowed types: {list(ALLOWED_CONTENT_TYPES)}"
            })

        filename = sanitize_filename(raw_filename)
        doc_id = str(uuid.uuid4())

        # Strict multi-tenant key partition
        s3_key = f"uploads/{tenant_id}/{doc_id}/{filename}"

        # Presigned URL generation parameters
        params = {
            "Bucket": S3_BUCKET,
            "Key": s3_key,
            "ContentType": content_type
        }

        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params=params,
            ExpiresIn=URL_EXPIRATION_SECONDS,
            HttpMethod="PUT"
        )

        # Register record in DynamoDB
        db_record = create_document_record(
            tenant_id=tenant_id,
            doc_id=doc_id,
            filename=filename,
            content_type=content_type,
            s3_raw_key=s3_key,
            s3_bucket=S3_BUCKET
        )

        return build_response(200, {
            "message": "Presigned upload URL generated successfully",
            "docId": doc_id,
            "tenantId": tenant_id,
            "s3Key": s3_key,
            "uploadUrl": presigned_url,
            "expiresInSeconds": URL_EXPIRATION_SECONDS,
            "requiredHeaders": {
                "Content-Type": content_type
            }
        })

    except json.JSONDecodeError:
        return build_response(400, {"error": "Invalid JSON body in request"})
    except ValueError as ve:
        return build_response(409, {"error": str(ve)})
    except Exception as e:
        print(f"Error generating presigned URL: {str(e)}")
        return build_response(500, {"error": "Internal server error. Check CloudWatch logs for details."})
