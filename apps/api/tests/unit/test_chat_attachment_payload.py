"""Unit tests for chat multimodal attachment payload builders."""

from __future__ import annotations

import uuid

from app.chat_attachments.payload import (
    ChatTurnAttachment,
    build_user_message_content,
    openrouter_attachment_parts,
)


def _att(*, mime: str, data: bytes, name: str = "file.bin") -> ChatTurnAttachment:
    return ChatTurnAttachment(
        id=uuid.uuid4(),
        filename=name,
        mime_type=mime,
        byte_size=len(data),
        data=data,
    )


def test_image_parts_use_image_url() -> None:
    parts = openrouter_attachment_parts(_att(mime="image/png", data=b"\x89PNG", name="a.png"))
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_pdf_parts_are_raw_file_without_plugins() -> None:
    parts = openrouter_attachment_parts(
        _att(mime="application/pdf", data=b"%PDF-1.4", name="doc.pdf")
    )
    assert parts[0]["type"] == "file"
    assert parts[0]["file"]["filename"] == "doc.pdf"
    assert parts[0]["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_text_parts_inline_utf8() -> None:
    parts = openrouter_attachment_parts(
        _att(mime="text/plain", data=b"hello", name="note.txt")
    )
    assert parts[0]["type"] == "text"
    assert "hello" in parts[0]["text"]


def test_build_user_message_content_text_only() -> None:
    assert build_user_message_content("hi", None) == "hi"


def test_build_user_message_content_multimodal() -> None:
    content = build_user_message_content(
        "look",
        _att(mime="image/jpeg", data=b"\xff\xd8\xff", name="x.jpg"),
    )
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1]["type"] == "image_url"
