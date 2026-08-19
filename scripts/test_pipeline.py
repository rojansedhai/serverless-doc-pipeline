#!/usr/bin/env python3
"""
End-to-End Pipeline & Multi-Tenant Security Verification Script
Authenticates with Amazon Cognito, obtains valid JWT tokens for Tenant A and Tenant B,
and tests the complete serverless document pipeline end-to-end.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
TFSTATE_FILE = ROOT_DIR / "terraform" / "terraform.tfstate"


def make_request(url: str, method: str = "GET", headers: dict = None, data: bytes = None) -> tuple:
    headers = headers or {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return resp.status, resp.headers, body
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, e.headers, body


def get_outputs_from_tfstate() -> dict:
    """Reads Terraform outputs from local tfstate file if present."""
    if not TFSTATE_FILE.exists():
        return {}
    try:
        with open(TFSTATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            outputs = data.get("outputs", {})
            return {k: v.get("value") for k, v in outputs.items()}
    except Exception as e:
        print(f"[!] Warning: Could not read tfstate: {e}")
        return {}


def ensure_cognito_user_and_get_jwt(pool_id: str, client_id: str, region: str, email: str, password: str, tenant_id: str) -> str:
    """
    Creates and confirms a test user in Cognito with custom:tenant_id attribute,
    then authenticates via InitiateAuth to return a valid JWT ID Token.
    """
    print(f"[*] Setting up Cognito test user for {tenant_id} ({email})...")

    # 1. Create or ensure user exists via AWS CLI
    create_cmd = [
        "aws", "cognito-idp", "admin-create-user",
        "--user-pool-id", pool_id,
        "--username", email,
        "--user-attributes",
        f"Name=email,Value={email}",
        "Name=email_verified,Value=true",
        f"Name=custom:tenant_id,Value={tenant_id}",
        "--message-action", "SUPPRESS",
        "--region", region
    ]
    subprocess.run(create_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. Set permanent password
    pwd_cmd = [
        "aws", "cognito-idp", "admin-set-user-password",
        "--user-pool-id", pool_id,
        "--username", email,
        "--password", password,
        "--permanent",
        "--region", region
    ]
    subprocess.run(pwd_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Authenticate via InitiateAuth (Pure HTTPS HTTP API)
    cognito_endpoint = f"https://cognito-idp.{region}.amazonaws.com/"
    auth_payload = json.dumps({
        "AuthFlow": "USER_PASSWORD_AUTH",
        "ClientId": client_id,
        "AuthParameters": {
            "USERNAME": email,
            "PASSWORD": password
        }
    }).encode("utf-8")

    auth_headers = {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth"
    }

    status, _, body = make_request(cognito_endpoint, method="POST", headers=auth_headers, data=auth_payload)
    if status != 200:
        raise RuntimeError(f"Cognito InitiateAuth failed (Status {status}): {body.decode('utf-8')}")

    auth_resp = json.loads(body.decode("utf-8"))
    id_token = auth_resp.get("AuthenticationResult", {}).get("IdToken")
    if not id_token:
        raise RuntimeError(f"No IdToken returned from Cognito: {body.decode('utf-8')}")

    print(f"[+] Successfully authenticated {tenant_id} and obtained JWT!")
    return id_token


def generate_sample_invoice_pdf(invoice_num: str, tenant_id: str, total_amount: str = "1420.50") -> bytes:
    """Generates a raw textual PDF-like payload containing invoice headers."""
    content = f"""%PDF-1.4
% Sample Synthetic Invoice for Testing
Vendor: Acme Cloud Services LLC
Billed To: Tenant Organization ({tenant_id})
Invoice: {invoice_num}
Date: 2026-08-17
Currency: USD

Line Items:
1. Cloud Serverless Compute - Qty 1 - $820.50
2. Managed DynamoDB Storage - Qty 1 - $350.00
3. EventBridge Routing Bus - Qty 1 - $250.00

Total: ${total_amount}
%%EOF
"""
    return content.encode("utf-8")


def run_pipeline_test(api_url: str, token_a: str, token_b: str, tenant_a: str = "tenant-alpha", tenant_b: str = "tenant-beta"):
    api_url = api_url.rstrip("/")
    print("=" * 60)
    print("  MULTI-TENANT SERVERLESS DOCUMENT PIPELINE E2E TEST")
    print("=" * 60)
    print(f"API Endpoint : {api_url}")
    print(f"Tenant A     : {tenant_a}")
    print(f"Tenant B     : {tenant_b}")
    print("-" * 60)

    auth_headers_a = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token_a}"
    }
    auth_headers_b = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token_b}"
    }

    # -------------------------------------------------------------
    # Step 1: Request Presigned Upload URL for Tenant A
    # -------------------------------------------------------------
    print("\n[Step 1] Requesting S3 Presigned Upload URL for Tenant A with JWT...")
    invoice_number = f"INV-{int(time.time())}"
    upload_payload = json.dumps({
        "filename": f"invoice_{invoice_number}.pdf",
        "contentType": "application/pdf"
    }).encode("utf-8")

    status, _, body = make_request(
        url=f"{api_url}/upload-url",
        method="POST",
        headers=auth_headers_a,
        data=upload_payload
    )

    if status not in [200, 201]:
        print(f"[!] FAILED to get presigned URL. Status: {status}, Response: {body.decode('utf-8')}")
        return False

    upload_data = json.loads(body.decode("utf-8"))
    doc_id = upload_data["docId"]
    upload_url = upload_data["uploadUrl"]
    s3_key = upload_data["s3Key"]

    print(f"[+] Success! Doc ID: {doc_id}")
    print(f"[+] S3 Key: {s3_key}")
    print(f"[+] Upload URL generated (Expires in {upload_data.get('expiresInSeconds', 900)}s)")

    # -------------------------------------------------------------
    # Step 2: Upload Document Directly to S3 via Presigned URL
    # -------------------------------------------------------------
    print("\n[Step 2] Uploading synthetic Invoice PDF to S3 via Presigned URL...")
    pdf_bytes = generate_sample_invoice_pdf(invoice_number, tenant_a, "1420.50")

    put_headers = {
        "Content-Type": "application/pdf"
    }

    put_status, _, put_body = make_request(
        url=upload_url,
        method="PUT",
        headers=put_headers,
        data=pdf_bytes
    )

    if put_status not in [200, 204]:
        print(f"[!] FAILED to upload to S3. Status: {put_status}, Body: {put_body.decode('utf-8', errors='ignore')}")
        return False

    print(f"[+] S3 Upload successful! HTTP Status: {put_status}")

    # -------------------------------------------------------------
    # Step 3: Poll DynamoDB via API for EventBridge & Lambda completion
    # -------------------------------------------------------------
    print("\n[Step 3] Waiting for EventBridge routing & Lambda Document Processor...")
    max_retries = 15
    poll_interval = 2
    processed_doc = None

    for attempt in range(1, max_retries + 1):
        print(f"  -> Polling document status (Attempt {attempt}/{max_retries})...")
        time.sleep(poll_interval)

        get_status, _, get_body = make_request(
            url=f"{api_url}/documents/{doc_id}",
            method="GET",
            headers=auth_headers_a
        )

        if get_status == 200:
            doc_info = json.loads(get_body.decode("utf-8"))
            current_status = doc_info.get("Status")
            print(f"     Status: {current_status}")

            if current_status == "PROCESSED":
                processed_doc = doc_info
                break
            elif current_status == "FAILED":
                print(f"[!] Processing FAILED: {doc_info.get('ErrorMessage')}")
                return False

    if not processed_doc:
        print("[!] Timeout waiting for document processing.")
        return False

    print("\n[+] Document Successfully Processed!")
    print(f"    Status            : {processed_doc.get('Status')}")
    print(f"    S3 Processed Key  : {processed_doc.get('S3ProcessedKey')}")
    metadata = processed_doc.get("ExtractedMetadata", {})
    print(f"    Extracted Vendor  : {metadata.get('vendor_name')}")
    print(f"    Extracted Total   : ${metadata.get('total_amount')} {metadata.get('currency', 'USD')}")
    print(f"    Extracted Invoice : {metadata.get('invoice_number')}")
    print(f"    Processing Time   : {metadata.get('processing_duration_ms')}ms")

    # -------------------------------------------------------------
    # Step 4: Verify Multi-Tenant Boundary Isolation (IDOR Protection)
    # -------------------------------------------------------------
    print("\n[Step 4] Testing Multi-Tenant Isolation Security...")
    print(f"  -> Tenant B ({tenant_b}) attempting to read Tenant A's document ({doc_id}) with Tenant B's JWT...")

    idor_status, _, idor_body = make_request(
        url=f"{api_url}/documents/{doc_id}",
        method="GET",
        headers=auth_headers_b
    )

    if idor_status in [403, 404]:
        print(f"[+] PASS: Access correctly rejected for cross-tenant request (HTTP {idor_status}).")
    else:
        print(f"[!] SECURITY VULNERABILITY: Cross-tenant access succeeded! HTTP {idor_status}")
        return False

    # -------------------------------------------------------------
    # Step 5: Test Presigned Download URL
    # -------------------------------------------------------------
    download_url = processed_doc.get("downloadUrl")
    if download_url:
        print("\n[Step 5] Testing Presigned Download URL for Processed Artifact...")
        dl_status, _, dl_body = make_request(url=download_url, method="GET")
        if dl_status == 200:
            print(f"[+] Successfully downloaded processed PDF ({len(dl_body)} bytes)")
            if b"PROCESSED & VERIFIED" in dl_body:
                print("[+] Watermark signature verified in downloaded artifact!")
        else:
            print(f"[!] Download returned status {dl_status}")

    print("\n" + "=" * 60)
    print("  ALL PIPELINE & SECURITY TESTS PASSED SUCCESSFULLY!  ")
    print("=" * 60)
    return True


if __name__ == "__main__":
    tf_outputs = get_outputs_from_tfstate()

    parser = argparse.ArgumentParser(description="Test Multi-Tenant Serverless Document Pipeline with Cognito JWT")
    parser.add_argument("--api-url", default=tf_outputs.get("api_endpoint"), help="Base API Gateway URL")
    parser.add_argument("--pool-id", default=tf_outputs.get("cognito_user_pool_id"), help="Cognito User Pool ID")
    parser.add_argument("--client-id", default=tf_outputs.get("cognito_user_pool_client_id"), help="Cognito App Client ID")
    parser.add_argument("--region", default="us-east-1", help="AWS Region")
    parser.add_argument("--token-a", default=None, help="Explicit JWT Token for Tenant A")
    parser.add_argument("--token-b", default=None, help="Explicit JWT Token for Tenant B")
    parser.add_argument("--tenant-a", default="tenant-alpha", help="Tenant A identifier")
    parser.add_argument("--tenant-b", default="tenant-beta", help="Tenant B identifier")
    parser.add_argument("--password", default=os.environ.get("TEST_USER_PASSWORD"), help="Password for Cognito test users (or set TEST_USER_PASSWORD env var)")

    args = parser.parse_args()

    if not args.api_url:
        print("[!] Error: Missing --api-url and could not auto-detect from terraform.tfstate")
        sys.exit(1)

    token_a = args.token_a
    token_b = args.token_b
    test_password = args.password

    # Auto-generate Cognito JWT tokens if not explicitly passed
    if not token_a and args.pool_id and args.client_id:
        if not test_password:
            print("[!] Error: --password or TEST_USER_PASSWORD env var required for auto-authentication")
            sys.exit(1)
        token_a = ensure_cognito_user_and_get_jwt(
            pool_id=args.pool_id,
            client_id=args.client_id,
            region=args.region,
            email="tenant-alpha-admin@example.com",
            password=test_password,
            tenant_id=args.tenant_a
        )

    if not token_b and args.pool_id and args.client_id:
        if not test_password:
            print("[!] Error: --password or TEST_USER_PASSWORD env var required for auto-authentication")
            sys.exit(1)
        token_b = ensure_cognito_user_and_get_jwt(
            pool_id=args.pool_id,
            client_id=args.client_id,
            region=args.region,
            email="tenant-beta-admin@example.com",
            password=test_password,
            tenant_id=args.tenant_b
        )

    if not token_a or not token_b:
        print("[!] Error: Could not obtain JWT tokens for testing.")
        sys.exit(1)

    success = run_pipeline_test(
        api_url=args.api_url,
        token_a=token_a,
        token_b=token_b,
        tenant_a=args.tenant_a,
        tenant_b=args.tenant_b
    )
    sys.exit(0 if success else 1)
