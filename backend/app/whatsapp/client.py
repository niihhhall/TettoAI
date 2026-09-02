"""WhatsApp senders.

  * TwilioSender  — real sends via the Twilio SDK using Content templates.
  * OutboxSender  — in-memory capture for offline tests / local runs.

Sends are always guarded by the 24h session window at the state-machine layer, so an
out-of-session unapproved send never reaches Twilio (would be error 63016).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from app.whatsapp.templates import content_sid_for

logger = logging.getLogger("codeverity")


@dataclass
class SentMessage:
    to: str
    content_sid: str | None = None
    variables: dict | None = None
    body: str | None = None


class Sender(Protocol):
    def send_template(self, to: str, template: str, variables: dict | None = None) -> SentMessage: ...
    def send_text(self, to: str, body: str) -> SentMessage: ...


class OutboxSender:
    def __init__(self) -> None:
        self.outbox: list[SentMessage] = []

    def send_template(self, to: str, template: str, variables: dict | None = None) -> SentMessage:
        msg = SentMessage(to=to, content_sid=content_sid_for(template), variables=variables)
        self.outbox.append(msg)
        return msg

    def send_text(self, to: str, body: str) -> SentMessage:
        msg = SentMessage(to=to, body=body)
        self.outbox.append(msg)
        return msg

    def clear(self) -> None:
        self.outbox.clear()


class TwilioSender:
    def __init__(self) -> None:
        from twilio.rest import Client

        from app.config import get_settings

        s = get_settings()
        self._client = Client(s.TWILIO_ACCOUNT_SID, s.TWILIO_AUTH_TOKEN)
        self._from = s.TWILIO_WHATSAPP_FROM

    def send_template(self, to: str, template: str, variables: dict | None = None) -> SentMessage:
        content_sid = content_sid_for(template)
        try:
            self._client.messages.create(
                from_=self._from,
                to=to,
                content_sid=content_sid,
                content_variables=json.dumps(variables or {}),
            )
        except Exception as e:
            # Never let a single failed send (rate limit 63038, transient 5xx, etc.) abort the
            # rest of the turn or crash the background task. Log and continue best-effort.
            logger.warning("WhatsApp send_template(%s) to %s failed: %s", template, to, e)
        return SentMessage(to=to, content_sid=content_sid, variables=variables)

    def send_text(self, to: str, body: str) -> SentMessage:
        try:
            self._client.messages.create(from_=self._from, to=to, body=body)
        except Exception as e:
            logger.warning("WhatsApp send_text to %s failed: %s", to, e)
        return SentMessage(to=to, body=body)
