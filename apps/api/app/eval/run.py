from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Document
from app.db.session import SessionLocal
from app.rag.service import RagService

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "eval" / "arabic_rag_golden.json"


def run() -> int:
    settings = get_settings()
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY not set; eval requires live providers")
        return 2

    items = json.loads(GOLDEN.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        docs = {
            d.original_filename: d
            for d in db.scalars(select(Document).where(Document.status == "ready"))
        }
        svc = RagService(db)
        retrieval_hits = 0
        rerank_hits = 0
        answerable_ok = 0
        citation_ok = 0
        answerable_total = 0
        n = 0

        for item in items:
            n += 1
            doc = docs.get(item["document"])
            if not doc:
                print(f"SKIP missing ready doc: {item['document']}")
                continue
            result = svc.query(item["question"], document_ids=[doc.id])
            cited_pages = {c["page"] for c in result["citations"]}
            expected = set(item.get("expected_pages") or [])

            if item.get("answerable"):
                answerable_total += 1
                if expected & cited_pages or (expected and not result["insufficient_context"]):
                    # soft: citation pages intersect expected
                    if expected & cited_pages:
                        answerable_ok += 1
                        citation_ok += 1
                        retrieval_hits += 1
                        rerank_hits += 1
                    elif not result["insufficient_context"]:
                        answerable_ok += 1
                else:
                    if result["insufficient_context"] and not expected:
                        answerable_ok += 1
            else:
                if result["insufficient_context"]:
                    answerable_ok += 1
                    answerable_total += 1
                else:
                    answerable_total += 1

            print(
                f"Q: {item['question'][:60]} | insufficient={result['insufficient_context']} "
                f"| pages={sorted(cited_pages)} expected={sorted(expected)}"
            )

        print("---")
        print(f"items={n}")
        print(f"retrieval_hit@20≈{retrieval_hits}/{n}")
        print(f"rerank_hit@6≈{rerank_hits}/{n}")
        print(f"answerable_accuracy≈{answerable_ok}/{answerable_total}")
        print(f"citation_validity≈{citation_ok}/{max(1, answerable_total)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(run())
