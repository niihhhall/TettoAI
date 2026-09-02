"""Operator authentication: password hashing (stdlib pbkdf2) + JWT sessions.

No compiled dependencies — pbkdf2_hmac(sha256) for hashing and PyJWT (pure Python) for
short-lived HS256 session tokens. Company-scoped: every token carries `company_id`, and
the `require_operator` dependency turns it into a Principal that routers use to enforce
tenant isolation.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException

from app.config import get_settings

_ALGO = "HS256"
_PBKDF2_ITERATIONS = 200_000


# --- Password hashing -----------------------------------------------------------

def hash_password(password: str, *, salt: str | None = None,
                  iterations: int = _PBKDF2_ITERATIONS) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt, digest = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


# --- Sessions -------------------------------------------------------------------

@dataclass
class Principal:
    operator_id: str
    company_id: str
    email: str


def _secret() -> str:
    s = get_settings()
    if not s.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    return s.JWT_SECRET


def create_token(operator_id: str, company_id: str, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(operator_id),
        "company_id": str(company_id),
        "email": email,
        "iat": now,
        "exp": now + get_settings().JWT_TTL_MINUTES * 60,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def decode_token(token: str) -> Principal:
    payload = jwt.decode(token, _secret(), algorithms=[_ALGO])
    return Principal(
        operator_id=str(payload["sub"]),
        company_id=str(payload["company_id"]),
        email=payload.get("email", ""),
    )


def principal_from_token(token: str | None) -> Principal | None:
    """Non-raising decode for WebSocket query-param auth (browsers can't set headers)."""
    if not token:
        return None
    try:
        return decode_token(token)
    except Exception:
        return None


async def require_operator(authorization: str | None = Header(default=None)) -> Principal:
    """FastAPI dependency: require a valid `Authorization: Bearer <jwt>`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired token")
