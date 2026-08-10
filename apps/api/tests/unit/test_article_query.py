from __future__ import annotations

from app.ingestion.article_query import (
    arabic_ordinal_feminine,
    expand_article_query,
    extract_article_numbers,
)
from app.ingestion.arabic_normalize import normalize_search


def test_extract_article_numbers_eastern_digits():
    assert extract_article_numbers("ما هي المادة ١٤") == [14]
    assert extract_article_numbers("المادة 14") == [14]


def test_arabic_ordinal_14():
    assert arabic_ordinal_feminine(14) == "الرابعة عشرة"
    assert arabic_ordinal_feminine(4) == "الرابعة"
    assert arabic_ordinal_feminine(24) == "الرابعة والعشرون"


def test_expand_article_query_includes_ordinal():
    q = expand_article_query("ما هي المادة ١٤")
    assert "الرابعة عشرة" in q
    assert "المادة 14" in q


def test_search_normalizes_eastern_digits():
    assert "14" in normalize_search("المادة ١٤")
    assert "٠" not in normalize_search("المادة ١٤")
