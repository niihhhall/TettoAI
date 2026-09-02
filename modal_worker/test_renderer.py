"""Offline tests for the pure PDF renderer (no Modal, no R2)."""

from __future__ import annotations

from renderer import build_supplement_pdf

PAYLOAD = {
    "claim_number": "A-1029",
    "address": "1420 Elmwood Dr, Dallas, TX 75201",
    "building_code_citation": "Dallas §51A roofing ordinance",
    "line_items": [
        {"code": "RFG DRIP", "description": "Drip edge", "qty": 180, "unit": "LF"},
        {"code": "RFG IWS", "description": "Ice & Water Shield", "qty": 2, "unit": "SQ"},
    ],
    "photos": ["https://cdn.codeverity.ai/photos/a.jpg"],
}


def test_renders_valid_pdf():
    pdf = build_supplement_pdf(PAYLOAD)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")      # valid PDF header
    assert len(pdf) > 800               # non-trivial document


def test_survives_unicode_and_emoji():
    # Field notes / addresses may contain non-latin-1 characters — must not crash.
    payload = {**PAYLOAD, "address": "1420 Elmwood Dr 🏠 café — Dallas", "claim_number": "Ä-1029"}
    pdf = build_supplement_pdf(payload)
    assert pdf.startswith(b"%PDF")


def test_handles_empty_line_items():
    pdf = build_supplement_pdf({"claim_number": "X", "address": "A", "line_items": []})
    assert pdf.startswith(b"%PDF")
