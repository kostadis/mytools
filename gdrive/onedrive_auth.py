"""Shared OAuth helper for OneDrive tools (personal Microsoft account).

Reads the app registration from ~/.config/onedrive-tools/app.json and
caches the user token at ~/.config/onedrive-tools/token.json. First run
opens a browser for consent; later runs are headless.

app.json format:
    {"client_id": "YOUR_APP_CLIENT_ID"}
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import msal
import requests

CONFIG_DIR = Path.home() / ".config" / "onedrive-tools"
APP_PATH = CONFIG_DIR / "app.json"
TOKEN_PATH = CONFIG_DIR / "token.json"

READ_SCOPES = ["Files.Read"]
WRITE_SCOPES = ["Files.ReadWrite"]

AUTHORITY = "https://login.microsoftonline.com/consumers"


def _load_app_config() -> dict:
    if not APP_PATH.exists():
        raise SystemExit(
            f"missing {APP_PATH}\n"
            "Create an Azure app registration (see ONEDRIVE_SETUP.md),\n"
            "then save {\"client_id\": \"YOUR_ID\"} to that file."
        )
    return json.loads(APP_PATH.read_text())


def _build_app(client_id: str) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        client_id,
        authority=AUTHORITY,
        token_cache=_load_cache(),
    )


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if TOKEN_PATH.exists():
        cache.deserialize(TOKEN_PATH.read_text())
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if cache.has_state_changed:
        TOKEN_PATH.write_text(cache.serialize())


def get_token(scopes: list[str] = READ_SCOPES) -> str:
    """Return a valid access token, prompting for login if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = _load_app_config()
    app = _build_app(config["client_id"])

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(app.token_cache)
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise SystemExit(f"Device flow failed: {flow.get('error_description', flow)}")

    print(flow["message"], file=sys.stderr)
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise SystemExit(f"Auth failed: {result.get('error_description', result)}")

    _save_cache(app.token_cache)
    return result["access_token"]


RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5


def _backoff_seconds(attempt: int) -> float:
    base = 2 ** attempt
    return base + random.uniform(0, base * 0.25)


def graph_get(url: str, token: str, **kwargs) -> requests.Response:
    """GET from Microsoft Graph with auth, retrying transient failures."""
    headers = {"Authorization": f"Bearer {token}"}
    kwargs.setdefault("timeout", 60)

    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = requests.get(url, headers=headers, **kwargs)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            delay = _backoff_seconds(attempt)
            print(
                f"transient {type(e).__name__}; "
                f"retry {attempt + 1}/{MAX_ATTEMPTS - 1} in {delay:.1f}s",
                file=sys.stderr,
            )
            time.sleep(delay)
            continue

        if resp.status_code in RETRYABLE_STATUSES and attempt < MAX_ATTEMPTS - 1:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else _backoff_seconds(attempt)
            print(
                f"http {resp.status_code}; "
                f"retry {attempt + 1}/{MAX_ATTEMPTS - 1} in {delay:.1f}s",
                file=sys.stderr,
            )
            time.sleep(delay)
            continue

        return resp
