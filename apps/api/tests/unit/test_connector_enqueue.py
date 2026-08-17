"""Connector enqueue-after-commit helpers."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import text

from app.connectors.enqueue import enqueue_connector_sync_after_commit, run_after_commit


def test_run_after_commit_fires_only_on_commit(db) -> None:
    calls: list[int] = []

    # Touch the session so SQLAlchemy opens a transaction.
    db.execute(text("SELECT 1"))
    run_after_commit(db, lambda: calls.append(1))
    assert calls == []

    db.commit()
    assert calls == [1]


def test_run_after_commit_skips_on_rollback(db) -> None:
    calls: list[int] = []
    db.execute(text("SELECT 1"))
    run_after_commit(db, lambda: calls.append(1))
    db.rollback()
    assert calls == []


def test_enqueue_connector_sync_after_commit_defers_delay(db) -> None:
    ws = uuid.uuid4()
    conn = uuid.uuid4()
    run = uuid.uuid4()
    actor = uuid.uuid4()

    with patch("app.connectors.tasks.enqueue_connector_sync") as enq:
        db.execute(text("SELECT 1"))
        enqueue_connector_sync_after_commit(
            db,
            workspace_id=ws,
            connection_id=conn,
            sync_run_id=run,
            actor_id=actor,
        )
        enq.assert_not_called()
        db.commit()
        enq.assert_called_once_with(
            workspace_id=ws,
            connection_id=conn,
            sync_run_id=run,
            actor_id=actor,
        )
