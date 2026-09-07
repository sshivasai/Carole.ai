"""
# backend/core/api/auth_routes.py

Authentication REST API routes.

- POST /api/auth/signup — Create account + return JWT
- POST /api/auth/login — Authenticate + return JWT
- GET  /api/auth/me — Get current user from Bearer token

Rate limits (Finding #7):
  - /login  : 10 attempts / minute per IP
  - /signup : 5 attempts / minute per IP
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import get_db
from core.auth.auth_service import auth_service
from core.auth.rate_limiter import rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/signup")
@rate_limit("5/minute")
async def signup(request: Request, body: SignupRequest, db: AsyncSession = Depends(get_db)):
    # Rate limit: 5 signup attempts per minute per IP (enforced by slowapi)
    result = await auth_service.signup(
        db=db, email=body.email, password=body.password,
        first_name=body.first_name, last_name=body.last_name,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/login")
@rate_limit("10/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Rate limit: 10 login attempts per minute per IP (enforced by slowapi)
    result = await auth_service.login(db=db, email=body.email, password=body.password)
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


@router.get("/me")
async def get_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token.")

    token = authorization[7:]
    user = await auth_service.get_current_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token.")

    return user


@router.post("/ws-ticket")
async def get_ws_ticket(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(None)
):
    """Returns a short-lived (30s) WebSocket ticket for authentication."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token.")

    token = authorization[7:]
    user = await auth_service.get_current_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token.")

    ticket = auth_service.generate_ws_ticket(user["id"])
    return {"ticket": ticket}
