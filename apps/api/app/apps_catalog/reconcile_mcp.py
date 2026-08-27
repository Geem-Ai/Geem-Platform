"""Production-safe reconciliation for only the MCP Connectors catalog row.

This command never runs the broad App catalog seed. It preserves all other
Apps and preserves the MCP App's lifecycle status, plans, entitlements, and
operator-owned ``extra`` metadata.

Usage (from ``apps/api``):

    python -m app.apps_catalog.reconcile_mcp --dry-run
    python -m app.apps_catalog.reconcile_mcp --apply
    python -m app.apps_catalog.reconcile_mcp --verify
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.apps_catalog.mcp_product import MCP_CONNECTORS_APP_SLUG
from app.apps_catalog.models import AppPlan
from app.apps_catalog.repository import AppCatalogRepository
from app.apps_catalog.runtime_locks import acquire_app_runtime_mutation_fence
from app.apps_catalog.seed import (
    MCP_APP_SPEC,
    MCP_CATEGORY_SPEC,
    reconcile_mcp_app_catalog,
)
from app.core.config import Settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

Mode = Literal["dry-run", "apply", "verify"]


@dataclass(frozen=True, slots=True)
class CatalogChange:
    resource: str
    field: str
    before: Any
    after: Any


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    mode: Mode
    changes: tuple[CatalogChange, ...]
    matches: bool
    status_preserved: str | None
    plan_count_preserved: int


_APP_FIELDS: tuple[str, ...] = (
    "name",
    "short_description",
    "description",
    "icon_url",
    "billing_type",
    "is_featured",
    "sort_order",
    "connector_key",
    "connector_kind",
)


def inspect_mcp_app_catalog(db: Session, *, mode: Mode = "dry-run") -> ReconcileResult:
    """Return the bounded MCP-only diff without mutating the session."""

    repo = AppCatalogRepository(db)
    category = repo.get_category_by_slug(MCP_CATEGORY_SPEC.slug)
    app = repo.get_app_by_slug(MCP_CONNECTORS_APP_SLUG)
    changes: list[CatalogChange] = []

    if category is None:
        changes.append(
            CatalogChange(
                resource=f"category:{MCP_CATEGORY_SPEC.slug}",
                field="exists",
                before=False,
                after=True,
            )
        )

    if app is None:
        changes.append(
            CatalogChange(
                resource=f"app:{MCP_CONNECTORS_APP_SLUG}",
                field="exists",
                before=False,
                after=True,
            )
        )
        return ReconcileResult(
            mode=mode,
            changes=tuple(changes),
            matches=not changes,
            status_preserved=None,
            plan_count_preserved=0,
        )

    current_category_slug = app.category.slug if app.category is not None else None
    if current_category_slug != MCP_APP_SPEC.category_slug:
        changes.append(
            CatalogChange(
                resource=f"app:{MCP_CONNECTORS_APP_SLUG}",
                field="category_slug",
                before=current_category_slug,
                after=MCP_APP_SPEC.category_slug,
            )
        )
    for field in _APP_FIELDS:
        current = getattr(app, field)
        expected = getattr(MCP_APP_SPEC, field)
        if current != expected:
            changes.append(
                CatalogChange(
                    resource=f"app:{MCP_CONNECTORS_APP_SLUG}",
                    field=field,
                    before=current,
                    after=expected,
                )
            )

    return ReconcileResult(
        mode=mode,
        changes=tuple(changes),
        matches=not changes,
        status_preserved=app.status,
        plan_count_preserved=int(
            db.scalar(
                select(func.count()).select_from(AppPlan).where(AppPlan.app_id == app.id)
            )
            or 0
        ),
    )


def run_mcp_app_catalog_reconciliation(
    db: Session,
    *,
    mode: Mode,
    settings: Settings | None = None,
) -> ReconcileResult:
    """Inspect, apply, or verify the MCP-only catalog contract."""

    if mode not in {"dry-run", "apply", "verify"}:
        raise ValueError(f"Unsupported MCP catalog reconciliation mode: {mode}")
    if mode == "apply":
        # Keep the reported before-image and the MCP-only mutation in one
        # serialized production decision. The lower-level mutator also takes
        # this transaction-scoped lock so direct callers remain safe.
        acquire_app_runtime_mutation_fence(db, MCP_CONNECTORS_APP_SLUG)
    before = inspect_mcp_app_catalog(db, mode=mode)
    if mode != "apply":
        return before

    reconcile_mcp_app_catalog(db, settings=settings)
    after = inspect_mcp_app_catalog(db, mode=mode)
    if not after.matches:
        fields = ", ".join(change.field for change in after.changes)
        raise RuntimeError(f"MCP catalog reconciliation did not converge: {fields}")
    return ReconcileResult(
        mode=mode,
        changes=before.changes,
        matches=True,
        status_preserved=after.status_preserved,
        plan_count_preserved=after.plan_count_preserved,
    )


def _json_result(result: ReconcileResult) -> str:
    return json.dumps(
        {
            "mode": result.mode,
            "target_app": MCP_CONNECTORS_APP_SLUG,
            "matches": result.matches,
            "change_count": len(result.changes),
            "changes": [asdict(change) for change in result.changes],
            "status_preserved": result.status_preserved,
            "plan_count_preserved": result.plan_count_preserved,
            "scope": "mcp-only",
        },
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    selected: Mode = (
        "apply" if args.apply else "verify" if args.verify else "dry-run"
    )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    db = SessionLocal()
    try:
        result = run_mcp_app_catalog_reconciliation(
            db,
            mode=selected,
        )
        if selected == "apply":
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        logger.exception("mcp_app_catalog_reconciliation_failed")
        return 1
    finally:
        db.close()

    print(_json_result(result))
    if selected == "verify" and not result.matches:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
