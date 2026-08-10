from __future__ import annotations

import re

# Eastern Arabic-Indic digits → Western
_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_ONES = {
    1: "الأولى",
    2: "الثانية",
    3: "الثالثة",
    4: "الرابعة",
    5: "الخامسة",
    6: "السادسة",
    7: "السابعة",
    8: "الثامنة",
    9: "التاسعة",
    10: "العاشرة",
    11: "الحادية عشرة",
    12: "الثانية عشرة",
    13: "الثالثة عشرة",
    14: "الرابعة عشرة",
    15: "الخامسة عشرة",
    16: "السادسة عشرة",
    17: "السابعة عشرة",
    18: "الثامنة عشرة",
    19: "التاسعة عشرة",
}

_TENS = {
    20: "العشرون",
    30: "الثلاثون",
    40: "الأربعون",
    50: "الخمسون",
    60: "الستون",
    70: "السبعون",
    80: "الثمانون",
    90: "التسعون",
}

_ONES_FEM_FOR_COMPOUND = {
    1: "الحادية",
    2: "الثانية",
    3: "الثالثة",
    4: "الرابعة",
    5: "الخامسة",
    6: "السادسة",
    7: "السابعة",
    8: "الثامنة",
    9: "التاسعة",
}

_ARTICLE_NUM_RE = re.compile(
    r"(?:المادة|ماده|مادة)\s*(?:رقم\s*)?(?P<num>[0-9٠-٩]{1,3})\b",
    re.UNICODE,
)


def normalize_arabic_digits(text: str) -> str:
    return text.translate(_ARABIC_INDIC_DIGITS)


def arabic_ordinal_feminine(n: int) -> str | None:
    """Return feminine ordinal used in Saudi legal article headings, e.g. 14 → الرابعة عشرة."""
    if n <= 0 or n > 99:
        return None
    if n in _ONES:
        return _ONES[n]
    tens = (n // 10) * 10
    ones = n % 10
    if ones == 0:
        return _TENS.get(tens)
    ones_word = _ONES_FEM_FOR_COMPOUND.get(ones)
    tens_word = _TENS.get(tens)
    if not ones_word or not tens_word:
        return None
    # المادة الرابعة والعشرون
    return f"{ones_word} و{tens_word}"


def extract_article_numbers(text: str) -> list[int]:
    found: list[int] = []
    for m in _ARTICLE_NUM_RE.finditer(normalize_arabic_digits(text)):
        try:
            n = int(m.group("num"))
        except ValueError:
            continue
        if 1 <= n <= 300 and n not in found:
            found.append(n)
    return found


def expand_article_query(question: str) -> str:
    """Append spelled ordinal forms so dense retrieval can match legal headings."""
    nums = extract_article_numbers(question)
    if not nums:
        return question
    extras: list[str] = []
    for n in nums:
        ordinal = arabic_ordinal_feminine(n)
        extras.append(f"المادة {n}")
        if ordinal:
            extras.append(f"المادة {ordinal}")
            extras.append(f"## المادة {ordinal}")
    # Keep original + expansions
    return question + "\n" + "\n".join(extras)


def article_lexical_patterns(n: int) -> list[str]:
    patterns = [f"المادة {n}", f"مادة {n}"]
    ordinal = arabic_ordinal_feminine(n)
    if ordinal:
        patterns.append(f"المادة {ordinal}")
        patterns.append(f"## المادة {ordinal}")
    return patterns
