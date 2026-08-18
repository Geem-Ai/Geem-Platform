"""ZATCA Phase 1 TLV QR payload (seller, VAT no., timestamp, totals)."""

from __future__ import annotations

import base64


def _tlv(tag: int, value: str) -> bytes:
    encoded = (value or "").encode("utf-8")
    if len(encoded) > 255:
        raise ValueError(f"ZATCA TLV tag {tag} exceeds 255 bytes.")
    return bytes([tag, len(encoded)]) + encoded


def zatca_qr_base64(
    *,
    seller_name: str,
    vat_number: str,
    timestamp: str,
    total_with_vat: str,
    vat_amount: str,
) -> str:
    """Base64 TLV per ZATCA e-invoicing Phase 1 (simplified tax invoice QR)."""
    payload = b"".join(
        [
            _tlv(1, seller_name),
            _tlv(2, vat_number),
            _tlv(3, timestamp),
            _tlv(4, total_with_vat),
            _tlv(5, vat_amount),
        ]
    )
    return base64.b64encode(payload).decode("ascii")
