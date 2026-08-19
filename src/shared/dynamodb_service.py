"""
Shared DynamoDB Service for Multi-Tenant Document Pipeline
Implements Single-Table Design patterns with strict tenant isolation.
"""
import os
import time
from decimal import Decimal
from typing import Dict, Any, Optional, List
import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "doc-pipeline-metadata")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)


def _convert_floats(obj: Any) -> Any:
    """Recursively converts all float values to Decimal for DynamoDB serialization."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_floats(v) for v in obj]
    return obj


def create_document_record(
    tenant_id: str,
    doc_id: str,
    filename: str,
    content_type: str,
    s3_raw_key: str,
    s3_bucket: str,
    file_size_bytes: int = 0
) -> Dict[str, Any]:
    """
    Creates an initial 'PENDING_UPLOAD' record in DynamoDB.
    
    PK: TENANT#<tenant_id>
    SK: DOC#<doc_id>
    GSI1PK: TENANT#<tenant_id>#STATUS#PENDING_UPLOAD
    GSI1SK: CREATED#<iso_timestamp>
    """
    now = int(time.time())
    iso_now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))
    ttl_timestamp = now + (30 * 86400)  # 30 days retention by default

    item = {
        "PK": f"TENANT#{tenant_id}",
        "SK": f"DOC#{doc_id}",
        "GSI1PK": f"TENANT#{tenant_id}#STATUS#PENDING_UPLOAD",
        "GSI1SK": f"CREATED#{iso_now}",
        "TenantId": tenant_id,
        "DocId": doc_id,
        "Filename": filename,
        "ContentType": content_type,
        "S3Bucket": s3_bucket,
        "S3RawKey": s3_raw_key,
        "Status": "PENDING_UPLOAD",
        "CreatedAt": iso_now,
        "UpdatedAt": iso_now,
        "SizeBytes": file_size_bytes,
        "TimeToLive": ttl_timestamp
    }

    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)"
        )
        return item
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ValueError(f"Document {doc_id} already exists for tenant {tenant_id}")
        raise e


def update_document_processing_status(
    tenant_id: str,
    doc_id: str,
    status: str,
    extracted_metadata: Optional[Dict[str, Any]] = None,
    s3_processed_key: Optional[str] = None,
    error_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates the document status to 'PROCESSING', 'PROCESSED', or 'FAILED'.
    Updates GSI1PK to reflect the new status for tenant-level status queries.
    """
    now = int(time.time())
    iso_now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))

    update_expr = "SET #status = :status, #gsi1pk = :gsi1pk, #updatedAt = :updatedAt"
    expr_attr_names = {
        "#status": "Status",
        "#gsi1pk": "GSI1PK",
        "#updatedAt": "UpdatedAt"
    }
    expr_attr_values = {
        ":status": status,
        ":gsi1pk": f"TENANT#{tenant_id}#STATUS#{status}",
        ":updatedAt": iso_now
    }

    if extracted_metadata is not None:
        converted_metadata = _convert_floats(extracted_metadata)
        update_expr += ", #metadata = :metadata"
        expr_attr_names["#metadata"] = "ExtractedMetadata"
        expr_attr_values[":metadata"] = converted_metadata

    if s3_processed_key:
        update_expr += ", #s3ProcessedKey = :s3ProcessedKey"
        expr_attr_names["#s3ProcessedKey"] = "S3ProcessedKey"
        expr_attr_values[":s3ProcessedKey"] = s3_processed_key

    if error_message:
        update_expr += ", #errorMessage = :errorMessage"
        expr_attr_names["#errorMessage"] = "ErrorMessage"
        expr_attr_values[":errorMessage"] = error_message

    response = table.update_item(
        Key={
            "PK": f"TENANT#{tenant_id}",
            "SK": f"DOC#{doc_id}"
        },
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values,
        ReturnValues="ALL_NEW"
    )
    return response.get("Attributes", {})


def get_document_by_id(tenant_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches a single document ensuring strict tenant boundary isolation.
    """
    response = table.get_item(
        Key={
            "PK": f"TENANT#{tenant_id}",
            "SK": f"DOC#{doc_id}"
        }
    )
    return response.get("Item")


def list_documents_by_tenant_and_status(
    tenant_id: str,
    status: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Queries documents for a tenant, optionally filtered by status using GSI1.
    """
    if status:
        gsi1_pk = f"TENANT#{tenant_id}#STATUS#{status}"
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :gsi1pk",
            ExpressionAttributeValues={":gsi1pk": gsi1_pk},
            ScanIndexForward=False,
            Limit=limit
        )
        return response.get("Items", [])
    else:
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"TENANT#{tenant_id}",
                ":sk_prefix": "DOC#"
            },
            ScanIndexForward=False,
            Limit=limit
        )
        return response.get("Items", [])
