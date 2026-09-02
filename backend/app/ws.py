"""WebSocket connection manager + keep-alive (PRD §3.3).

Heroku routers drop idle WebSockets after 55s, so the server emits a {"type":"ping"} frame
every 30s. The React dashboard reconnects with exponential backoff on any drop.
"""

from __future__ import annotations

import asyncio

from fastapi import WebSocket

PING_INTERVAL_SECONDS = 30


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()
        # Per-connection tenant, so completion events only reach the owning company.
        self.company: dict[WebSocket, str | None] = {}

    async def connect(self, ws: WebSocket, company_id: str | None = None) -> None:
        await ws.accept()
        self.active.add(ws)
        self.company[ws] = company_id

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)
        self.company.pop(ws, None)

    async def broadcast(self, message: dict) -> None:
        """Fan a JSON message out to live clients; prune any that error.

        If the message carries a company_id (e.g. inspection.completed), only clients of
        that tenant receive it. Messages without one (pings) go to everyone.
        """
        data = message.get("data")
        target_company = data.get("company_id") if isinstance(data, dict) else None
        dead: list[WebSocket] = []
        for ws in list(self.active):
            if target_company is not None and self.company.get(ws) != target_company:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


async def keepalive(ws: WebSocket, interval: int = PING_INTERVAL_SECONDS) -> None:
    """Emit a ping every `interval` seconds until cancelled or the socket dies."""
    try:
        while True:
            await asyncio.sleep(interval)
            await ws.send_json({"type": "ping"})
    except Exception:
        return
