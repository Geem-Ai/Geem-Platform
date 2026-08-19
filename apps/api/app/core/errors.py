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
    INVALID_RESET_TOKEN = "invalid_reset_token"
    RESET_TOKEN_EXPIRED = "reset_token_expired"
    EMAIL_NOT_VERIFIED = "email_not_verified"
    INVALID_VERIFICATION_TOKEN = "invalid_verification_token"
    VERIFICATION_TOKEN_EXPIRED = "verification_token_expired"

    # Workspaces / membership
    WORKSPACE_SLUG_TAKEN = "workspace_slug_taken"
    WORKSPACE_SLUG_INVALID = "workspace_slug_invalid"
    WORKSPACE_NOT_FOUND = "workspace_not_found"
    MEMBERSHIP_NOT_FOUND = "membership_not_found"
    WORKSPACE_ACCESS_DENIED = "workspace_access_denied"
    INSUFFICIENT_WORKSPACE_ROLE = "insufficient_workspace_role"
    LAST_WORKSPACE_OWNER = "last_workspace_owner"
    UNKNOWN_PERMISSION = "unknown_permission"
    ROLE_NOT_FOUND = "role_not_found"
    ROLE_IN_USE = "role_in_use"
    ROLE_PROTECTED = "role_protected"
    ROLE_NAME_TAKEN = "role_name_taken"

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
    # Chat composer attachments
    CHAT_ATTACHMENT_NOT_FOUND = "chat_attachment_not_found"
    UPLOAD_TOO_LARGE = "upload_too_large"
    # Chat voice STT
    UNSUPPORTED_AUDIO_TYPE = "unsupported_audio_type"

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
    INVOICE_NOT_AVAILABLE = "invoice_not_available"
    INVOICE_NOT_CONFIGURED = "invoice_not_configured"

    # App Store (Phase 9A) — cross-workspace misses use not_found (404)
    APP_NOT_FOUND = "app_not_found"
    APP_NOT_AVAILABLE = "app_not_available"
    APP_ALREADY_INSTALLED = "app_already_installed"
    APP_NOT_INSTALLED = "app_not_installed"
    APP_BILLING_REQUIRED = "app_billing_required"
    APP_INSTALL_FORBIDDEN = "app_install_forbidden"
    APP_INSTALLATION_NOT_FOUND = "app_installation_not_found"

    # App Store billing (Phase 9B)
    APP_PLAN_NOT_FOUND = "app_plan_not_found"
    APP_PLAN_INACTIVE = "app_plan_inactive"
    APP_PLAN_MISMATCH = "app_plan_mismatch"
    APP_ALREADY_LICENSED = "app_already_licensed"
    APP_SUBSCRIPTION_REQUIRED = "app_subscription_required"
    APP_SUBSCRIPTION_EXPIRED = "app_subscription_expired"
    APP_SUBSCRIPTION_ALREADY_ACTIVE = "app_subscription_already_active"
    APP_RENEWAL_NOT_ALLOWED = "app_renewal_not_allowed"
    APP_CURRENCY_NOT_SUPPORTED = "app_currency_not_supported"
    APP_CHECKOUT_FORBIDDEN = "app_checkout_forbidden"
    APP_CHECKOUT_IN_PROGRESS = "app_checkout_in_progress"
    APP_PURCHASE_NOT_PAYABLE = "app_purchase_not_payable"

    # Connectors (Phase 9C)
    CONNECTOR_NOT_AVAILABLE = "connector_not_available"
    CONNECTOR_NOT_SUPPORTED = "connector_not_supported"
    CONNECTOR_ALREADY_REGISTERED = "connector_already_registered"
    CONNECTOR_ACCESS_REQUIRED = "connector_access_required"
    CONNECTOR_INSTALLATION_REQUIRED = "connector_installation_required"
    CONNECTOR_LIMIT_REACHED = "connector_limit_reached"
    CONNECTOR_NOT_FOUND = "connector_not_found"
    CONNECTOR_ALREADY_DISCONNECTED = "connector_already_disconnected"
    CONNECTOR_CREDENTIALS_INVALID = "connector_credentials_invalid"
    CONNECTOR_CREDENTIALS_EXPIRED = "connector_credentials_expired"
    CONNECTOR_CONNECTION_FAILED = "connector_connection_failed"
    CONNECTOR_HEALTH_CHECK_FAILED = "connector_health_check_failed"
    CONNECTOR_SYNC_NOT_SUPPORTED = "connector_sync_not_supported"
    CONNECTOR_SYNC_IN_PROGRESS = "connector_sync_in_progress"
    CONNECTOR_SYNC_NOT_FOUND = "connector_sync_not_found"
    CONNECTOR_OAUTH_STATE_INVALID = "connector_oauth_state_invalid"
    CONNECTOR_OAUTH_STATE_EXPIRED = "connector_oauth_state_expired"
    CONNECTOR_OAUTH_STATE_REPLAYED = "connector_oauth_state_replayed"
    CONNECTOR_OAUTH_RETURN_PATH_INVALID = "connector_oauth_return_path_invalid"
    CONNECTOR_WEBHOOK_INVALID = "connector_webhook_invalid"
    CONNECTOR_WEBHOOK_UNAUTHORIZED = "connector_webhook_unauthorized"
    CONNECTOR_INVALID_TRANSITION = "connector_invalid_transition"

    # Google Drive (Phase 9D)
    GOOGLE_DRIVE_NOT_CONFIGURED = "google_drive_not_configured"
    GOOGLE_DRIVE_AUTHORIZATION_FAILED = "google_drive_authorization_failed"
    GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED = "google_drive_reauthorization_required"
    GOOGLE_DRIVE_FILE_NOT_FOUND = "google_drive_file_not_found"
    GOOGLE_DRIVE_FILE_ACCESS_DENIED = "google_drive_file_access_denied"
    GOOGLE_DRIVE_FILE_TYPE_UNSUPPORTED = "google_drive_file_type_unsupported"
    GOOGLE_DRIVE_EXPORT_TOO_LARGE = "google_drive_export_too_large"
    GOOGLE_DRIVE_DOWNLOAD_FAILED = "google_drive_download_failed"
    GOOGLE_DRIVE_RATE_LIMITED = "google_drive_rate_limited"
    GOOGLE_DRIVE_WATCH_FAILED = "google_drive_watch_failed"
    GOOGLE_DRIVE_SYNC_FAILED = "google_drive_sync_failed"

    # Microsoft OneDrive (Phase 9E)
    MICROSOFT_ONEDRIVE_NOT_CONFIGURED = "microsoft_onedrive_not_configured"
    MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED = "microsoft_onedrive_authorization_failed"
    MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED = (
        "microsoft_onedrive_reauthorization_required"
    )
    MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED = "microsoft_onedrive_drive_not_supported"
    MICROSOFT_ONEDRIVE_ITEM_NOT_FOUND = "microsoft_onedrive_item_not_found"
    MICROSOFT_ONEDRIVE_ACCESS_DENIED = "microsoft_onedrive_access_denied"
    MICROSOFT_ONEDRIVE_FILE_TYPE_UNSUPPORTED = "microsoft_onedrive_file_type_unsupported"
    MICROSOFT_ONEDRIVE_CONVERSION_FAILED = "microsoft_onedrive_conversion_failed"
    MICROSOFT_ONEDRIVE_DOWNLOAD_FAILED = "microsoft_onedrive_download_failed"
    MICROSOFT_ONEDRIVE_RATE_LIMITED = "microsoft_onedrive_rate_limited"
    MICROSOFT_ONEDRIVE_DELTA_RESYNC_REQUIRED = "microsoft_onedrive_delta_resync_required"
    MICROSOFT_ONEDRIVE_SUBSCRIPTION_FAILED = "microsoft_onedrive_subscription_failed"
    MICROSOFT_ONEDRIVE_SYNC_FAILED = "microsoft_onedrive_sync_failed"

    # OpenWA / WhatsApp (Phase 9F)
    OPENWA_NOT_CONFIGURED = "openwa_not_configured"
    OPENWA_UNAVAILABLE = "openwa_unavailable"
    OPENWA_UNAUTHORIZED = "openwa_unauthorized"
    OPENWA_TIMEOUT = "openwa_timeout"
    OPENWA_REQUEST_INVALID = "openwa_request_invalid"
    OPENWA_SESSION_NOT_FOUND = "openwa_session_not_found"
    OPENWA_SESSION_CONFLICT = "openwa_session_conflict"
    OPENWA_QR_NOT_READY = "openwa_qr_not_ready"
    OPENWA_PAIRING_FAILED = "openwa_pairing_failed"
    OPENWA_PHONE_INVALID = "openwa_phone_invalid"
    OPENWA_WEBHOOK_FAILED = "openwa_webhook_failed"
    OPENWA_SEND_FAILED = "openwa_send_failed"
    CHANNEL_BINDING_REQUIRED = "channel_binding_required"
    CHANNEL_EXPERT_INVALID = "channel_expert_invalid"

    # Workspace invitations (Phase 10A)
    INVITATION_NOT_FOUND = "invitation_not_found"
    INVITATION_ALREADY_EXISTS = "invitation_already_exists"
    ALREADY_WORKSPACE_MEMBER = "already_workspace_member"
    INVALID_INVITATION = "invalid_invitation"
    INVITATION_EXPIRED = "invitation_expired"
    INVITATION_REVOKED = "invitation_revoked"
    INVITATION_EMAIL_MISMATCH = "invitation_email_mismatch"
    INVITATION_ALREADY_ACCEPTED = "invitation_already_accepted"
    EMAIL_DELIVERY_FAILED = "email_delivery_failed"


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
    "invalid_reset_token": 400,
    "reset_token_expired": 410,
    "email_not_verified": 403,
    "invalid_verification_token": 400,
    "verification_token_expired": 410,
    "workspace_slug_taken": 409,
    "workspace_slug_invalid": 422,
    "workspace_not_found": 404,
    "membership_not_found": 404,
    "workspace_access_denied": 403,
    "insufficient_workspace_role": 403,
    "last_workspace_owner": 409,
    "unknown_permission": 422,
    "role_not_found": 404,
    "role_in_use": 409,
    "role_protected": 403,
    "role_name_taken": 409,
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
    "chat_attachment_not_found": 404,
    "upload_too_large": 413,
    "unsupported_audio_type": 400,
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
    "invoice_not_available": 409,
    "invoice_not_configured": 503,
    # Phase 7A — API keys
    "api_key_not_found": 404,
    # Phase 7B — public API rate limiting
    "rate_limit_exceeded": 429,
    # Phase 9A — App Store
    "app_not_found": 404,
    "app_not_available": 409,
    "app_already_installed": 409,
    "app_not_installed": 409,
    "app_billing_required": 402,
    "app_install_forbidden": 403,
    "app_installation_not_found": 404,
    # Phase 9B — App billing
    "app_plan_not_found": 404,
    "app_plan_inactive": 409,
    "app_plan_mismatch": 409,
    "app_already_licensed": 409,
    "app_subscription_required": 402,
    "app_subscription_expired": 402,
    "app_subscription_already_active": 409,
    "app_renewal_not_allowed": 409,
    "app_currency_not_supported": 422,
    "app_checkout_forbidden": 403,
    "app_checkout_in_progress": 409,
    "app_purchase_not_payable": 422,
    # Phase 9C — Connectors
    "connector_not_available": 409,
    "connector_not_supported": 409,
    "connector_already_registered": 409,
    "connector_access_required": 402,
    "connector_installation_required": 409,
    "connector_limit_reached": 429,
    "connector_not_found": 404,
    "connector_already_disconnected": 409,
    "connector_credentials_invalid": 401,
    "connector_credentials_expired": 401,
    "connector_connection_failed": 502,
    "connector_health_check_failed": 502,
    "connector_sync_not_supported": 409,
    "connector_sync_in_progress": 409,
    "connector_sync_not_found": 404,
    "connector_oauth_state_invalid": 400,
    "connector_oauth_state_expired": 400,
    "connector_oauth_state_replayed": 400,
    "connector_oauth_return_path_invalid": 400,
    "connector_webhook_invalid": 400,
    "connector_webhook_unauthorized": 401,
    "connector_invalid_transition": 409,
    # Phase 9D — Google Drive
    "google_drive_not_configured": 409,
    # 403 — authenticated Geem session; provider OAuth failed (SPA must not logout).
    "google_drive_authorization_failed": 403,
    "google_drive_reauthorization_required": 403,
    "google_drive_file_not_found": 404,
    "google_drive_file_access_denied": 403,
    "google_drive_file_type_unsupported": 422,
    "google_drive_export_too_large": 413,
    "google_drive_download_failed": 502,
    "google_drive_rate_limited": 429,
    "google_drive_watch_failed": 502,
    "google_drive_sync_failed": 502,
    # Phase 9E — Microsoft OneDrive
    "microsoft_onedrive_not_configured": 409,
    # 403 — authenticated Geem session; provider OAuth failed (SPA must not logout).
    "microsoft_onedrive_authorization_failed": 403,
    "microsoft_onedrive_reauthorization_required": 403,
    "microsoft_onedrive_drive_not_supported": 422,
    "microsoft_onedrive_item_not_found": 404,
    "microsoft_onedrive_access_denied": 403,
    "microsoft_onedrive_file_type_unsupported": 422,
    "microsoft_onedrive_conversion_failed": 422,
    "microsoft_onedrive_download_failed": 502,
    "microsoft_onedrive_rate_limited": 429,
    "microsoft_onedrive_delta_resync_required": 409,
    "microsoft_onedrive_subscription_failed": 502,
    "microsoft_onedrive_sync_failed": 502,
    # Phase 9F — OpenWA / WhatsApp
    "openwa_not_configured": 409,
    "openwa_unavailable": 503,
    "openwa_unauthorized": 502,
    "openwa_timeout": 504,
    "openwa_request_invalid": 422,
    "openwa_session_not_found": 404,
    "openwa_session_conflict": 409,
    "openwa_qr_not_ready": 409,
    "openwa_pairing_failed": 422,
    "openwa_phone_invalid": 422,
    "openwa_webhook_failed": 502,
    "openwa_send_failed": 502,
    "channel_binding_required": 422,
    "channel_expert_invalid": 422,
    # Phase 10A — workspace invitations
    "invitation_not_found": 404,
    "invitation_already_exists": 409,
    "already_workspace_member": 409,
    "invalid_invitation": 400,
    "invitation_expired": 410,
    "invitation_revoked": 409,
    "invitation_email_mismatch": 403,
    "invitation_already_accepted": 409,
    "email_delivery_failed": 502,
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
