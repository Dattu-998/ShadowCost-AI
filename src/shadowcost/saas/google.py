"""Google connector: snapshot a Google Sheet and read Gmail, read-only.

ShadowCost discovers work from *dated copies* of a spreadsheet, which small companies rarely keep.
The connector makes them: every sync saves the sheet as `ledger/<sheet>_<date>.csv`, so after a
few weeks the workspace has exactly the history discovery needs. Gmail is read with a search
query the workspace chooses (e.g. `from:me newer_than:90d`); only headers and Google's snippet are
stored, never full bodies or attachments.

Refresh tokens are encrypted at rest with a key derived from `TOKEN_ENCRYPTION_KEY`, and the OAuth
`state` is HMAC-signed and expires, so a callback can't be forged or replayed into another
workspace.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import re
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from shadowcost.saas.config import settings

SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]
STATE_TTL_SECONDS = 600
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
METADATA_HEADERS = ["From", "To", "Subject", "Date", "In-Reply-To", "Message-ID"]
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _key_bytes() -> bytes:
    if not settings().token_key:
        raise HTTPException(503, "the Google connector is not configured on this server")
    return hashlib.sha256(settings().token_key.encode()).digest()


def encrypt(token: str) -> str:
    return Fernet(base64.urlsafe_b64encode(_key_bytes())).encrypt(token.encode()).decode()


def decrypt(blob: str) -> str:
    try:
        return Fernet(base64.urlsafe_b64encode(_key_bytes())).decrypt(blob.encode()).decode()
    except InvalidToken as err:
        raise HTTPException(500, "stored Google token can't be read; reconnect Google") from err


def sign_state(payload: dict) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps({**payload, "exp": int(time.time()) + STATE_TTL_SECONDS}).encode()
    )
    signature = hmac.new(_key_bytes(), body, hashlib.sha256).hexdigest()
    return f"{body.decode()}.{signature}"


def verify_state(state: str) -> dict:
    try:
        body, signature = state.rsplit(".", 1)
    except ValueError as err:
        raise HTTPException(400, "malformed OAuth state") from err
    expected = hmac.new(_key_bytes(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(400, "OAuth state was tampered with")
    payload = json.loads(base64.urlsafe_b64decode(body))
    if payload.get("exp", 0) < time.time():
        raise HTTPException(400, "the Google sign-in took too long; start again")
    return payload


def redirect_uri() -> str:
    return f"{settings().api_url}/v1/connectors/google/callback"


def auth_url(state: str) -> str:
    params = {
        "client_id": settings().google_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    s = settings()
    response = httpx.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise HTTPException(400, f"Google refused the sign-in: {response.text[:200]}")
    return response.json()


def access_token(refresh_token: str) -> str:
    s = settings()
    response = httpx.post(
        TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise HTTPException(409, "Google access was revoked or expired; reconnect Google")
    return response.json()["access_token"]


def id_token_email(id_token: str | None) -> str:
    """The email in Google's id_token (already verified by Google's token endpoint over TLS)."""
    if not id_token:
        return ""
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get(
            "email", ""
        )
    except (IndexError, ValueError):
        return ""


def fetch_sheet(token: str, spreadsheet_id: str, sheet_range: str) -> tuple[str, list[list[str]]]:
    headers = {"Authorization": f"Bearer {token}"}
    meta = httpx.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}",
        params={"fields": "properties.title"}, headers=headers, timeout=20,
    )  # fmt: skip
    if meta.status_code >= 400:
        raise HTTPException(
            400, "couldn't open that spreadsheet; check the link and that you can view it"
        )
    values = httpx.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{sheet_range}",
        params={"valueRenderOption": "FORMATTED_VALUE"}, headers=headers, timeout=30,
    )  # fmt: skip
    if values.status_code >= 400:
        raise HTTPException(400, f"couldn't read the range {sheet_range!r}")
    return meta.json()["properties"]["title"], values.json().get("values", [])


def fetch_gmail(token: str, query: str, limit: int = 300) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    ids: list[str] = []
    page = None
    while len(ids) < limit:
        params = {"q": query, "maxResults": min(100, limit - len(ids))}
        if page:
            params["pageToken"] = page
        listing = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params=params,
            headers=headers,
            timeout=20,
        )
        if listing.status_code >= 400:
            raise HTTPException(400, "couldn't read Gmail with that search")
        body = listing.json()
        ids += [m["id"] for m in body.get("messages", [])]
        page = body.get("nextPageToken")
        if not page:
            break
    messages = []
    for message_id in ids:
        detail = httpx.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            params={"format": "metadata", "metadataHeaders": METADATA_HEADERS},
            headers=headers, timeout=20,
        )  # fmt: skip
        if detail.status_code < 400:
            messages.append(detail.json())
    return messages


def sheet_to_csv(values: list[list[str]]) -> str:
    """Rows from the Sheets API as CSV; ragged rows are padded to the header's width."""
    if not values:
        return ""
    width = max(len(r) for r in values)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for row in values:
        writer.writerow(list(row) + [""] * (width - len(row)))
    return out.getvalue()


def gmail_to_records(messages: list[dict]) -> list[dict]:
    """Gmail API messages as ShadowCost email records (headers and snippet only)."""
    records = []
    for m in messages:
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        try:
            when = parsedate_to_datetime(headers.get("date", "")).isoformat()
        except (TypeError, ValueError):
            when = time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(int(m.get("internalDate", "0")) / 1000)
            )
        records.append(
            {
                "message_id": m["id"],
                "thread_id": m.get("threadId", ""),
                "timestamp": when,
                "from_addr": _address(headers.get("from", "")),
                "to_addr": _address(headers.get("to", "")),
                "subject": headers.get("subject", ""),
                "body": m.get("snippet", ""),
                "in_reply_to": headers.get("in-reply-to", ""),
            }
        )
    return records


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "sheet"


def spreadsheet_id_from(link_or_id: str) -> str:
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", link_or_id)
    return match.group(1) if match else link_or_id.strip()


def _address(header: str) -> str:
    match = re.search(r"<([^>]+)>", header)
    return (match.group(1) if match else header).strip().lower()
