from __future__ import annotations

from enum import StrEnum


class ErrorCategory(StrEnum):
    INVALID_PDF = "invalid_pdf"
    ENCRYPTED_PDF = "encrypted_pdf"
    STORAGE_ERROR = "storage_error"
    PARSER_TIMEOUT = "parser_timeout"
    PARSER_RATE_LIMITED = "parser_rate_limited"
    PARSER_FAILED = "parser_failed"
    EMPTY_PAGE = "empty_page"
    EMBEDDING_FAILED = "embedding_failed"
    QDRANT_FAILED = "qdrant_failed"
    RERANK_FAILED = "rerank_failed"
    GENERATION_FAILED = "generation_failed"
    CITATION_VALIDATION_FAILED = "citation_validation_failed"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    VALIDATION = "validation"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    QUOTA_EXCEEDED = "quota_exceeded"
    BILLING_REQUIRED = "billing_required"
    RATE_LIMITED = "rate_limited"

    # Identity / auth (stable codes for Workspace frontend)
    INVALID_CREDENTIALS = "invalid_credentials"
    EMAIL_ALREADY_EXISTS = "email_already_exists"
    SESSION_EXPIRED = "session_expired"
    SESSION_REVOKED = "session_revoked"
    WEAK_PASSWORD = "weak_password"

    # Workspaces / membership
    WORKSPACE_SLUG_TAKEN = "workspace_slug_taken"
    WORKSPACE_SLUG_INVALID = "workspace_slug_invalid"
    WORKSPACE_NOT_FOUND = "workspace_not_found"
    MEMBERSHIP_NOT_FOUND = "membership_not_found"
    WORKSPACE_ACCESS_DENIED = "workspace_access_denied"
    INSUFFICIENT_WORKSPACE_ROLE = "insufficient_workspace_role"
    LAST_WORKSPACE_OWNER = "last_workspace_owner"

    # Documents (Phase 2A) — cross-tenant misses use document_not_found (404), not 403
    DOCUMENT_NOT_FOUND = "document_not_found"
    DOCUMENT_ALREADY_EXISTS = "document_already_exists"
    DOCUMENT_DELETED = "document_deleted"
    INVALID_DOCUMENT = "invalid_document"
    UNSUPPORTED_DOCUMENT_TYPE = "unsupported_document_type"

    # Experts (Phase 3A) — cross-tenant / unauthorized misses use expert_not_found (404)
    EXPERT_NOT_FOUND = "expert_not_found"
    EXPERT_ACCESS_DENIED = "expert_access_denied"
    EXPERT_IMMUTABLE = "expert_immutable"
    PLATFORM_ADMIN_REQUIRED = "platform_admin_required"

    # Experts (Phase 3B) — Expert-scoped RAG lifecycle / availability
    EXPERT_NOT_READY = "expert_not_ready"
    EXPERT_DISABLED = "expert_disabled"
    EXPERT_HAS_NO_KNOWLEDGE = "expert_has_no_knowledge"
    EXPERT_KNOWLEDGE_UNAVAILABLE = "expert_knowledge_unavailable"

    # Conversations (Phase 4A) — cross-tenant / cross-user misses use 404
    CONVERSATION_NOT_FOUND = "conversation_not_found"
    MESSAGE_NOT_FOUND = "message_not_found"
    # Conversations (Phase 4B) — overlapping generation
    CONVERSATION_BUSY = "conversation_busy"


# HTTP status mapping for AppError.category
HTTP_STATUS_BY_CATEGORY: dict[str, int] = {
    "not_found": 404,
    "conflict": 409,
    "validation": 422,
    "unauthorized": 401,
    "forbidden": 403,
    "quota_exceeded": 429,
    "billing_required": 402,
    "invalid_pdf": 400,
    "encrypted_pdf": 400,
    "rate_limited": 429,
    "invalid_credentials": 401,
    "email_already_exists": 409,
    "session_expired": 401,
    "session_revoked": 401,
    "weak_password": 422,
    "workspace_slug_taken": 409,
    "workspace_slug_invalid": 422,
    "workspace_not_found": 404,
    "membership_not_found": 404,
    "workspace_access_denied": 403,
    "insufficient_workspace_role": 403,
    "last_workspace_owner": 409,
    "document_not_found": 404,
    "document_already_exists": 409,
    "document_deleted": 409,
    "invalid_document": 400,
    "unsupported_document_type": 400,
    "expert_not_found": 404,
    "expert_access_denied": 403,
    "expert_immutable": 403,
    "platform_admin_required": 403,
    # Phase 3B — Expert lifecycle / availability
    "expert_not_ready": 409,
    "expert_disabled": 403,
    "expert_has_no_knowledge": 422,
    "expert_knowledge_unavailable": 422,
    # Phase 4A — Conversations
    "conversation_not_found": 404,
    "message_not_found": 404,
    # Phase 4B
    "conversation_busy": 409,
}


class AppError(Exception):
    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        details: dict | None = None,
        retryable: bool = False,
    ) -> None:
        self.category = category
        self.message = message
        self.details = details
        self.retryable = retryable
        super().__init__(f"{category}: {message}")
