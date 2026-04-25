"""Shared OAuth helper for gdrive tools.

Reads the OAuth client from ~/.config/gdrive-tools/credentials.json and
caches the user token at ~/.config/gdrive-tools/token.json. First run
opens a browser for consent; later runs are headless.
"""
from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CONFIG_DIR = Path.home() / ".config" / "gdrive-tools"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"

READ_SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)
WRITE_SCOPES = ("https://www.googleapis.com/auth/drive",)


def _token_path(scopes: tuple[str, ...]) -> Path:
    if "drive.readonly" in scopes[0]:
        return CONFIG_DIR / "token.json"
    return CONFIG_DIR / "token-write.json"


def get_credentials(scopes: tuple[str, ...]) -> Credentials:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    token_path = _token_path(scopes)
    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), list(scopes))
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CREDENTIALS_PATH.exists():
            raise SystemExit(
                f"missing {CREDENTIALS_PATH}\n"
                "create an OAuth Desktop client in a GCP project with the "
                "Drive API enabled, download the JSON, and save it there."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), list(scopes))
        creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    return creds


def drive_service(scopes: tuple[str, ...] = READ_SCOPES):
    creds = get_credentials(scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)
