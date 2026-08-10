from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import tiktoken

from app.core.config import Settings, get_settings
from app.ingestion.arabic_normalize import normalize_canonical, normalize_search

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_RE = re.compile(r"^(\s*[-*+]|\s*\d+[.)])\s+")


@dataclass
class ChunkDraft:
    page_number: int
    ordinal: int
    heading_path: list[str]
    canonical_text: str
    search_text: str
    token_count: int
    content_hash: str


class PageChunker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        try:
            self._enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._enc = None

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self._enc is not None:
            return len(self._enc.encode(text))
        # Fallback: ~4 chars per token
        return max(1, len(text) // 4)

    def chunk_page(
        self,
        page_number: int,
        markdown: str,
        skip_headers: set[str] | None = None,
    ) -> list[ChunkDraft]:
        skip_headers = skip_headers or set()
        canonical = normalize_canonical(markdown)
        if not canonical.strip():
            return []

        blocks = self._split_blocks(canonical)
        blocks = [b for b in blocks if b["text"].strip() and b["text"].strip() not in skip_headers]

        target_min = self.settings.chunk_target_min_tokens
        target_max = self.settings.chunk_target_max_tokens
        hard_max = self.settings.chunk_hard_max_tokens
        overlap = self.settings.chunk_overlap_tokens
        min_tokens = self.settings.chunk_min_tokens

        drafts: list[ChunkDraft] = []
        buffer_parts: list[str] = []
        buffer_headings: list[str] = []
        current_headings: list[str] = []

        def flush(force: bool = False) -> None:
            nonlocal buffer_parts, buffer_headings
            if not buffer_parts:
                return
            text = "\n\n".join(buffer_parts).strip()
            tokens = self.count_tokens(text)
            if tokens < min_tokens and not force:
                return
            if tokens == 0:
                buffer_parts = []
                return
            search = normalize_search(text)
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            drafts.append(
                ChunkDraft(
                    page_number=page_number,
                    ordinal=len(drafts),
                    heading_path=list(buffer_headings),
                    canonical_text=text,
                    search_text=search,
                    token_count=tokens,
                    content_hash=content_hash,
                )
            )
            # Overlap: keep tail
            if overlap > 0 and not force:
                overlap_text = self._tail_by_tokens(text, overlap)
                buffer_parts = [overlap_text] if overlap_text else []
            else:
                buffer_parts = []
            buffer_headings = list(current_headings)

        for block in blocks:
            if block["type"] == "heading":
                level = block["level"]
                title = block["title"]
                current_headings = current_headings[: level - 1] + [title]
                # Start new chunk on major headings if buffer is substantial
                if buffer_parts and self.count_tokens("\n\n".join(buffer_parts)) >= target_min:
                    flush(force=True)
                buffer_headings = list(current_headings)
                buffer_parts.append(block["text"])
                continue

            candidate = ("\n\n".join(buffer_parts + [block["text"]])).strip()
            tokens = self.count_tokens(candidate)
            if tokens > hard_max and buffer_parts:
                flush(force=True)
                buffer_parts.append(block["text"])
                # If single block still too large, hard-split
                while self.count_tokens("\n\n".join(buffer_parts)) > hard_max:
                    text = "\n\n".join(buffer_parts)
                    head, rest = self._split_at_sentence(text, hard_max)
                    buffer_parts = [head]
                    flush(force=True)
                    buffer_parts = [rest] if rest else []
            elif tokens >= target_max:
                buffer_parts.append(block["text"])
                flush(force=True)
            else:
                buffer_parts.append(block["text"])

        if buffer_parts:
            flush(force=True)

        # Drop tiny trailing leftovers already handled by force flush
        return drafts

    def _split_blocks(self, text: str) -> list[dict]:
        blocks: list[dict] = []
        paragraphs = re.split(r"\n\s*\n", text)
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            lines = para.split("\n")
            first = lines[0].strip()
            m = _HEADING_RE.match(first)
            if m and len(lines) == 1:
                blocks.append(
                    {
                        "type": "heading",
                        "level": len(m.group(1)),
                        "title": m.group(2).strip(),
                        "text": para,
                    }
                )
                continue
            # Table-ish blocks keep together
            if "|" in para and para.count("|") >= 2:
                blocks.append({"type": "table", "text": para})
                continue
            if _LIST_RE.match(first):
                blocks.append({"type": "list", "text": para})
                continue
            blocks.append({"type": "paragraph", "text": para})
        return blocks

    def _tail_by_tokens(self, text: str, token_budget: int) -> str:
        if self._enc is None:
            chars = token_budget * 4
            return text[-chars:].strip()
        tokens = self._enc.encode(text)
        if len(tokens) <= token_budget:
            return text
        return self._enc.decode(tokens[-token_budget:]).strip()

    def _split_at_sentence(self, text: str, max_tokens: int) -> tuple[str, str]:
        # Prefer Arabic/English sentence boundaries
        if self._enc is not None:
            tokens = self._enc.encode(text)
            if len(tokens) <= max_tokens:
                return text, ""
            head_tokens = tokens[:max_tokens]
            head = self._enc.decode(head_tokens)
        else:
            head = text[: max_tokens * 4]
        # Back up to sentence end
        for sep in ["۔", ".", "!", "?", "\n"]:
            idx = head.rfind(sep)
            if idx > len(head) * 0.4:
                head = head[: idx + 1]
                break
        rest = text[len(head) :].strip()
        return head.strip(), rest


def detect_repeated_headers_footers(page_texts: list[str], min_pages: int = 3) -> set[str]:
    """Simple deterministic repeated first/last line detector."""
    if len(page_texts) < min_pages:
        return set()
    first_lines: dict[str, int] = {}
    last_lines: dict[str, int] = {}
    for text in page_texts:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        first_lines[lines[0]] = first_lines.get(lines[0], 0) + 1
        last_lines[lines[-1]] = last_lines.get(lines[-1], 0) + 1
    threshold = max(min_pages, len(page_texts) // 2)
    repeated = set()
    for line, count in {**first_lines, **last_lines}.items():
        if count >= threshold and len(line) < 120:
            repeated.add(line)
    return repeated
