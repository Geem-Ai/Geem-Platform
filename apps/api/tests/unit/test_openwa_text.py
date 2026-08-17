"""Phase 9F — OpenWA text helpers."""

from __future__ import annotations

import pytest

from app.connectors.providers.openwa.text import (
    normalize_whatsapp_phone,
    split_whatsapp_text,
)
from app.core.errors import ErrorCategory


def test_normalize_whatsapp_phone_strips_formatting() -> None:
    assert normalize_whatsapp_phone("+966 50-000-0000") == "966500000000"
    assert normalize_whatsapp_phone("00966500000000") == "966500000000"


def test_normalize_whatsapp_phone_rejects_invalid_values() -> None:
    with pytest.raises(Exception) as excinfo:
        normalize_whatsapp_phone("12-34")

    assert getattr(excinfo.value, "category", None) == ErrorCategory.OPENWA_PHONE_INVALID


def test_split_whatsapp_text_keeps_segments_under_limit_for_arabic() -> None:
    text = (
        "هذا نص عربي طويل لاختبار تقسيم الرسائل بشكل آمن دون كسر الأحرف أو تجاوز الحد. "
        "ويجب أن يفضّل التقسيم عند الفراغات أو علامات الترقيم كلما أمكن ذلك. "
    ) * 8

    segments = split_whatsapp_text(text, max_chars=120)

    assert len(segments) > 1
    assert all(len(segment) <= 120 for segment in segments)
    assert all(segment.strip() for segment in segments)
    assert "هذا نص عربي طويل" in segments[0]
    assert "التقسيم" in "".join(segments)
