"""
# backend/core/auth/auth_service.py

JWT-based authentication service for Carole.ai.

- Password hashing with PBKDF2-HMAC-SHA256 (100k iterations).
- JWT token creation and verification.
- Login, signup, and current user resolution.
"""

import os
import uuid
import base64
import binascii
import asyncio
import math
import hashlib
import hmac
import json
import logging
import time
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from core.memory.models import User

logger = logging.getLogger("carole.auth")

# ── JWT Config ──────────────────────────────────────────────────────────────
# If JWT_SECRET is not set, generate a cryptographically random ephemeral
# secret. This is safe (random, unpredictable) but means all sessions are
# invalidated on every server restart. Set JWT_SECRET in .env for persistence.
_JWT_SECRET_FROM_ENV = os.getenv("JWT_SECRET")
if not _JWT_SECRET_FROM_ENV:
    import secrets as _secrets
    JWT_SECRET = _secrets.token_hex(32)
    import logging as _logging
    _logging.getLogger("carole.auth").warning(
        "JWT_SECRET not set — using a random ephemeral secret. "
        "All sessions will be invalidated on restart. "
        "Set JWT_SECRET in your .env file for production."
    )
else:
    JWT_SECRET = _JWT_SECRET_FROM_ENV

_DEFAULT_DEV_SECRET = "carole-ai-dev-secret-change-in-production"  # kept for validate_auth_config check
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "72"))


def validate_auth_config():
    """Fail-fast guard to ensure JWT_SECRET is explicitly set in production environments."""
    env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
    if env in ["production", "prod"]:
        secret = os.getenv("JWT_SECRET")
        if not secret or secret == _DEFAULT_DEV_SECRET:
            raise RuntimeError(
                "CRITICAL SECURITY FAILURE: JWT_SECRET must be set to a secure, random value in production mode!"
            )



# PBKDF2 config — 100k iterations is OWASP-recommended minimum for SHA-256.
_PBKDF2_ITERATIONS = 100_000
_PBKDF2_PREFIX = "pbkdf2$"
_DUMMY_PBKDF2_HASH = "pbkdf2$YWFhYWFhYWFhYWFhYWFhYQ==$YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE="


def _hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with 100k iterations."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    salt_b64 = base64.b64encode(salt).decode()
    hash_b64 = base64.b64encode(dk).decode()
    return f"{_PBKDF2_PREFIX}{salt_b64}${hash_b64}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash.

    Supports three formats (newest → oldest):
      1. pbkdf2$<salt_b64>$<hash_b64>  (current — PBKDF2-HMAC-SHA256)
      2. <salt_hex>$<sha256_hex>        (legacy — single-round SHA-256)
      3. raw plaintext                  (ancient seed data — always rejected)
    """
    if not isinstance(stored_hash, str):
        return False
    if "$" not in stored_hash:
        # Legacy plain-text: NEVER accept — log a security warning
        logger.warning("⚠️  Plain-text password detected in database. Rejecting login; account needs password reset.")
        return False

    if stored_hash.startswith(_PBKDF2_PREFIX):
        # Current PBKDF2 format
        try:
            remainder = stored_hash[len(_PBKDF2_PREFIX):]
            salt_b64, hash_b64 = remainder.split("$", 1)
            salt = base64.b64decode(salt_b64, validate=True)
            expected = base64.b64decode(hash_b64, validate=True)
        except (ValueError, binascii.Error):
            return False
        if len(salt) != 16 or len(expected) != 32:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
        return hmac.compare_digest(dk, expected)

    # Legacy SHA-256 format — verify but log deprecation warning
    salt, hashed = stored_hash.split("$", 1)
    check = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    if not hashed.isascii():
        return False
    if hmac.compare_digest(check, hashed):
        logger.warning("⚠️  User authenticated with legacy SHA-256 hash. Hash should be upgraded on next password change.")
        return True
    return False


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding (JWT standard)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    """Base64url-decode with padding restoration."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.b64decode(s, altchars=b"-_", validate=True)


def _create_jwt(payload: dict) -> str:
    """Creates a simple JWT token (HS256)."""
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}

    h = _b64url(json.dumps(header).encode())
    p = _b64url(json.dumps(payload).encode())
    signing_input = f"{h}.{p}"
    sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(sig)}"


def _decode_jwt(token: str) -> Optional[dict]:
    """Verify the signature and claims shared by access tokens and WS tickets."""
    if not isinstance(token, str):
        return None
    try:
        h, p, s = token.split(".")
        signing_input = f"{h}.{p}".encode("ascii")
        expected_sig = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, _b64url_decode(s)):
            return None
        header = json.loads(_b64url_decode(h))
        payload = json.loads(_b64url_decode(p))
        if not isinstance(header, dict) or header.get("alg") != JWT_ALGORITHM:
            return None
        if not isinstance(payload, dict):
            return None
        expiry = payload.get("exp")
        if type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry <= time.time():
            return None
        subject = payload.get("sub")
        if not isinstance(subject, str):
            return None
        uuid.UUID(subject)
    except (ValueError, TypeError, binascii.Error, OverflowError, RecursionError):
        return None
    return payload


def _decode_access_jwt(token: str) -> Optional[dict]:
    """Existing access tokens have no purpose claim; WS tickets are not HTTP credentials."""
    payload = _decode_jwt(token)
    if payload is None or "type" in payload:
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
            hashed_password=await asyncio.to_thread(_hash_password, password),
            first_name=first_name,
            last_name=last_name,
            is_verified=True,
            is_active=True,
        )
        db.add(user)
        try:
            await db.flush()
            await db.commit()
        except IntegrityError:
            # The pre-check cannot serialize concurrent signups. Recover the
            # session, and translate only a confirmed email collision.
            await db.rollback()
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if existing:
                return {"error": "A user with this email already exists."}
            raise

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

        # Constant-time verification to prevent user enumeration timing attacks
        target_hash = user.hashed_password if user and user.hashed_password else _DUMMY_PBKDF2_HASH
        valid_password = await asyncio.to_thread(_verify_password, password, target_hash)

        if not user or not valid_password:
            return {"error": "Invalid email or password."}

        if not user.is_active:
            return {"error": "Account is deactivated."}

        # Snapshot before commit/rollback: rollback expires ORM attributes even
        # when expire_on_commit=False. A best-effort upgrade must not break login.
        response = {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "token": self._generate_token(user),
        }

        # Finding #6 — transparently upgrade legacy SHA-256 hashes to PBKDF2 on
        # successful login so old accounts are progressively secured without
        # requiring a forced password reset.
        if user.hashed_password and not user.hashed_password.startswith(_PBKDF2_PREFIX):
            try:
                user.hashed_password = await asyncio.to_thread(_hash_password, password)
                await db.commit()
                logger.info("Upgraded legacy password hash to PBKDF2 for user %s", email)
            except Exception as upgrade_err:
                await db.rollback()
                logger.warning("Failed to upgrade password hash for %s: %s", email, upgrade_err)

        return response

    async def get_current_user(self, db: AsyncSession, token: str) -> Optional[dict]:
        """Resolves the current user from a JWT token."""
        payload = _decode_access_jwt(token)
        if not payload:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        user = await self.get_active_user(db, user_id)
        if not user:
            return None

        return {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
        }

    async def get_active_user(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """Resolve a live account for HTTP requests and WebSocket handshakes."""
        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError, AttributeError):
            return None
        result = await db.execute(select(User).where(User.id == user_uuid, User.is_active.is_(True)))
        return result.scalar_one_or_none()

    def _generate_token(self, user: User) -> str:
        """Generates a JWT token for the given user."""
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "iat": int(time.time()),
            "exp": int(time.time()) + (JWT_EXPIRY_HOURS * 3600),
        }
        return _create_jwt(payload)

    def generate_ws_ticket(self, user_id: str) -> str:
        """Generates a short-lived (30s) JWT ticket for WebSocket authentication."""
        payload = {
            "sub": user_id,
            "type": "ws_ticket",
            "iat": int(time.time()),
            "exp": int(time.time()) + 30,  # 30 seconds expiry
        }
        return _create_jwt(payload)

    def verify_ws_ticket(self, ticket: str) -> Optional[str]:
        """Verifies a WebSocket ticket and returns the user_id if valid."""
        payload = _decode_jwt(ticket)
        if not payload:
            return None
        if payload.get("type") != "ws_ticket":
            return None
        return payload.get("sub")

# Singleton
auth_service = AuthService()
