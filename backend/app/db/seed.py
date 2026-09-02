"""Seed baseline demo data so the state machine has companies/crew/jobs to resolve.

Usage (from backend/):
    python -m app.db.seed

Idempotent via ON CONFLICT on natural keys (invite_code, phone_number).
"""

from __future__ import annotations

import asyncio

import asyncpg

from app.auth import hash_password
from app.config import get_settings
from app.db.pool import normalize_dsn

# (company invite_code, email, password) — demo operator login for the console.
OPERATORS = [
    ("4821", "operator@apex.test", "demo-password"),
]

COMPANIES = [
    # (company_name, invite_code, crm_type)
    ("Apex Roofing", "4821", "JobNimbus"),
    ("Titan Storm Restoration", "7710", "AccuLynx"),
]

# (company invite_code, phone E.164, full_name, role)
CREW = [
    ("4821", "+12145550199", "Marcus Johnson", "Foreman"),
    ("4821", "+12145550142", "Diego Ramirez", "Foreman"),
]

# (company invite_code, claim_number, address, zip, city, state, county)
JOBSITES = [
    ("4821", "A-1029", "1420 Elmwood Dr, Dallas, TX 75201", "75201", "Dallas", "TX", "Dallas County"),
    ("4821", "A-1044", "88 Cedar Hollow Ln, Plano, TX 75024", "75024", "Plano", "TX", "Collin County"),
]


async def seed() -> None:
    settings = get_settings()
    dsn, ssl_arg = normalize_dsn(settings.DATABASE_URL)
    conn = await asyncpg.connect(dsn=dsn, ssl=ssl_arg)
    try:
        for name, code, crm in COMPANIES:
            await conn.execute(
                """
                INSERT INTO companies (company_name, invite_code, crm_type)
                VALUES ($1, $2, $3)
                ON CONFLICT (invite_code) DO NOTHING
                """,
                name, code, crm,
            )

        for code, phone, name, role in CREW:
            await conn.execute(
                """
                INSERT INTO crew_members (company_id, phone_number, full_name, role)
                VALUES ((SELECT company_id FROM companies WHERE invite_code = $1), $2, $3, $4)
                ON CONFLICT (phone_number) DO NOTHING
                """,
                code, phone, name, role,
            )

        for code, claim, addr, zip_, city, state, county in JOBSITES:
            await conn.execute(
                """
                INSERT INTO jobsites
                    (company_id, claim_number, property_address, zip_code, city, state, county)
                VALUES
                    ((SELECT company_id FROM companies WHERE invite_code = $1), $2, $3, $4, $5, $6, $7)
                """,
                code, claim, addr, zip_, city, state, county,
            )

        for code, email, password in OPERATORS:
            await conn.execute(
                """
                INSERT INTO operators (company_id, email, password_hash)
                VALUES ((SELECT company_id FROM companies WHERE invite_code = $1), $2, $3)
                ON CONFLICT (email) DO NOTHING
                """,
                code, email, hash_password(password),
            )

        companies = await conn.fetchval("SELECT COUNT(*) FROM companies")
        crew = await conn.fetchval("SELECT COUNT(*) FROM crew_members")
        jobs = await conn.fetchval("SELECT COUNT(*) FROM jobsites")
        ops = await conn.fetchval("SELECT COUNT(*) FROM operators")
        print(f"Seed complete: {companies} companies, {crew} crew, {jobs} jobsites, {ops} operators.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
