from __future__ import annotations

import re
import unicodedata

# Arabic script block + presentation forms (approximate)
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_ZERO_WIDTH = "".join(
    [
        "\u200b",  # ZWSP
        "\u200c",  # ZWNJ
        "\u200d",  # ZWJ
        "\ufeff",  # BOM
        "\u2060",  # word joiner
    ]
)
_TATWEEL = "\u0640"
# Arabic diacritics (tashkeel)
_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_canonical(text: str) -> str:
    """Minimal cleanup for display / evidence. Never rewrite Arabic spelling."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove zero-width garbage safely
    for ch in _ZERO_WIDTH:
        text = text.replace(ch, "")
    text = _CTRL_RE.sub("", text)
    # Collapse pathological whitespace but keep paragraph breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_search(text: str, strip_diacritics: bool = True) -> str:
    """Conservative search-only normalization. Does not mutate canonical storage."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for ch in _ZERO_WIDTH:
        text = text.replace(ch, "")
    text = text.replace(_TATWEEL, "")
    # Unify Eastern Arabic-Indic digits with Western digits for retrieval
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    if strip_diacritics:
        text = _DIACRITICS_RE.sub("", text)
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def arabic_ratio(text: str) -> float:
    if not text:
        return 0.0
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    arabic = sum(1 for c in letters if _ARABIC_RE.match(c))
    return arabic / len(letters)


def page_quality_diagnostics(text: str) -> dict:
    length = len(text or "")
    replacement = text.count("\ufffd") if text else 0
    control = len(_CTRL_RE.findall(text or ""))
    control_ratio = (control / length) if length else 0.0
    # Repeated character ratio (e.g. "aaaaaaa")
    repeated = 0
    if text:
        for m in re.finditer(r"(.)\1{9,}", text):
            repeated += len(m.group(0))
    repeated_ratio = (repeated / length) if length else 0.0
    empty = length == 0 or not text.strip()
    return {
        "text_length": length,
        "arabic_ratio": arabic_ratio(text or ""),
        "replacement_char_count": replacement,
        "control_char_ratio": control_ratio,
        "repeated_char_ratio": repeated_ratio,
        "empty_output": empty,
        "suspicious": (
            empty
            or replacement > 5
            or control_ratio > 0.05
            or repeated_ratio > 0.3
        ),
    }
