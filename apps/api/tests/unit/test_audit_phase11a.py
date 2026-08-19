"""Phase 11A — audit sanitizer, writer, and transaction semantics."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import AuditAction, AuditEntityType, AuditLog, record_audit, sanitize_audit_metadata
from app.audit.sanitize import BLOCKED_METADATA_KEYS
from app.workspaces.service import WorkspaceService


def test_sanitizer_strips_secrets_and_honors_allowlist() -> None:
    dirty = {
        "password": "secret",
        "refresh_token": "rrr",
        "access_token": "aaa",
        "invitation_token": "inv",
        "api_key": "geem_sk_live",
        "credentials_encrypted": "blob",
        "clickpay_server_key": "sk",
        "authorization": "Bearer x",
        "cookie": "sid=1",
        "role_id": str(uuid.uuid4()),
        "nested": {"password_hash": "x", "ok": 1},
    }
    cleaned = sanitize_audit_metadata(dirty)
    for key in (
        "password",
        "refresh_token",
        "access_token",
        "invitation_token",
        "api_key",
        "credentials_encrypted",
        "clickpay_server_key",
        "authorization",
        "cookie",
    ):
        assert key not in cleaned
    allowed = sanitize_audit_metadata(dirty, allowlist=frozenset({"role_id"}))
    assert set(allowed) == {"role_id"}
    assert "password" in BLOCKED_METADATA_KEYS


def test_record_audit_persists_sanitized_row(db: Session, register_user) -> None:
    user = register_user(email="audit-write@example.com")
    actor_id = uuid.UUID(user["user"]["id"])
    ws, _ = WorkspaceService(db).create_workspace(
        name="Audit WS", slug="audit-ws-write", created_by=actor_id
    )
    record_audit(
        db,
        action=AuditAction.API_KEY_CREATED,
        entity_type=AuditEntityType.API_KEY,
        entity_id=uuid.uuid4(),
        workspace_id=ws.id,
        actor_user_id=actor_id,
        metadata={"plaintext": "geem_sk_should_not_land", "prefix": "geem_sk_abcd"},
        allowlist=frozenset({"prefix", "plaintext"}),
    )
    db.commit()
    row = db.scalar(
        select(AuditLog).where(AuditLog.action == AuditAction.API_KEY_CREATED.value)
    )
    assert row is not None
    assert row.workspace_id == ws.id
    assert row.actor_user_id == actor_id
    assert row.extra.get("prefix") == "geem_sk_abcd"
    assert "plaintext" not in row.extra
    assert "geem_sk_should_not_land" not in str(row.extra)


def test_rollback_does_not_leave_success_audit(db: Session, register_user) -> None:
    user = register_user(email="audit-tx@example.com")
    actor_id = uuid.UUID(user["user"]["id"])
    ws, _ = WorkspaceService(db).create_workspace(
        name="Audit TX", slug="audit-ws-tx", created_by=actor_id
    )
    before = len(list(db.scalars(select(AuditLog))))
    record_audit(
        db,
        action=AuditAction.MEMBER_REMOVED,
        entity_type=AuditEntityType.MEMBERSHIP,
        entity_id=uuid.uuid4(),
        workspace_id=ws.id,
        actor_user_id=actor_id,
    )
    db.rollback()
    assert len(list(db.scalars(select(AuditLog)))) == before


def test_required_audit_flush_failure_does_not_poison_session(db: Session, register_user) -> None:
    from app.audit.service import AuditPersistenceError

    user = register_user(email="audit-poison@example.com")
    actor_id = uuid.UUID(user["user"]["id"])
    ws, _ = WorkspaceService(db).create_workspace(
        name="Audit poison", slug="audit-ws-poison", created_by=actor_id
    )
    try:
        record_audit(
            db,
            action=AuditAction.API_KEY_CREATED,
            entity_type=AuditEntityType.API_KEY,
            entity_id=uuid.uuid4(),
            workspace_id=ws.id,
            actor_user_id=actor_id,
            actor_api_key_id=uuid.uuid4(),
            required=True,
        )
        raise AssertionError("expected AuditPersistenceError")
    except AuditPersistenceError:
        pass

    record_audit(
        db,
        action=AuditAction.API_KEY_REVOKED,
        entity_type=AuditEntityType.API_KEY,
        entity_id=uuid.uuid4(),
        workspace_id=ws.id,
        actor_user_id=actor_id,
        required=True,
    )
    db.commit()
    row = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.API_KEY_REVOKED.value))
    assert row is not None
    assert row.workspace_id == ws.id


def test_workspace_create_writes_audit(db: Session, register_user) -> None:
    user = register_user(email="audit-ws-create@example.com")
    actor_id = uuid.UUID(user["user"]["id"])
    ws, _ = WorkspaceService(db).create_workspace(
        name="Audited", slug="audited-create", created_by=actor_id
    )
    row = db.scalar(
        select(AuditLog).where(
            AuditLog.action == AuditAction.WORKSPACE_CREATED.value,
            AuditLog.entity_id == ws.id,
        )
    )
    assert row is not None
    assert row.actor_user_id == actor_id
    assert row.workspace_id == ws.id
    assert "password" not in (row.extra or {})
