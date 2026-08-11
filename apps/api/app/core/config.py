from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    app_name: str = "Geem"
    app_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:3000"
    log_level: str = "INFO"

    # Phase 0 default: MVP routes remain open. Flip true after identity bootstrap (Phase 1+).
    auth_required: bool = False

    # Root domain for workspace subdomain resolution (e.g. geem.ai). Local DX uses header fallback.
    app_root_domain: str = "localhost"
    app_admin_host: str = "admin.localhost"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
