"""Operator Console API: live WebSocket feed + REST for the dashboard views (PRD §6)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.auth import Principal, principal_from_token, require_operator
from app.deps import get_runtime
from app.models import BOUNTY_AMOUNT
from app.ws import keepalive

router = APIRouter(prefix="/api/v1", tags=["inspections"])


class CrewRegistration(BaseModel):
    full_name: str
    phone_number: str
    company_code: str


class JobsiteCreate(BaseModel):
    property_address: str
    claim_number: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    county: str | None = None
    municipal_code_summary: str | None = None


class JobsiteUpdate(BaseModel):
    property_address: str | None = None
    claim_number: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    county: str | None = None
    municipal_code_summary: str | None = None


class CompanyCreate(BaseModel):
    company_name: str
    invite_code: str
    crm_type: str = "JobNimbus"
    crm_webhook_url: str | None = None


class CompanyUpdate(BaseModel):
    company_name: str | None = None
    invite_code: str | None = None
    crm_type: str | None = None
    crm_webhook_url: str | None = None


def _jobsite_dict(j) -> dict:
    return {
        "job_id": str(j.job_id),
        "company_id": str(j.company_id),
        "property_address": j.property_address,
        "claim_number": j.claim_number,
        "city": j.city,
        "state": j.state,
        "zip_code": j.zip_code,
        "county": j.county,
        "municipal_code_summary": j.municipal_code_summary,
    }


def _company_dict(c) -> dict:
    return {
        "company_id": str(c.company_id),
        "company_name": c.company_name,
        "invite_code": c.invite_code,
        "crm_type": c.crm_type,
        "crm_webhook_url": c.crm_webhook_url,
    }


@router.get("/inspections")
async def list_inspections(limit: int = 50,
                           principal: Principal = Depends(require_operator)) -> dict:
    """Claims table + live-feed backfill — scoped to the operator's company."""
    rt = get_runtime()
    return {"inspections": await rt.repo.list_recent_inspections(limit, company_id=principal.company_id)}


@router.get("/inspections/{session_id}")
async def get_inspection(session_id: str,
                         principal: Principal = Depends(require_operator)) -> dict:
    rt = get_runtime()
    card = await rt.repo.get_inspection(session_id, company_id=principal.company_id)
    return {"inspection": card}


@router.delete("/inspections/{session_id}")
async def delete_inspection(session_id: str,
                            principal: Principal = Depends(require_operator)) -> dict:
    """Delete an inspection (tenant-scoped) and tell every console of that tenant to drop it."""
    rt = get_runtime()
    ok = await rt.repo.delete_inspection(session_id, company_id=principal.company_id)
    if ok:
        await rt.ws.broadcast({
            "type": "inspection.deleted",
            "data": {"session_id": session_id, "company_id": principal.company_id},
        })
    return {"ok": ok}


@router.get("/crew")
async def list_crew(principal: Principal = Depends(require_operator)) -> dict:
    """Crew Manager + bounty ledger — scoped to the operator's company."""
    rt = get_runtime()
    return {"crew": await rt.repo.list_crew(company_id=principal.company_id)}


@router.post("/crew")
async def register_crew(body: CrewRegistration,
                        principal: Principal = Depends(require_operator)) -> dict:
    """Pre-register a foreman into the operator's OWN company (no cross-tenant writes)."""
    rt = get_runtime()
    company = await rt.repo.get_company_by_code(body.company_code)
    if company is None:
        return {"ok": False, "error": "invalid company code"}
    if str(company.company_id) != principal.company_id:
        return {"ok": False, "error": "company code does not match your account"}
    phone = body.phone_number.strip()
    if await rt.repo.get_crew_by_phone(phone):
        return {"ok": False, "error": "phone already registered"}
    crew = await rt.repo.create_crew_member(phone, body.full_name.strip(), company.company_id)
    return {"ok": True, "crew_id": str(crew.crew_id)}


@router.post("/inspections/{session_id}/approve")
async def approve_and_push(session_id: str,
                           principal: Principal = Depends(require_operator)) -> dict:
    """Approve: push the package to the company CRM, then credit the $25 bounty exactly once.

    Tenant-scoped. The CRM payload includes the generated PDF URL. Crediting is idempotent
    (a second approve does not double-pay). The refreshed card is broadcast so every console
    of the tenant updates live.
    """
    rt = get_runtime()
    card = await rt.repo.get_inspection(session_id, company_id=principal.company_id)
    if card is None:
        return {"ok": False, "error": "not found"}

    company = await rt.repo.get_company_by_id(principal.company_id)
    crm_url = company.crm_webhook_url if company else None
    crm_status = await rt.services.dispatch_crm(crm_url, card)
    await rt.repo.set_crm_status(session_id, crm_status)

    credited = await rt.repo.approve_inspection(session_id, BOUNTY_AMOUNT,
                                                company_id=principal.company_id)

    fresh = await rt.repo.get_inspection(session_id, company_id=principal.company_id)
    await rt.ws.broadcast({"type": "inspection.updated", "data": fresh})
    return {
        "ok": True,
        "session_id": session_id,
        "crm_status": crm_status,
        "credited": credited,
        "bounty_status": fresh["bounty_status"] if fresh else None,
    }


# --- Jobsite management (tenant-scoped) -----------------------------------------

@router.get("/jobsites")
async def list_jobsites(principal: Principal = Depends(require_operator)) -> dict:
    """List jobsites the operator's company owns (foremen pick these on WhatsApp)."""
    rt = get_runtime()
    jobs = await rt.repo.list_jobsites(principal.company_id)
    return {"jobsites": [_jobsite_dict(j) for j in jobs]}


@router.post("/jobsites")
async def create_jobsite(body: JobsiteCreate,
                         principal: Principal = Depends(require_operator)) -> dict:
    """Preload a jobsite into the operator's OWN company (no cross-tenant writes)."""
    if not body.property_address.strip():
        return {"ok": False, "error": "property address is required"}
    rt = get_runtime()
    job = await rt.repo.create_jobsite(
        principal.company_id,
        property_address=body.property_address.strip(),
        city=body.city, county=body.county, zip_code=body.zip_code,
        state=body.state, claim_number=body.claim_number,
        municipal_code_summary=body.municipal_code_summary,
    )
    return {"ok": True, "job_id": str(job.job_id)}


@router.patch("/jobsites/{job_id}")
async def update_jobsite(job_id: str, body: JobsiteUpdate,
                         principal: Principal = Depends(require_operator)) -> dict:
    """Edit a jobsite, guarded to the operator's company."""
    rt = get_runtime()
    existing = await rt.repo.get_jobsite(job_id, company_id=principal.company_id)
    if existing is None:
        return {"ok": False, "error": "not found"}
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if fields:
        await rt.repo.update_jobsite(existing.job_id, **fields)
    return {"ok": True}


# --- Company branches (management surface) --------------------------------------
# NOTE: this is an admin/management view of tenant companies. It exposes only company
# profile fields (name, invite code, CRM config) — never another tenant's inspections or
# crew. In production it would be gated to an admin role; for the demo any operator can
# manage branches.

@router.get("/companies")
async def list_companies(principal: Principal = Depends(require_operator)) -> dict:
    rt = get_runtime()
    companies = await rt.repo.list_companies()
    return {"companies": [_company_dict(c) for c in companies]}


@router.post("/companies")
async def create_company(body: CompanyCreate,
                         principal: Principal = Depends(require_operator)) -> dict:
    if not body.company_name.strip() or not body.invite_code.strip():
        return {"ok": False, "error": "company name and invite code are required"}
    rt = get_runtime()
    if await rt.repo.get_company_by_code(body.invite_code.strip()):
        return {"ok": False, "error": "invite code already in use"}
    company = await rt.repo.create_company(
        body.company_name.strip(), body.invite_code.strip(),
        crm_type=body.crm_type or "JobNimbus", crm_webhook_url=body.crm_webhook_url,
    )
    return {"ok": True, "company_id": str(company.company_id)}


@router.patch("/companies/{company_id}")
async def update_company(company_id: str, body: CompanyUpdate,
                         principal: Principal = Depends(require_operator)) -> dict:
    rt = get_runtime()
    if await rt.repo.get_company_by_id(company_id) is None:
        return {"ok": False, "error": "not found"}
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    # If invite_code is changing, ensure it doesn't collide with a different company.
    if "invite_code" in fields:
        clash = await rt.repo.get_company_by_code(fields["invite_code"].strip())
        if clash and str(clash.company_id) != str(company_id):
            return {"ok": False, "error": "invite code already in use"}
        fields["invite_code"] = fields["invite_code"].strip()
    if fields:
        await rt.repo.update_company(company_id, **fields)
    return {"ok": True}


@router.websocket("/ws/inspections")
async def ws_inspections(ws: WebSocket, token: str | None = Query(default=None)) -> None:
    # WebSocket auth via query param (browsers can't set Authorization on WS).
    principal = principal_from_token(token)
    if principal is None:
        await ws.close(code=1008)  # policy violation
        return
    rt = get_runtime()
    await rt.ws.connect(ws, company_id=principal.company_id)
    # Initial snapshot, scoped to the operator's company.
    await ws.send_json({
        "type": "snapshot",
        "data": await rt.repo.list_recent_inspections(company_id=principal.company_id),
    })

    ping = asyncio.create_task(keepalive(ws))
    try:
        while True:
            # We don't need client messages; receiving detects disconnect.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ping.cancel()
        rt.ws.disconnect(ws)
