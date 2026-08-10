from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = QdrantClient(url=self.settings.qdrant_url, timeout=60, check_compatibility=False)
        self.collection = self.settings.qdrant_collection
        self._vector_size: int | None = None

    def ensure_collection(self, vector_size: int) -> None:
        try:
            exists = self.client.collection_exists(self.collection)
            if exists:
                info = self.client.get_collection(self.collection)
                current = info.config.params.vectors.size  # type: ignore[union-attr]
                if current != vector_size:
                    raise AppError(
                        ErrorCategory.QDRANT_FAILED,
                        f"Vector dimension mismatch: collection={current}, embedding={vector_size}",
                    )
                self._vector_size = current
                return

            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
            )
            for field in ("document_id", "page", "embedding_model"):
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema=qm.PayloadSchemaType.KEYWORD
                    if field != "page"
                    else qm.PayloadSchemaType.INTEGER,
                )
            self._vector_size = vector_size
        except AppError:
            raise
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Failed to ensure collection: {exc}") from exc

    def upsert(self, points: list[dict]) -> None:
        if not points:
            return
        try:
            qpoints = []
            for p in points:
                qpoints.append(
                    qm.PointStruct(
                        id=str(p["id"]),
                        vector=p["vector"],
                        payload=p.get("payload") or {},
                    )
                )
            self.client.upsert(collection_name=self.collection, points=qpoints, wait=True)
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Upsert failed: {exc}") from exc

    def search(
        self,
        vector: list[float],
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[dict]:
        try:
            query_filter = None
            if document_ids:
                query_filter = qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="document_id",
                            match=qm.MatchAny(any=document_ids),
                        )
                    ]
                )
            response = self.client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
            results = response.points if hasattr(response, "points") else response
            out: list[dict[str, Any]] = []
            for hit in results:
                payload = hit.payload or {}
                out.append(
                    {
                        "chunk_id": payload.get("chunk_id"),
                        "document_id": payload.get("document_id"),
                        "document_title": payload.get("document_title"),
                        "page": payload.get("page"),
                        "ordinal": payload.get("ordinal"),
                        "heading_path": payload.get("heading_path"),
                        "embedding_model": payload.get("embedding_model"),
                        "canonical_text": payload.get("canonical_text"),
                        "search_text": payload.get("search_text"),
                        "vector_score": hit.score,
                        "qdrant_point_id": str(hit.id),
                    }
                )
            return out
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Search failed: {exc}") from exc

    def delete_by_document(self, document_id: str) -> None:
        try:
            if not self.client.collection_exists(self.collection):
                return
            self.client.delete(
                collection_name=self.collection,
                points_selector=qm.FilterSelector(
                    filter=qm.Filter(
                        must=[
                            qm.FieldCondition(
                                key="document_id",
                                match=qm.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Delete by document failed: {exc}") from exc


def deterministic_point_id(chunk_id: uuid.UUID) -> uuid.UUID:
    """Use chunk UUID as Qdrant point ID for idempotent upserts."""
    return chunk_id
