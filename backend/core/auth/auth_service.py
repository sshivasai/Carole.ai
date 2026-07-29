"""
# backend/core/auth/auth_service.py

JWT-based authentication service for Carole.ai.

- Password hashing with bcrypt (via hashlib fallback).
- JWT token creation and verification.
- Login, signup, and current user resolution.
"""

import os
import uuid
import hashlib
import hmac
import json
import time
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.models import User

# Config
DEFAULT_DEV_SECRET = "carole-ai-dev-secret-change-in-production"
JWT_SECRET = os.getenv("JWT_SECRET", DEFAULT_DEV_SECRET)
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "72"))


def validate_auth_config():
    """Fail-fast guard to ensure JWT_SECRET is explicitly set in production environments."""
    env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
    if env in ["production", "prod"]:
        secret = os.getenv("JWT_SECRET")
        if not secret or secret == DEFAULT_DEV_SECRET:
            raise RuntimeError(
                "CRITICAL SECURITY FAILURE: JWT_SECRET must be set to a secure, random value in production mode!"
            )



def _hash_password(password: str) -> str:
    """Hash a password using SHA-256 + salt."""
    salt = uuid.uuid4().hex[:16]
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${hashed}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash."""
    if "$" not in stored_hash:
        # Legacy plain-text comparison (for demo/seed data)
        return password == stored_hash
    salt, hashed = stored_hash.split("$", 1)
    check = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return hmac.compare_digest(check, hashed)


def _create_jwt(payload: dict) -> str:
    """Creates a simple JWT token (HS256)."""
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}

    import base64
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    h = b64url(json.dumps(header).encode())
    p = b64url(json.dumps(payload).encode())
    signing_input = f"{h}.{p}"
    sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(sig)}"


def _decode_jwt(token: str) -> Optional[dict]:
    """Decodes and verifies a JWT token. Returns payload or None."""
    import base64

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    def b64url_decode(s: str) -> bytes:
        padding = 4 - len(s) % 4
        if padding != 4:
            s += "=" * padding
        return base64.urlsafe_b64decode(s)

    parts = token.split(".")
    if len(parts) != 3:
        return None

    h, p, s = parts
    signing_input = f"{h}.{p}"
    expected_sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    actual_sig = b64url_decode(s)

    if not hmac.compare_digest(expected_sig, actual_sig):
        return None

    try:
        payload = json.loads(b64url_decode(p))
    except (json.JSONDecodeError, Exception):
        return None

    # Check expiry
    if payload.get("exp") and payload["exp"] < time.time():
        return None

    return payload


class AuthService:
    async def signup(self, db: AsyncSession, email: str, password: str,
                     first_name: str = None, last_name: str = None) -> dict:
        """Creates a new user account."""
        # Check if email already exists
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return {"error": "A user with this email already exists."}

        user = User(
            email=email,
            hashed_password=_hash_password(password),
            first_name=first_name,
            last_name=last_name,
            is_verified=True,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        token = self._generate_token(user)
        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "token": token,
        }

    async def login(self, db: AsyncSession, email: str, password: str) -> dict:
        """Authenticates a user and returns a JWT token."""
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return {"error": "Invalid email or password."}

        if not _verify_password(password, user.hashed_password):
            return {"error": "Invalid email or password."}

        if not user.is_active:
            return {"error": "Account is deactivated."}

        token = self._generate_token(user)
        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "token": token,
        }

    async def get_current_user(self, db: AsyncSession, token: str) -> Optional[dict]:
        """Resolves the current user from a JWT token."""
        payload = _decode_jwt(token)
        if not payload:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        stmt = select(User).where(User.id == uuid.UUID(user_id))
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            return None

        return {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
        }

    def _generate_token(self, user: User) -> str:
        """Generates a JWT token for the given user."""
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "iat": int(time.time()),
            "exp": int(time.time()) + (JWT_EXPIRY_HOURS * 3600),
        }
        return _create_jwt(payload)


# Singleton
auth_service = AuthService()
