"""Reset CodeVerity test data so you can re-run the WhatsApp flow from a clean slate.

Usage (from backend/):
    python -m app.db.reset            # clear ALL inspection sessions.
                                      #   -> dashboard empties, and your next WhatsApp message
                                      #      starts a fresh jobsite pick (you stay onboarded).
    python -m app.db.reset --hard     # also remove test-onboarded crew + foreman-created
                                      #   jobsites -> your number re-onboards (name + company).
    python -m app.db.reset --demo     # clear sessions, then insert one demo inspection.

The seed baseline (companies, seeded crew/jobsites, operator login) is ALWAYS preserved, so
the operator console login and the two demo jobsites keep working after every reset.
"""

from __future__ import annotations

import argparse
import asyncio

import asyncpg

from app.config import get_settings
from app.db.pool import normalize_dsn
from app.db.seed import CREW as SEED_CREW
from app.db.seed import JOBSITES as SEED_JOBSITES

SEED_PHONES = [phone for _, phone, _, _ in SEED_CREW]
SEED_CLAIMS = [row[1] for row in SEED_JOBSITES]  # claim_number is the 2nd column


async def reset(hard: bool, demo: bool) -> None:
    s = get_settings()
    dsn, ssl_arg = normalize_dsn(s.DATABASE_URL)
    conn = await asyncpg.connect(dsn=dsn, ssl=ssl_arg)
    try:
        n_sessions = await conn.fetchval("SELECT COUNT(*) FROM inspection_sessions")
        await conn.execute("DELETE FROM inspection_sessions")
        print(f"Cleared {n_sessions} inspection session(s) — dashboard is now empty.")

        if hard:
            deleted_crew = await conn.fetchval(
                """
                WITH d AS (
                    DELETE FROM crew_members WHERE phone_number <> ALL($1::text[]) RETURNING 1
                ) SELECT COUNT(*) FROM d
                """,
                SEED_PHONES,
            )
            deleted_jobs = await conn.fetchval(
                """
                WITH d AS (
                    DELETE FROM jobsites
                    WHERE claim_number IS NULL OR claim_number <> ALL($1::text[]) RETURNING 1
                ) SELECT COUNT(*) FROM d
                """,
                SEED_CLAIMS,
            )
            print(f"Removed {deleted_crew} test crew member(s) and {deleted_jobs} "
                  "foreman-created jobsite(s). Your number will re-onboard next message.")

        print("Reset complete. Seed baseline (companies / seeded crew / jobsites / operator) preserved.")
    finally:
        await conn.close()

    if demo:
        from app.db.seed_demo_inspection import main as seed_demo
        await seed_demo()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reset CodeVerity test data (keeps seed baseline).")
    p.add_argument("--hard", action="store_true",
                   help="also remove test-onboarded crew + foreman-created jobsites")
    p.add_argument("--demo", action="store_true",
                   help="insert one demo inspection after clearing sessions")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(reset(args.hard, args.demo))
