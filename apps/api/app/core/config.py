from __future__ import annotations

import re
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Central reserved workspace slug list (infrastructure / product hosts).
# Extend via RESERVED_WORKSPACE_SLUGS env (comma-separated) without editing call sites.
DEFAULT_RESERVED_WORKSPACE_SLUGS: frozenset[str] = frozenset(
    {
        "www",
        "api",
        "admin",
        "app",
        "app-uat",
        "api-uat",
        "dashboard",
        "status",
        "support",
        "docs",
        "mail",
        "smtp",
        "cdn",
        "assets",
        "static",
        "auth",
        "login",
        "register",
        "billing",
        "console",
        "workspace",
        "workspaces",
        "geem",
        "null",
        "undefined",
        # Platform Knowledge system Workspace (also reserved via settings slug).
        "platform-knowledge",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    app_name: str = "Geem"
    app_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:3000"
    log_level: str = "INFO"

    # Phase 2C+: Document/Query/Jobs HTTP always require authenticated Workspace.
    # Public: /api/auth/login|register|refresh, /api/health/*, OpenAPI in local.
    # /api/api-keys is session-authenticated Workspace management (owner/admin).
    # This flag documents production expectation and is echoed on GET /.
    auth_required: bool = True

    # Legacy unauthenticated MVP writes are retired after Phase 2C cutover.
    # Kept for migration tooling / emergency freeze checks; production should be false.
    legacy_mvp_writes_enabled: bool = False

    # Root domain for workspace subdomain resolution (e.g. geem.ai). Local DX uses header fallback.
    app_root_domain: str = "localhost"
    app_admin_host: str = "admin.localhost"

    # Comma-separated extras merged with DEFAULT_RESERVED_WORKSPACE_SLUGS.
    reserved_workspace_slugs: str = ""

    # Slug used when bootstrapping the migration/default workspace (Phase 2 attaches docs).
    default_workspace_slug: str = "default"
    default_workspace_name: str = "Default Workspace"

    # Internal Platform Knowledge Workspace (Phase 3A). Owns Platform Expert Documents.
    # Distinct from DEFAULT_WORKSPACE_SLUG (tenant migration home). Never a tenant Workspace.
    platform_knowledge_workspace_slug: str = "platform-knowledge"
    platform_knowledge_workspace_name: str = "Platform Knowledge"

    # Idempotent platform-admin bootstrap (never ship a production default password).
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    # Auth / session
    jwt_secret: str = "change-me-in-production-use-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900  # 15 minutes
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days
    refresh_cookie_name: str = "geem_refresh"
    refresh_cookie_secure: bool | None = None  # None → secure when app_env != local
    refresh_cookie_samesite: str = "lax"
    # Multi-tab: reuse of a just-rotated refresh token within this window rotates from
    # the replacement tip instead of nuking the entire session family.
    refresh_reuse_grace_seconds: int = 60
    auth_rate_limit_per_minute: int = 20
    # Only trust X-Forwarded-For when true (edge/proxy must overwrite the header).
    trust_proxy_headers: bool = False

    database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"
    redis_url: str = "redis://localhost:6379/0"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "arabic_rag_chunks_v1"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "change-me"
    minio_bucket: str = "rag-documents"
    minio_secure: bool = False

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_pdf_trigger_model: str = "openai/gpt-5.6-luna"
    openrouter_pdf_engine: str = "mistral-ocr"
    openrouter_stt_model: str = "google/chirp-3"
    openrouter_embedding_model: str = "qwen/qwen3-embedding-8b"
    openrouter_rerank_model: str = "cohere/rerank-v3.5"
    openrouter_chat_model: str = "qwen/qwen3.8-max"
    openrouter_chat_fallback_model: str = "openai/gpt-5.6-terra"
    openrouter_general_model: str = ""
    openrouter_allow_fallbacks: bool = True
    openrouter_data_collection: str = "deny"

    general_fallback_enabled: bool = True

    # Phase 5A — bootstrap/dev plan entitlements (NOT Geem commercial pricing).
    # Existing Workspaces receive this plan so they keep a valid entitlement set.
    bootstrap_plan_code: str = "bootstrap_dev"
    bootstrap_plan_name: str = "Bootstrap (development)"
    bootstrap_plan_description: str = (
        "Development/bootstrap default plan. Values are conservative high limits "
        "so existing Workspaces keep working; they are not Geem product pricing."
    )
    bootstrap_ai_tokens_daily: int = 1_000_000
    bootstrap_ai_tokens_weekly: int = 5_000_000
    bootstrap_ai_tokens_monthly: int = 20_000_000
    bootstrap_experts_limit: int = 100
    bootstrap_storage_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GiB
    # Development-safe public API RPM. Not Geem commercial pricing.
    bootstrap_api_requests_per_minute: int = 60

    # Phase 5B — tokens held before an LLM call. 0 means max_context_tokens.
    ai_usage_reservation_tokens: int = 0

    # Workspace AI token pool weights. billed = round(provider_tokens * multiplier).
    # Family rates apply to the matching OPENROUTER_*_MODEL unless overridden.
    ai_token_multiplier_chat: float = 1.0
    ai_token_multiplier_embed: float = 1.0
    ai_token_multiplier_rerank: float = 1.0
    ai_token_multiplier_ocr: float = 3.0
    ai_token_multiplier_title: float = 1.0
    ai_token_multiplier_stt: float = 2.0
    # Optional JSON object: {"openai/gpt-5.6-luna": 3, "cohere/rerank-v3.5": 2}
    ai_token_model_multipliers: str = ""
    ai_token_fallback_embed: int = 100
    ai_token_fallback_rerank: int = 50
    ai_token_fallback_ocr_per_page: int = 500
    ai_token_fallback_title: int = 64
    # STT: when provider omits token totals, prefer duration * per-second rate.
    ai_token_stt_per_second: int = 50
    ai_token_fallback_stt: int = 500

    # Phase 5C — stale storage holds (crashed upload before finalize/release).
    storage_reservation_ttl_seconds: int = 900

    # Phase 6A — secret-at-rest key for payment_gateway_configs credentials.
    # Empty → derived from JWT_SECRET. Set a dedicated key in non-local env.
    secrets_encryption_key: str = ""

    # Phase 7A — HMAC-SHA256 pepper for API-key lookup hashes (not a password hasher).
    # Empty in local/test derives from JWT_SECRET. Non-local must set a dedicated value.
    api_key_hash_pepper: str = Field(default="", repr=False, exclude=True)

    # Phase 6A — ClickPay hosted-page (used when DB credentials are empty).
    clickpay_profile_id: str = ""
    clickpay_server_key: str = ""
    clickpay_test_mode: bool = True
    clickpay_base_url: str = "https://secure.clickpay.com.sa"
    clickpay_timeout_seconds: float = 30.0
    billing_currency: str = "SAR"
    # ZATCA simplified tax invoice — seller is the Geem legal entity.
    # INVOICE_SELLER_NAME should match the VAT registration name (QR tag 1).
    invoice_seller_name: str = "Geem"
    invoice_seller_name_ar: str = "جيم"
    invoice_vat_number: str = ""
    invoice_cr_number: str = ""
    invoice_address: str = "Kingdom of Saudi Arabia"
    invoice_address_ar: str = "المملكة العربية السعودية"
    # Standard KSA VAT. Catalog prices are treated as VAT-inclusive.
    invoice_vat_rate: str = "0.15"
    invoice_prices_include_vat: bool = True
    # SPA origin for post-verification browser handoff (Phase 6B).
    # Empty: local/test fall back to http://localhost:5174; non-local disables HTML redirect.
    workspace_web_url: str = ""

    # Phase 10A — workspace email invitations.
    workspace_invite_ttl_hours: int = 72
    # console = local/test only (may print accept URLs with raw tokens).
    # smtp = production-capable. Non-local must not use console.
    email_provider: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = Field(default="", repr=False, exclude=True)
    smtp_from_email: str = ""
    smtp_from_name: str = "Geem"
    smtp_use_tls: bool = True  # required true outside local/test
    # false skips SMTP server cert verification (self-signed hosts). Local/test only.
    smtp_tls_verify: bool = True
    smtp_timeout_seconds: float = 10.0
    # Empty → reuse API-key HMAC pepper (local derives from JWT_SECRET).
    invitation_token_hash_pepper: str = Field(default="", repr=False, exclude=True)

    # Phase 9D — Google Drive knowledge connector (OAuth). Empty → unavailable.
    google_drive_client_id: str = ""
    google_drive_client_secret: str = Field(default="", repr=False, exclude=True)
    # Empty → derive from app_url + /api/connectors/oauth/google_drive/callback
    google_drive_redirect_uri: str = ""
    # selected_files | readonly
    google_drive_scope_mode: str = "selected_files"
    # Optional backend echo for Picker; frontend may use Vite env instead.
    google_drive_picker_api_key: str = ""
    # Google Cloud project number for Picker.
    google_drive_app_id: str = ""

    # Phase 9E — Microsoft OneDrive knowledge connector (Entra / Graph). Empty → unavailable.
    microsoft_onedrive_client_id: str = ""
    microsoft_onedrive_client_secret: str = Field(default="", repr=False, exclude=True)
    # Empty → derive from app_url + /api/connectors/oauth/microsoft_onedrive/callback
    microsoft_onedrive_redirect_uri: str = ""
    # organizations | common | consumers | specific tenant GUID
    # Use common for work/school + personal File Picker (9E.1); organizations for work-only.
    microsoft_onedrive_tenant: str = "organizations"
    # Graph subscription lifetime minutes (must stay below provider max ~42300).
    microsoft_onedrive_subscription_minutes: int = 4000

    # Phase 9F — OpenWA / WhatsApp channel connector. Empty API key → unavailable.
    openwa_base_url: str = "https://whatsapp-hub.dalseen.sa"
    openwa_api_key: str = Field(default="", repr=False, exclude=True)
    openwa_timeout_seconds: float = 30.0

    # Phase 4B — persisted chat orchestration
    chat_history_max_messages: int = 20
    conversation_title_max_length: int = 80
    conversation_generation_lock_ttl_seconds: int = 300
    max_chat_message_chars: int = 32_000
    # Chat composer attachments (ephemeral — not Expert knowledge Documents)
    chat_attachment_max_mb: int = 20
    chat_attachment_ttl_hours: int = 12
    # Chat Widget visitor threads (Phase 9H)
    widget_chat_history_max_messages: int = 15
    widget_message_ttl_hours: int = 1
    widget_session_max_messages_per_day: int = 50
    # Chat voice STT upload cap (OpenRouter allows up to 25 MiB; keep lower for mic clips)
    chat_transcribe_max_mb: int = 10

    max_upload_mb: int = 100
    max_pdf_pages: int = 1000
    ocr_page_concurrency: int = 4
    embedding_batch_size: int = 32
    retrieval_top_k: int = 20
    rerank_top_n: int = 6
    max_context_tokens: int = 12000

    chunk_target_min_tokens: int = 350
    chunk_target_max_tokens: int = 550
    chunk_hard_max_tokens: int = 700
    chunk_overlap_tokens: int = 60
    chunk_min_tokens: int = 80

    rag_pipeline_version: str = "v1"
    parser_version: str = "openrouter:mistral-ocr"
    normalizer_version: str = "arabic-v1"
    chunker_version: str = "page-structure-v1"
    prompt_version: str = "rag_answer_v1"
    general_prompt_version: str = "general_fallback_v1"
    embedding_version: str = "v1"

    @property
    def effective_ai_usage_reservation_tokens(self) -> int:
        n = int(self.ai_usage_reservation_tokens)
        return n if n > 0 else int(self.max_context_tokens)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def chat_attachment_max_bytes(self) -> int:
        return self.chat_attachment_max_mb * 1024 * 1024

    @property
    def chat_attachment_ttl_seconds(self) -> int:
        hours = max(1, int(self.chat_attachment_ttl_hours))
        return hours * 3600

    @property
    def widget_message_ttl_seconds(self) -> int:
        hours = max(1, int(self.widget_message_ttl_hours))
        return hours * 3600

    @property
    def chat_transcribe_max_bytes(self) -> int:
        return max(1, int(self.chat_transcribe_max_mb)) * 1024 * 1024

    @property
    def is_local(self) -> bool:
        return self.app_env.lower() in {"local", "dev", "development", "test"}

    def local_spa_origin_regex(self) -> str | None:
        """Allow http(s)://{optional-subdomain.}{APP_ROOT_DOMAIN}{:port} in local/dev only."""
        if not self.is_local:
            return None
        root = self.app_root_domain.strip().lower().lstrip(".")
        if not root or root in {"localhost", "127.0.0.1"}:
            return None
        escaped = re.escape(root)
        return rf"^https?://([a-z0-9-]+\.)?{escaped}(:\d+)?$"

    def is_allowed_spa_origin(self, origin: str) -> bool:
        raw = (origin or "").strip().rstrip("/")
        if not raw:
            return False
        if raw in self.cors_origin_list:
            return True
        pattern = self.local_spa_origin_regex()
        return bool(pattern and re.match(pattern, raw))

    @property
    def effective_workspace_web_url(self) -> str:
        raw = (self.workspace_web_url or "").strip().rstrip("/")
        if raw:
            return raw
        if not self.is_local:
            return ""
        root = (self.app_root_domain or "").strip().lower().lstrip(".")
        if root and root not in {"localhost", "127.0.0.1"}:
            return f"http://app.{root}:5174"
        return "http://localhost:5174"

    @property
    def cookie_secure(self) -> bool:
        if self.refresh_cookie_secure is not None:
            return self.refresh_cookie_secure
        return not self.is_local

    @property
    def effective_api_key_hash_pepper(self) -> str:
        raw = (self.api_key_hash_pepper or "").strip()
        if raw:
            return raw
        if self.is_local:
            jwt = (self.jwt_secret or "").strip()
            if not jwt:
                raise RuntimeError(
                    "API_KEY_HASH_PEPPER is missing and JWT_SECRET is empty."
                )
            return f"geem-api-key-pepper:{jwt}"
        raise RuntimeError(
            "API_KEY_HASH_PEPPER is required in non-local environments. "
            "Set a dedicated random secret (≥32 chars), distinct from JWT_SECRET."
        )

    @property
    def effective_invitation_token_hash_pepper(self) -> str:
        raw = (self.invitation_token_hash_pepper or "").strip()
        if raw:
            return raw
        return self.effective_api_key_hash_pepper

    @property
    def effective_workspace_invite_ttl_hours(self) -> int:
        hours = int(self.workspace_invite_ttl_hours)
        return hours if hours > 0 else 72

    @property
    def google_drive_configured(self) -> bool:
        return bool(
            (self.google_drive_client_id or "").strip()
            and (self.google_drive_client_secret or "").strip()
        )

    @property
    def effective_google_drive_redirect_uri(self) -> str:
        raw = (self.google_drive_redirect_uri or "").strip()
        if raw:
            return raw
        base = (self.app_url or "").rstrip("/")
        return f"{base}/api/connectors/oauth/google_drive/callback"

    @property
    def microsoft_onedrive_configured(self) -> bool:
        return bool(
            (self.microsoft_onedrive_client_id or "").strip()
            and (self.microsoft_onedrive_client_secret or "").strip()
        )

    @property
    def effective_microsoft_onedrive_redirect_uri(self) -> str:
        raw = (self.microsoft_onedrive_redirect_uri or "").strip()
        if raw:
            return raw
        base = (self.app_url or "").rstrip("/")
        return f"{base}/api/connectors/oauth/microsoft_onedrive/callback"

    @property
    def openwa_configured(self) -> bool:
        return bool(
            (self.openwa_base_url or "").strip() and (self.openwa_api_key or "").strip()
        )

    @property
    def reserved_slugs(self) -> frozenset[str]:
        extras = {s.strip().lower() for s in self.reserved_workspace_slugs.split(",") if s.strip()}
        # Always reserve the platform-knowledge slug even if env overrides the setting.
        pk = self.platform_knowledge_workspace_slug.strip().lower()
        return frozenset(DEFAULT_RESERVED_WORKSPACE_SLUGS | extras | ({pk} if pk else set()))


INSECURE_JWT_SECRETS = frozenset(
    {
        "",
        "change-me",
        "change-me-in-production-use-long-random-secret",
        "secret",
        "jwt-secret",
    }
)

INSECURE_API_KEY_PEPPERS = frozenset(
    {
        "",
        "change-me",
        "pepper",
        "api-key-pepper",
        "change-me-api-key-pepper",
    }
)


def assert_secure_settings(settings: Settings) -> None:
    """Fail fast in non-local environments when auth secrets are unsafe."""
    if settings.is_local:
        return
    if settings.jwt_secret.strip() in INSECURE_JWT_SECRETS or len(settings.jwt_secret.strip()) < 32:
        raise RuntimeError(
            "JWT_SECRET is missing or insecure. Set a strong random secret "
            "(≥32 chars) before starting Geem in non-local environments."
        )
    if "*" in settings.cors_origins:
        raise RuntimeError(
            "CORS_ORIGINS must not use '*' when credentialed cookies are enabled."
        )
    pepper = (settings.api_key_hash_pepper or "").strip()
    if (
        pepper in INSECURE_API_KEY_PEPPERS
        or len(pepper) < 32
        or pepper == settings.jwt_secret.strip()
    ):
        raise RuntimeError(
            "API_KEY_HASH_PEPPER is missing, insecure, or reused from JWT_SECRET. "
            "Set a dedicated random secret (≥32 chars) before starting Geem "
            "in non-local environments."
        )
    provider = (settings.email_provider or "").strip().lower()
    if provider in {"", "console"}:
        raise RuntimeError(
            "EMAIL_PROVIDER=console is not allowed outside local/test. "
            "Set EMAIL_PROVIDER=smtp and SMTP_* settings before starting Geem "
            "in non-local environments. The console adapter may print invitation "
            "URLs that contain raw tokens."
        )
    if provider != "smtp":
        raise RuntimeError(
            f"Unknown EMAIL_PROVIDER={provider!r}. Use 'smtp' in non-local environments."
        )
    if not (settings.smtp_host or "").strip() or not (settings.smtp_from_email or "").strip():
        raise RuntimeError(
            "SMTP_HOST and SMTP_FROM_EMAIL are required when EMAIL_PROVIDER=smtp."
        )
    if not settings.smtp_use_tls:
        raise RuntimeError(
            "SMTP_USE_TLS must be true in non-local environments so invitation "
            "tokens and SMTP credentials are not sent in the clear."
        )
    if not settings.smtp_tls_verify:
        raise RuntimeError(
            "SMTP_TLS_VERIFY must be true in non-local environments so invitation "
            "tokens are not exposed to a TLS man-in-the-middle. Install a CA-trusted "
            "certificate on the SMTP host instead of disabling verification."
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    assert_secure_settings(settings)
    return settings
