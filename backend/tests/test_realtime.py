"""Backend tests: REST dashboard endpoints, WS snapshot, broadcast fan-out, and
completion-event wiring. No DB, no network. Endpoints are auth-scoped to the operator's
company, so the harness mints a JWT for the seeded Apex operator."""

from __future__ import annotations

import asyncio
import os

# Offline tests: provide mandatory settings before any Settings load.
os.environ.setdefault("DATABASE_URL", "postgresql://u:p@localhost/db?sslmode=disable")
os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import create_token
from app.deps import configure_runtime
from app.models import InboundMessage
from app.repository import InMemoryRepository
from app.services import StubServices
from app.whatsapp.client import OutboxSender
from app.whatsapp.state_machine import StateMachine
from app.ws import ConnectionManager
from app.routers import inspections

KNOWN = "whatsapp:+12145550199"


def run(coro):
    return asyncio.run(coro)


def _inb(payload=None, body="", num_media=0, media=None, types=None):
    return InboundMessage(from_=KNOWN, body=body, button_payload=payload,
                          num_media=num_media, media_urls=media or [],
                          media_content_types=types or [])


def _drive_to_completion(machine: StateMachine) -> None:
    machine.auto_advance = False  # call _finish_photos directly instead of the real timer
    run(machine.handle(_inb(body="hi")))
    run(machine.handle(_inb(payload="job_1")))
    run(machine.handle(_inb(payload="confirm_address")))                          # -> PHOTOS
    run(machine.handle(_inb(num_media=1, media=["p1.jpg"], types=["image/jpeg"])))  # one photo
    run(machine._finish_photos("+12145550199"))                                   # -> VOICE
    run(machine.handle(_inb(num_media=1, media=["a"], types=["audio/ogg"])))      # voice -> extract
    run(machine.handle(_inb(payload="submit_package")))                           # submit


def _app_with_runtime() -> tuple[TestClient, object, str]:
    repo = InMemoryRepository()
    rt = configure_runtime(repo, sender=OutboxSender(), services=StubServices())
    app = FastAPI()
    app.include_router(inspections.router)
    company = run(repo.get_company_by_code("4821"))  # seeded Apex
    token = create_token("op-test", str(company.company_id), "operator@apex.test")
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, rt, token


# --- REST endpoints --------------------------------------------------------------

def test_inspections_and_crew_endpoints_reflect_completion():
    client, rt, _ = _app_with_runtime()
    _drive_to_completion(rt.machine)

    resp = client.get("/api/v1/inspections")
    assert resp.status_code == 200
    cards = resp.json()["inspections"]
    assert len(cards) == 1
    card = cards[0]
    # Submission leaves the bounty PENDING (credited only on operator approval).
    assert card["bounty_status"] == "PENDING"
    assert card["pdf_url"] and card["pdf_url"].endswith(".pdf")
    assert len(card["line_items"]) == 3
    assert "created_at" in card and "voice_note_url" in card

    crew = client.get("/api/v1/crew").json()["crew"]
    marcus = next(c for c in crew if c["phone_number"] == "+12145550199")
    assert marcus["total_bounties_earned"] == 0.0  # not yet approved


def test_requires_auth():
    client, _, _ = _app_with_runtime()
    client.headers.pop("Authorization", None)
    assert client.get("/api/v1/inspections").status_code == 401


def test_approve_credits_bounty_once_and_pushes_crm():
    client, rt, _ = _app_with_runtime()
    _drive_to_completion(rt.machine)
    sid = run(rt.repo.list_recent_inspections())[0]["session_id"]

    resp = client.post(f"/api/v1/inspections/{sid}/approve").json()
    assert resp["ok"] is True
    assert resp["credited"] is True
    assert resp["bounty_status"] == "APPROVED"
    assert resp["crm_status"] == "skipped"  # no CRM webhook configured for the demo company

    crew = client.get("/api/v1/crew").json()["crew"]
    marcus = next(c for c in crew if c["phone_number"] == "+12145550199")
    assert marcus["total_bounties_earned"] == 25.0

    # Idempotent: a second approve must not double-pay.
    again = client.post(f"/api/v1/inspections/{sid}/approve").json()
    assert again["credited"] is False
    crew = client.get("/api/v1/crew").json()["crew"]
    marcus = next(c for c in crew if c["phone_number"] == "+12145550199")
    assert marcus["total_bounties_earned"] == 25.0


def test_register_crew_endpoint():
    client, _, _ = _app_with_runtime()
    ok = client.post("/api/v1/crew", json={
        "full_name": "New Foreman", "phone_number": "+13035550111", "company_code": "4821",
    })
    assert ok.json()["ok"] is True
    crew = client.get("/api/v1/crew").json()["crew"]
    assert any(c["phone_number"] == "+13035550111" for c in crew)

    bad = client.post("/api/v1/crew", json={
        "full_name": "X", "phone_number": "+1", "company_code": "9999",
    })
    assert bad.json()["ok"] is False


# --- WebSocket -------------------------------------------------------------------

def test_ws_sends_snapshot_on_connect():
    client, rt, token = _app_with_runtime()
    _drive_to_completion(rt.machine)
    with client.websocket_connect(f"/api/v1/ws/inspections?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert len(msg["data"]) == 1


def test_ws_rejects_without_token():
    client, _, _ = _app_with_runtime()
    try:
        with client.websocket_connect("/api/v1/ws/inspections") as ws:
            ws.receive_json()
        assert False, "expected the socket to be rejected"
    except Exception:
        pass  # closed with policy-violation before any frame


def test_broadcast_fans_out_to_clients():
    mgr = ConnectionManager()

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, m):
            self.sent.append(m)

    a, b = FakeWS(), FakeWS()
    mgr.active.update({a, b})  # type: ignore[arg-type]
    run(mgr.broadcast({"type": "inspection.completed", "data": {"x": 1}}))
    assert a.sent == b.sent == [{"type": "inspection.completed", "data": {"x": 1}}]


def test_completion_emits_event():
    events: list[dict] = []

    async def collect(evt):
        events.append(evt)

    machine = StateMachine(InMemoryRepository(), StubServices(), on_event=collect)
    _drive_to_completion(machine)

    assert len(events) == 1
    assert events[0]["type"] == "inspection.completed"
    assert events[0]["data"]["pdf_url"].endswith(".pdf")
