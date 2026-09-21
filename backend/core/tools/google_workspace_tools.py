"""
# backend/core/tools/google_workspace_tools.py

Google Workspace tools: Calendar (Meet) + Gmail.

Auth is handled by the web OAuth flow in core/api/google_auth_routes.py.
Tokens are persisted at ~/.carole/google_token.json and auto-refreshed.
"""

import os
import base64
from email.message import EmailMessage
from typing import List

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.api.google_auth_routes import get_google_credentials

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_creds(user_id: str | None):
    """Returns valid Google credentials or None."""
    creds = get_google_credentials(user_id)
    return creds

_NOT_CONNECTED = (
    "Google account not connected. Go to Settings → Google Account and click "
    "\"Connect Google Account\" to authorize Calendar & Gmail access."
)

# ── Calendar / Meet ───────────────────────────────────────────────────────────

def create_meeting(summary: str, start_time_iso: str, end_time_iso: str, attendees_emails: List[str], user_id: str | None = None) -> str:
    """
    Creates a Google Calendar event with a Google Meet link.
    Returns the Meet link on success.
    """
    creds = _get_creds(user_id)
    if not creds:
        return _NOT_CONNECTED

    try:
        service = build("calendar", "v3", credentials=creds)
        attendees = [{"email": email} for email in attendees_emails]
        event = {
            "summary": summary,
            "start": {"dateTime": start_time_iso, "timeZone": "UTC"},
            "end":   {"dateTime": end_time_iso,   "timeZone": "UTC"},
            "attendees": attendees,
            "conferenceData": {
                "createRequest": {
                    "requestId": f"req-{os.urandom(10).hex()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        result = service.events().insert(
            calendarId="primary",
            body=event,
            conferenceDataVersion=1,
            sendUpdates="all",
        ).execute()

        meet_link = result.get("hangoutLink")
        if meet_link:
            return f"Meeting created successfully. Meet Link: {meet_link}"
        return "Meeting created successfully, but no Meet link was generated."

    except HttpError as e:
        return f"Google Calendar API error: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"


# ── Gmail ─────────────────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, body: str, user_id: str | None = None) -> str:
    """
    Sends an email via the Gmail API from the connected Google account.
    """
    creds = _get_creds(user_id)
    if not creds:
        return _NOT_CONNECTED

    try:
        service = build("gmail", "v1", credentials=creds)
        message = EmailMessage()
        message.set_content(body)
        message["To"]      = to_email
        message["From"]    = "me"
        message["Subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email sent successfully. Message ID: {result['id']}"

    except HttpError as e:
        return f"Gmail API error: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"