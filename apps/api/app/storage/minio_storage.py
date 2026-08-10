from __future__ import annotations

import io
import logging
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

logger = logging.getLogger(__name__)


class MinioObjectStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        endpoint = self.settings.minio_endpoint
        # Strip scheme if present
        if "://" in endpoint:
            parsed = urlparse(endpoint)
            endpoint = parsed.netloc or parsed.path
        self.client = Minio(
            endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=self.settings.minio_secure,
        )
        self.bucket = self.settings.minio_bucket

    def ensure_bucket(self) -> None:
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error as exc:
            raise AppError(ErrorCategory.STORAGE_ERROR, f"Failed to ensure bucket: {exc}") from exc

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.put_object(
                self.bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        except S3Error as exc:
            raise AppError(ErrorCategory.STORAGE_ERROR, f"Failed to store object: {exc}") from exc

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            raise AppError(ErrorCategory.STORAGE_ERROR, f"Failed to read object: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except S3Error as exc:
            # Idempotent delete: missing object is OK
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return
            raise AppError(ErrorCategory.STORAGE_ERROR, f"Failed to delete object: {exc}") from exc


def document_storage_key(document_id: str) -> str:
    return f"documents/{document_id}/original.pdf"
