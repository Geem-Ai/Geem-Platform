from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.storage.scopes import (
    ExpertRagScope,
    LegacyVectorScope,
    VectorScope,
    WorkspaceVectorScope,
)
from app.observability.tracing import start_span

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
                self._ensure_payload_indexes()
                return

            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
            )
            self._ensure_payload_indexes()
            self._vector_size = vector_size
        except AppError:
            raise
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Failed to ensure collection: {exc}") from exc

    def _ensure_payload_indexes(self) -> None:
        """Idempotent payload indexes.

        - ``workspace_id`` keyword: mandatory tenant filter for all Workspace/Expert
          retrieval. UUID is stored as string.
        - ``expert_ids`` keyword: array of Expert UUIDs a point currently belongs to
          (Phase 3B). Keyword arrays in Qdrant support "contains" via MatchValue /
          MatchAny; we always filter by a single expert_id at query time.
        """
        for field, schema in (
            ("document_id", qm.PayloadSchemaType.KEYWORD),
            ("workspace_id", qm.PayloadSchemaType.KEYWORD),
            ("expert_ids", qm.PayloadSchemaType.KEYWORD),
            ("page", qm.PayloadSchemaType.INTEGER),
            ("embedding_model", qm.PayloadSchemaType.KEYWORD),
        ):
            try:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema=schema,
                )
            except Exception as exc:  # noqa: BLE001 — already exists / race
                msg = str(exc).lower()
                if "already" in msg or "exists" in msg or "duplicate" in msg:
                    continue
                logger.debug("payload_index_ensure", extra={"field": field, "error": str(exc)})

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
            with start_span("qdrant.upsert"):
                self.client.upsert(collection_name=self.collection, points=qpoints, wait=True)
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Upsert failed: {exc}") from exc

    def set_payload(self, point_ids: list[str], payload: dict[str, Any]) -> None:
        """Update payload metadata without re-embedding (Phase 2B backfill)."""
        if not point_ids:
            return
        try:
            self.client.set_payload(
                collection_name=self.collection,
                payload=payload,
                points=point_ids,
                wait=True,
            )
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Set payload failed: {exc}") from exc

    def search_workspace(
        self,
        *,
        workspace_id: uuid.UUID | str,
        vector: list[float],
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[dict]:
        """Mandatory Qdrant-side workspace_id filter. Never searches globally.

        Kept for maintenance / reconciliation flows and for legacy population
        retrieval. Production Expert-scoped RAG must call ``search_expert``.
        """
        scope = WorkspaceVectorScope(workspace_id=uuid.UUID(str(workspace_id)))
        return self._search(scope=scope, vector=vector, top_k=top_k, document_ids=document_ids)

    def search_expert(
        self,
        *,
        knowledge_workspace_id: uuid.UUID | str,
        expert_id: uuid.UUID | str,
        vector: list[float],
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[dict]:
        """Expert-scoped retrieval (Phase 3B).

        Applies two mandatory Qdrant-side filters:

        1. ``workspace_id == knowledge_workspace_id`` — the tenant / Platform
           Knowledge Workspace whose Documents back this Expert.
        2. ``expert_ids`` contains ``expert_id`` — keyword-array membership.
           Qdrant matches "array contains X" with ``MatchValue(value=X)`` on a
           keyword-typed array field.

        Optional ``document_ids`` restricts further to a specific set of ready
        Documents (already scoped to the same knowledge Workspace by the caller).
        """
        scope = ExpertRagScope(
            consumer_workspace_id=uuid.UUID(str(knowledge_workspace_id)),
            knowledge_workspace_id=uuid.UUID(str(knowledge_workspace_id)),
            expert_id=uuid.UUID(str(expert_id)),
            expert_type="workspace",
        )
        return self._search(scope=scope, vector=vector, top_k=top_k, document_ids=document_ids)

    def search_legacy(
        self,
        *,
        vector: list[float],
        top_k: int,
        document_ids: list[str],
    ) -> list[dict]:
        """Legacy retrieval constrained to an explicit PostgreSQL-approved document_id set.

        Never call with an empty list — that would be an unscoped search.
        """
        if not document_ids:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Legacy vector search requires an explicit document_id set",
            )
        return self._search(
            scope=LegacyVectorScope(),
            vector=vector,
            top_k=top_k,
            document_ids=document_ids,
        )

    def search(
        self,
        vector: list[float],
        top_k: int,
        document_ids: list[str] | None = None,
        *,
        scope: VectorScope | None = None,
        workspace_id: uuid.UUID | str | None = None,
    ) -> list[dict]:
        """Deprecated open signature — prefer search_workspace / search_legacy.

        Requires an explicit scope (or workspace_id) so forgetting tenant context
        cannot produce a global search.
        """
        if scope is None:
            if workspace_id is not None:
                scope = WorkspaceVectorScope(workspace_id=uuid.UUID(str(workspace_id)))
            else:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Vector search requires an explicit tenant scope "
                    "(use search_workspace or search_legacy)",
                )
        return self._search(scope=scope, vector=vector, top_k=top_k, document_ids=document_ids)

    def _search(
        self,
        *,
        scope: VectorScope,
        vector: list[float],
        top_k: int,
        document_ids: list[str] | None,
    ) -> list[dict]:
        try:
            must: list[qm.Condition] = []
            expected_workspace_id: str | None = None
            expected_expert_id: str | None = None

            if isinstance(scope, WorkspaceVectorScope):
                expected_workspace_id = str(scope.workspace_id)
                must.append(
                    qm.FieldCondition(
                        key="workspace_id",
                        match=qm.MatchValue(value=expected_workspace_id),
                    )
                )
            elif isinstance(scope, ExpertRagScope):
                expected_workspace_id = str(scope.knowledge_workspace_id)
                expected_expert_id = str(scope.expert_id)
                must.append(
                    qm.FieldCondition(
                        key="workspace_id",
                        match=qm.MatchValue(value=expected_workspace_id),
                    )
                )
                # Keyword-array "contains" — Qdrant matches a single keyword value
                # against every element of an array-typed keyword payload field.
                must.append(
                    qm.FieldCondition(
                        key="expert_ids",
                        match=qm.MatchValue(value=expected_expert_id),
                    )
                )
            elif isinstance(scope, LegacyVectorScope):
                if not document_ids:
                    raise AppError(
                        ErrorCategory.VALIDATION,
                        "Legacy vector search requires explicit document_ids",
                    )
            else:
                raise AppError(ErrorCategory.VALIDATION, "Unknown vector scope")

            if document_ids:
                must.append(
                    qm.FieldCondition(
                        key="document_id",
                        match=qm.MatchAny(any=document_ids),
                    )
                )
            elif isinstance(scope, (WorkspaceVectorScope, ExpertRagScope)):
                # Workspace / Expert "all docs" still filter by workspace_id (and
                # expert_ids for Expert) — never a global search.
                pass
            else:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Unscoped vector search is not allowed",
                )

            query_filter = qm.Filter(must=must)
            with start_span("qdrant.search"):
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
                # Defense in depth: drop payload mismatches that shouldn't survive
                # the Qdrant filter (index rebuilds / stale points / bad payloads).
                if expected_workspace_id is not None:
                    payload_ws = payload.get("workspace_id")
                    if payload_ws is None or str(payload_ws) != expected_workspace_id:
                        continue
                if expected_expert_id is not None:
                    payload_experts = payload.get("expert_ids") or []
                    if not isinstance(payload_experts, list):
                        continue
                    if expected_expert_id not in {str(e) for e in payload_experts}:
                        continue
                out.append(
                    {
                        "chunk_id": payload.get("chunk_id"),
                        "document_id": payload.get("document_id"),
                        "workspace_id": payload.get("workspace_id"),
                        "expert_ids": list(payload.get("expert_ids") or []),
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
        except AppError:
            raise
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Search failed: {exc}") from exc

    def delete_by_document(
        self,
        document_id: str,
        *,
        workspace_id: uuid.UUID | str | None = None,
    ) -> None:
        try:
            if not self.client.collection_exists(self.collection):
                return
            must: list[qm.Condition] = [
                qm.FieldCondition(
                    key="document_id",
                    match=qm.MatchValue(value=document_id),
                )
            ]
            if workspace_id is not None:
                must.append(
                    qm.FieldCondition(
                        key="workspace_id",
                        match=qm.MatchValue(value=str(workspace_id)),
                    )
                )
            with start_span("qdrant.delete"):
                self.client.delete(
                    collection_name=self.collection,
                    points_selector=qm.FilterSelector(filter=qm.Filter(must=must)),
                    wait=True,
                )
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Delete by document failed: {exc}") from exc

    def get_payload_expert_ids_for_document(
        self, document_id: str, *, limit: int = 1
    ) -> list[str]:
        """Return ``expert_ids`` from the first Qdrant point for a Document.

        Useful for reconciliation — comparing Qdrant-side membership vs. PG
        ``expert_documents`` to detect drift. Returns an empty list when the
        Document has no points yet (pre-ingestion) or no ``expert_ids`` payload.
        """
        try:
            if not self.client.collection_exists(self.collection):
                return []
            records, _ = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="document_id",
                            match=qm.MatchValue(value=document_id),
                        )
                    ]
                ),
                limit=max(1, limit),
                with_payload=True,
                with_vectors=False,
            )
            for rec in records:
                payload = rec.payload or {}
                values = payload.get("expert_ids")
                if isinstance(values, list):
                    return [str(v) for v in values]
                return []
            return []
        except Exception as exc:
            raise AppError(
                ErrorCategory.QDRANT_FAILED, f"Read expert_ids payload failed: {exc}"
            ) from exc

    def scroll_point_ids_for_document(self, document_id: str, *, limit: int = 256) -> list[str]:
        """List Qdrant point IDs for a document (payload backfill)."""
        try:
            if not self.client.collection_exists(self.collection):
                return []
            point_ids: list[str] = []
            next_offset = None
            while True:
                records, next_offset = self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=qm.Filter(
                        must=[
                            qm.FieldCondition(
                                key="document_id",
                                match=qm.MatchValue(value=document_id),
                            )
                        ]
                    ),
                    limit=limit,
                    offset=next_offset,
                    with_payload=False,
                    with_vectors=False,
                )
                for rec in records:
                    point_ids.append(str(rec.id))
                if next_offset is None:
                    break
            return point_ids
        except Exception as exc:
            raise AppError(ErrorCategory.QDRANT_FAILED, f"Scroll failed: {exc}") from exc


def deterministic_point_id(chunk_id: uuid.UUID) -> uuid.UUID:
    """Use chunk UUID as Qdrant point ID for idempotent upserts."""
    return chunk_id
