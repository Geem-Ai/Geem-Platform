from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# Central reserved workspace slug list (infrastructure / product hosts).
# Extend via RESERVED_WORKSPACE_SLUGS env (comma-separated) without editing call sites.
DEFAULT_RESERVED_WORKSPACE_SLUGS: frozenset[str] = frozenset(
    {
        "www",
        "api",
        "admin",
        "app",
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
    openrouter_embedding_model: str = "qwen/qwen3-embedding-8b"
    openrouter_rerank_model: str = "cohere/rerank-v3.5"
    openrouter_chat_model: str = "qwen/qwen3.8-max"
    openrouter_chat_fallback_model: str = "openai/gpt-5.6-terra"
    openrouter_general_model: str = ""
    openrouter_allow_fallbacks: bool = True
    openrouter_data_collection: str = "deny"

    general_fallback_enabled: bool = True

    # Phase 4B — persisted chat orchestration
    chat_history_max_messages: int = 20
    conversation_title_max_length: int = 80
    conversation_generation_lock_ttl_seconds: int = 300
    max_chat_message_chars: int = 32_000

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
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_local(self) -> bool:
        return self.app_env.lower() in {"local", "dev", "development", "test"}

    @property
    def cookie_secure(self) -> bool:
        if self.refresh_cookie_secure is not None:
            return self.refresh_cookie_secure
        return not self.is_local

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


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    assert_secure_settings(settings)
    return settings
