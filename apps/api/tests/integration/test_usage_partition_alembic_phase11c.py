"""Upgrade from the Phase 11B revision onto partitioned usage_events."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text

from app.core.config import get_settings

API_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = API_ROOT / "alembic.ini"
MIG_DB = "geem_test_usage_11c"
FRESH_DB = "geem_test_usage_11c_fresh"


def _admin_url():
    url = make_url(get_settings().database_url)
    return url.set(database="postgres")


def _mig_url():
    url = make_url(get_settings().database_url)
    return url.set(database=MIG_DB)


def _alembic_cfg(database_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    return cfg


def _make_db(name: str):
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
            conn.execute(text(f"CREATE DATABASE {name}"))
    except Exception as exc:  # noqa: BLE001
        admin.dispose()
        pytest.skip(f"cannot create {name}: {exc}")
    url = make_url(get_settings().database_url).set(database=name)
    engine = create_engine(url)
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(
            text(
                f"""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = '{name}' AND pid <> pg_backend_pid()
                """
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
    admin.dispose()
    os.environ.pop("ALEMBIC_DATABASE_URL", None)


@pytest.fixture(scope="module")
def mig_engine():
    yield from _make_db(MIG_DB)


@pytest.fixture(scope="module")
def fresh_engine():
    yield from _make_db(FRESH_DB)


def test_upgrade_from_phase11b_preserves_rows(mig_engine) -> None:
    url = _mig_url().render_as_string(hide_password=False)
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "0032_usage_daily_workspace")
    ids = {
        "jul25": uuid.uuid4(),
        "dec25": uuid.uuid4(),
        "jan26": uuid.uuid4(),
        "jul26": uuid.uuid4(),
        "aug26": uuid.uuid4(),
    }
    stamps = {
        "jul25": datetime(2025, 7, 15, 12, tzinfo=UTC),
        "dec25": datetime(2025, 12, 2, 8, tzinfo=UTC),
        "jan26": datetime(2026, 1, 20, 9, tzinfo=UTC),
        "jul26": datetime(2026, 7, 4, 11, tzinfo=UTC),
        "aug26": datetime(2026, 8, 18, 16, tzinfo=UTC),
    }
    with mig_engine.begin() as conn:
        kind = conn.execute(
            text("SELECT relkind FROM pg_class WHERE relname = 'usage_events'")
        ).scalar()
        assert kind == "r"
        for key, event_id in ids.items():
            conn.execute(
                text(
                    """
                    INSERT INTO usage_events (id, operation_type, created_at, cost_metadata)
                    VALUES (:id, 'chat', :created_at, CAST(:meta AS jsonb))
                    """
                ),
                {"id": event_id, "created_at": stamps[key], "meta": '{"family":"chat","billed_tokens":7}'},
            )
        before = conn.execute(text("SELECT COUNT(*) FROM usage_events")).scalar()
        assert int(before or 0) == 5

    command.upgrade(cfg, "head")

    with mig_engine.begin() as conn:
        kind = conn.execute(
            text(
                """
                SELECT c.relkind
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = 'usage_events'
                """
            )
        ).scalar()
        assert kind == "p"
        after = conn.execute(text("SELECT COUNT(*) FROM usage_events")).scalar()
        assert int(after or 0) == 5
        rows = conn.execute(
            text("SELECT id, created_at, cost_metadata->>'family' AS family FROM usage_events")
        ).mappings()
        found = {row["id"]: row for row in rows}
        for key, event_id in ids.items():
            assert event_id in found
            assert found[event_id]["family"] == "chat"
        child = conn.execute(
            text("SELECT tableoid::regclass::text FROM usage_events WHERE id = :id"),
            {"id": ids["jul26"]},
        ).scalar()
        assert child == "usage_events_2026_07"
        idx = conn.execute(
            text(
                """
                SELECT 1 FROM pg_indexes
                WHERE tablename LIKE 'usage_events%'
                  AND indexname LIKE 'ix_usage_events_workspace_created%'
                LIMIT 1
                """
            )
        ).scalar()
        assert idx == 1
        conn.execute(
            text(
                """
                INSERT INTO usage_events (id, operation_type, created_at)
                VALUES (:id, 'chat', :created_at)
                """
            ),
            {
                "id": uuid.uuid4(),
                "created_at": datetime(2026, 8, 19, 12, tzinfo=UTC),
            },
        )
        new_child = conn.execute(
            text(
                """
                SELECT tableoid::regclass::text FROM usage_events
                WHERE created_at = :ts
                """
            ),
            {"ts": datetime(2026, 8, 19, 12, tzinfo=UTC)},
        ).scalar()
        assert new_child == "usage_events_2026_08"


def test_fresh_database_upgrade_creates_partitions(fresh_engine) -> None:
    url = make_url(get_settings().database_url).set(
        database=FRESH_DB
    ).render_as_string(hide_password=False)
    command.upgrade(_alembic_cfg(url), "head")
    with fresh_engine.begin() as conn:
        kind = conn.execute(
            text(
                """
                SELECT c.relkind
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = 'usage_events'
                """
            )
        ).scalar()
        assert kind == "p"
        now = datetime.now(UTC)
        name = f"usage_events_{now.year:04d}_{now.month:02d}"
        found = conn.execute(
            text(
                """
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = :name
                """
            ),
            {"name": name},
        ).scalar()
        assert found == 1
        daily = conn.execute(
            text(
                """
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                  AND c.relname = 'usage_daily_workspace'
                """
            )
        ).scalar()
        assert daily == 1
