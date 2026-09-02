"""Phase 2 offline tests: full state machine + webhook contract.

No DB, no Twilio. InMemoryRepository + StubServices + OutboxSender, driven with
asyncio.run so we don't need a pytest-asyncio plugin.
"""

from __future__ import annotations

import asyncio
import os
import time
from decimal import Decimal

# Offline tests run without real infra; provide mandatory settings before any Settings load.
os.environ.setdefault("DATABASE_URL", "postgresql://u:p@localhost/db?sslmode=disable")
os.environ.setdefault("JWT_SECRET", "test-secret")
# Force offline WhatsApp behavior even when a real local .env is present (deterministic tests).
for _k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "PUBLIC_BASE_URL",
           "CONTENT_SID_COMPANY_LIST", "CONTENT_SID_JOBSITE_LIST", "CONTENT_SID_LOCATION_CONFIRM",
           "CONTENT_SID_PHOTO_QA", "CONTENT_SID_VOICE_CONFIRM"):
    os.environ[_k] = ""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import configure_runtime
from app.models import InboundMessage, State
from app.repository import InMemoryRepository
from app.services import StubServices
from app.whatsapp.client import OutboxSender
from app.whatsapp.state_machine import StateMachine
from app.whatsapp.templates import validate_templates
from app.routers import whatsapp

KNOWN = "whatsapp:+12145550199"      # Marcus Johnson (seeded, Apex) — as Twilio sends it
KNOWN_E164 = "+12145550199"          # as stored in the DB
UNKNOWN = "whatsapp:+19995550000"
UNKNOWN_E164 = "+19995550000"


def run(coro):
    return asyncio.run(coro)


def machine() -> tuple[StateMachine, InMemoryRepository]:
    repo = InMemoryRepository()
    return StateMachine(repo, StubServices()), repo


def inbound(from_=KNOWN, body="", payload=None, num_media=0, media=None, types=None,
            latitude=None, longitude=None):
    return InboundMessage(
        from_=from_, body=body, button_payload=payload, num_media=num_media,
        media_urls=media or [], media_content_types=types or [],
        latitude=latitude, longitude=longitude,
    )


# --- Templates -------------------------------------------------------------------

def test_templates_valid():
    assert validate_templates() == []


# --- Known crew: full happy path -------------------------------------------------

def test_known_crew_first_contact_gets_jobsite_list():
    sm, _ = machine()
    actions = run(sm.handle(inbound(body="hi")))
    assert actions[-1].template == "codeverity_jobsite_list"


def test_full_happy_path_known_crew():
    sm, repo = machine()
    crew = run(repo.get_crew_by_phone(KNOWN_E164))

    run(sm.handle(inbound(body="hi")))                       # create session -> STATE_1

    a = run(sm.handle(inbound(payload="job_1")))             # STATE_1 -> STATE_2 (ask for GPS)
    assert a[-1].text and "location" in a[-1].text.lower()

    a = run(sm.handle(inbound(latitude=32.7801, longitude=-96.8000)))  # share GPS -> geocode
    assert a[-1].template == "codeverity_location_confirm"
    assert a[-1].variables and a[-1].variables.get("1")   # a real detected address is shown

    a = run(sm.handle(inbound(payload="confirm_address")))   # STATE_2 -> STATE_3 (photo prompt)
    assert a[-1].text and "one at a time" in a[-1].text.lower()

    # Photos one at a time — each good photo gets an auto caption + voice-note invite.
    a = run(sm.handle(inbound(num_media=1, media=["u1.jpg"], types=["image/jpeg"])))
    assert a and "photo 1" in a[-1].text.lower()
    a = run(sm.handle(inbound(num_media=1, media=["u2.jpg"], types=["image/jpeg"])))
    assert a and "photo 2" in a[-1].text.lower()

    run(sm._finish_photos(KNOWN_E164))                       # quiet-timer fires -> STATE_4

    a = run(sm.handle(inbound(num_media=1,                    # voice note -> extract
                              media=["audio1"], types=["audio/ogg"])))
    assert a[-1].template == "codeverity_voice_confirm"

    a = run(sm.handle(inbound(payload="submit_package")))    # STATE_4 -> COMPLETE
    assert a[-1].text and "submitted" in a[-1].text.lower()

    # Submission does NOT credit — package is complete but bounty stays PENDING until the
    # office approves (spec R8). Photos + line items + PDF are persisted.
    session = next(s for s in repo.sessions.values() if s.crew_id == crew.crew_id)
    assert session.current_state == State.COMPLETE
    assert session.bounty_status == "PENDING"
    assert len(session.approved_photos) == 2
    assert len(session.photo_evidence) == 2
    assert session.photo_evidence[0]["caption"]              # vision auto-caption stored
    assert len(session.structured_line_items) == 3
    assert session.pdf_url and session.pdf_url.endswith(".pdf")
    assert run(repo.get_crew_by_phone(KNOWN_E164)).total_bounties_earned == Decimal("0.00")

    # Office approval credits the bounty exactly once (idempotent on repeat).
    assert run(repo.approve_inspection(session.session_id, Decimal("25.00"))) is True
    assert run(repo.approve_inspection(session.session_id, Decimal("25.00"))) is False
    assert session.bounty_status == "APPROVED"
    assert run(repo.get_crew_by_phone(KNOWN_E164)).total_bounties_earned == Decimal("25.00")


def test_photos_caption_on_good_and_flag_duplicate():
    sm, _ = machine()
    run(sm.handle(inbound(body="hi")))
    run(sm.handle(inbound(payload="job_1")))
    run(sm.handle(inbound(payload="confirm_address")))       # -> PHOTOS
    a = run(sm.handle(inbound(num_media=1, media=["shot.jpg"], types=["image/jpeg"])))
    assert a and "photo 1" in a[-1].text.lower()             # good photo -> auto caption
    a = run(sm.handle(inbound(num_media=1, media=["shot.jpg"], types=["image/jpeg"])))
    assert a and "duplicate" in a[0].text.lower()            # same photo -> flagged


def test_per_photo_voice_note_attaches_to_last_photo():
    sm, repo = machine()
    run(sm.handle(inbound(body="hi")))
    run(sm.handle(inbound(payload="job_1")))
    run(sm.handle(inbound(payload="confirm_address")))       # -> PHOTOS
    run(sm.handle(inbound(num_media=1, media=["shot.jpg"], types=["image/jpeg"])))
    # An optional voice note during the photo step attaches to that photo (stays in PHOTOS).
    a = run(sm.handle(inbound(num_media=1, media=["voice.ogg"], types=["audio/ogg"])))
    assert a and "voice note added to photo 1" in a[-1].text.lower()
    crew = run(repo.get_crew_by_phone(KNOWN_E164))
    session = run(repo.get_active_session(crew.crew_id))
    assert session.current_state == State.PHOTOS
    assert session.photo_evidence[0]["voice_note_url"]
    assert session.photo_evidence[0]["transcript"]


def test_new_jobsite_autocreated_from_gps():
    sm, repo = machine()
    run(sm.handle(inbound(body="hi")))                    # -> STATE_1
    before = len(repo.jobsites)
    a = run(sm.handle(inbound(payload="new_jobsite")))    # -> STATE_2, asks for GPS
    assert a[-1].text and "location" in a[-1].text.lower()
    a = run(sm.handle(inbound(latitude=40.0, longitude=-74.0)))  # share GPS -> create jobsite
    assert a[-1].template == "codeverity_location_confirm"
    assert len(repo.jobsites) == before + 1  # a jobsite was auto-created from the pin


def test_edit_address_reprompts_location():
    sm, _ = machine()
    run(sm.handle(inbound(body="hi")))
    run(sm.handle(inbound(payload="job_1")))
    a = run(sm.handle(inbound(payload="edit_address")))
    assert a[-1].text and "location" in a[-1].text.lower()


# --- Onboarding (State 0.5) ------------------------------------------------------

def test_onboarding_new_worker_via_list_pick():
    sm, repo = machine()
    a = run(sm.handle(inbound(from_=UNKNOWN, body="hello")))  # first contact
    assert "full name" in a[0].text.lower()

    a = run(sm.handle(inbound(from_=UNKNOWN, body="Marcus Doe")))  # name
    assert a[0].template == "codeverity_company_list"

    a = run(sm.handle(inbound(from_=UNKNOWN, payload="company_apex")))  # pick company
    assert "linked to" in a[0].text.lower()
    assert a[-1].template == "codeverity_jobsite_list"

    crew = run(repo.get_crew_by_phone(UNKNOWN_E164))
    assert crew is not None and crew.full_name == "Marcus Doe"


def test_onboarding_via_manual_code_entry():
    sm, repo = machine()
    run(sm.handle(inbound(from_=UNKNOWN, body="hello")))
    run(sm.handle(inbound(from_=UNKNOWN, body="Jane Smith")))
    a = run(sm.handle(inbound(from_=UNKNOWN, payload="enter_company_code")))
    assert "company code" in a[0].text.lower()
    a = run(sm.handle(inbound(from_=UNKNOWN, body="4821")))
    assert a[-1].template == "codeverity_jobsite_list"
    assert run(repo.get_crew_by_phone(UNKNOWN_E164)).full_name == "Jane Smith"


def test_onboarding_rejects_bad_code():
    sm, _ = machine()
    run(sm.handle(inbound(from_=UNKNOWN, body="hello")))
    run(sm.handle(inbound(from_=UNKNOWN, body="Bad Code Bob")))
    a = run(sm.handle(inbound(from_=UNKNOWN, body="0000")))
    assert "not recognized" in a[0].text.lower()


# --- Webhook HTTP contract (no DB lifespan) --------------------------------------

def _webhook_client() -> tuple[TestClient, OutboxSender]:
    outbox = OutboxSender()
    configure_runtime(InMemoryRepository(), sender=outbox, services=StubServices())
    test_app = FastAPI()
    test_app.include_router(whatsapp.router)
    return TestClient(test_app), outbox


def test_webhook_returns_empty_twiml_fast():
    client, _ = _webhook_client()
    start = time.perf_counter()
    resp = client.post("/api/v1/whatsapp/webhook",
                       data={"From": KNOWN, "Body": "hi", "NumMedia": "0"})
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text
    assert "application/xml" in resp.headers["content-type"]
    assert elapsed_ms < 500


def test_webhook_processes_and_sends():
    client, outbox = _webhook_client()
    # TestClient runs background tasks after the response returns.
    client.post("/api/v1/whatsapp/webhook", data={"From": KNOWN, "Body": "hi", "NumMedia": "0"})
    assert len(outbox.outbox) == 1
    assert outbox.outbox[0].content_sid == "OFFLINE:codeverity_jobsite_list"


def test_webhook_parses_button_payload_and_media():
    msg = whatsapp.parse_inbound({
        "From": KNOWN, "ButtonPayload": "confirm_address", "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/media/abc", "MediaContentType0": "image/jpeg",
    })
    assert msg.button_payload == "confirm_address"
    assert msg.num_media == 1
    assert msg.media_urls == ["https://api.twilio.com/media/abc"]
