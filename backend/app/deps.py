"""Runtime dependency container.

main.py configures this on startup (PgRepository + real Services + TwilioSender + WS
manager). Tests configure it with InMemoryRepository + StubServices + OutboxSender. The
routers read it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.repository import Repository
from app.services import Services, StubServices
from app.whatsapp.client import OutboxSender, Sender
from app.whatsapp.state_machine import StateMachine
from app.ws import ConnectionManager


@dataclass
class Runtime:
    repo: Repository
    sender: Sender
    services: Services
    machine: StateMachine
    ws: ConnectionManager


_runtime: Runtime | None = None


def configure_runtime(repo: Repository, sender: Sender | None = None,
                      services: Services | None = None) -> Runtime:
    global _runtime
    services = services or StubServices()
    sender = sender or OutboxSender()
    ws = ConnectionManager()
    # State machine broadcasts completed inspections to all live console clients, and (in
    # production) runs the photo quiet-timer to auto-advance after the foreman stops sending.
    from app.config import get_settings
    machine = StateMachine(repo, services, sender=sender, on_event=ws.broadcast,
                           auto_advance=True, lean_photos=get_settings().WHATSAPP_LEAN_MODE)
    _runtime = Runtime(repo=repo, sender=sender, services=services, machine=machine, ws=ws)
    return _runtime


def get_runtime() -> Runtime:
    if _runtime is None:
        raise RuntimeError("Runtime not configured. Call configure_runtime() on startup.")
    return _runtime
