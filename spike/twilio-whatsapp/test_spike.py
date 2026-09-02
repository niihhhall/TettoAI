"""Offline test harness for the Twilio WhatsApp de-risk spike.

Runs with NO Twilio account. Uses FastAPI's TestClient + the in-memory OutboxSender to
prove the full send/receive/route round-trip and the guardrails.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main
from content_templates import TEMPLATES, validate_templates
from session_window import SessionWindow
from whatsapp_client import OutboxSender, set_sender

WEBHOOK = "/api/v1/whatsapp/webhook"
FOREMAN = "whatsapp:+12145550199"


@pytest.fixture
def outbox() -> OutboxSender:
    box = OutboxSender()
    set_sender(box)
    # Fresh session state per test.
    main.session_window.__init__()  # type: ignore[misc]
    return box


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


def _post(client: TestClient, **fields) -> None:
    fields.setdefault("From", FOREMAN)
    fields.setdefault("To", "whatsapp:+14155238886")
    client.post(WEBHOOK, data=fields)


# --- Template definition guarantees (the de-risk constraints) ---------------------

def test_templates_are_valid():
    assert validate_templates() == []


def test_quick_replies_capped_at_three():
    for name, types in TEMPLATES.items():
        if "twilio/quick-reply" in types:
            assert len(types["twilio/quick-reply"]["actions"]) <= 3, name


def test_button_ids_are_unique_within_each_template():
    for name, types in TEMPLATES.items():
        if "twilio/quick-reply" in types:
            ids = [a["id"] for a in types["twilio/quick-reply"]["actions"]]
        elif "twilio/list-picker" in types:
            ids = [i["id"] for i in types["twilio/list-picker"]["items"]]
        else:
            continue
        assert len(ids) == len(set(ids)), f"duplicate ids in {name}"


# --- Webhook contract -------------------------------------------------------------

def test_webhook_returns_empty_twiml_fast(client, outbox):
    start = time.perf_counter()
    resp = client.post(WEBHOOK, data={"From": FOREMAN, "Body": "start", "NumMedia": "0"})
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    assert "<Response></Response>" in resp.text
    assert "application/xml" in resp.headers["content-type"]
    # Generous ceiling for CI; proves no heavy work is done inline.
    assert elapsed_ms < 500, f"webhook too slow: {elapsed_ms:.1f}ms"


# --- Inbound parsing --------------------------------------------------------------

def test_parse_extracts_button_payload():
    msg = main.parse_inbound({"From": FOREMAN, "Body": "Apex Roofing", "ButtonPayload": "company_apex"})
    assert msg.button_payload == "company_apex"
    assert msg.from_ == FOREMAN


def test_parse_treats_list_id_as_routing_key():
    msg = main.parse_inbound({"From": FOREMAN, "ListId": "job_1"})
    assert msg.button_payload == "job_1"


# --- State routing ----------------------------------------------------------------

def test_first_contact_sends_company_list(client, outbox):
    _post(client, Body="hi", NumMedia="0")
    assert len(outbox.outbox) == 1
    assert outbox.outbox[0].content_sid == "OFFLINE:codeverity_company_list"


def test_full_happy_path_walks_states(client, outbox):
    # State 0.5 -> pick company -> State 1
    _post(client, ButtonPayload="company_apex")
    assert outbox.outbox[-1].content_sid == "OFFLINE:codeverity_jobsite_list"

    # State 1 -> pick job -> State 2 (location confirm)
    _post(client, ButtonPayload="job_1")
    assert outbox.outbox[-1].content_sid == "OFFLINE:codeverity_location_confirm"

    # State 2 -> confirm address -> State 3 (photo QA)
    _post(client, ButtonPayload="confirm_address")
    assert outbox.outbox[-1].content_sid == "OFFLINE:codeverity_photo_qa"

    # State 3 -> skip to voice -> State 4 (voice confirm)
    _post(client, ButtonPayload="skip_to_voice")
    assert outbox.outbox[-1].content_sid == "OFFLINE:codeverity_voice_confirm"

    # State 4 -> submit -> terminal text w/ bounty
    _post(client, ButtonPayload="submit_package")
    last = outbox.outbox[-1]
    assert last.content_sid is None
    assert "bounty" in (last.body or "").lower()


def test_edit_address_reprompts_location(client, outbox):
    _post(client, ButtonPayload="edit_address")
    assert outbox.outbox[-1].content_sid == "OFFLINE:codeverity_location_confirm"


def test_unknown_payload_restarts_safely(client, outbox):
    _post(client, ButtonPayload="garbage_value")
    assert outbox.outbox[-1].content_sid == "OFFLINE:codeverity_company_list"


# --- 24-hour session window -------------------------------------------------------

def test_out_of_session_blocks_unapproved_send():
    sw = SessionWindow()
    # Last inbound 25h ago -> window closed.
    sw.record_inbound(FOREMAN, at=datetime.now(timezone.utc) - timedelta(hours=25))
    assert sw.requires_approved_template(FOREMAN) is True


def test_fresh_inbound_opens_session():
    sw = SessionWindow()
    sw.record_inbound(FOREMAN)
    assert sw.is_in_session(FOREMAN) is True
    assert sw.requires_approved_template(FOREMAN) is False
