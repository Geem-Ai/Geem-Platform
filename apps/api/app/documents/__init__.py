"""Documents domain — upload, list, tenant-scoped access (Phase 2A)."""

from app.documents.service import DocumentService, sanitize_filename

__all__ = ["DocumentService", "sanitize_filename"]
