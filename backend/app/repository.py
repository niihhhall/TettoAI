"""Data access behind a Protocol so the state machine is DB-agnostic and unit-testable.

  * InMemoryRepository — for tests / local runs (no DB).
  * PgRepository       — asyncpg-backed, for production.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from app.auth import hash_password
from app.models import Company, CrewMember, InspectionSession, Jobsite, Operator, State

SESSION_TTL = timedelta(hours=24)


class Repository(Protocol):
    async def get_crew_by_phone(self, phone: str) -> CrewMember | None: ...
    async def record_inbound(self, phone: str, at: datetime | None = None) -> None: ...
    async def create_crew_member(self, phone: str, full_name: str, company_id: UUID | None) -> CrewMember: ...
    async def get_company_by_code(self, code: str) -> Company | None: ...
    async def get_company_by_id(self, company_id: UUID) -> Company | None: ...
    async def list_jobsites(self, company_id: UUID) -> list[Jobsite]: ...
    async def get_jobsite(self, job_id: UUID, company_id: UUID | str | None = None) -> Jobsite | None: ...
    async def update_jobsite(self, job_id: UUID, **fields) -> None: ...
    async def create_jobsite(self, company_id: UUID, property_address: str, city: str | None = None,
                             county: str | None = None, zip_code: str | None = None,
                             state: str | None = None, claim_number: str | None = None,
                             municipal_code_summary: str | None = None) -> Jobsite: ...
    # Companies / branches (operator management surface)
    async def list_companies(self) -> list[Company]: ...
    async def create_company(self, company_name: str, invite_code: str,
                             crm_type: str = "JobNimbus", crm_webhook_url: str | None = None) -> Company: ...
    async def update_company(self, company_id: UUID, **fields) -> None: ...
    async def get_active_session(self, crew_id: UUID) -> InspectionSession | None: ...
    async def create_session(self, crew_id: UUID) -> InspectionSession: ...
    async def update_session(self, session_id: UUID, **fields) -> None: ...
    # Credit the bounty exactly once, only if currently PENDING (idempotent). Returns True
    # if this call performed the credit. Tenant-guarded when company_id is provided.
    async def approve_inspection(self, session_id, amount: Decimal,
                                 company_id: UUID | str | None = None) -> bool: ...
    async def set_crm_status(self, session_id, status: str) -> None: ...
    # company_id filters to a single tenant; None = unscoped (internal/state-machine use).
    async def list_recent_inspections(self, limit: int = 50, company_id: UUID | str | None = None) -> list[dict]: ...
    async def get_inspection(self, session_id, company_id: UUID | str | None = None) -> dict | None: ...
    # Delete an inspection, tenant-guarded when company_id is provided. Returns True if removed.
    async def delete_inspection(self, session_id, company_id: UUID | str | None = None) -> bool: ...
    async def list_crew(self, company_id: UUID | str | None = None) -> list[dict]: ...
    # Operators (console auth)
    async def get_operator_by_email(self, email: str) -> Operator | None: ...
    async def create_operator(self, email: str, password_hash: str, company_id: UUID | None,
                              role: str = "operator") -> Operator: ...


def in_session(crew: CrewMember | None, now: datetime | None = None) -> bool:
    """24h WhatsApp window check driven by crew_members.last_inbound_at."""
    if crew is None or crew.last_inbound_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - crew.last_inbound_at) <= SESSION_TTL


# --- In-memory implementation ---------------------------------------------------

class InMemoryRepository:
    """Seeded with the same demo data as db/seed.py."""

    def __init__(self) -> None:
        self.companies: dict[UUID, Company] = {}
        self.crew: dict[UUID, CrewMember] = {}
        self.jobsites: dict[UUID, Jobsite] = {}
        self.sessions: dict[UUID, InspectionSession] = {}
        self.operators: dict[UUID, Operator] = {}
        self._seed()

    def _seed(self) -> None:
        apex = Company(uuid4(), "Apex Roofing", "4821", "JobNimbus")
        titan = Company(uuid4(), "Titan Storm Restoration", "7710", "AccuLynx")
        self.companies[apex.company_id] = apex
        self.companies[titan.company_id] = titan

        op = Operator(uuid4(), apex.company_id, "operator@apex.test",
                      hash_password("demo-password"))
        self.operators[op.operator_id] = op

        marcus = CrewMember(uuid4(), apex.company_id, "+12145550199", "Marcus Johnson")
        self.crew[marcus.crew_id] = marcus

        j1 = Jobsite(uuid4(), apex.company_id, "1420 Elmwood Dr, Dallas, TX 75201",
                     "75201", "Dallas", "TX", "A-1029", "Dallas County")
        j2 = Jobsite(uuid4(), apex.company_id, "88 Cedar Hollow Ln, Plano, TX 75024",
                     "75024", "Plano", "TX", "A-1044", "Collin County")
        self.jobsites[j1.job_id] = j1
        self.jobsites[j2.job_id] = j2

    async def get_crew_by_phone(self, phone: str) -> CrewMember | None:
        return next((c for c in self.crew.values() if c.phone_number == phone), None)

    async def record_inbound(self, phone: str, at: datetime | None = None) -> None:
        crew = await self.get_crew_by_phone(phone)
        if crew:
            crew.last_inbound_at = at or datetime.now(timezone.utc)

    async def create_crew_member(self, phone: str, full_name: str, company_id: UUID | None) -> CrewMember:
        crew = CrewMember(uuid4(), company_id, phone, full_name,
                          last_inbound_at=datetime.now(timezone.utc))
        self.crew[crew.crew_id] = crew
        return crew

    async def get_company_by_code(self, code: str) -> Company | None:
        code = code.strip().upper()
        return next((c for c in self.companies.values() if c.invite_code.upper() == code), None)

    async def get_company_by_id(self, company_id) -> Company | None:
        return self.companies.get(company_id) or next(
            (c for c in self.companies.values() if str(c.company_id) == str(company_id)), None)

    async def get_operator_by_email(self, email: str) -> Operator | None:
        email = email.strip().lower()
        return next((o for o in self.operators.values() if o.email.lower() == email), None)

    async def create_operator(self, email: str, password_hash: str, company_id: UUID | None,
                              role: str = "operator") -> Operator:
        op = Operator(uuid4(), company_id, email.strip().lower(), password_hash, role)
        self.operators[op.operator_id] = op
        return op

    async def list_jobsites(self, company_id: UUID) -> list[Jobsite]:
        return [j for j in self.jobsites.values() if j.company_id == company_id]

    async def update_jobsite(self, job_id: UUID, **fields) -> None:
        j = self.jobsites.get(job_id)
        if j:
            for k, v in fields.items():
                setattr(j, k, v)

    async def get_jobsite(self, job_id, company_id=None) -> Jobsite | None:
        j = self.jobsites.get(job_id) or next(
            (x for x in self.jobsites.values() if str(x.job_id) == str(job_id)), None)
        if j is None:
            return None
        if company_id is not None and str(j.company_id) != str(company_id):
            return None
        return j

    async def create_jobsite(self, company_id, property_address, city=None, county=None,
                             zip_code=None, state=None, claim_number=None,
                             municipal_code_summary=None) -> Jobsite:
        j = Jobsite(uuid4(), company_id, property_address, zip_code or "", city or "",
                    state or "", claim_number, county, municipal_code_summary)
        self.jobsites[j.job_id] = j
        return j

    async def list_companies(self) -> list[Company]:
        return list(self.companies.values())

    async def create_company(self, company_name, invite_code, crm_type="JobNimbus",
                             crm_webhook_url=None) -> Company:
        c = Company(uuid4(), company_name, invite_code, crm_type, crm_webhook_url)
        self.companies[c.company_id] = c
        return c

    async def update_company(self, company_id, **fields) -> None:
        c = self.companies.get(company_id) or next(
            (x for x in self.companies.values() if str(x.company_id) == str(company_id)), None)
        if c:
            for k, v in fields.items():
                setattr(c, k, v)

    async def get_active_session(self, crew_id: UUID) -> InspectionSession | None:
        active = [s for s in self.sessions.values()
                  if s.crew_id == crew_id and s.current_state != State.COMPLETE]
        return active[-1] if active else None

    async def create_session(self, crew_id: UUID) -> InspectionSession:
        s = InspectionSession(uuid4(), crew_id, current_state=State.JOBSITE,
                              created_at=datetime.now(timezone.utc))
        self.sessions[s.session_id] = s
        return s

    async def update_session(self, session_id: UUID, **fields) -> None:
        s = self.sessions[session_id]
        for k, v in fields.items():
            setattr(s, k, v)

    def _find_session(self, session_id) -> InspectionSession | None:
        return next((x for x in self.sessions.values()
                     if str(x.session_id) == str(session_id)), None)

    async def approve_inspection(self, session_id, amount: Decimal,
                                 company_id: UUID | str | None = None) -> bool:
        s = self._find_session(session_id)
        if s is None:
            return False
        crew = self.crew.get(s.crew_id)
        if company_id is not None and (crew is None or str(crew.company_id) != str(company_id)):
            return False
        if s.bounty_status != "PENDING":
            return False  # already approved/paid — idempotent no-op
        s.bounty_status = "APPROVED"
        if crew:
            crew.total_bounties_earned += amount
        return True

    async def set_crm_status(self, session_id, status: str) -> None:
        s = self._find_session(session_id)
        if s:
            s.crm_status = status

    def _card(self, s: InspectionSession) -> dict:
        crew = self.crew.get(s.crew_id)
        job = self.jobsites.get(s.job_id) if s.job_id else None
        company = self.companies.get(crew.company_id) if crew and crew.company_id else None
        return {
            "session_id": str(s.session_id),
            "company_id": str(company.company_id) if company else None,
            "crew_name": crew.full_name if crew else None,
            "company_name": company.company_name if company else None,
            "address": job.property_address if job else None,
            "city": job.city if job else None,
            "claim_number": job.claim_number if job else None,
            "building_code": (job.municipal_code_summary if job else None),
            "photos": list(s.approved_photos),
            "photo_evidence": list(s.photo_evidence),
            "transcription": s.transcription_text,
            "voice_note_url": s.voice_note_url,
            "line_items": list(s.structured_line_items),
            "pdf_url": s.pdf_url,
            "bounty_status": s.bounty_status,
            "crm_status": s.crm_status,
            "supplement_value": float(s.supplement_value) if s.supplement_value is not None else None,
            "current_state": s.current_state,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }

    async def list_recent_inspections(self, limit: int = 50,
                                      company_id: UUID | str | None = None) -> list[dict]:
        cards = [self._card(s) for s in self.sessions.values()]
        if company_id is not None:
            cards = [c for c in cards if c["company_id"] == str(company_id)]
        return list(reversed(cards))[:limit]

    async def get_inspection(self, session_id: UUID | str,
                             company_id: UUID | str | None = None) -> dict | None:
        for s in self.sessions.values():
            if str(s.session_id) == str(session_id):
                card = self._card(s)
                if company_id is not None and card["company_id"] != str(company_id):
                    return None
                return card
        return None

    async def delete_inspection(self, session_id, company_id=None) -> bool:
        s = self._find_session(session_id)
        if s is None:
            return False
        if company_id is not None:
            crew = self.crew.get(s.crew_id)
            if crew is None or str(crew.company_id) != str(company_id):
                return False
        del self.sessions[s.session_id]
        return True

    async def list_crew(self, company_id: UUID | str | None = None) -> list[dict]:
        out = []
        for c in self.crew.values():
            if company_id is not None and str(c.company_id) != str(company_id):
                continue
            comp = self.companies.get(c.company_id) if c.company_id else None
            out.append({
                "crew_id": str(c.crew_id), "full_name": c.full_name,
                "phone_number": c.phone_number, "role": c.role,
                "company_name": comp.company_name if comp else None,
                "company_code": comp.invite_code if comp else None,
                "total_bounties_earned": float(c.total_bounties_earned),
            })
        return out


# --- Postgres implementation ----------------------------------------------------

class PgRepository:
    """asyncpg-backed repository. Uses the shared pool."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def get_crew_by_phone(self, phone: str) -> CrewMember | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM crew_members WHERE phone_number = $1", phone
        )
        return self._crew(row) if row else None

    async def record_inbound(self, phone: str, at: datetime | None = None) -> None:
        await self._pool.execute(
            "UPDATE crew_members SET last_inbound_at = COALESCE($2, NOW()) WHERE phone_number = $1",
            phone, at,
        )

    async def create_crew_member(self, phone: str, full_name: str, company_id: UUID | None) -> CrewMember:
        row = await self._pool.fetchrow(
            """
            INSERT INTO crew_members (phone_number, full_name, company_id, last_inbound_at)
            VALUES ($1, $2, $3, NOW())
            RETURNING *
            """,
            phone, full_name, company_id,
        )
        return self._crew(row)

    async def get_company_by_code(self, code: str) -> Company | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM companies WHERE UPPER(invite_code) = UPPER($1)", code.strip()
        )
        return self._company(row) if row else None

    async def get_company_by_id(self, company_id) -> Company | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM companies WHERE company_id = $1::uuid", str(company_id)
        )
        return self._company(row) if row else None

    async def get_operator_by_email(self, email: str) -> Operator | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM operators WHERE LOWER(email) = LOWER($1)", email.strip()
        )
        return self._operator(row) if row else None

    async def create_operator(self, email: str, password_hash: str, company_id: UUID | None,
                              role: str = "operator") -> Operator:
        row = await self._pool.fetchrow(
            """
            INSERT INTO operators (email, password_hash, company_id, role)
            VALUES ($1, $2, $3, $4) RETURNING *
            """,
            email.strip().lower(), password_hash, company_id, role,
        )
        return self._operator(row)

    async def list_jobsites(self, company_id: UUID) -> list[Jobsite]:
        rows = await self._pool.fetch(
            "SELECT * FROM jobsites WHERE company_id = $1 ORDER BY created_at DESC", company_id
        )
        return [self._jobsite(r) for r in rows]

    async def update_jobsite(self, job_id: UUID, **fields) -> None:
        if not fields:
            return
        cols, vals = [], []
        for i, (k, v) in enumerate(fields.items(), start=2):
            cols.append(f"{k} = ${i}")
            vals.append(v)
        await self._pool.execute(
            f"UPDATE jobsites SET {', '.join(cols)} WHERE job_id = $1", job_id, *vals
        )

    async def get_jobsite(self, job_id, company_id=None) -> Jobsite | None:
        if company_id is not None:
            row = await self._pool.fetchrow(
                "SELECT * FROM jobsites WHERE job_id = $1::uuid AND company_id = $2::uuid",
                str(job_id), str(company_id),
            )
        else:
            row = await self._pool.fetchrow(
                "SELECT * FROM jobsites WHERE job_id = $1::uuid", str(job_id))
        return self._jobsite(row) if row else None

    async def create_jobsite(self, company_id, property_address, city=None, county=None,
                             zip_code=None, state=None, claim_number=None,
                             municipal_code_summary=None) -> Jobsite:
        row = await self._pool.fetchrow(
            """
            INSERT INTO jobsites
                (company_id, property_address, city, county, zip_code, state, claim_number,
                 municipal_code_summary)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *
            """,
            company_id, property_address, city, county, zip_code, state, claim_number,
            municipal_code_summary,
        )
        return self._jobsite(row)

    async def list_companies(self) -> list[Company]:
        rows = await self._pool.fetch("SELECT * FROM companies ORDER BY created_at DESC")
        return [self._company(r) for r in rows]

    async def create_company(self, company_name, invite_code, crm_type="JobNimbus",
                             crm_webhook_url=None) -> Company:
        row = await self._pool.fetchrow(
            """
            INSERT INTO companies (company_name, invite_code, crm_type, crm_webhook_url)
            VALUES ($1, $2, $3, $4) RETURNING *
            """,
            company_name, invite_code, crm_type, crm_webhook_url,
        )
        return self._company(row)

    async def update_company(self, company_id, **fields) -> None:
        if not fields:
            return
        cols, vals = [], []
        for i, (k, v) in enumerate(fields.items(), start=2):
            cols.append(f"{k} = ${i}")
            vals.append(v)
        await self._pool.execute(
            f"UPDATE companies SET {', '.join(cols)} WHERE company_id = $1::uuid",
            str(company_id), *vals,
        )

    async def get_active_session(self, crew_id: UUID) -> InspectionSession | None:
        row = await self._pool.fetchrow(
            """
            SELECT * FROM inspection_sessions
            WHERE crew_id = $1 AND current_state <> $2
            ORDER BY created_at DESC LIMIT 1
            """,
            crew_id, State.COMPLETE,
        )
        return self._session(row) if row else None

    async def create_session(self, crew_id: UUID) -> InspectionSession:
        row = await self._pool.fetchrow(
            """
            INSERT INTO inspection_sessions (crew_id, current_state)
            VALUES ($1, $2) RETURNING *
            """,
            crew_id, State.JOBSITE,
        )
        return self._session(row)

    async def update_session(self, session_id: UUID, **fields) -> None:
        if not fields:
            return
        import json
        cols, vals = [], []
        for i, (k, v) in enumerate(fields.items(), start=2):
            cols.append(f"{k} = ${i}")
            vals.append(json.dumps(v) if isinstance(v, (list, dict)) else v)
        await self._pool.execute(
            f"UPDATE inspection_sessions SET {', '.join(cols)} WHERE session_id = $1",
            session_id, *vals,
        )

    async def approve_inspection(self, session_id, amount: Decimal,
                                 company_id: UUID | str | None = None) -> bool:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Atomic guard: flip to APPROVED only if still PENDING (and tenant matches).
                if company_id is not None:
                    row = await conn.fetchrow(
                        """
                        UPDATE inspection_sessions s SET bounty_status = 'APPROVED'
                        FROM crew_members c
                        WHERE s.session_id = $1::uuid AND s.crew_id = c.crew_id
                          AND c.company_id = $2::uuid AND s.bounty_status = 'PENDING'
                        RETURNING s.crew_id
                        """,
                        str(session_id), str(company_id),
                    )
                else:
                    row = await conn.fetchrow(
                        """
                        UPDATE inspection_sessions SET bounty_status = 'APPROVED'
                        WHERE session_id = $1::uuid AND bounty_status = 'PENDING'
                        RETURNING crew_id
                        """,
                        str(session_id),
                    )
                if row is None:
                    return False  # not found, wrong tenant, or already approved
                await conn.execute(
                    "UPDATE crew_members SET total_bounties_earned = total_bounties_earned + $2 WHERE crew_id = $1",
                    row["crew_id"], amount,
                )
                return True

    async def set_crm_status(self, session_id, status: str) -> None:
        await self._pool.execute(
            "UPDATE inspection_sessions SET crm_status = $2, crm_response_at = NOW() WHERE session_id = $1::uuid",
            str(session_id), status,
        )

    async def list_recent_inspections(self, limit: int = 50,
                                      company_id: UUID | str | None = None) -> list[dict]:
        base = """
            SELECT s.session_id, s.approved_photos, s.photo_evidence, s.transcription_text,
                   s.voice_note_url, s.structured_line_items, s.pdf_url, s.bounty_status,
                   s.crm_status, s.supplement_value, s.current_state, s.created_at,
                   c.full_name AS crew_name, co.company_name, co.company_id,
                   j.property_address AS address, j.city, j.claim_number,
                   j.municipal_code_summary AS building_code
            FROM inspection_sessions s
            LEFT JOIN crew_members c ON c.crew_id = s.crew_id
            LEFT JOIN companies co ON co.company_id = c.company_id
            LEFT JOIN jobsites j ON j.job_id = s.job_id
        """
        if company_id is not None:
            rows = await self._pool.fetch(
                base + " WHERE co.company_id = $1::uuid ORDER BY s.created_at DESC LIMIT $2",
                str(company_id), limit,
            )
        else:
            rows = await self._pool.fetch(
                base + " ORDER BY s.created_at DESC LIMIT $1", limit
            )
        return [self._card_row(r) for r in rows]

    async def get_inspection(self, session_id, company_id: UUID | str | None = None) -> dict | None:
        base = """
            SELECT s.session_id, s.approved_photos, s.photo_evidence, s.transcription_text,
                   s.voice_note_url, s.structured_line_items, s.pdf_url, s.bounty_status,
                   s.crm_status, s.supplement_value, s.current_state, s.created_at,
                   c.full_name AS crew_name, co.company_name, co.company_id,
                   j.property_address AS address, j.city, j.claim_number,
                   j.municipal_code_summary AS building_code
            FROM inspection_sessions s
            LEFT JOIN crew_members c ON c.crew_id = s.crew_id
            LEFT JOIN companies co ON co.company_id = c.company_id
            LEFT JOIN jobsites j ON j.job_id = s.job_id
            WHERE s.session_id = $1::uuid
        """
        if company_id is not None:
            row = await self._pool.fetchrow(base + " AND co.company_id = $2::uuid",
                                            str(session_id), str(company_id))
        else:
            row = await self._pool.fetchrow(base, str(session_id))
        return self._card_row(row) if row else None

    async def delete_inspection(self, session_id, company_id=None) -> bool:
        if company_id is not None:
            row = await self._pool.fetchrow(
                """
                DELETE FROM inspection_sessions s
                USING crew_members c
                WHERE s.session_id = $1::uuid AND s.crew_id = c.crew_id
                  AND c.company_id = $2::uuid
                RETURNING s.session_id
                """,
                str(session_id), str(company_id),
            )
        else:
            row = await self._pool.fetchrow(
                "DELETE FROM inspection_sessions WHERE session_id = $1::uuid RETURNING session_id",
                str(session_id),
            )
        return row is not None

    async def list_crew(self, company_id: UUID | str | None = None) -> list[dict]:
        base = """
            SELECT c.crew_id, c.full_name, c.phone_number, c.role, c.total_bounties_earned,
                   co.company_name, co.invite_code AS company_code
            FROM crew_members c
            LEFT JOIN companies co ON co.company_id = c.company_id
        """
        if company_id is not None:
            rows = await self._pool.fetch(
                base + " WHERE co.company_id = $1::uuid ORDER BY c.created_at DESC", str(company_id)
            )
        else:
            rows = await self._pool.fetch(base + " ORDER BY c.created_at DESC")
        return [{
            "crew_id": str(r["crew_id"]), "full_name": r["full_name"],
            "phone_number": r["phone_number"], "role": r["role"],
            "company_name": r["company_name"], "company_code": r["company_code"],
            "total_bounties_earned": float(r["total_bounties_earned"]),
        } for r in rows]

    # --- row mappers ---
    @staticmethod
    def _card_row(row) -> dict:
        import json

        def _j(v):
            return json.loads(v) if isinstance(v, str) else (v or [])

        return {
            "session_id": str(row["session_id"]),
            "company_id": str(row["company_id"]) if row["company_id"] else None,
            "crew_name": row["crew_name"],
            "company_name": row["company_name"],
            "address": row["address"],
            "city": row["city"],
            "claim_number": row["claim_number"],
            "building_code": row["building_code"],
            "photos": _j(row["approved_photos"]),
            "photo_evidence": _j(row["photo_evidence"]),
            "transcription": row["transcription_text"],
            "voice_note_url": row["voice_note_url"],
            "line_items": _j(row["structured_line_items"]),
            "pdf_url": row["pdf_url"],
            "bounty_status": row["bounty_status"],
            "crm_status": row["crm_status"],
            "supplement_value": float(row["supplement_value"]) if row["supplement_value"] is not None else None,
            "current_state": row["current_state"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    @staticmethod
    def _crew(row) -> CrewMember:
        return CrewMember(
            crew_id=row["crew_id"], company_id=row["company_id"],
            phone_number=row["phone_number"], full_name=row["full_name"],
            role=row["role"], preferred_language=row["preferred_language"],
            total_bounties_earned=row["total_bounties_earned"],
            last_inbound_at=row["last_inbound_at"],
        )

    @staticmethod
    def _company(row) -> Company:
        return Company(
            company_id=row["company_id"], company_name=row["company_name"],
            invite_code=row["invite_code"], crm_type=row["crm_type"],
            crm_webhook_url=row["crm_webhook_url"],
        )

    @staticmethod
    def _operator(row) -> Operator:
        return Operator(
            operator_id=row["operator_id"], company_id=row["company_id"],
            email=row["email"], password_hash=row["password_hash"], role=row["role"],
        )

    @staticmethod
    def _jobsite(row) -> Jobsite:
        return Jobsite(
            job_id=row["job_id"], company_id=row["company_id"],
            property_address=row["property_address"], zip_code=row["zip_code"],
            city=row["city"], state=row["state"], claim_number=row["claim_number"],
            county=row["county"], municipal_code_summary=row["municipal_code_summary"],
        )

    @staticmethod
    def _session(row) -> InspectionSession:
        import json
        def _j(v):
            return json.loads(v) if isinstance(v, str) else (v or [])
        return InspectionSession(
            session_id=row["session_id"], crew_id=row["crew_id"], job_id=row["job_id"],
            current_state=row["current_state"], approved_photos=_j(row["approved_photos"]),
            photo_evidence=_j(row["photo_evidence"]),
            voice_note_url=row["voice_note_url"], transcription_text=row["transcription_text"],
            structured_line_items=_j(row["structured_line_items"]), pdf_url=row["pdf_url"],
            bounty_status=row["bounty_status"],
            crm_status=row["crm_status"], supplement_value=row["supplement_value"],
            created_at=row["created_at"],
        )
