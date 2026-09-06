"""Meta WhatsApp Cloud API webhook: GET verification handshake + POST inbound.

Reuses the provider-agnostic `process` (state machine + configured sender) from the Twilio
router, so the whole intake flow is identical regardless of channel. Only the wire format
differs: Meta sends JSON (entry -> changes -> value -> messages) instead of Twilio's form.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import PlainTextResponse

from app.config import get_settings
from app.models import InboundMessage
from app.routers.whatsapp import process
from app.whatsapp.dedup import get_dedup

router = APIRouter(prefix="/api/v1/whatsapp/meta", tags=["whatsapp-meta"])
logger = logging.getLogger("codeverity")


@router.get("")
async def verify(request: Request) -> Response:
    """Meta webhook verification: echo hub.challenge when the verify token matches."""
    s = get_settings()
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and s.META_VERIFY_TOKEN
        and params.get("hub.verify_token") == s.META_VERIFY_TOKEN
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    return Response(status_code=403)


def _verify_signature(raw: bytes, header: str | None, app_secret: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def parse_meta_inbound(body: dict) -> InboundMessage | None:
    """Parse a Meta webhook payload into an InboundMessage. Returns None for non-message
    callbacks (delivery/read statuses) so they're acknowledged but not processed."""
    try:
        value = body["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return None

    messages = value.get("messages")
    if not messages:
        return None  # status/delivery/read receipt — ignore

    m = messages[0]
    wa_from = m.get("from", "")
    from_ = ("+" + wa_from) if (wa_from and not wa_from.startswith("+")) else wa_from

    contacts = value.get("contacts") or []
    profile = (contacts[0].get("profile") or {}).get("name") if contacts else None

    mtype = m.get("type")
    body_text = ""
    payload = None
    media_urls: list[str] = []
    media_types: list[str] = []
    lat = lon = None
    loc_label = None

    if mtype == "text":
        body_text = (m.get("text") or {}).get("body", "")
    elif mtype == "interactive":
        inter = m.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        payload = reply.get("id")
    elif mtype == "button":  # quick-reply on a template message
        btn = m.get("button") or {}
        payload = btn.get("payload")
        body_text = btn.get("text", "")
    elif mtype in ("image", "audio", "video", "document", "sticker"):
        media = m.get(mtype) or {}
        mid = media.get("id")
        if mid:
            media_urls = [mid]
            media_types = [media.get("mime_type") or f"{mtype}/"]
    elif mtype == "location":
        loc = m.get("location") or {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        loc_label = loc.get("address") or loc.get("name")

    def _f(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return InboundMessage(
        from_=from_, body=body_text or "", button_payload=payload,
        profile_name=profile, num_media=len(media_urls),
        media_urls=media_urls, media_content_types=media_types,
        message_sid=m.get("id"),
        latitude=_f(lat), longitude=_f(lon), location_label=loc_label,
    )


@router.post("")
async def webhook(request: Request, background: BackgroundTasks) -> Response:
    s = get_settings()
    raw = await request.body()
    # Optional but recommended: verify the payload signature when an app secret is configured.
    if s.META_APP_SECRET:
        if not _verify_signature(raw, request.headers.get("X-Hub-Signature-256"), s.META_APP_SECRET):
            return Response(content="invalid signature", status_code=403)
    try:
        body = json.loads(raw)
    except Exception:
        return Response(status_code=200)  # ack malformed bodies so Meta stops retrying
    inbound = parse_meta_inbound(body)
    if inbound is not None:
        # Meta is at-least-once: drop a re-delivered message id so the state machine
        # (and its welcome/onboarding replies) only runs once per real message.
        if get_dedup().check_and_mark(inbound.message_sid):
            logger.info("Meta webhook: duplicate message %s ignored", inbound.message_sid)
        else:
            background.add_task(process, inbound)
    # Always 200 fast — Meta retries aggressively on non-2xx.
    return Response(status_code=200)
