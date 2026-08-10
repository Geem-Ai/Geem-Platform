from __future__ import annotations

from app.ingestion.arabic_normalize import (
    arabic_ratio,
    normalize_canonical,
    normalize_search,
    page_quality_diagnostics,
)


def test_canonical_preserves_arabic_letters_and_diacritics():
    src = "إِنَّ الْعَقْدَ يَنْتَهِي بَعْدَ سَنَةٍ. التاء المربوطة: مادة. الهمزات: أ إ آ ؤ ئ"
    out = normalize_canonical(src)
    assert "ة" in out
    assert "أ" in out and "إ" in out and "آ" in out
    assert "ؤ" in out and "ئ" in out
    assert "ِ" in out or "ّ" in out  # diacritics preserved in canonical


def test_canonical_nfc_and_no_destructive_rewrite():
    src = "عقد\u0640\u0640تجاري"  # with tatweel — canonical keeps tatweel
    out = normalize_canonical(src)
    assert "عقد" in out
    assert normalize_canonical("hello\r\nworld") == "hello\nworld"


def test_search_strips_tatweel_and_optional_diacritics():
    src = "إِنَّ الْعَقْـدَ"
    search = normalize_search(src, strip_diacritics=True)
    assert "ـ" not in search
    assert "ِ" not in search
    assert "عقد" in search.replace(" ", "")


def test_arabic_ratio_and_quality():
    ar = "هذا نص عربي بالكامل تقريبا"
    en = "This is entirely English text"
    assert arabic_ratio(ar) > 0.8
    assert arabic_ratio(en) < 0.2
    diag = page_quality_diagnostics("")
    assert diag["empty_output"] is True
    diag2 = page_quality_diagnostics(ar)
    assert diag2["empty_output"] is False
    assert diag2["suspicious"] is False


def test_zero_width_removed():
    src = "مرحبا\u200bبالعالم"
    assert "\u200b" not in normalize_canonical(src)
    assert "\u200b" not in normalize_search(src)
