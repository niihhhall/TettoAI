"""Seed ONE fully-populated demo inspection so the operator console has real content
(photo + supplement PDF served from Cloudflare R2) without a live WhatsApp pipeline.

Usage (from backend/, with R2_* set in .env):
    python -m app.db.seed_demo_inspection

Idempotent-ish: it inserts a fresh COMPLETE session each run (bounty PENDING so you can
demo the Approve -> bounty + CRM flow). Safe to run once before a demo.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import asyncpg
import boto3
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.config import get_settings
from app.db.pool import normalize_dsn

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_PHOTO = REPO_ROOT / "frontend" / "photos" / "Black Red.jpg"

TRANSCRIPT = (
    "Missing drip edge on all eaves, two squares of decking rot on the north slope, "
    "and ice-and-water shield required per city code."
)
LINE_ITEMS = [
    {"code": "RFG DRIP", "description": "Drip edge", "qty": 180, "unit": "LF"},
    {"code": "RFG SHTHN", "description": 'OSB Sheathing 1/2"', "qty": 64, "unit": "SF"},
    {"code": "RFG IWS", "description": "Ice & Water Shield", "qty": 2, "unit": "SQ"},
]


def _r2_client(s):
    return boto3.client(
        "s3", endpoint_url=s.R2_ENDPOINT_URL,
        aws_access_key_id=s.R2_ACCESS_KEY_ID, aws_secret_access_key=s.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def _public_url(s, key: str) -> str:
    if s.R2_PUBLIC_CUSTOM_DOMAIN:
        return f"https://{s.R2_PUBLIC_CUSTOM_DOMAIN}/{key}"
    return f"{s.R2_ENDPOINT_URL}/{s.R2_BUCKET_NAME}/{key}"


def _render_pdf(address: str, claim: str, citation: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    nl = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}
    pdf.cell(0, 10, "SUPPLEMENT REQUEST PACKAGE", align="C", **nl)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Property Address: {address}", **nl)
    pdf.cell(0, 8, f"Claim Number: {claim}", **nl)
    pdf.cell(0, 8, f"Municipal Ordinance: {citation}", **nl)
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Xactimate Line Items Required:", **nl)
    pdf.set_font("Helvetica", "", 10)
    for it in LINE_ITEMS:
        pdf.cell(0, 6, f"- [{it['code']}] {it['description']} - {it['qty']} {it['unit']}", **nl)
    return bytes(pdf.output())


async def main() -> None:
    s = get_settings()
    if not (s.R2_ACCESS_KEY_ID and s.R2_BUCKET_NAME):
        raise SystemExit("R2_* not configured — set them in backend/.env first.")

    s3 = _r2_client(s)

    # 1. Upload a sample geo-tagged photo to R2.
    photo_url = None
    if SAMPLE_PHOTO.exists():
        pkey = f"photos/demo-{uuid4().hex}.jpg"
        s3.put_object(Bucket=s.R2_BUCKET_NAME, Key=pkey,
                      Body=SAMPLE_PHOTO.read_bytes(), ContentType="image/jpeg")
        photo_url = _public_url(s, pkey)
        print(f"uploaded photo -> {photo_url}")
    else:
        print(f"(sample photo not found at {SAMPLE_PHOTO}; continuing without a photo)")

    # 2. Render + upload the supplement PDF to R2.
    dsn, ssl_arg = normalize_dsn(s.DATABASE_URL)
    conn = await asyncpg.connect(dsn=dsn, ssl=ssl_arg)
    try:
        job = await conn.fetchrow(
            """
            SELECT j.job_id, j.property_address, j.claim_number, j.city
            FROM jobsites j JOIN companies c ON c.company_id = j.company_id
            WHERE c.invite_code = '4821' AND j.claim_number = 'A-1029'
            """
        )
        crew = await conn.fetchrow(
            "SELECT crew_id FROM crew_members WHERE phone_number = '+12145550199'"
        )
        if not job or not crew:
            raise SystemExit("Run `python -m app.db.seed` first (missing Apex job/crew).")

        citation = f"{job['city']} municipal roofing code"
        pdf_bytes = _render_pdf(job["property_address"], job["claim_number"], citation)
        pkey = f"pdf/{job['claim_number']}-{uuid4().hex[:8]}.pdf"
        s3.put_object(Bucket=s.R2_BUCKET_NAME, Key=pkey, Body=pdf_bytes,
                      ContentType="application/pdf")
        pdf_url = _public_url(s, pkey)
        print(f"uploaded pdf   -> {pdf_url}")

        # 3. Insert a COMPLETE inspection (bounty PENDING for the demo approval flow).
        photos = [photo_url] if photo_url else []
        session_id = await conn.fetchval(
            """
            INSERT INTO inspection_sessions
                (crew_id, job_id, current_state, approved_photos, voice_note_url,
                 transcription_text, structured_line_items, pdf_url, bounty_status, supplement_value)
            VALUES ($1, $2, 'STATE_6_COMPLETE', $3::jsonb, NULL,
                    $4, $5::jsonb, $6, 'PENDING', $7)
            RETURNING session_id
            """,
            crew["crew_id"], job["job_id"], json.dumps(photos),
            TRANSCRIPT, json.dumps(LINE_ITEMS), pdf_url, 1850.00,
        )
        print(f"seeded inspection session {session_id} (bounty PENDING).")
        print("Open the console -> Live Feed to see it; open the drawer for photo + PDF.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
