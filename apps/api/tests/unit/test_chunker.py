from __future__ import annotations

from app.ingestion.chunker import PageChunker, detect_repeated_headers_footers


def test_chunk_provenance_and_hash():
    chunker = PageChunker()
    md = """# الباب الثالث

المادة الأولى تتعلق بإنهاء العقد بعد إشعار مدته ثلاثون يوماً. """ + ("نص إضافي. " * 80)

    drafts = chunker.chunk_page(17, md)
    assert drafts
    assert all(d.page_number == 17 for d in drafts)
    assert drafts[0].ordinal == 0
    assert drafts[0].content_hash
    assert "الباب الثالث" in (drafts[0].heading_path or [""])[0] or "الباب" in drafts[0].canonical_text


def test_chunk_does_not_drop_page():
    chunker = PageChunker()
    drafts = chunker.chunk_page(3, "جملة قصيرة جدا")
    # May be below min tokens — force still creates when flushing at end with force
    # Our chunker force-flushes at end, but skips if tokens < min unless force...
    # End flush uses force=True so it should keep short page content.
    assert len(drafts) >= 1
    assert drafts[0].page_number == 3


def test_repeated_header_detection():
    pages = ["HEADER\nbody one\nFOOTER", "HEADER\nbody two\nFOOTER", "HEADER\nbody three\nFOOTER"]
    repeated = detect_repeated_headers_footers(pages, min_pages=3)
    assert "HEADER" in repeated
    assert "FOOTER" in repeated
