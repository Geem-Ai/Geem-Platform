from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.conversations.schemas import (
    MessageOut,
    MessageToolActivityOut,
    MessageToolApprovalOut,
)
from app.conversations.service import ConversationService


def _message(**overrides: object) -> MessageOut:
    now = datetime.now(timezone.utc)
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "conversation_id": uuid.uuid4(),
        "role": "assistant",
        "content": "answer",
        "status": "completed",
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return MessageOut.model_validate(values)


def test_message_without_mcp_metadata_preserves_legacy_shape() -> None:
    payload = _message().model_dump(mode="json")

    assert "tool_activities" not in payload
    assert "tool_approval" not in payload


def test_message_includes_persisted_mcp_activity_and_approval() -> None:
    pending_id = uuid.uuid4()
    payload = _message(
        tool_activities=[
            MessageToolActivityOut(
                id=pending_id,
                tool_call_id="call-1",
                connection_name="CRM",
                tool_name="create_contact",
                status="approval_required",
            )
        ],
        tool_approval=MessageToolApprovalOut(
            id=pending_id,
            tool_call_id="call-1",
            connection_name="CRM",
            tool_name="create_contact",
            arguments={"name": "Ada"},
            status="pending",
        ),
    ).model_dump(mode="json")

    assert payload["tool_activities"][0]["status"] == "approval_required"
    assert payload["tool_approval"]["arguments"] == {"name": "Ada"}


def test_message_history_exposes_only_file_attachment_metadata() -> None:
    now = datetime.now(timezone.utc)
    file_id = uuid.uuid4()
    message = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="assistant",
        content="answer",
        citations=[],
        attachments=[
            {
                "id": str(file_id),
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "byte_size": 42,
            },
            {"channel": {"provider_message_id": "must-stay-internal"}},
        ],
        status="completed",
        usage_event_id=None,
        created_at=now,
        updated_at=now,
    )

    payload = ConversationService._message_out(message).model_dump(mode="json")

    assert payload["attachments"] == [
        {
            "id": str(file_id),
            "filename": "report.pdf",
            "mime_type": "application/pdf",
            "byte_size": 42,
        }
    ]
    assert "must-stay-internal" not in str(payload)
