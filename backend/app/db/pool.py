"""asyncpg connection-pool lifecycle for Neon Postgres.

Neon connection strings carry `?sslmode=require`, which asyncpg does NOT understand in
the DSN (it raises on the unknown query param). We normalize the DSN and pass an explicit
SSL context instead — a real gotcha that would otherwise fail on first deploy.
"""

from __future__ import annotations

import ssl
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

import asyncpg

from app.config import get_settings

_pool: asyncpg.Pool | None = None


def normalize_dsn(dsn: str) -> tuple[str, ssl.SSLContext | bool]:
    """Strip libpq-style `sslmode` from the DSN and translate it to an asyncpg ssl arg.

    Returns (clean_dsn, ssl_arg). For Neon (`sslmode=require`) we return a permissive
    TLS context (encryption on, no local CA verification) which matches libpq `require`.
    """
    parsed = urlparse(dsn)
    query = parse_qs(parsed.query)
    sslmode = (query.pop("sslmode", ["require"]) or ["require"])[0]
    # asyncpg also rejects libpq's `channel_binding` param (it negotiates this itself).
    query.pop("channel_binding", None)

    clean = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    if sslmode in ("disable", "allow", "prefer"):
        return clean, False
    # require / verify-ca / verify-full -> enable TLS. `require` = encrypt, don't verify.
    ctx = ssl.create_default_context()
    if sslmode == "require":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return clean, ctx


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    settings = get_settings()
    dsn, ssl_arg = normalize_dsn(settings.DATABASE_URL)
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        ssl=ssl_arg,
        min_size=settings.DB_POOL_MIN_SIZE,
        max_size=settings.DB_POOL_MAX_SIZE,
        command_timeout=30,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_pool() on startup.")
    return _pool
