"""Fresh paid-App admission and restrictive-mutation advisory fences.

The lock keys are derived only from stable identifiers known before paid
authorization. Admission obtains shared locks in canonical App -> Workspace ->
Workspace+App order in one statement. Restrictive writers take the matching
exclusive key before changing authority state.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCategory


def begin_runtime_admission_transaction(db: Session) -> None:
    """Start a fresh transaction pinned and verified as READ COMMITTED."""
    if db.in_transaction():
        raise AppError(
            ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
            "Paid App admission requires a fresh database transaction.",
            retryable=True,
        )
    try:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        level = str(db.scalar(text("SHOW transaction_isolation")) or "").lower()
    except Exception as exc:  # database availability/configuration boundary
        raise AppError(
            ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
            "Paid App runtime access is temporarily unavailable.",
            retryable=True,
        ) from exc
    if level != "read committed":
        raise AppError(
            ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
            "Paid App admission requires READ COMMITTED isolation.",
            retryable=True,
        )


def acquire_runtime_admission_fences(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    app_slugs: Iterable[str],
    surface_target_keys: Iterable[str] = (),
) -> None:
    """Acquire all shared admission fences in one preliminary statement."""
    slugs = tuple(sorted({_normalize_slug(slug) for slug in app_slugs}))
    if not slugs:
        raise ValueError("At least one App slug is required for paid admission.")
    locks: list[tuple[str, int]] = []
    locks.extend(("shared", _fence_key(f"app:{slug}")) for slug in slugs)
    locks.append(("shared", _fence_key(f"workspace:{workspace_id}")))
    locks.extend(
        (
            "shared",
            _fence_key(f"workspace-app:{workspace_id}:{slug}"),
        )
        for slug in slugs
    )
    targets = tuple(sorted({_normalize_target_key(key) for key in surface_target_keys}))
    locks.extend(
        (
            "shared",
            _fence_key(f"surface:{workspace_id}:{target}"),
        )
        for target in targets
    )
    try:
        _execute_lock_statement(db, locks)
    except SQLAlchemyError as exc:
        raise AppError(
            ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE,
            "Paid App runtime access is temporarily unavailable.",
            retryable=True,
        ) from exc


def acquire_app_runtime_mutation_fence(db: Session, app_slug: str) -> None:
    _execute_lock_statement(
        db, [("exclusive", _fence_key(f"app:{_normalize_slug(app_slug)}"))]
    )


def acquire_workspace_runtime_mutation_fence(
    db: Session, workspace_id: uuid.UUID
) -> None:
    _execute_lock_statement(
        db, [("exclusive", _fence_key(f"workspace:{workspace_id}"))]
    )


def acquire_workspace_app_runtime_mutation_fence(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    app_slug: str,
) -> None:
    slug = _normalize_slug(app_slug)
    _execute_lock_statement(
        db,
        [("exclusive", _fence_key(f"workspace-app:{workspace_id}:{slug}"))],
    )


def acquire_surface_target_runtime_mutation_fences(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    surface_target_keys: Iterable[str],
) -> None:
    """Serialize restrictive audience/account mutations with paid dispatch.

    Exact target keys are server-derived identifiers such as
    ``widget:<uuid>`` or ``whatsapp:<connection>:<binding>``. Multiple keys
    are acquired lexically in one statement to avoid lock-order inversions.
    """

    targets = tuple(sorted({_normalize_target_key(key) for key in surface_target_keys}))
    if not targets:
        raise ValueError("At least one exact surface target key is required.")
    _execute_lock_statement(
        db,
        [
            (
                "exclusive",
                _fence_key(f"surface:{workspace_id}:{target}"),
            )
            for target in targets
        ],
    )


def _execute_lock_statement(db: Session, locks: list[tuple[str, int]]) -> None:
    if not locks:
        return
    params: dict[str, int] = {}
    ctes: list[str] = []
    previous = ""
    for index, (mode, key) in enumerate(locks):
        fn = (
            "pg_advisory_xact_lock_shared"
            if mode == "shared"
            else "pg_advisory_xact_lock"
        )
        name = f"lock_{index}"
        params[f"key_{index}"] = key
        dependency = f" FROM {previous}" if previous else ""
        ctes.append(
            f"{name} AS MATERIALIZED "
            f"(SELECT {fn}(:key_{index}) AS acquired{dependency})"
        )
        previous = name
    statement = "WITH " + ", ".join(ctes) + f" SELECT 1 FROM {previous}"
    db.execute(text(statement), params)


def _normalize_slug(raw: str) -> str:
    slug = (raw or "").strip().lower()
    if not slug:
        raise ValueError("App slug is required.")
    return slug


def _normalize_target_key(raw: str) -> str:
    key = (raw or "").strip().lower()
    if not key or len(key) > 512 or any(ch.isspace() for ch in key):
        raise ValueError("A bounded exact surface target key is required.")
    return key


def _fence_key(value: str) -> int:
    digest = hashlib.blake2b(
        value.encode("utf-8"), digest_size=8, person=b"geemapp"
    ).digest()
    return int.from_bytes(digest, "big", signed=True)
