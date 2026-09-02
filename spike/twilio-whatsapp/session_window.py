"""24-hour WhatsApp session-window tracker.

The single hardest constraint surfaced during the de-risk: unapproved interactive
messages (quick replies, list pickers) and free-form text only work within 24h of the
foreman's last INBOUND message. Outside that window we must send a pre-approved template.

In the spike this is in-memory. In production this becomes a `last_inbound_at` column on
`crew_members` / `inspection_sessions` in Neon Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

SESSION_TTL = timedelta(hours=24)


class SessionWindow:
    def __init__(self) -> None:
        self._last_inbound: dict[str, datetime] = {}

    def record_inbound(self, phone: str, at: datetime | None = None) -> None:
        """Call on every inbound message from a user — this (re)opens the 24h window."""
        self._last_inbound[phone] = at or datetime.now(timezone.utc)

    def is_in_session(self, phone: str, now: datetime | None = None) -> bool:
        last = self._last_inbound.get(phone)
        if last is None:
            return False
        now = now or datetime.now(timezone.utc)
        return (now - last) <= SESSION_TTL

    def requires_approved_template(self, phone: str, now: datetime | None = None) -> bool:
        """True when we CANNOT send unapproved interactive content / free-form text."""
        return not self.is_in_session(phone, now=now)


# Module-level singleton for the spike app.
session_window = SessionWindow()
