"""HTTP header helpers shared across routers."""

from __future__ import annotations

from urllib.parse import quote


def content_disposition(filename: str, *, inline: bool = False) -> str:
    """Build a latin-1-safe Content-Disposition header.

    Starlette encodes header values as latin-1; Arabic/other Unicode filenames
    must use RFC 5987 ``filename*`` with an ASCII ``filename`` fallback.
    """
    raw = (filename or "document.pdf").replace("\r", "").replace("\n", "")
    ascii_name = raw.encode("ascii", "ignore").decode("ascii").strip().strip(".")
    if not ascii_name or ascii_name in {'"', "'"}:
        ascii_name = "document.pdf"
    ascii_name = ascii_name.replace("\\", "_").replace('"', "'")
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(raw)}"


def content_disposition_inline(filename: str) -> str:
    return content_disposition(filename, inline=True)
