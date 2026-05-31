"""
# backend/core/api/auth_routes.py

Authentication REST API routes.

- POST /api/auth/signup — Create account + return JWT
- POST /api/auth/login — Authenticate + return JWT
- GET /api/auth/me — Get current user from Bearer token
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import get_db
from core.auth.auth_service import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/signup")
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    result = await auth_service.signup(
        db=db, email=body.email, password=body.password,
        first_name=body.first_name, last_name=body.last_name,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await auth_service.login(db=db, email=body.email, password=body.password)
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


@router.get("/me")
async def get_me(
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")

    token = authorization[7:]  # Strip "Bearer "
    user = await auth_service.get_current_user(db=db, token=token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return user
