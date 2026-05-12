"""
MinIO sanity check — tests every S3 operation the app uses.

Run inside the container:
  docker compose run --rm backend python scripts/minio_sanity_check.py
Or directly:
  python scripts/minio_sanity_check.py
"""

import base64
import hashlib
import os
import sys
import time
from io import BytesIO

import boto3
from botocore.config import Config as BotoConfig

ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio.nanai.khoofia.com")
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
BUCKET = os.getenv("MINIO_BUCKET", "cognitive-companion")
SECURE = os.getenv("MINIO_SECURE", "false").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

failures = 0


def check(desc: str) -> None:
    global failures
    try:
        yield
        print(f"  OK    {desc}")
    except Exception as exc:
        failures += 1
        print(f"  FAIL  {desc}: {exc}")


def header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _inject_content_md5(request, **kwargs):
    """Replicate of the app's event handler for accurate testing."""
    body = request.body
    if body:
        if isinstance(body, str):
            body = body.encode("utf-8")
        elif not isinstance(body, bytes):
            # Read the stream to compute MD5 — BUG: does not reset position
            body = body.read()
        md5 = base64.b64encode(hashlib.md5(body).digest()).decode()
        request.headers["Content-MD5"] = md5


# ---------------------------------------------------------------------------
# Test 0: Basic network reachability
# ---------------------------------------------------------------------------
header("0. DNS & TCP reachability")

import socket

with check("DNS resolution"):
    ip = socket.gethostbyname(ENDPOINT)
    print(f"        {ENDPOINT} → {ip}")

scheme = "https" if SECURE else "http"
port = 443 if SECURE else 9000  # MinIO default API port is 9000
url = f"{scheme}://{ENDPOINT}:{port}"

with check(f"TCP connect to {ENDPOINT}:{port}"):
    sock = socket.create_connection((ENDPOINT, port), timeout=5)
    sock.close()

# Also try port 80 since the app uses http://endpoint (no port)
if not SECURE:
    with check(f"TCP connect to {ENDPOINT}:80"):
        sock = socket.create_connection((ENDPOINT, 80), timeout=5)
        sock.close()

# ---------------------------------------------------------------------------
# Test 1: boto3 client creation & bucket check
# ---------------------------------------------------------------------------
header("1. Client creation & bucket operations")

client = boto3.client(
    "s3",
    endpoint_url=f"{scheme}://{ENDPOINT}",
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    verify=SECURE,
    use_ssl=SECURE,
    config=BotoConfig(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        connect_timeout=30,
        read_timeout=30,
        retries={"max_attempts": 2, "mode": "standard"},
    ),
)

with check("client created"):
    assert client is not None

with check(f"head_bucket('{BUCKET}')"):
    client.head_bucket(Bucket=BUCKET)

# ---------------------------------------------------------------------------
# Test 2: Upload bytes (the reCamera path)
# ---------------------------------------------------------------------------
header("2. Upload (upload_fileobj) — reCamera path")

test_obj = f"sanity_check/test_{int(time.time())}.txt"
test_data = b"Hello from MinIO sanity check! " * 100  # ~3 KB
test_content_type = "text/plain"

# 2a — without Content-MD5 injection
with check("upload_fileobj (no Content-MD5 injection)"):
    client.upload_fileobj(
        BytesIO(test_data),
        BUCKET,
        f"{test_obj}_no_md5",
        ExtraArgs={"ContentType": test_content_type},
    )

# 2b — with Content-MD5 injection (replicates app behaviour)
client_no_md5 = client
client_with_md5 = boto3.client(
    "s3",
    endpoint_url=f"{scheme}://{ENDPOINT}",
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    verify=SECURE,
    use_ssl=SECURE,
    config=BotoConfig(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        connect_timeout=30,
        read_timeout=30,
        retries={"max_attempts": 2, "mode": "standard"},
    ),
)
client_with_md5.meta.events.register("before-send.s3", _inject_content_md5)

with check("upload_fileobj (WITH Content-MD5 injection)"):
    client_with_md5.upload_fileobj(
        BytesIO(test_data),
        BUCKET,
        f"{test_obj}_with_md5",
        ExtraArgs={"ContentType": test_content_type},
    )

# ---------------------------------------------------------------------------
# Test 3: Upload file (the upload_file path)
# ---------------------------------------------------------------------------
header("3. Upload (upload_file) — file path")

import tempfile

tmpfile = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
tmpfile.write(test_data)
tmpfile.close()

with check("upload_file"):
    client.upload_file(tmpfile.name, BUCKET, f"{test_obj}_file")

os.unlink(tmpfile.name)

# ---------------------------------------------------------------------------
# Test 4: Download (get_object)
# ---------------------------------------------------------------------------
header("4. Download (get_object)")

with check("get_object (no MD5)"):
    resp = client.get_object(Bucket=BUCKET, Key=f"{test_obj}_no_md5")
    body = resp["Body"].read()
    assert body == test_data, f"Data mismatch: {len(body)} vs {len(test_data)}"

with check("get_object (with MD5)"):
    resp = client.get_object(Bucket=BUCKET, Key=f"{test_obj}_with_md5")
    body = resp["Body"].read()
    assert body == test_data, f"Data mismatch: {len(body)} vs {len(test_data)}"

# ---------------------------------------------------------------------------
# Test 5: Presigned URL
# ---------------------------------------------------------------------------
header("5. Presigned URL")

with check("generate_presigned_url"):
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": f"{test_obj}_no_md5"},
        ExpiresIn=3600,
    )
    assert url.startswith("http"), f"Invalid URL: {url}"
    print(f"        {url[:80]}...")

# ---------------------------------------------------------------------------
# Test 6: List & Delete
# ---------------------------------------------------------------------------
header("6. List & delete")

with check("list_objects_v2"):
    resp = client.list_objects_v2(Bucket=BUCKET, Prefix="sanity_check/")
    count = len(resp.get("Contents", []))
    print(f"        {count} objects under sanity_check/")

with check("delete_object (single)"):
    client.delete_object(Bucket=BUCKET, Key=f"{test_obj}_no_md5")

with check("delete_objects (batch)"):
    resp = client.delete_objects(
        Bucket=BUCKET,
        Delete={
            "Objects": [
                {"Key": f"{test_obj}_with_md5"},
                {"Key": f"{test_obj}_file"},
            ],
            "Quiet": False,
        },
    )
    errors = resp.get("Errors", [])
    if errors:
        for e in errors:
            print(f"        Delete error: {e['Key']}: {e.get('Message', '')}")
        raise RuntimeError(f"{len(errors)} delete errors")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
header("Result")

if failures:
    print(f"  {failures} check(s) FAILED")
    sys.exit(1)
else:
    print("  All checks passed")
