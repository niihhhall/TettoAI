"""Twilio WhatsApp webhook (PRD §3.1).

Returns an empty <Response/> in well under 50ms and runs all state-machine work +
outbound sends inside a BackgroundTask, so Twilio's 15s timeout never fires.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, Response

import logging

from app.config import get_settings
from app.deps import get_runtime
from app.models import InboundMessage, OutboundAction
from app.whatsapp.dedup import get_dedup

logger = logging.getLogger("codeverity")

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def verify_twilio_signature(request: Request, form: dict) -> bool:
    """Reject spoofed webhooks. Validates X-Twilio-Signature against the auth token.

    Skipped only when no auth token is configured (local/stub runs), so offline tests and
    credential-free local dev still work. In any deployment with a Twilio token, an invalid
    or missing signature is rejected.
    """
    s = get_settings()
    if not s.TWILIO_AUTH_TOKEN or not s.TWILIO_WEBHOOK_VALIDATE:
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False
    from twilio.request_validator import RequestValidator

    validator = RequestValidator(s.TWILIO_AUTH_TOKEN)
    url = (
        s.PUBLIC_BASE_URL.rstrip("/") + request.url.path
        if s.PUBLIC_BASE_URL
        else str(request.url)
    )
    return validator.validate(url, form, signature)


def parse_inbound(form: dict) -> InboundMessage:
    """Parse a Twilio inbound webhook form. The tapped quick-reply / list `id` arrives in
    `ButtonPayload` (or `ListId`); media arrive as MediaUrlN / MediaContentTypeN."""
    num_media = int(form.get("NumMedia", "0") or "0")
    media_urls = [form[f"MediaUrl{i}"] for i in range(num_media) if f"MediaUrl{i}" in form]
    media_types = [form.get(f"MediaContentType{i}", "") for i in range(num_media)]
    payload = form.get("ButtonPayload") or form.get("ListId") or None

    def _float(v: str | None) -> float | None:
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return InboundMessage(
        from_=form.get("From", ""),
        body=form.get("Body", "") or "",
        button_payload=payload,
        profile_name=form.get("ProfileName"),
        num_media=num_media,
        media_urls=media_urls,
        media_content_types=media_types,
        message_sid=form.get("MessageSid"),
        latitude=_float(form.get("Latitude")),
        longitude=_float(form.get("Longitude")),
        location_label=form.get("Address") or form.get("Label"),
    )


async def process(inbound: InboundMessage) -> None:
    """Runs off the webhook path: drive the state machine and send the replies."""
    rt = get_runtime()
    actions: list[OutboundAction] = await rt.machine.handle(inbound)
    for action in actions:
        if action.template:
            rt.sender.send_template(inbound.from_, action.template, action.variables)
        elif action.text:
            rt.sender.send_text(inbound.from_, action.text)


@router.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks) -> Response:
    form = dict(await request.form())
    if not verify_twilio_signature(request, form):
        return Response(content="invalid signature", status_code=403)
    inbound = parse_inbound(form)
    # Twilio re-POSTs on any non-2xx/slow ACK; dedupe on MessageSid so a redelivered
    # webhook doesn't drive the state machine (and its replies) a second time.
    if get_dedup().check_and_mark(inbound.message_sid):
        logger.info("Twilio webhook: duplicate message %s ignored", inbound.message_sid)
    else:
        background.add_task(process, inbound)
    return Response(content=EMPTY_TWIML, media_type="application/xml")
