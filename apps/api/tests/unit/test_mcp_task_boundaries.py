"""MCP Celery boundaries must never serialize or traceback-log tenant data."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

import app.db.models  # noqa: F401 - register isolated SQLAlchemy relationships
import app.mcp.delivery as delivery_module
import app.mcp.resume as resume_module
import app.widgets.service as widget_service_module
import app.worker.tasks as tasks


class _ClosableDb:
    def close(self) -> None:
        pass


def _serialized_result(result) -> str:
    assert result.successful()
    return json.dumps(result.result, default=str)


def test_widget_task_exception_is_redacted_from_log_and_result_backend(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    receipt_id = uuid.uuid4()
    secret = "visitor-text-and-tool-result-must-not-leak"

    class ExplodingWidgetService:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def execute_mcp_turn_receipt(_receipt_id):
            raise RuntimeError(secret)

    monkeypatch.setattr(tasks, "SessionLocal", _ClosableDb)
    monkeypatch.setattr(widget_service_module, "WidgetService", ExplodingWidgetService)

    outcome = tasks.run_mcp_widget_turn_receipt.apply(args=[str(receipt_id)])
    encoded = _serialized_result(outcome)

    assert outcome.result["status"] == "failed"
    assert outcome.result["receipt_id"] == str(receipt_id)
    assert secret not in encoded
    assert secret not in caplog.text
    assert "Traceback" not in caplog.text


def test_invalid_id_payload_is_not_reflected_by_task_boundary(
    caplog: pytest.LogCaptureFixture,
) -> None:
    hostile = "https://tenant.example/mcp?client_secret=must-not-leak"

    outcome = tasks.run_mcp_widget_turn_receipt.apply(args=[hostile])
    encoded = _serialized_result(outcome)

    assert outcome.result["status"] == "failed"
    assert "receipt_id" not in outcome.result
    assert hostile not in encoded
    assert hostile not in caplog.text


def test_ambiguous_resume_and_delivery_failures_keep_safe_terminal_statuses(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pending_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    secret = "decrypted-arguments-provider-body-must-not-leak"

    monkeypatch.setattr(
        tasks,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    resumed = tasks.resume_mcp_pending_tool_call.apply(args=[str(pending_id)])

    class ExplodingDeliveryService:
        @staticmethod
        def deliver(_delivery_id):
            raise RuntimeError(secret)

    monkeypatch.setattr(
        delivery_module,
        "McpWhatsAppDeliveryService",
        ExplodingDeliveryService,
    )
    delivered = tasks.deliver_mcp_surface_segment.apply(args=[str(delivery_id)])

    resumed_encoded = _serialized_result(resumed)
    delivered_encoded = _serialized_result(delivered)
    assert resumed.result["status"] == "outcome_unknown"
    assert delivered.result["status"] == "delivery_unknown"
    assert secret not in resumed_encoded + delivered_encoded + caplog.text
    assert "Traceback" not in caplog.text


def test_successful_task_results_are_allowlisted_before_backend_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    secret = "raw-provider-id-or-decrypted-result-must-not-leak"

    class ResumeService:
        def __init__(self, _db) -> None:
            pass

        @staticmethod
        def resume(_pending_id):
            return {
                "status": "executed",
                "deliveries": 1,
                "arguments": secret,
                "raw_result": secret,
            }

    class DeliveryService:
        @staticmethod
        def deliver(_delivery_id):
            return {
                "status": "sent",
                "delivery_id": str(delivery_id),
                "provider_message_id": secret,
            }

    monkeypatch.setattr(tasks, "SessionLocal", _ClosableDb)
    monkeypatch.setattr(resume_module, "McpPendingResumeService", ResumeService)
    monkeypatch.setattr(delivery_module, "McpWhatsAppDeliveryService", DeliveryService)

    resumed = tasks.resume_mcp_pending_tool_call.apply(args=[str(pending_id)])
    delivered = tasks.deliver_mcp_surface_segment.apply(args=[str(delivery_id)])

    combined = _serialized_result(resumed) + _serialized_result(delivered)
    assert resumed.result["status"] == "executed"
    assert resumed.result["deliveries"] == 1
    assert delivered.result["status"] == "sent"
    assert secret not in combined
    assert "arguments" not in resumed.result
    assert "raw_result" not in resumed.result
    assert "provider_message_id" not in delivered.result


def test_mcp_paths_cannot_reintroduce_traceback_logging() -> None:
    api_root = Path(__file__).resolve().parents[2]
    for path in (api_root / "app" / "mcp").glob("*.py"):
        assert "logger.exception" not in path.read_text(), path
        assert "exc_info=True" not in path.read_text(), path

    widget_source = (api_root / "app" / "widgets" / "service.py").read_text()
    assert "logger.exception" not in widget_source
    assert "exc_info=True" not in widget_source

    worker_source = (api_root / "app" / "worker" / "tasks.py").read_text()
    mcp_task_source = worker_source.split(
        '@celery_app.task(name="run_mcp_widget_turn_receipt"',
        1,
    )[1]
    assert "logger.exception" not in mcp_task_source
    assert "exc_info=True" not in mcp_task_source
    for name in (
        "run_mcp_widget_turn_receipt",
        "recover_mcp_widget_turn_receipts",
        "discover_mcp_connection",
        "poll_mcp_connections",
        "resume_mcp_pending_tool_call",
        "recover_mcp_approval_state",
        "deliver_mcp_surface_segment",
        "recover_mcp_surface_deliveries",
    ):
        task_marker = f'def {name}('
        decorator_marker = "@_mcp_task_boundary("
        before = mcp_task_source.split(task_marker, 1)[0]
        assert decorator_marker in before.rsplit("@celery_app.task", 1)[-1]
