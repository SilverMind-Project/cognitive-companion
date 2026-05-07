"""
MinIO / S3-compatible object storage client.

Wraps boto3 to provide upload, download, presigned-URL generation,
and cleanup helpers for the application's media bucket.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from backend.core.config import settings
from backend.core.logging import get_logger

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = get_logger(__name__)


class MinioClient:
    """Thin wrapper around boto3 S3 for a single bucket on MinIO."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        self.bucket = bucket
        self._endpoint = endpoint

        scheme = "https" if secure else "http"
        endpoint_url = f"{scheme}://{endpoint}"

        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )
        logger.info("minio_client_initialized", endpoint=endpoint, bucket=bucket)

    # -- bucket management ----------------------------------------------------

    def ensure_bucket(self) -> None:
        """Create the configured bucket if it does not already exist."""
        try:
            self._client.head_bucket(Bucket=self.bucket)
            logger.debug("bucket_exists", bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)
            logger.info("bucket_created", bucket=self.bucket)

    # -- upload ---------------------------------------------------------------

    def upload_file(self, file_path: str, object_name: str) -> str:
        """Upload a local file and return a presigned URL for it."""
        self._client.upload_file(file_path, self.bucket, object_name)
        logger.info("file_uploaded", object_name=object_name)
        return self.generate_presigned_url(object_name)

    def upload_bytes(self, data: bytes, object_name: str, content_type: str) -> str:
        """Upload raw bytes and return a presigned URL for the new object."""
        self._client.upload_fileobj(
            BytesIO(data),
            self.bucket,
            object_name,
            ExtraArgs={"ContentType": content_type},
        )
        logger.info("bytes_uploaded", object_name=object_name, size=len(data))
        return self.generate_presigned_url(object_name)

    # -- presigned URLs -------------------------------------------------------

    def generate_presigned_url(self, object_name: str, expiration: int = 3600) -> str:
        """Return a presigned GET URL valid for *expiration* seconds."""
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_name},
            ExpiresIn=expiration,
        )
        return url

    # -- download --------------------------------------------------------------

    def get_object(self, object_name: str) -> bytes | None:
        """Download an object's body as raw bytes, or None on failure."""
        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=object_name)
            return resp["Body"].read()
        except (ClientError, KeyError) as exc:
            logger.warning("minio_get_object_error", object_name=object_name, error=str(exc))
            return None

    # -- delete ---------------------------------------------------------------

    def delete_object(self, object_name: str) -> None:
        """Delete a single object from the bucket."""
        self._client.delete_object(Bucket=self.bucket, Key=object_name)
        logger.info("object_deleted", object_name=object_name)

    # -- helpers --------------------------------------------------------------

    def extract_object_name(self, presigned_url: str) -> str:
        """Parse the object name (key) from a MinIO presigned URL.

        Presigned URLs have the form:
            http(s)://endpoint/bucket/object/name?X-Amz-...
        """
        parsed = urlparse(presigned_url)
        # The path starts with /<bucket>/<object_name...>
        path = parsed.path
        prefix = f"/{self.bucket}/"
        if path.startswith(prefix):
            return path[len(prefix) :]
        # Fallback: strip leading slash and bucket segment
        parts = path.lstrip("/").split("/", 1)
        if len(parts) == 2:
            return parts[1]
        return path.lstrip("/")


# -- factory ------------------------------------------------------------------


_instance: MinioClient | None = None


def get_minio_client() -> MinioClient:
    """Create (or return the cached) MinioClient from application settings."""
    global _instance
    if _instance is not None:
        return _instance

    _instance = MinioClient(
        endpoint=settings.get("minio.endpoint", "minio.nanai.khoofia.com"),
        access_key=settings.get("minio.access_key", "minioadmin"),
        secret_key=settings.get("minio.secret_key", "minioadmin"),
        bucket=settings.get("minio.bucket", "cognitive-companion"),
        secure=settings.get("minio.secure", False),
    )
    _instance.ensure_bucket()
    return _instance
