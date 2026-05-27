"""Gmail OAuth + draft creation."""
import base64
import os
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


class GmailClient:
    def __init__(
        self,
        credentials_path: str = "credentials/google_client_secret.json",
        token_path: str = "credentials/google_token.json",
    ):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self._service = None
        self._email: Optional[str] = None

    def is_authenticated(self) -> bool:
        if not self.token_path.exists():
            return False
        try:
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            return creds.valid or (creds.expired and creds.refresh_token is not None)
        except Exception:
            return False

    def authenticate(self) -> str:
        """Run the OAuth flow. Opens a browser for consent. Returns the connected email."""
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"OAuth client secret missing at {self.credentials_path}. "
                "Download it from Google Cloud Console (APIs & Services > Credentials)."
            )

        creds = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception:
                creds = None

        if creds and creds.valid:
            pass
        elif creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)

        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json())

        self._service = build("gmail", "v1", credentials=creds)
        profile = self._service.users().getProfile(userId="me").execute()
        self._email = profile.get("emailAddress", "")
        return self._email

    def _get_service(self):
        if self._service is not None:
            return self._service
        if not self.token_path.exists():
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.write_text(creds.to_json())
        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def get_connected_email(self) -> Optional[str]:
        if self._email:
            return self._email
        if not self.token_path.exists():
            return None
        try:
            service = self._get_service()
            profile = service.users().getProfile(userId="me").execute()
            self._email = profile.get("emailAddress", "")
            return self._email
        except Exception:
            return None

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        """Create a Gmail draft. Returns the API response (includes draft id)."""
        service = self._get_service()
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return service.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw}},
        ).execute()

    def logout(self):
        if self.token_path.exists():
            self.token_path.unlink()
        self._service = None
        self._email = None
