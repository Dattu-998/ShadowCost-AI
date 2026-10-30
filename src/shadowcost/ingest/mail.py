"""Turn an email log into sent/received events linked to cases.

An email is linked to a case when it mentions exactly one case id. Emails that
mention none, such as a customer's "this was paid last week", inherit the case
of their thread.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from shadowcost.ingest.detect import DetectedFile, find_column, read_table
from shadowcost.ingest.events import event
from shadowcost.ingest.linking import CaseIndex

FIELD_ALIASES = {
    "message_id": ("message_id", "msg_id", "id"),
    "thread_id": ("thread_id", "conversation_id", "thread"),
    "timestamp": ("timestamp", "date", "sent_at", "received_at"),
    "from": ("from_addr", "from", "sender"),
    "to": ("to_addr", "to", "recipient"),
    "subject": ("subject",),
    "body": ("body", "text", "content"),
    "in_reply_to": ("in_reply_to", "reply_to"),
    "direction": ("direction",),
}
_OUTBOUND = {"outbound", "sent", "out"}
_REPLY_PREFIX = re.compile(r"^\s*((re|fwd?|aw)\s*:\s*)+", re.IGNORECASE)


def load_messages(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("messages", [])
    return read_table(path).to_dict("records")


def email_events(root: Path, file: DetectedFile, index: CaseIndex) -> tuple[list[dict], list[str]]:
    records = load_messages(root / file.path)
    if not records:
        return [], []
    fields = {
        name: find_column(records[0].keys(), aliases, exact=True)
        for name, aliases in FIELD_ALIASES.items()
    }

    def get(record: dict, name: str) -> str:
        column = fields[name]
        value = record.get(column, "") if column else ""
        return "" if value is None else str(value)

    home = _home_domain(get(r, "from") for r in records)
    events, warnings = [], []
    for i, record in enumerate(records, start=1):
        when = pd.to_datetime(get(record, "timestamp"), errors="coerce")
        if pd.isna(when):
            warnings.append(f"{file.path} message {i}: unreadable timestamp, skipped")
            continue
        sender, subject, body = get(record, "from"), get(record, "subject"), get(record, "body")
        direction = get(record, "direction").lower()
        sent = direction in _OUTBOUND if direction else _domain(sender) == home
        mentioned = index.mentions(f"{subject}\n{body}")
        case_id = mentioned[0] if len(mentioned) == 1 else ""
        events.append(
            event(
                when,
                "exact",
                "email",
                "email.sent" if sent else "email.received",
                object_id=get(record, "message_id") or f"{file.path.stem}/{i}",
                case_id=case_id,
                link_method="mention",
                actor=sender,
                payload={
                    "subject": subject,
                    "body": body,
                    "from": sender,
                    "to": get(record, "to"),
                    "thread_id": get(record, "thread_id") or _thread_from_subject(subject),
                    "in_reply_to": get(record, "in_reply_to"),
                },
            )
        )

    # Emails without a mention inherit their thread's case, if the thread has just one.
    thread_cases: dict[str, set[str]] = defaultdict(set)
    for e in events:
        if e["case_id"]:
            thread_cases[e["payload"]["thread_id"]].add(e["case_id"])
    for e in events:
        cases = thread_cases[e["payload"]["thread_id"]]
        if not e["case_id"] and len(cases) == 1:
            e["case_id"], e["link_method"] = next(iter(cases)), "thread"
    return events, warnings


def _home_domain(senders) -> str:
    """The mailbox owner's domain: the one that sends most of the email."""
    counts = Counter(_domain(s) for s in senders if s)
    return counts.most_common(1)[0][0] if counts else ""


def _domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].strip(" >").lower() if "@" in address else ""


def _thread_from_subject(subject: str) -> str:
    return "subject:" + _REPLY_PREFIX.sub("", subject).strip().lower()
