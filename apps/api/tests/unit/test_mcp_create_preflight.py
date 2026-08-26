"""Creation must resolve-policy-check every MCP target before persistence."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import app.db.models  # noqa: F401 - register isolated SQLAlchemy relationships
import app.mcp.services as services_module
from app.core.errors import AppError, ErrorCategory
from app.mcp.gateway import McpTargetValidationResult
from app.mcp.schemas import McpServerCreateIn
from app.mcp.services import McpServerService


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def add(self, row: object) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class _SessionFactory:
    def __init__(self) -> None:
        self.sessions: list[_Session] = []

    def __call__(self) -> _Session:
        session = _Session()
        self.sessions.append(session)
        return session


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        is_local=False,
        mcp_allow_private_egress=False,
        mcp_egress_total_timeout_seconds=10.0,
    )


def _body() -> McpServerCreateIn:
    return McpServerCreateIn.model_validate(
        {
            "display_name": "Tenant tools",
            "server_url": "https://tenant-tools.example.com/mcp",
            "auth": {"mode": "none"},
        }
    )


def test_dns_private_preflight_failure_cannot_persist_a_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _SessionFactory()
    requests: list[object] = []

    class BlockingGateway:
        def validate_target(self, request):
            requests.append(request)
            raise AppError(
                ErrorCategory.EGRESS_TARGET_BLOCKED,
                "The outbound target is blocked by policy.",
            )

    monkeypatch.setattr(
        services_module,
        "_begin_paid_access",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        services_module,
        "_require_current_connect_actor",
        lambda *_args, **_kwargs: None,
    )
    service = McpServerService(
        object(),  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        session_factory=sessions,  # type: ignore[arg-type]
        gateway=BlockingGateway(),  # type: ignore[arg-type]
        oauth=object(),  # type: ignore[arg-type]
    )

    with pytest.raises(AppError) as raised:
        service.create_server(
            workspace_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            body=_body(),
        )

    assert raised.value.category == ErrorCategory.EGRESS_TARGET_BLOCKED
    assert len(requests) == 1
    # Only the committed admission session existed. The final insert
    # transaction is not opened until every target passes preflight.
    assert len(sessions.sessions) == 1
    assert sessions.sessions[0].commits == 1
    assert sessions.sessions[0].added == []
    assert sessions.sessions[0].closed is True


def test_actor_permission_is_rechecked_after_dns_preflight_before_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _SessionFactory()
    actor_checks = 0

    class AllowedGateway:
        @staticmethod
        def validate_target(_request):
            return McpTargetValidationResult(origin_digest="a" * 64)

    monkeypatch.setattr(
        services_module,
        "_begin_paid_access",
        lambda *_args, **_kwargs: object(),
    )

    def check_actor(*_args, **_kwargs) -> None:
        nonlocal actor_checks
        actor_checks += 1
        if actor_checks == 2:
            raise AppError(
                ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
                "Current Workspace App connection permission is required.",
            )

    monkeypatch.setattr(
        services_module,
        "_require_current_connect_actor",
        check_actor,
    )
    service = McpServerService(
        object(),  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        session_factory=sessions,  # type: ignore[arg-type]
        gateway=AllowedGateway(),  # type: ignore[arg-type]
        oauth=object(),  # type: ignore[arg-type]
    )

    with pytest.raises(AppError) as raised:
        service.create_server(
            workspace_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            body=_body(),
        )

    assert raised.value.category == ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE
    assert actor_checks == 2
    assert len(sessions.sessions) == 2
    assert sessions.sessions[0].commits == 1
    assert sessions.sessions[1].rollbacks == 1
    assert all(session.added == [] for session in sessions.sessions)
    assert all(session.closed for session in sessions.sessions)


def test_all_target_preflights_share_one_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    requests: list[object] = []

    class AdvancingGateway:
        @staticmethod
        def validate_target(request):
            requests.append(request)
            clock[0] += 6.0
            return McpTargetValidationResult(origin_digest="a" * 64)

    monkeypatch.setattr(services_module.time, "monotonic", lambda: clock[0])
    service = McpServerService(
        object(),  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        session_factory=_SessionFactory(),  # type: ignore[arg-type]
        gateway=AdvancingGateway(),  # type: ignore[arg-type]
        oauth=object(),  # type: ignore[arg-type]
    )

    with pytest.raises(AppError) as raised:
        service._preflight_targets(
            workspace_id=uuid.uuid4(),
            connection_id=uuid.uuid4(),
            targets=(
                "https://server.example.com/mcp",
                "https://resource.example.com/",
                "https://issuer.example.com/",
            ),
        )

    assert raised.value.category == ErrorCategory.MCP_SERVER_UNREACHABLE
    assert len(requests) == 2
    assert [request.deadline_seconds for request in requests] == [10.0, 4.0]
