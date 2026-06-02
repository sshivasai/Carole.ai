"""
# backend/core/auth/auth_middleware.py

FastAPI dependency for protecting routes with JWT authentication.

Usage:
    @router.get("/protected")
    async def protected_route(user = Depends(require_auth)):
        return {"user_id": user["id"]}
"""

from typing import Optional
from fastapi import HTTPException, Header

from core.auth.auth_service import _decode_jwt


async def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """
    FastAPI dependency that extracts and validates the JWT from the Authorization header.
    Returns the decoded JWT payload (contains sub, email, iat, exp).
    Raises 401 if missing/invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")

    token = authorization[7:]
    payload = _decode_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    return payload


async def optional_auth(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """
    Same as require_auth but returns None instead of raising if no token.
    Useful for routes that work both authenticated and unauthenticated.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]
    return _decode_jwt(token)
