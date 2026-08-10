#!/usr/bin/env python3
"""Generate legal-safe multi-page PDF fixtures for structural/OCR tests."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parent


def write_blank_pdf(path: Path, pages: int, note: str) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Title": note, "/Producer": "ArabicRagFixtures"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        writer.write(f)
    # Sidecar with intended Arabic content for humans / OCR paste tests
    path.with_suffix(".md").write_text(note + "\n", encoding="utf-8")
    print(f"wrote {path} ({pages} pages)")


def main() -> None:
    write_blank_pdf(
        ROOT / "fixture-native-arabic.pdf",
        1,
        "عقد خدمات استشارية\nالمادة الأولى: مدة العقد سنة واحدة تبدأ من تاريخ التوقيع.\nالمادة الثانية: قيمة العقد خمسون ألف ريال.",
    )
    write_blank_pdf(
        ROOT / "fixture-scanned-arabic.pdf",
        1,
        "وثيقة ممسوحة ضوئياً\nيقر الطرفان بأن الإشعار يجب أن يكون كتابياً قبل ثلاثين يوماً.",
    )
    write_blank_pdf(
        ROOT / "fixture-mixed-ar-en.pdf",
        1,
        "Service Agreement / اتفاقية خدمة\nTermination notice: 30 days. مدة الإشعار: ٣٠ يوماً.\nGoverning law: KSA.",
    )
    write_blank_pdf(
        ROOT / "fixture-table.pdf",
        1,
        "جدول الرسوم\n| البند | المبلغ |\n| الاشتراك | 1000 |\n| الدعم | 250 |",
    )
    write_blank_pdf(
        ROOT / "fixture-two-page.pdf",
        2,
        "صفحة1: يبدأ الالتزام المالي في اليوم الأول من الشهر التالي.\nصفحة2: ويستمر حتى انتهاء مدة العقد سنة واحدة.",
    )


if __name__ == "__main__":
    main()
