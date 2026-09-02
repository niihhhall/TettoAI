"""Meta WhatsApp Cloud API sender + template translation.

Within the 24-hour customer-service window (opened when the foreman messages us first),
interactive messages — reply buttons and lists — can be sent free-form, with no pre-approved
templates. So we translate the same TEMPLATES definitions used for Twilio into Meta
interactive payloads at send time. Plain text sends map directly.

Sends are best-effort and never raise (parity with the resilient TwilioSender): a failed
send is logged, not propagated, so one drop can't abort the rest of a turn.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.whatsapp.client import SentMessage
from app.whatsapp.templates import TEMPLATES

logger = logging.getLogger("codeverity")


def _sub(text: str | None, variables: dict | None) -> str:
    """Substitute {{1}}, {{2}} ... placeholders with the provided variables."""
    out = text or ""
    for k, v in (variables or {}).items():
        out = out.replace("{{" + str(k) + "}}", str(v))
    return out


def _clip(text: str | None, limit: int) -> str:
    s = text or ""
    return s if len(s) <= limit else s[: limit - 1] + "…"


def build_meta_message(to: str, template: str, variables: dict | None = None) -> dict:
    """Translate a TEMPLATES entry into a Meta /messages payload.

    quick-reply -> interactive "button" (<=3 reply buttons).
    list-picker -> interactive "list" (<=10 rows). Meta length caps are enforced with _clip.
    """
    spec = TEMPLATES.get(template, {})
    variables = variables or {}

    if "twilio/quick-reply" in spec:
        qr = spec["twilio/quick-reply"]
        buttons = [
            {"type": "reply", "reply": {"id": a["id"], "title": _clip(a["title"], 20)}}
            for a in qr["actions"][:3]
        ]
        return {
            "messaging_product": "whatsapp", "to": to, "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": _clip(_sub(qr["body"], variables) or "…", 1024)},
                "action": {"buttons": buttons},
            },
        }

    if "twilio/list-picker" in spec:
        lp = spec["twilio/list-picker"]
        rows = [
            {
                "id": it["id"],
                "title": _clip(_sub(it["item"], variables), 24),
                "description": _clip(_sub(it.get("description", ""), variables), 72),
            }
            for it in lp["items"][:10]
        ]
        return {
            "messaging_product": "whatsapp", "to": to, "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": _clip(_sub(lp["body"], variables) or "…", 1024)},
                "action": {
                    "button": _clip(lp.get("button", "Select"), 20),
                    "sections": [{"title": "Options", "rows": rows}],
                },
            },
        }

    # Unknown template — fall back to plain text so nothing is silently dropped.
    return {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": template}}


class MetaSender:
    """Implements the Sender protocol against the Meta WhatsApp Cloud API."""

    def __init__(self) -> None:
        s = get_settings()
        self._token = s.META_ACCESS_TOKEN or ""
        self._url = (
            f"https://graph.facebook.com/{s.META_GRAPH_VERSION}/"
            f"{s.META_PHONE_NUMBER_ID}/messages"
        )
        self._client = httpx.Client(timeout=30)

    @staticmethod
    def _to(to: str) -> str:
        """State machine passes 'whatsapp:+E164' or bare; Meta wants the wa_id (digits, no +)."""
        t = to.split(":", 1)[1] if ":" in to else to
        return t.lstrip("+").strip()

    def _post(self, payload: dict) -> None:
        try:
            resp = self._client.post(
                self._url, json=payload, headers={"Authorization": f"Bearer {self._token}"}
            )
            if resp.status_code >= 400:
                logger.warning("Meta send failed %s: %s", resp.status_code, resp.text[:300])
        except Exception as e:
            logger.warning("Meta send error to %s: %s", payload.get("to"), e)

    def send_template(self, to: str, template: str, variables: dict | None = None) -> SentMessage:
        self._post(build_meta_message(self._to(to), template, variables))
        return SentMessage(to=to, content_sid=template, variables=variables)

    def send_text(self, to: str, body: str) -> SentMessage:
        self._post({
            "messaging_product": "whatsapp", "to": self._to(to),
            "type": "text", "text": {"body": body},
        })
        return SentMessage(to=to, body=body)
