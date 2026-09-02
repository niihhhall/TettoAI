"""WhatsApp send helpers.

Two implementations behind one interface:
  * TwilioSender   — real sends via the Twilio SDK (needs creds).
  * OutboxSender   — records sends to an in-memory list for offline tests / local runs.

The app talks to whichever sender is installed via `set_sender()`, so the same routing
logic is exercised in tests and in production.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SentMessage:
    to: str
    content_sid: str | None = None
    content_variables: dict | None = None
    body: str | None = None


class Sender(Protocol):
    def send_content(self, to: str, content_sid: str, variables: dict | None = None) -> SentMessage: ...
    def send_text(self, to: str, body: str) -> SentMessage: ...


class OutboxSender:
    """Test/local sender. Captures everything instead of hitting Twilio."""

    def __init__(self) -> None:
        self.outbox: list[SentMessage] = []

    def send_content(self, to: str, content_sid: str, variables: dict | None = None) -> SentMessage:
        msg = SentMessage(to=to, content_sid=content_sid, content_variables=variables)
        self.outbox.append(msg)
        return msg

    def send_text(self, to: str, body: str) -> SentMessage:
        msg = SentMessage(to=to, body=body)
        self.outbox.append(msg)
        return msg

    def clear(self) -> None:
        self.outbox.clear()


class TwilioSender:
    """Real sender using the Twilio Python SDK."""

    def __init__(self) -> None:
        from twilio.rest import Client  # local import keeps offline tests dependency-free

        self._client = Client(
            os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
        )
        self._from = os.environ["TWILIO_WHATSAPP_FROM"]

    def send_content(self, to: str, content_sid: str, variables: dict | None = None) -> SentMessage:
        self._client.messages.create(
            from_=self._from,
            to=to,
            content_sid=content_sid,
            content_variables=json.dumps(variables or {}),
        )
        return SentMessage(to=to, content_sid=content_sid, content_variables=variables)

    def send_text(self, to: str, body: str) -> SentMessage:
        self._client.messages.create(from_=self._from, to=to, body=body)
        return SentMessage(to=to, body=body)


# Default to the offline sender; production swaps in TwilioSender at startup.
_sender: Sender = OutboxSender()


def set_sender(sender: Sender) -> None:
    global _sender
    _sender = sender


def get_sender() -> Sender:
    return _sender
