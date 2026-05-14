"""
One-time script to authorize this app to access your Google Calendar.
Run this once with: python authorize_calendar.py
After it succeeds, google_token.json will be saved and the main app will use it.
"""

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import os

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def authorize():
    creds = None
    if os.path.exists("google_token.json"):
        creds = Credentials.from_authorized_user_file("google_token.json", SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "google_credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open("google_token.json", "w") as token:
            token.write(creds.to_json())
        print("✅ Authorization successful. Token saved to google_token.json")
    else:
        print("✅ Already authorized. Token is valid.")

if __name__ == "__main__":
    authorize()