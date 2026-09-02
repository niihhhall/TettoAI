"""CodeVerity FastAPI application entry point.

Phase 1: app skeleton + DB pool lifecycle + health checks.
Phase 2: WhatsApp webhook + state machine wired via the runtime container.
Later phases mount the WebSocket and real service integrations.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.config import Settings, get_settings
from app.db.pool import close_pool, get_pool, init_pool
from app.deps import configure_runtime
from app.repository import PgRepository
from app.routers import auth, inspections, meta_whatsapp, whatsapp
from app.services import StubServices
from app.services.real import RealServices, has_real_credentials
from app.whatsapp.client import OutboxSender, TwilioSender

logger = logging.getLogger("codeverity")


def validate_startup_config(settings: Settings, use_real_services: bool) -> None:
    """Fail fast on unsafe/incomplete production config; warn in non-prod.

    Prevents two footguns: a wildcard CORS origin in production, and a "real" service
    bundle selected with a required dependency (R2 endpoint/bucket, Modal, Mapbox) missing
    — which would otherwise surface as a runtime 500 mid-inspection.
    """
    problems: list[str] = []

    if "*" in settings.cors_origin_list:
        problems.append("CORS_ORIGINS is '*' — set the exact console origin.")

    if not settings.JWT_SECRET:
        problems.append("JWT_SECRET is not set — operator login/auth cannot work.")

    if use_real_services:
        # R2 is truly required for real media/PDF. Modal has a local PDF fallback; Mapbox
        # geocoding is optional until wired — so neither blocks real mode.
        required = {
            "R2_ENDPOINT_URL": settings.R2_ENDPOINT_URL,
            "R2_BUCKET_NAME": settings.R2_BUCKET_NAME,
        }
        missing = [name for name, val in required.items() if not val]
        if missing:
            problems.append(f"real services selected but missing: {', '.join(missing)}")

    if settings.TWILIO_ACCOUNT_SID and not settings.TWILIO_WEBHOOK_VALIDATE:
        problems.append("Twilio configured but signature validation is disabled.")

    if not problems:
        return
    message = "Startup config issues: " + "; ".join(problems)
    if settings.is_production:
        raise RuntimeError(message)
    logger.warning("%s (allowed in %s)", message, settings.ENV)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    use_real_services = has_real_credentials(settings)
    validate_startup_config(settings, use_real_services)
    logger.info("CodeVerity starting: env=%s real_services=%s", settings.ENV, use_real_services)

    pool = await init_pool()

    # Choose a sender by provider. Meta Cloud API when selected + configured; else Twilio
    # when its creds are present; else an in-memory outbox so the app still boots locally.
    if settings.use_meta and settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID:
        from app.whatsapp.meta_client import MetaSender
        sender = MetaSender()
        logger.info("Messaging provider: Meta WhatsApp Cloud API")
    elif settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
        sender = TwilioSender()
        logger.info("Messaging provider: Twilio")
    else:
        sender = OutboxSender()
        logger.info("Messaging provider: in-memory outbox (no live sends)")

    # Real integrations when the credentials exist; otherwise deterministic stubs so the
    # app still boots locally without external accounts.
    services = RealServices(settings) if use_real_services else StubServices()
    configure_runtime(PgRepository(pool), sender=sender, services=services)

    yield

    if isinstance(services, RealServices):
        await services.aclose()
    await close_pool()


app = FastAPI(title="CodeVerity API", version="0.6.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(whatsapp.router)
app.include_router(meta_whatsapp.router)
app.include_router(inspections.router)

# CORS so the Vercel-hosted React console can call the API + WS.
# Configurable via CORS_ORIGINS; defaults to "*" for local dev, lock down in prod.
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if get_settings().is_production:
        resp.headers.setdefault(
            "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
        )
    return resp


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "env": get_settings().ENV}


@app.get("/readyz")
async def readyz():
    """Readiness = DB reachable. Returns 503 (not 500) when the DB is down, so load
    balancers and uptime checks can route/alert correctly."""
    from fastapi.responses import JSONResponse

    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            one = await conn.fetchval("SELECT 1")
        if one == 1:
            return {"status": "ready", "db": True}
    except Exception as exc:  # pragma: no cover - exercised in real deploys
        logger.warning("readiness check failed: %s", exc)
    return JSONResponse(status_code=503, content={"status": "degraded", "db": False})
