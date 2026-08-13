"""Phase 5C — Workspace Expert allowance + storage quota enforcement."""

from __future__ import annotations

import io
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.billing.service import PlanService, SubscriptionService
from app.core.errors import AppError, ErrorCategory
from app.documents.service import DocumentService
from app.entitlements.cache import invalidate_entitlements
from app.entitlements.keys import EntitlementKey
from app.experts.geem_general import ensure_geem_general_expert
from app.experts.membership_sync import ExpertVectorMembershipSynchronizer
from app.experts.models import ExpertStatus, ExpertType, ExpertVisibility
from app.experts.service import ExpertService
from app.identity.models import PlatformRole, User
from app.identity.repository import UserRepository
from app.usage.ai_usage import AiUsageService
from app.usage.metrics import StorageReservationStatus, StorageUsageReason, UsageMetric
from app.usage.models import StorageReservation, WorkspaceResourceUsage
from app.usage.repository import StorageUsageRepository
from app.usage.storage import StorageQuotaService
from app.workspaces.models import Workspace
from app.workspaces.repository import MembershipRepository
from app.workspaces.service import WorkspaceService
from tests.conftest import TestingSessionLocal


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def _create_workspace(client, token: str, name: str, slug: str) -> dict:
    res = client.post(
        "/api/workspaces",
        headers=_auth(token),
        json={"name": name, "slug": slug},
    )
    assert res.status_code in {200, 201}, res.text
    return res.json()


def _ws_headers(token: str, workspace: dict) -> dict[str, str]:
    return _auth(token, **{"X-Workspace-Id": workspace["id"]})


def _unique_pdf(marker: bytes | str | None = None) -> bytes:
    raw = marker.encode() if isinstance(marker, str) else (marker or uuid.uuid4().bytes)
    seed = int.from_bytes(raw[:4].ljust(4, b"\0"), "big")
    writer = PdfWriter()
    writer.add_blank_page(width=100 + (seed % 80), height=100 + ((seed // 80) % 80))
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _create_plan(db: Session, *, code: str, experts: int, storage: int, tokens: int = 100_000):
    return PlanService(db).create_plan(
        code=code,
        name=f"Test {code}",
        description="Test-only plan — not Geem product pricing.",
        entitlements={
            EntitlementKey.AI_TOKENS_DAILY.value: tokens,
            EntitlementKey.AI_TOKENS_WEEKLY.value: tokens,
            EntitlementKey.AI_TOKENS_MONTHLY.value: tokens,
            EntitlementKey.EXPERTS_LIMIT.value: experts,
            EntitlementKey.STORAGE_BYTES.value: storage,
        },
        extra={"kind": "test", "commercial": False},
    )


def _assign_plan(db: Session, workspace_id: uuid.UUID, plan_id: uuid.UUID) -> None:
    SubscriptionService(db).assign_plan(workspace_id, plan_id)
    db.commit()
    invalidate_entitlements(workspace_id)


def _promote_platform_admin(db, user_id: str) -> User:
    user = UserRepository(db).get_by_id(uuid.UUID(user_id))
    assert user is not None
    user.platform_role = PlatformRole.ADMIN.value
    db.commit()
    db.refresh(user)
    return user


def _upload(client, headers: dict[str, str], data: bytes, filename: str = "doc.pdf"):
    return client.post(
        "/api/documents",
        headers=headers,
        files={"file": (filename, data, "application/pdf")},
    )


def _summary(client, headers: dict[str, str]) -> dict:
    res = client.get("/api/usage/summary", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _reserved_bytes(db: Session, workspace_id: uuid.UUID) -> int:
    row = db.query(WorkspaceResourceUsage).filter_by(
        workspace_id=workspace_id, metric=UsageMetric.STORAGE_BYTES.value
    ).one_or_none()
    return int(row.reserved_bytes) if row is not None else 0


@pytest.fixture()
def mock_storage_and_ingest():
    with (
        patch("app.documents.service.MinioObjectStorage") as storage_cls,
        patch("app.api.documents.enqueue_ingest", return_value="task-id"),
        patch("app.experts.service._enqueue_ingest", return_value="task-id"),
        patch("app.platform_admin.router.enqueue_ingest", return_value="task-id"),
    ):
        storage = MagicMock()
        storage.get_document_bytes.return_value = (
            b"%PDF-1.4 mock",
            "workspaces/x/documents/y/original.pdf",
        )

        def _put(**kw):
            from app.storage.document_keys import resolve_document_storage_key

            return resolve_document_storage_key(kw["document_id"], kw.get("workspace_id"))

        storage.put_document_bytes.side_effect = _put
        storage_cls.return_value = storage
        yield storage


# ---------------------------------------------------------------------------
# Experts 1–7
# ---------------------------------------------------------------------------


def test_1_expert_below_limit_succeeds(client, register_user, db) -> None:
    user = register_user(email="5c-e1@example.com")
    ws = _create_workspace(client, user["access_token"], "E1", "p5c-e1")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_plan(db, code="p5c_e1", experts=2, storage=10_000_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    res = client.post("/api/experts", headers=headers, json={"name": "Alpha"})
    assert res.status_code == 201, res.text
    body = _summary(client, headers)
    assert body["experts"]["limit"] == 2
    assert body["experts"]["used"] == 1
    assert body["experts"]["remaining"] == 1


def test_2_expert_at_limit_blocked(client, register_user, db) -> None:
    user = register_user(email="5c-e2@example.com")
    ws = _create_workspace(client, user["access_token"], "E2", "p5c-e2")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_plan(db, code="p5c_e2", experts=1, storage=10_000_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    assert client.post("/api/experts", headers=headers, json={"name": "One"}).status_code == 201
    res = client.post("/api/experts", headers=headers, json={"name": "Two"})
    assert res.status_code == 429, res.text
    body = res.json()
    assert body["code"] == ErrorCategory.EXPERT_LIMIT_REACHED.value
    assert body["metric"] == EntitlementKey.EXPERTS_LIMIT.value
    assert body["limit"] == 1
    assert body["used"] == 1
    assert body["remaining"] == 0
    assert "message" in body
    listed = client.get("/api/experts", headers=headers).json()
    owned = [e for e in listed if e["type"] == ExpertType.WORKSPACE.value]
    assert len(owned) == 1


def test_3_platform_experts_not_counted(client, register_user, db) -> None:
    admin_body = register_user(email="5c-e3-admin@example.com")
    admin = _promote_platform_admin(db, admin_body["user"]["id"])
    user = register_user(email="5c-e3@example.com")
    ws = _create_workspace(client, user["access_token"], "E3", "p5c-e3")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_plan(db, code="p5c_e3", experts=1, storage=10_000_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    svc = ExpertService(db)
    platform = svc.create_platform_expert(
        actor=admin,
        name="Platform One",
        visibility=ExpertVisibility.PLATFORM_PUBLISHED.value,
        status=ExpertStatus.READY.value,
    )
    svc.grant_platform_expert(actor=admin, expert_id=platform.id, workspace_id=uuid.UUID(ws["id"]))

    body = _summary(client, headers)
    assert body["experts"]["used"] == 0
    res = client.post("/api/experts", headers=headers, json={"name": "Tenant"})
    assert res.status_code == 201, res.text
    blocked = client.post("/api/experts", headers=headers, json={"name": "Overflow"})
    assert blocked.status_code == 429
    assert _summary(client, headers)["experts"]["used"] == 1


def test_4_general_expert_not_counted(client, register_user, db) -> None:
    user = register_user(email="5c-e4@example.com")
    ws = _create_workspace(client, user["access_token"], "E4", "p5c-e4")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_plan(db, code="p5c_e4", experts=1, storage=10_000_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)
    ensure_geem_general_expert(db)

    listed = client.get("/api/experts", headers=headers).json()
    assert any(e.get("knowledge_mode") == "general" for e in listed)
    assert _summary(client, headers)["experts"]["used"] == 0
    assert client.post("/api/experts", headers=headers, json={"name": "Only"}).status_code == 201
    assert client.post("/api/experts", headers=headers, json={"name": "No"}).status_code == 429


def test_5_deleted_workspace_expert_not_counted(client, register_user, db) -> None:
    user = register_user(email="5c-e5@example.com")
    ws = _create_workspace(client, user["access_token"], "E5", "p5c-e5")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_plan(db, code="p5c_e5", experts=1, storage=10_000_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    created = client.post("/api/experts", headers=headers, json={"name": "Temp"})
    assert created.status_code == 201
    expert_id = created.json()["id"]
    assert client.delete(f"/api/experts/{expert_id}", headers=headers).status_code == 204
    assert _summary(client, headers)["experts"]["used"] == 0
    assert client.post("/api/experts", headers=headers, json={"name": "Next"}).status_code == 201


def test_5b_restore_expert_rechecks_quota(client, register_user, db) -> None:
    user = register_user(email="5c-e5b@example.com")
    ws = _create_workspace(client, user["access_token"], "E5b", "p5c-e5b")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_plan(db, code="p5c_e5b", experts=1, storage=10_000_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    first = client.post("/api/experts", headers=headers, json={"name": "Gone"})
    expert_id = uuid.UUID(first.json()["id"])
    assert client.delete(f"/api/experts/{expert_id}", headers=headers).status_code == 204
    assert client.post("/api/experts", headers=headers, json={"name": "Fills"}).status_code == 201

    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    membership = MembershipRepository(db).get(workspace.id, uuid.UUID(user["user"]["id"]))
    actor = UserRepository(db).get_by_id(uuid.UUID(user["user"]["id"]))
    with pytest.raises(AppError) as exc:
        ExpertService(db).restore_workspace_expert(
            workspace=workspace,
            membership=membership,
            actor=actor,
            expert_id=expert_id,
        )
    assert exc.value.category == ErrorCategory.EXPERT_LIMIT_REACHED


def test_5c_restore_expert_resyncs_vector_membership(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-e5c@example.com")
    ws = _create_workspace(client, user["access_token"], "E5c", "p5c-e5c")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_plan(db, code="p5c_e5c", experts=2, storage=10_000_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    expert = client.post("/api/experts", headers=headers, json={"name": "Synced"}).json()
    pdf = _unique_pdf(b"e5c")
    uploaded = _upload(client, headers, pdf, "e5c.pdf")
    doc_id = uuid.UUID(uploaded.json()["id"])
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    membership = MembershipRepository(db).get(workspace.id, uuid.UUID(user["user"]["id"]))
    actor = UserRepository(db).get_by_id(uuid.UUID(user["user"]["id"]))
    svc = ExpertService(db)
    svc.link_document(
        workspace=workspace,
        membership=membership,
        actor=actor,
        expert_id=uuid.UUID(expert["id"]),
        document_id=doc_id,
    )
    assert client.delete(f"/api/experts/{expert['id']}", headers=headers).status_code == 204

    synced: list[str] = []

    def _fake_sync(document_id):
        synced.append(str(document_id))
        return [str(document_id)]

    with patch.object(ExpertVectorMembershipSynchronizer, "sync_document", side_effect=_fake_sync):
        restored = svc.restore_workspace_expert(
            workspace=workspace,
            membership=membership,
            actor=actor,
            expert_id=uuid.UUID(expert["id"]),
        )
    assert restored.deleted_at is None
    assert str(doc_id) in synced
    assert _summary(client, headers)["experts"]["used"] == 1


def test_6_concurrent_last_slot_exactly_one_succeeds(client, register_user, db) -> None:
    user = register_user(email="5c-e6@example.com")
    ws = _create_workspace(client, user["access_token"], "E6", "p5c-e6")
    headers = _ws_headers(user["access_token"], ws)
    plan = _create_plan(db, code="p5c_e6", experts=1, storage=10_000_000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)
    workspace_id = uuid.UUID(ws["id"])
    user_id = uuid.UUID(user["user"]["id"])

    barrier = threading.Barrier(2, timeout=10)
    results: list[tuple[str, Any]] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        session = TestingSessionLocal()
        try:
            workspace = session.get(Workspace, workspace_id)
            membership = MembershipRepository(session).get(workspace_id, user_id)
            actor = session.get(User, user_id)
            barrier.wait()
            try:
                ExpertService(session).create_workspace_expert(
                    workspace=workspace,
                    membership=membership,
                    actor=actor,
                    name=f"Race {i}",
                )
                with lock:
                    results.append(("ok", i))
            except AppError as exc:
                session.rollback()
                with lock:
                    results.append(("fail", exc.category))
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()

    oks = [r for r in results if r[0] == "ok"]
    fails = [r for r in results if r[0] == "fail"]
    assert len(oks) == 1, results
    assert len(fails) == 1
    assert fails[0][1] == ErrorCategory.EXPERT_LIMIT_REACHED
    db.expire_all()
    assert _summary(client, headers)["experts"]["used"] == 1


def test_7_expert_quota_workspace_isolation(client, register_user, db) -> None:
    user_a = register_user(email="5c-e7a@example.com")
    user_b = register_user(email="5c-e7b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "E7A", "p5c-e7a")
    ws_b = _create_workspace(client, user_b["access_token"], "E7B", "p5c-e7b")
    plan = _create_plan(db, code="p5c_e7", experts=1, storage=10_000_000)
    _assign_plan(db, uuid.UUID(ws_a["id"]), plan.id)
    _assign_plan(db, uuid.UUID(ws_b["id"]), plan.id)

    ha = _ws_headers(user_a["access_token"], ws_a)
    hb = _ws_headers(user_b["access_token"], ws_b)
    assert client.post("/api/experts", headers=ha, json={"name": "A"}).status_code == 201
    assert client.post("/api/experts", headers=ha, json={"name": "A2"}).status_code == 429
    assert client.post("/api/experts", headers=hb, json={"name": "B"}).status_code == 201
    err = client.post("/api/experts", headers=ha, json={"name": "A3"}).json()
    assert err["used"] == 1
    assert _summary(client, hb)["experts"]["used"] == 1


# ---------------------------------------------------------------------------
# Storage 8–16
# ---------------------------------------------------------------------------


def test_8_upload_below_quota_succeeds(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-s8@example.com")
    ws = _create_workspace(client, user["access_token"], "S8", "p5c-s8")
    headers = _ws_headers(user["access_token"], ws)
    pdf = _unique_pdf(b"s8")
    plan = _create_plan(db, code="p5c_s8", experts=10, storage=len(pdf) + 100)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    res = _upload(client, headers, pdf, "s8.pdf")
    assert res.status_code in {200, 201}, res.text
    body = _summary(client, headers)
    assert body["storage"]["used_bytes"] == len(pdf)
    assert body["storage"]["limit_bytes"] == len(pdf) + 100
    assert body["storage"]["remaining_bytes"] == 100
    assert body["storage_bytes"]["used"] == len(pdf)
    assert body["storage"]["percentage"] > 0
    assert _reserved_bytes(db, uuid.UUID(ws["id"])) == 0


def test_9_upload_exceeding_quota_blocked(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-s9@example.com")
    ws = _create_workspace(client, user["access_token"], "S9", "p5c-s9")
    headers = _ws_headers(user["access_token"], ws)
    pdf = _unique_pdf(b"s9")
    plan = _create_plan(db, code="p5c_s9", experts=10, storage=max(1, len(pdf) - 10))
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    res = _upload(client, headers, pdf, "s9.pdf")
    assert res.status_code == 429, res.text
    body = res.json()
    assert body["code"] == ErrorCategory.STORAGE_QUOTA_EXCEEDED.value
    assert body["metric"] == EntitlementKey.STORAGE_BYTES.value
    assert body["limit"] == max(1, len(pdf) - 10)
    assert body["used"] == 0
    assert body["remaining"] == body["limit"]
    assert _summary(client, headers)["storage"]["used_bytes"] == 0
    assert client.get("/api/documents", headers=headers).json() == []


def test_10_same_workspace_hash_reuse_does_not_double_charge(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-s10@example.com")
    ws = _create_workspace(client, user["access_token"], "S10", "p5c-s10")
    headers = _ws_headers(user["access_token"], ws)
    pdf = _unique_pdf(b"s10")
    plan = _create_plan(db, code="p5c_s10", experts=10, storage=len(pdf) + 50)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    e1 = client.post("/api/experts", headers=headers, json={"name": "EA"}).json()
    e2 = client.post("/api/experts", headers=headers, json={"name": "EB"}).json()
    first = client.post(
        f"/api/experts/{e1['id']}/upload",
        headers=headers,
        files={"file": ("same.pdf", pdf, "application/pdf")},
    )
    assert first.status_code == 201, first.text
    assert first.json()["reused"] is False
    second = client.post(
        f"/api/experts/{e2['id']}/upload",
        headers=headers,
        files={"file": ("same.pdf", pdf, "application/pdf")},
    )
    assert second.status_code == 201, second.text
    assert second.json()["reused"] is True
    assert second.json()["document_id"] == first.json()["document_id"]
    assert _summary(client, headers)["storage"]["used_bytes"] == len(pdf)


def test_11_linking_one_document_to_multiple_experts_does_not_double_charge(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-s11@example.com")
    ws = _create_workspace(client, user["access_token"], "S11", "p5c-s11")
    headers = _ws_headers(user["access_token"], ws)
    pdf = _unique_pdf(b"s11")
    plan = _create_plan(db, code="p5c_s11", experts=10, storage=len(pdf) + 50)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    uploaded = _upload(client, headers, pdf, "shared.pdf")
    doc_id = uploaded.json()["id"]
    e1 = client.post("/api/experts", headers=headers, json={"name": "L1"}).json()
    e2 = client.post("/api/experts", headers=headers, json={"name": "L2"}).json()
    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    membership = MembershipRepository(db).get(workspace.id, uuid.UUID(user["user"]["id"]))
    actor = UserRepository(db).get_by_id(uuid.UUID(user["user"]["id"]))
    svc = ExpertService(db)
    svc.link_document(
        workspace=workspace,
        membership=membership,
        actor=actor,
        expert_id=uuid.UUID(e1["id"]),
        document_id=uuid.UUID(doc_id),
    )
    svc.link_document(
        workspace=workspace,
        membership=membership,
        actor=actor,
        expert_id=uuid.UUID(e2["id"]),
        document_id=uuid.UUID(doc_id),
    )
    assert _summary(client, headers)["storage"]["used_bytes"] == len(pdf)


def test_12_platform_knowledge_does_not_count(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    admin_body = register_user(email="5c-s12-admin@example.com")
    admin = _promote_platform_admin(db, admin_body["user"]["id"])
    user = register_user(email="5c-s12@example.com")
    ws = _create_workspace(client, user["access_token"], "S12", "p5c-s12")
    headers = _ws_headers(user["access_token"], ws)
    pdf = _unique_pdf(b"s12pk")
    plan = _create_plan(db, code="p5c_s12", experts=10, storage=100)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)
    WorkspaceService(db).ensure_platform_knowledge_workspace()

    ExpertService(db).upload_platform_knowledge_document(
        actor=admin, file_bytes=pdf, filename="pk.pdf"
    )
    body = _summary(client, headers)
    assert body["storage"]["used_bytes"] == 0
    tenant_pdf = _unique_pdf(b"s12t")
    blocked = _upload(client, headers, tenant_pdf, "tenant.pdf")
    assert blocked.status_code == 429


def test_13_failed_upload_releases_reservation(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-s13@example.com")
    ws = _create_workspace(client, user["access_token"], "S13", "p5c-s13")
    headers = _ws_headers(user["access_token"], ws)
    pdf = _unique_pdf(b"s13")
    plan = _create_plan(db, code="p5c_s13", experts=10, storage=len(pdf) + 1000)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)
    workspace_id = uuid.UUID(ws["id"])

    mock_storage_and_ingest.put_document_bytes.side_effect = RuntimeError("minio down")
    with pytest.raises(RuntimeError, match="minio down"):
        DocumentService(db).upload_for_workspace(
            db.get(Workspace, workspace_id), pdf, "fail.pdf"
        )

    db.expire_all()
    assert _reserved_bytes(db, workspace_id) == 0
    assert _summary(client, headers)["storage"]["used_bytes"] == 0
    assert client.get("/api/documents", headers=headers).json() == []
    rows = db.query(StorageReservation).filter_by(workspace_id=workspace_id).all()
    assert all(r.status != StorageReservationStatus.RESERVED.value for r in rows)


def test_13b_stale_reservation_heal_survives_quota_exceeded(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-s13b@example.com")
    ws = _create_workspace(client, user["access_token"], "S13b", "p5c-s13b")
    headers = _ws_headers(user["access_token"], ws)
    pdf = _unique_pdf(b"s13b")
    plan = _create_plan(db, code="p5c_s13b", experts=10, storage=100)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)
    workspace_id = uuid.UUID(ws["id"])

    stale = StorageReservation(
        workspace_id=workspace_id,
        request_id="stale-hold",
        byte_size=40,
        status=StorageReservationStatus.RESERVED.value,
    )
    counter = WorkspaceResourceUsage(
        workspace_id=workspace_id,
        metric=UsageMetric.STORAGE_BYTES.value,
        reserved_bytes=40,
    )
    db.add(stale)
    db.add(counter)
    db.commit()
    stale.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    res = _upload(client, headers, pdf, "too-big.pdf")
    assert res.status_code == 429, res.text
    db.expire_all()
    healed = db.query(StorageReservation).filter_by(request_id="stale-hold").one()
    assert healed.status == StorageReservationStatus.RELEASED.value
    assert _reserved_bytes(db, workspace_id) == 0


def test_14_delete_updates_billable_storage(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-s14@example.com")
    ws = _create_workspace(client, user["access_token"], "S14", "p5c-s14")
    headers = _ws_headers(user["access_token"], ws)
    pdf = _unique_pdf(b"s14")
    plan = _create_plan(db, code="p5c_s14", experts=10, storage=len(pdf))
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)

    uploaded = _upload(client, headers, pdf, "keep.pdf")
    doc_id = uploaded.json()["id"]
    assert _summary(client, headers)["storage"]["used_bytes"] == len(pdf)
    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == 200
    assert _summary(client, headers)["storage"]["used_bytes"] == 0
    events = StorageUsageRepository(db).list_for_workspace(uuid.UUID(ws["id"]))
    assert any(e.reason == StorageUsageReason.DELETE.value and e.delta_bytes == -len(pdf) for e in events)

    workspace = db.get(Workspace, uuid.UUID(ws["id"]))
    restored = DocumentService(db).restore_for_workspace(workspace, uuid.UUID(doc_id))
    assert restored.deleted_at is None
    assert _summary(client, headers)["storage"]["used_bytes"] == len(pdf)

    other = _unique_pdf(b"s14b")
    assert _upload(client, headers, other, "nope.pdf").status_code == 429

    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == 200
    assert _summary(client, headers)["storage"]["used_bytes"] == 0
    restored_again = DocumentService(db).restore_for_workspace(workspace, uuid.UUID(doc_id))
    assert restored_again.deleted_at is None
    assert _summary(client, headers)["storage"]["used_bytes"] == len(pdf)


def test_15_concurrent_uploads_cannot_exceed_quota(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-s15@example.com")
    ws = _create_workspace(client, user["access_token"], "S15", "p5c-s15")
    headers = _ws_headers(user["access_token"], ws)
    pdf_a = _unique_pdf(b"s15a")
    pdf_b = _unique_pdf(b"s15b")
    slot = max(len(pdf_a), len(pdf_b))
    plan = _create_plan(db, code="p5c_s15", experts=10, storage=slot)
    _assign_plan(db, uuid.UUID(ws["id"]), plan.id)
    workspace_id = uuid.UUID(ws["id"])

    barrier = threading.Barrier(2, timeout=10)
    results: list[tuple[str, Any]] = []
    lock = threading.Lock()

    def worker(name: str, data: bytes) -> None:
        session = TestingSessionLocal()
        try:
            workspace = session.get(Workspace, workspace_id)
            barrier.wait()
            try:
                DocumentService(session).upload_for_workspace(workspace, data, name)
                with lock:
                    results.append(("ok", name))
            except AppError as exc:
                session.rollback()
                with lock:
                    results.append(("fail", exc.category))
        finally:
            session.close()

    threads = [
        threading.Thread(target=worker, args=("a.pdf", pdf_a)),
        threading.Thread(target=worker, args=("b.pdf", pdf_b)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()

    oks = [r for r in results if r[0] == "ok"]
    fails = [r for r in results if r[0] == "fail"]
    assert len(oks) == 1, results
    assert len(fails) == 1
    assert fails[0][1] == ErrorCategory.STORAGE_QUOTA_EXCEEDED
    db.expire_all()
    used = _summary(client, headers)["storage"]["used_bytes"]
    assert used <= slot
    assert used in {len(pdf_a), len(pdf_b)}
    assert _reserved_bytes(db, workspace_id) == 0


def test_16_storage_quota_workspace_isolation(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user_a = register_user(email="5c-s16a@example.com")
    user_b = register_user(email="5c-s16b@example.com")
    ws_a = _create_workspace(client, user_a["access_token"], "S16A", "p5c-s16a")
    ws_b = _create_workspace(client, user_b["access_token"], "S16B", "p5c-s16b")
    pdf = _unique_pdf(b"s16")
    plan = _create_plan(db, code="p5c_s16", experts=10, storage=len(pdf))
    _assign_plan(db, uuid.UUID(ws_a["id"]), plan.id)
    _assign_plan(db, uuid.UUID(ws_b["id"]), plan.id)
    ha = _ws_headers(user_a["access_token"], ws_a)
    hb = _ws_headers(user_b["access_token"], ws_b)

    assert _upload(client, ha, pdf, "a.pdf").status_code in {200, 201}
    assert _upload(client, ha, _unique_pdf(b"s16x"), "a2.pdf").status_code == 429
    b_pdf = _unique_pdf(b"s16b")
    assert _upload(client, hb, b_pdf, "b.pdf").status_code in {200, 201}
    assert _summary(client, ha)["storage"]["used_bytes"] == len(pdf)
    assert _summary(client, hb)["storage"]["used_bytes"] == len(b_pdf)


# ---------------------------------------------------------------------------
# Regression 17–19
# ---------------------------------------------------------------------------


def test_17_phase3_expert_upload_still_works(
    client, register_user, db, mock_storage_and_ingest
) -> None:
    user = register_user(email="5c-r17@example.com")
    ws = _create_workspace(client, user["access_token"], "R17", "p5c-r17")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "RAG"}).json()
    pdf = _unique_pdf(b"r17")
    res = client.post(
        f"/api/experts/{expert['id']}/upload",
        headers=headers,
        files={"file": ("rag.pdf", pdf, "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["reused"] is False
    docs = client.get(f"/api/experts/{expert['id']}/documents", headers=headers)
    assert docs.status_code == 200, docs.text
    assert len(docs.json()) == 1


def test_18_phase4_chat_still_works(client, register_user, db) -> None:
    user = register_user(email="5c-r18@example.com")
    ws = _create_workspace(client, user["access_token"], "R18", "p5c-r18")
    headers = _ws_headers(user["access_token"], ws)
    expert = client.post("/api/experts", headers=headers, json={"name": "Chat"}).json()
    from app.experts.models import Expert

    row = db.get(Expert, uuid.UUID(expert["id"]))
    row.status = ExpertStatus.READY.value
    db.commit()
    conv = client.post(
        "/api/conversations", headers=headers, json={"expert_id": expert["id"]}
    )
    assert conv.status_code in {200, 201}, conv.text
    assert conv.json()["expert_id"] == expert["id"]


def test_19_phase5b_token_metering_still_works(client, register_user, db) -> None:
    user = register_user(email="5c-r19@example.com")
    ws = _create_workspace(client, user["access_token"], "R19", "p5c-r19")
    workspace_id = uuid.UUID(ws["id"])
    dto = AiUsageService(db).reserve_ai_usage(workspace_id, "p5c-r19", 10)
    db.commit()
    assert dto.status == "reserved"
    settled = AiUsageService(db).settle_ai_usage(workspace_id, "p5c-r19", 7)
    db.commit()
    assert settled.status == "settled"
    body = _summary(client, _ws_headers(user["access_token"], ws))
    assert body["ai_tokens"]["daily"]["used"] == 7
    assert body["experts"]["limit"] >= 1
    assert "storage" in body
    assert "limit_bytes" in body["storage"]
