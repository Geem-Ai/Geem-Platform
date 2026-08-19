"""Tenant ContextVar helpers for Celery workers and non-HTTP execution.

HTTP requests use RequestContextMiddleware. Workers must bind and clear
explicitly so reused processes never leak tenant identity across tasks.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from app.common.request_context import (
    RequestContext,
    clear_request_context,
    get_request_context,
    reset_request_context,
    set_request_context,
)
from app.observability.attributes import attach_request_context


@contextmanager
def tenant_context(
    *,
    workspace_id: UUID | None,
    document_id: UUID | None = None,
    actor_id: UUID | None = None,
    request_id: str | None = None,
) -> Iterator[RequestContext]:
    """Bind tenant identity for the duration of a worker/task block, then clear."""
    extras: dict = {}
    if document_id is not None:
        extras["document_id"] = str(document_id)
    ctx = RequestContext(
        request_id=request_id,
        user_id=actor_id,
        workspace_id=workspace_id,
        extras=extras,
    )
    token = set_request_context(ctx)
    attach_request_context()
    try:
        yield ctx
    finally:
        reset_request_context(token)
        # Belt-and-suspenders for worker process reuse.
        if get_request_context().workspace_id == workspace_id:
            clear_request_context()
