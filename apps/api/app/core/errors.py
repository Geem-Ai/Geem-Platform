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
