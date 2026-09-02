"""CodeVerity de-risk spike: Twilio WhatsApp webhook + interactive state routing.

Proves:
  * Sub-50ms ACK: the webhook returns an empty <Response/> immediately and defers the
    "next message" send to a background task (PRD §3.1).
  * Deterministic routing on the inbound `ButtonPayload` field (the de-risk finding).
  * 24h session-window enforcement before any unapproved interactive send.

Routing and parsing are pure functions so the test harness can exercise them without a
running server or a live Twilio account.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import BackgroundTasks, FastAPI, Request, Response

from session_window import session_window
from whatsapp_client import get_sender

app = FastAPI(title="CodeVerity WhatsApp Spike")

# Empty TwiML — the fast ACK that stops Twilio's 15s timeout from ever firing.
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

# Map a template friendly-name to its ContentSid. Offline, we emit a sentinel so the
# outbox still records which template WOULD be sent.
_TEMPLATE_ENV = {
    "codeverity_company_list": "CONTENT_SID_COMPANY_LIST",
    "codeverity_jobsite_list": "CONTENT_SID_JOBSITE_LIST",
    "codeverity_location_confirm": "CONTENT_SID_LOCATION_CONFIRM",
    "codeverity_photo_qa": "CONTENT_SID_PHOTO_QA",
    "codeverity_voice_confirm": "CONTENT_SID_VOICE_CONFIRM",
}


def content_sid_for(template_name: str) -> str:
    env_key = _TEMPLATE_ENV.get(template_name, "")
    return os.environ.get(env_key) or f"OFFLINE:{template_name}"


@dataclass
class InboundMessage:
    from_: str
    body: str
    button_payload: str | None
    profile_name: str | None
    num_media: int
    message_sid: str | None


def parse_inbound(form: dict) -> InboundMessage:
    """Parse a Twilio inbound webhook form into a typed message.

    Twilio returns the tapped quick-reply / list `id` in `ButtonPayload`. Some list
    replies also arrive as `ListId`; we treat either as the routing key.
    """
    payload = form.get("ButtonPayload") or form.get("ListId") or None
    return InboundMessage(
        from_=form.get("From", ""),
        body=form.get("Body", "") or "",
        button_payload=payload,
        profile_name=form.get("ProfileName"),
        num_media=int(form.get("NumMedia", "0") or "0"),
        message_sid=form.get("MessageSid"),
    )


@dataclass
class NextAction:
    """What to send next. `template` OR `text` is set, never both."""
    template: str | None = None
    text: str | None = None
    variables: dict | None = None


# ButtonPayload id -> next action. `None` key = first inbound (no payload yet).
def decide_next(msg: InboundMessage) -> NextAction:
    payload = msg.button_payload

    # First contact / free-form entry -> State 0.5 company selection.
    if payload is None:
        # In production: DB identity lookup on msg.from_ happens here first.
        return NextAction(template="codeverity_company_list")

    # State 0.5 -> State 1 (jobsite selection)
    if payload in {"company_apex", "company_titan", "enter_company_code"}:
        return NextAction(
            template="codeverity_jobsite_list",
            variables={"1": "1420 Elmwood Dr", "2": "Claim #A-1029"},
        )

    # State 1 -> State 2 (location confirm)
    if payload in {"job_1", "new_jobsite"}:
        return NextAction(
            template="codeverity_location_confirm",
            variables={"1": "1420 Elmwood Dr, Dallas, TX 75201"},
        )

    # State 2 branches
    if payload == "confirm_address":
        return NextAction(
            template="codeverity_photo_qa",
            variables={"1": "Address locked. Upload 3–8 roof photos, then tap below."},
        )
    if payload in {"edit_address", "resend_gps"}:
        return NextAction(
            template="codeverity_location_confirm",
            variables={"1": "Please resend your GPS pin or a photo of the house front."},
        )

    # State 3 branches
    if payload in {"retake_photo", "add_more_photos"}:
        return NextAction(
            template="codeverity_photo_qa",
            variables={"1": "Send the photo now, then tap below."},
        )
    if payload == "skip_to_voice":
        return NextAction(template="codeverity_voice_confirm")

    # State 4 branches
    if payload == "submit_package":
        return NextAction(
            text="✅ Package submitted. $25 bounty locked. The office will review shortly."
        )
    if payload in {"rerecord_voice", "add_note"}:
        return NextAction(template="codeverity_voice_confirm")

    # Unknown payload -> restart safely.
    return NextAction(template="codeverity_company_list")


def dispatch(to: str, action: NextAction) -> None:
    """Perform the outbound send. Runs in a background task off the webhook path.

    Guarded by the 24h window: an unapproved interactive/free-form send outside the
    window would be rejected by WhatsApp (error 63016), so we detect and log it instead.
    """
    sender = get_sender()
    if session_window.requires_approved_template(to):
        # Production: send a pre-approved re-engagement template here.
        print(f"[OUT-OF-SESSION] {to}: would need an APPROVED template to re-engage.")
        return
    if action.template:
        sender.send_content(to, content_sid_for(action.template), action.variables)
    elif action.text:
        sender.send_text(to, action.text)


@app.post("/api/v1/whatsapp/webhook")
async def whatsapp_webhook(request: Request, background: BackgroundTasks) -> Response:
    form = dict(await request.form())
    msg = parse_inbound(form)

    # Every inbound (re)opens the 24h window — record BEFORE deciding what to send.
    if msg.from_:
        session_window.record_inbound(msg.from_)

    action = decide_next(msg)
    # Defer the actual send so the webhook returns in well under 50ms.
    background.add_task(dispatch, msg.from_, action)

    return Response(content=EMPTY_TWIML, media_type="application/xml")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
