"""Inbound webhook idempotency guard (dedupe on provider message id).

WhatsApp webhooks (both Meta Cloud API and Twilio) are *at-least-once*: the provider
re-delivers the same inbound message whenever it doesn't get a fast 2xx, and Meta in
particular sometimes double-delivers even on success. Every delivery carries the same
message id (Meta `messages[].id` / Twilio `MessageSid`), so we drop a repeat before it
ever reaches the state machine — otherwise a single "Demo" produced two welcome messages.

Scope for the demo: a process-local, bounded LRU set. `check_and_mark` is synchronous, so
within the single asyncio worker the check-and-insert is atomic (no await in between) and
two near-simultaneous duplicates can't both slip through. This does NOT dedupe across the
documented multi-worker deploy — that needs a shared store (Redis / a Postgres
`processed_messages` table); tracked with the other post-demo hardening items.
"""

from __future__ import annotations

import threading
from collections import OrderedDict


class MessageDedup:
    """Bounded set of recently-seen message ids with atomic check-and-mark."""

    def __init__(self, capacity: int = 4096) -> None:
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._capacity = capacity
        self._lock = threading.Lock()

    def check_and_mark(self, message_id: str | None) -> bool:
        """Return True if this id was already seen (caller should skip). A new id is
        recorded and returns False. A missing id can't be deduped, so it returns False
        (process it) — Twilio/Meta always send one in practice; tests omit it."""
        if not message_id:
            return False
        with self._lock:
            if message_id in self._seen:
                self._seen.move_to_end(message_id)
                return True
            self._seen[message_id] = None
            if len(self._seen) > self._capacity:
                self._seen.popitem(last=False)  # evict oldest
            return False


_dedup = MessageDedup()


def get_dedup() -> MessageDedup:
    """Process-wide singleton, shared by the Meta and Twilio webhook routers."""
    return _dedup
