from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedPage:
    page_number: int
    raw_markdown: str
    plain_text: str
    parser: str
    parser_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
