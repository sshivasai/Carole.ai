"""
# backend/core/api/google_auth_routes.py

Google OAuth 2.0 web flow for Calendar + Gmail integration.

Endpoints:
  GET  /api/auth/google/authorize   — Generate Google consent URL for an authenticated client
  GET  /api/auth/google/callback    — Receive auth code, exchange for tokens, save
  GET  /api/auth/google/status      — Check if Google account is connected
  POST /api/auth/google/disconnect  — Delete token, revoke connection
"""

import json
import asyncio
import uuid
import tempfile
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request, Depends
from core.auth.auth_middleware import require_auth

logger = logging.getLogger("carole.google_auth")
from fastapi.responses import RedirectResponse, JSONResponse
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_oauthlib.flow import Flow

router = APIRouter(prefix="/api/auth/google", tags=["google_oauth"])

# ── Config ─────────────────────────────────────────────────────────────────────
from core.config import CAROLE_HOME_DIR

_CREDS_PATH = Path(__file__).parent.parent.parent / "credentials.json"
def _token_path(user_id: str) -> Path:
    return CAROLE_HOME_DIR / "google_tokens" / f"{uuid.UUID(str(user_id))}.json"


SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

# Redirect URI must be registered in Google Cloud Console
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")
# Where to send the user after OAuth completes
FRONTEND_SUCCESS_URL = os.getenv("FRONTEND_URL", "http://localhost:3000") + "?google_connected=1"
FRONTEND_ERROR_URL   = os.getenv("FRONTEND_URL", "http://localhost:3000") + "?google_error=1"

# Store OAuth states in memory.
# Bounded to prevent memory DoS (max 200 sessions), entries expire after 10 min.
_AUTH_SESSIONS: dict = {}  # state -> {"code_verifier": ..., "expires_at": float}
_AUTH_SESSION_MAX = 200
_AUTH_SESSION_TTL = 600  # 10 minutes


def _purge_expired_sessions() -> None:
    """Remove expired OAuth sessions from the in-memory store."""
    import time
    now = time.time()
    expired = [k for k, v in _AUTH_SESSIONS.items() if v.get("expires_at", 0) < now]
    for k in expired:
        _AUTH_SESSIONS.pop(k, None)


def _credentials_file_exists() -> bool:
    return _CREDS_PATH.exists()


def _load_token(user_id: str) -> Credentials | None:
    """Load saved token from ~/.carole/google_token.json. Returns None if missing or invalid."""
    token_path = _token_path(user_id)
    if not token_path.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        # Try to refresh if expired
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(GoogleRequest())
                _save_token(creds, user_id)
            except Exception:
                token_path.unlink(missing_ok=True)
                return None
        return creds if creds and creds.valid else None
    except Exception:
        return None


def _save_token(creds: Credentials, user_id: str) -> None:
    """Atomically persist credentials in an owner-specific private file."""
    path = _token_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".token-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(creds.to_json())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def get_google_credentials(user_id: str | None = None) -> Credentials | None:
    """No global credential fallback: the caller must supply a trusted owner ID."""
    return _load_token(user_id) if user_id else None


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/status")
async def google_status(user: dict = Depends(require_auth)):
    """Returns whether a Google account is currently connected. Requires authentication."""
    if not _credentials_file_exists():
        return {"connected": False, "reason": "credentials.json not found on server"}

    creds = await asyncio.to_thread(_load_token, user["sub"])
    if not creds:
        return {"connected": False, "reason": "not_authorized"}

    # Get the user's email from the token info
    email = None
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"}
            )
        if resp.status_code == 200:
            email = resp.json().get("email")
    except Exception:
        pass

    return {
        "connected": True,
        "email": email,
        "scopes": ["calendar", "gmail"],
    }


@router.get("/authorize")
async def google_authorize(user: dict = Depends(require_auth)):
    """
    Generates the Google OAuth consent URL and redirects the user to it.
    Works with both 'web' and 'installed' (desktop) credentials.json types.
    Requires authentication.
    """
    if not _credentials_file_exists():
        return JSONResponse(
            status_code=503,
            content={"error": "credentials.json not found. Place your Google OAuth Web App credentials in the backend directory."},
        )

    try:
        with open(_CREDS_PATH) as f:
            raw = json.load(f)

        # Google Cloud issues either 'web' or 'installed' app credentials.
        # Normalise to what google-auth-oauthlib expects.
        cred_type = "web" if "web" in raw else "installed"
        client_config = {cred_type: raw[cred_type]}

        # Patch redirect URI into the config so it matches what we expect
        client_config[cred_type].setdefault("redirect_uris", [REDIRECT_URI])
        if REDIRECT_URI not in client_config[cred_type]["redirect_uris"]:
            client_config[cred_type]["redirect_uris"].append(REDIRECT_URI)

        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        
        # Purge expired sessions and enforce max size to prevent memory DoS
        import time
        _purge_expired_sessions()
        if len(_AUTH_SESSIONS) >= _AUTH_SESSION_MAX:
            # Evict the oldest entry
            oldest_key = next(iter(_AUTH_SESSIONS))
            _AUTH_SESSIONS.pop(oldest_key, None)

        # Save the code verifier with TTL so state cannot be replayed indefinitely
        _AUTH_SESSIONS[state] = {
            "user_id": user["sub"],
            "code_verifier": getattr(flow, "code_verifier", None),
            "expires_at": time.time() + _AUTH_SESSION_TTL,
        }

        response = JSONResponse({"url": auth_url})
        response.set_cookie("carole_google_state", state, httponly=True, samesite="lax",
                            secure=REDIRECT_URI.startswith("https:"), max_age=_AUTH_SESSION_TTL,
                            path="/api/auth/google")
        return response

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to build auth URL: {e}"})


@router.get("/callback")
async def google_callback(request: Request):
    """
    Handles the OAuth callback from Google.
    Exchanges the authorization code for access + refresh tokens,
    saves them to the authenticated account token file, and redirects to the frontend.
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error or not code:
        return RedirectResponse(FRONTEND_ERROR_URL)

    # Finding #12 — Explicit state validation to prevent OAuth CSRF.
    # Reject the callback if the state is unknown or has expired.
    import time
    _purge_expired_sessions()
    import secrets
    browser_state = request.cookies.get("carole_google_state", "")
    if not state or not browser_state or not secrets.compare_digest(state, browser_state) or state not in _AUTH_SESSIONS:
        logger.warning("OAuth callback rejected — unknown or expired state: %s", state)
        return RedirectResponse(FRONTEND_ERROR_URL + "&reason=invalid_state")

    session_data = _AUTH_SESSIONS.pop(state)  # Remove to prevent replay
    code_verifier = session_data.get("code_verifier")
    user_id = session_data.get("user_id")
    from core.memory.database import async_session
    from core.auth.auth_service import auth_service
    async with async_session() as db:
        if not user_id or not await auth_service.get_active_user(db, user_id):
            return RedirectResponse(FRONTEND_ERROR_URL)


    try:
        with open(_CREDS_PATH) as f:
            raw = json.load(f)

        cred_type = "web" if "web" in raw else "installed"
        client_config = {cred_type: raw[cred_type]}
        client_config[cred_type].setdefault("redirect_uris", [REDIRECT_URI])
        if REDIRECT_URI not in client_config[cred_type]["redirect_uris"]:
            client_config[cred_type]["redirect_uris"].append(REDIRECT_URI)

        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
            state=state,
        )
        
        # Restore PKCE code verifier
        if code_verifier:
            flow.code_verifier = code_verifier

        await asyncio.to_thread(flow.fetch_token, code=code)
        await asyncio.to_thread(_save_token, flow.credentials, user_id)
        return RedirectResponse(FRONTEND_SUCCESS_URL)
    except Exception as e:
        logger.warning("Google OAuth exchange failed (%s)", type(e).__name__)
        return RedirectResponse(FRONTEND_ERROR_URL)


@router.post("/disconnect")
async def google_disconnect(user: dict = Depends(require_auth)):
    """
    Revokes the Google token and deletes the local token file. Requires authentication.
    """
    creds = await asyncio.to_thread(_load_token, user["sub"])
    if creds:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": creds.token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except Exception:
            pass  # Best-effort revoke; always delete local token

    _token_path(user["sub"]).unlink(missing_ok=True)
    return {"status": "disconnected"}
