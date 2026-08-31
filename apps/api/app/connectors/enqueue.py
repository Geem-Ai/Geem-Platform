"""Defer Celery connector enqueues until the DB transaction commits.

Enqueueing inside an open request transaction races the worker: Celery can
claim the task before ``COMMIT``, hit ``Sync run not found``, and leave the
run stuck in ``pending`` (blocking future syncs).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.common.after_commit import run_after_commit

__all__ = ["enqueue_connector_sync_after_commit", "run_after_commit"]


def enqueue_connector_sync_after_commit(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    connection_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> None:
    from app.connectors.tasks import enqueue_connector_sync

    run_after_commit(
        db,
        lambda: enqueue_connector_sync(
            workspace_id=workspace_id,
            connection_id=connection_id,
            sync_run_id=sync_run_id,
            actor_id=actor_id,
        ),
    )
