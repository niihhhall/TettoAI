"""Pure supplement-PDF renderer (fpdf2). No Modal / no network — unit-testable.

Kept separate from pdf_service.py so the rendering logic can be tested without importing
the Modal runtime. Uses core Helvetica + latin-1-safe text so field notes containing
emoji/unicode never crash the render (fpdf2 core fonts are latin-1 only).
"""

from __future__ import annotations

from fpdf import FPDF
from fpdf.enums import XPos, YPos


def _safe(text: object) -> str:
    """Coerce any value to latin-1-safe text for fpdf2 core fonts."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def build_supplement_pdf(payload: dict) -> bytes:
    """Render the supplement request package to PDF bytes (PRD §7)."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _safe("SUPPLEMENT REQUEST PACKAGE"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(4)

    # Property + code justification
    pdf.set_font("Helvetica", "", 11)
    for label, key in (
        ("Property Address", "address"),
        ("Claim Number", "claim_number"),
        ("Municipal Ordinance", "building_code_citation"),
    ):
        pdf.cell(0, 8, _safe(f"{label}: {payload.get(key, 'N/A')}"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    # Line items table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _safe("Xactimate Line Items Required:"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)

    line_items = payload.get("line_items") or []
    if not line_items:
        pdf.cell(0, 6, _safe("- No line items captured."),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    for item in line_items:
        line = (f"- [{item.get('code', '')}] {item.get('description', '')} "
                f"- Qty: {item.get('qty', '')} {item.get('unit', '')}")
        pdf.multi_cell(0, 6, _safe(line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Evidence photos (URLs listed; images embedded is a future enhancement)
    photos = payload.get("photos") or []
    if photos:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, _safe("Geo-tagged Evidence:"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        for i, url in enumerate(photos, start=1):
            pdf.multi_cell(0, 5, _safe(f"Photo {i}: {url}"),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())
