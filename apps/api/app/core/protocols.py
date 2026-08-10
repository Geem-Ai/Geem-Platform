from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DocumentParser(Protocol):
    def parse_page(
        self,
        page_pdf_bytes: bytes,
        filename: str,
        page_number: int,
    ) -> "ParsedPage": ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


@runtime_checkable
class RerankProvider(Protocol):
    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_n: int,
    ) -> list[dict]: ...


@runtime_checkable
class ChatProvider(Protocol):
    def answer(self, question: str, context: str) -> dict: ...


@runtime_checkable
class VectorStore(Protocol):
    def ensure_collection(self, vector_size: int) -> None: ...

    def upsert(self, points: list[dict]) -> None: ...

    def search(
        self,
        vector: list[float],
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[dict]: ...

    def delete_by_document(self, document_id: str) -> None: ...


@runtime_checkable
class ObjectStorage(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def ensure_bucket(self) -> None: ...
