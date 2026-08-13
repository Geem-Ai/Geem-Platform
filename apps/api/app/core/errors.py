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

    # Entitlements / subscriptions (Phase 5A)
    ENTITLEMENT_NOT_FOUND = "entitlement_not_found"
    ENTITLEMENT_INVALID = "entitlement_invalid"
    ENTITLEMENT_TYPE_MISMATCH = "entitlement_type_mismatch"
    SUBSCRIPTION_NOT_FOUND = "subscription_not_found"

    # AI usage metering (Phase 5B)
    INSUFFICIENT_CREDITS = "insufficient_credits"

    # Workspace resource quotas (Phase 5C)
    EXPERT_LIMIT_REACHED = "expert_limit_reached"
    STORAGE_QUOTA_EXCEEDED = "storage_quota_exceeded"

    # API keys (Phase 7A) — cross-workspace misses use api_key_not_found (404)
    API_KEY_NOT_FOUND = "api_key_not_found"

    # Public API rate limiting (Phase 7B)
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

    # Billing / checkout (Phase 6A)
    BILLING_GATEWAY_UNAVAILABLE = "billing_gateway_unavailable"
    BILLING_GATEWAY_ERROR = "billing_gateway_error"
    INVALID_PURCHASE = "invalid_purchase"
    PURCHASE_NOT_FOUND = "purchase_not_found"
    PURCHASE_ALREADY_COMPLETED = "purchase_already_completed"
    PAYMENT_VERIFICATION_FAILED = "payment_verification_failed"
    PAYMENT_AMOUNT_MISMATCH = "payment_amount_mismatch"
    PAYMENT_CURRENCY_MISMATCH = "payment_currency_mismatch"
    CREDIT_PACK_UNAVAILABLE = "credit_pack_unavailable"
    PLAN_UNAVAILABLE = "plan_unavailable"
    SYSTEM_WORKSPACE_CHECKOUT_FORBIDDEN = "system_workspace_checkout_forbidden"


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
    # Phase 5A
    "entitlement_not_found": 404,
    "entitlement_invalid": 422,
    "entitlement_type_mismatch": 422,
    "subscription_not_found": 404,
    "insufficient_credits": 402,
    "expert_limit_reached": 429,
    "storage_quota_exceeded": 429,
    # Phase 6A — billing checkout
    "billing_gateway_unavailable": 503,
    "billing_gateway_error": 502,
    "invalid_purchase": 400,
    "purchase_not_found": 404,
    "purchase_already_completed": 409,
    "payment_verification_failed": 402,
    "payment_amount_mismatch": 409,
    "payment_currency_mismatch": 409,
    "credit_pack_unavailable": 404,
    "plan_unavailable": 404,
    "system_workspace_checkout_forbidden": 403,
    # Phase 7A — API keys
    "api_key_not_found": 404,
    # Phase 7B — public API rate limiting
    "rate_limit_exceeded": 429,
}


class AppError(Exception):
    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        details: dict | None = None,
        retryable: bool = False,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.category = category
        self.message = message
        self.details = details
        self.retryable = retryable
        self.headers = headers or {}
        super().__init__(f"{category}: {message}")


def raise_resource_quota(
    category: ErrorCategory,
    message: str,
    *,
    metric: str,
    limit: int,
    used: int,
    remaining: int,
) -> None:
    """Raise a typed quota error with machine-readable fields for the Workspace UI."""
    raise AppError(
        category,
        message,
        details={
            "metric": metric,
            "limit": int(limit),
            "used": int(used),
            "remaining": int(remaining),
        },
    )


def raise_rate_limit_exceeded(
    *,
    limit: int,
    remaining: int,
    retry_after: int,
    reset_at: int,
) -> None:
    """Raise a typed public-API rate-limit error with safe metadata + headers."""
    safe_remaining = max(0, int(remaining))
    safe_retry = max(0, int(retry_after))
    raise AppError(
        ErrorCategory.RATE_LIMIT_EXCEEDED,
        "API rate limit exceeded. Please retry later.",
        details={
            "limit": int(limit),
            "remaining": safe_remaining,
            "retry_after": safe_retry,
        },
        retryable=True,
        headers={
            "Retry-After": str(safe_retry),
            "X-RateLimit-Limit": str(int(limit)),
            "X-RateLimit-Remaining": str(safe_remaining),
            "X-RateLimit-Reset": str(int(reset_at)),
        },
    )
