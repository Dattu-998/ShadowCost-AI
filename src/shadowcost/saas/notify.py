"""Email the people who need to act, and keep a log of what was sent.

Sent through Resend when `RESEND_API_KEY` is set; otherwise the notification is only logged, so a
server without email still records what it would have sent. Every notification is a row in
`notifications`, visible to the workspace.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Callable

import httpx

from shadowcost.saas.auth import RANK
from shadowcost.saas.config import settings
from shadowcost.saas.db import Database

log = logging.getLogger(__name__)

Sender = Callable[[list[str], str, str], bool]


def resend_sender(recipients: list[str], subject: str, body_html: str) -> bool:
    s = settings()
    if not s.email_enabled or not recipients:
        return False
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {s.resend_api_key}"},
            json={"from": s.email_from, "to": recipients, "subject": subject, "html": body_html},
            timeout=15,
        )
        return response.status_code < 300
    except httpx.HTTPError:
        log.warning("email to %s failed", recipients, exc_info=True)
        return False


_sender: Sender = resend_sender

_EMAIL = (
    '<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.5;'
    'color:#1c1c1c">{paragraphs}'
    '<p><a href="{link}" style="color:#2c3620;font-weight:600">Open ShadowCost</a></p>'
    '<p style="color:#5b6670;font-size:13px">'
    "You get this because you approve agents in this workspace.</p></div>"
)


def set_sender(sender: Sender) -> None:
    global _sender
    _sender = sender


def recipients(db: Database, org_id: str, min_role: str) -> list[str]:
    members = db.select("memberships", where={"org_id": org_id})
    return sorted({m["email"] for m in members if RANK[m["role"]] >= RANK[min_role]})


def notify(
    db: Database,
    org_id: str,
    kind: str,
    subject: str,
    lines: list[str],
    link_path: str,
    min_role: str = "approver",
    to: list[str] | None = None,
) -> dict:
    to = to if to is not None else recipients(db, org_id, min_role)
    link = f"{settings().site_url}{link_path}"
    paragraphs = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    body = _EMAIL.format(paragraphs=paragraphs, link=html.escape(link))
    delivered = _sender(to, subject, body) if to else False
    return db.insert(
        "notifications",
        {
            "org_id": org_id,
            "kind": kind,
            "subject": subject,
            "recipients": to,
            "delivered": delivered,
        },
    )[0]
