"""Defer Celery connector enqueues until the DB transaction commits.

Enqueueing inside an open request transaction races the worker: Celery can
claim the task before ``COMMIT``, hit ``Sync run not found``, and leave the
run stuck in ``pending`` (blocking future syncs).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_after_commit(db: Session, callback: Callable[[], Any]) -> None:
    """Run ``callback`` after the current transaction commits.

    If the session is not in a transaction (already committed / autobegin
    idle), run immediately so unit tests with ``enqueue=False`` paths and
    post-commit callers still work.
    """
    if not db.in_transaction():
        callback()
        return

    # Capture once per registration; SQLAlchemy SessionEvents.after_commit.
    @event.listens_for(db, "after_commit", once=True)
    def _on_commit(_session: Session) -> None:  # noqa: ANN001
        try:
            callback()
        except Exception:  # noqa: BLE001
            logger.exception("connector_after_commit_hook_failed")

    @event.listens_for(db, "after_rollback", once=True)
    def _on_rollback(_session: Session) -> None:  # noqa: ANN001
        # No-op: after_commit won't fire; avoid dangling expectations.
        return


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
