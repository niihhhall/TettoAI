"""Operator authentication endpoints: login + current-operator lookup."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import Principal, create_token, require_operator, verify_password
from app.deps import get_runtime

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
async def login(body: LoginRequest) -> dict:
    rt = get_runtime()
    operator = await rt.repo.get_operator_by_email(body.email.strip().lower())
    if operator is None or not verify_password(body.password, operator.password_hash):
        # Same message for unknown email and bad password — no account enumeration.
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_token(str(operator.operator_id), str(operator.company_id), operator.email)
    company = None
    if operator.company_id:
        company = await rt.repo.get_company_by_id(operator.company_id)
    return {
        "token": token,
        "operator": {
            "email": operator.email,
            "company_id": str(operator.company_id),
            "company_name": company.company_name if company else None,
            "role": operator.role,
        },
    }


@router.get("/me")
async def me(principal: Principal = Depends(require_operator)) -> dict:
    return {
        "operator_id": principal.operator_id,
        "company_id": principal.company_id,
        "email": principal.email,
    }
