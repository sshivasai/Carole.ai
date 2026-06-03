import os
import json
import base64
from email.message import EmailMessage
from typing import List, Dict, Any, Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/gmail.send'
]

def get_credentials() -> Optional[Credentials]:
    """Gets valid user credentials from storage or environment variables."""
    creds = None
    token_path = os.environ.get('GOOGLE_TOKEN_PATH', 'token.json')
    creds_path = os.environ.get('GOOGLE_CREDS_PATH', 'credentials.json')

    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # If there are no (valid) credentials available, try to let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                # Refresh failed
                return None
        else:
            if not os.path.exists(creds_path):
                return None
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                return None
        
        # Save the credentials for the next run
        try:
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        except Exception:
            pass
            
    return creds

def create_meeting(summary: str, start_time_iso: str, end_time_iso: str, attendees_emails: List[str]) -> str:
    """
    Uses Google Calendar API to create an event with conferenceData (Google Meet link attached).
    Returns the Meet link.
    """
    creds = get_credentials()
    if not creds:
        return "Error: Missing or invalid Google credentials. Please ensure credentials.json is present and token.json is valid."

    try:
        service = build('calendar', 'v3', credentials=creds)
        
        attendees = [{'email': email} for email in attendees_emails]
        
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_time_iso,
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time_iso,
                'timeZone': 'UTC',
            },
            'attendees': attendees,
            'conferenceData': {
                'createRequest': {
                    'requestId': f"req-{os.urandom(10).hex()}",
                    'conferenceSolutionKey': {
                        'type': 'hangoutsMeet'
                    }
                }
            }
        }

        event_result = service.events().insert(
            calendarId='primary', 
            body=event, 
            conferenceDataVersion=1,
            sendUpdates='all'
        ).execute()

        meet_link = event_result.get('hangoutLink')
        if meet_link:
            return f"Meeting created successfully. Meet Link: {meet_link}"
        else:
            return "Meeting created successfully, but no Meet link was generated."
            
    except HttpError as error:
        return f"An error occurred calling the Google Calendar API: {error}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

def send_email(to_email: str, subject: str, body: str) -> str:
    """
    Uses Gmail API to send an email.
    """
    creds = get_credentials()
    if not creds:
        return "Error: Missing or invalid Google credentials. Please ensure credentials.json is present and token.json is valid."

    try:
        service = build('gmail', 'v1', credentials=creds)
        
        message = EmailMessage()
        message.set_content(body)
        message['To'] = to_email
        message['From'] = 'me'
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        send_message = (service.users().messages().send(userId="me", body=create_message).execute())
        
        return f"Email sent successfully. Message ID: {send_message['id']}"
        
    except HttpError as error:
        return f"An error occurred calling the Gmail API: {error}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"