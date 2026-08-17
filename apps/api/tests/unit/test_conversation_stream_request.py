"""ConversationMessageStreamRequest content/attachment validators."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.conversations.schemas import ConversationMessageStreamRequest


def test_content_only_ok() -> None:
    body = ConversationMessageStreamRequest(content="  Hello  ")
    assert body.content == "Hello"
    assert body.attachment_id is None


def test_attachment_only_ok() -> None:
    aid = uuid.uuid4()
    body = ConversationMessageStreamRequest(content="", attachment_id=aid)
    assert body.content == ""
    assert body.attachment_id == aid


def test_both_ok() -> None:
    aid = uuid.uuid4()
    body = ConversationMessageStreamRequest(content="q", attachment_id=aid)
    assert body.content == "q"
    assert body.attachment_id == aid


def test_neither_rejected() -> None:
    with pytest.raises(ValidationError):
        ConversationMessageStreamRequest(content="   ")
