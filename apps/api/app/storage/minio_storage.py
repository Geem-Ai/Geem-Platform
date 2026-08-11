from __future__ import annotations

import io
import logging
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.storage.document_keys import (
    DocumentStorageKey,
    document_storage_key,
    resolve_document_storage_key,
)

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

    def object_exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
            return True
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return False
            raise AppError(ErrorCategory.STORAGE_ERROR, f"Failed to stat object: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except S3Error as exc:
            # Idempotent delete: missing object is OK
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return
            raise AppError(ErrorCategory.STORAGE_ERROR, f"Failed to delete object: {exc}") from exc

    def get_document_bytes(
        self,
        *,
        document_id,
        workspace_id,
        stored_key: str | None,
    ) -> tuple[bytes, str]:
        """Read bytes for an already-authorized Document.

        Production reads use stored_key → canonical Workspace key only.
        Legacy flat keys are not used for normal Document HTTP access after Phase 2C.
        """
        keys = resolve_document_storage_key(document_id, workspace_id).candidate_read_keys(
            stored_key,
            include_legacy_flat=False,
        )
        last_error: AppError | None = None
        for key in keys:
            try:
                return self.get_bytes(key), key
            except AppError as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        raise AppError(ErrorCategory.STORAGE_ERROR, "Document object not found in storage")

    def put_document_bytes(
        self,
        *,
        document_id,
        workspace_id,
        data: bytes,
        content_type: str = "application/pdf",
    ) -> DocumentStorageKey:
        """Write at the canonical key for the document population."""
        resolved = resolve_document_storage_key(document_id, workspace_id)
        self.ensure_bucket()
        self.put_bytes(resolved.canonical, data, content_type)
        return resolved

    def rekey_workspace_document(
        self,
        *,
        document_id,
        workspace_id,
        stored_key: str | None,
        dry_run: bool = False,
    ) -> dict:
        """Copy Phase 2A flat object → workspace-prefixed key (idempotent).

        Returns a status dict. Does not guess ownership — caller must pass a
        Document already known to have workspace_id set.
        """
        if workspace_id is None:
            raise AppError(ErrorCategory.VALIDATION, "workspace_id required for rekey")
        resolved = resolve_document_storage_key(document_id, workspace_id)
        canonical = resolved.canonical
        if self.object_exists(canonical):
            return {
                "status": "already_canonical",
                "document_id": str(document_id),
                "key": canonical,
                "dry_run": dry_run,
            }

        source = None
        for key in resolved.candidate_read_keys(stored_key, include_legacy_flat=True):
            if key == canonical:
                continue
            if self.object_exists(key):
                source = key
                break
        if source is None:
            return {
                "status": "source_missing",
                "document_id": str(document_id),
                "key": canonical,
                "dry_run": dry_run,
            }

        if dry_run:
            return {
                "status": "would_rekey",
                "document_id": str(document_id),
                "from": source,
                "to": canonical,
                "dry_run": True,
            }

        data = self.get_bytes(source)
        self.put_bytes(canonical, data, "application/pdf")
        if not self.object_exists(canonical):
            raise AppError(ErrorCategory.STORAGE_ERROR, "Rekey verification failed")
        # Leave source in place until Phase 2C/purge; dual-read remains safe.
        return {
            "status": "rekeyed",
            "document_id": str(document_id),
            "from": source,
            "to": canonical,
            "dry_run": False,
        }


__all__ = [
    "MinioObjectStorage",
    "document_storage_key",
    "resolve_document_storage_key",
    "DocumentStorageKey",
]
