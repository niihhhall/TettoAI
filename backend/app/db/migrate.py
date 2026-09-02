"""Run the DDL against Neon (PRD Step 1).

Usage (from backend/):
    python -m app.db.migrate
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.db.pool import normalize_dsn

DDL_PATH = Path(__file__).parent / "ddl.sql"


async def run_migration() -> None:
    settings = get_settings()
    dsn, ssl_arg = normalize_dsn(settings.DATABASE_URL)
    ddl = DDL_PATH.read_text(encoding="utf-8")

    conn = await asyncpg.connect(dsn=dsn, ssl=ssl_arg)
    try:
        await conn.execute(ddl)
        rows = await conn.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        tables = [r["table_name"] for r in rows]
        print("Migration complete. Tables present:")
        for t in tables:
            print(f"  - {t}")
        expected = {"companies", "crew_members", "jobsites", "inspection_sessions", "operators"}
        missing = expected - set(tables)
        if missing:
            raise SystemExit(f"ERROR: expected tables missing: {sorted(missing)}")
        print(f"All {len(expected)} CodeVerity tables verified.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
