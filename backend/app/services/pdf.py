"""Local supplement-PDF renderer — the fallback used when the Modal microservice isn't
configured (no MODAL_API_URL). Renders the same one-page package with fpdf2 so a submitted
inspection always produces a real, R2-hosted PDF even before Modal is deployed. Once Modal
is wired, that path takes over and this is unused.
"""

from __future__ import annotations

from fpdf import FPDF
from fpdf.enums import XPos, YPos


def build_supplement_pdf(payload: dict) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    nl = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "SUPPLEMENT REQUEST PACKAGE", align="C", **nl)
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Property Address: {payload.get('address', 'N/A')}", **nl)
    pdf.cell(0, 8, f"Claim Number: {payload.get('claim_number', 'N/A')}", **nl)
    pdf.cell(0, 8, f"Municipal Ordinance: {payload.get('building_code_citation', 'N/A')}", **nl)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Xactimate Line Items Required:", **nl)
    pdf.set_font("Helvetica", "", 10)
    for it in payload.get("line_items", []):
        line = f"- [{it.get('code', '')}] {it.get('description', '')} - {it.get('qty', '')} {it.get('unit', '')}"
        pdf.cell(0, 6, line, **nl)

    return bytes(pdf.output())
