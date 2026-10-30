"""The event table: every source reduced to one shape.

Each row is one thing that happened: a spreadsheet row changed, a payment
arrived, an email was sent or received. Discovery works only on this table.

Columns:

- ``timestamp``: when it happened. With ``time_resolution == "day"`` (snapshot
  changes, bank postings) only the date is known, and the time is midnight.
- ``source``: "spreadsheet", "bank" or "email".
- ``activity``: what happened, e.g. "invoices.update[paid_date,status]",
  "bank.credit" or "email.sent". Spreadsheet updates name the columns that
  changed, so the same kind of edit always gets the same label.
- ``case_id`` / ``link_method``: the case (spreadsheet row key) the event is
  about and how that was worked out: "key", "reference", "amount+payer",
  "mention" or "thread". Both are "" when no case could be found.
- ``object_id``: the spreadsheet row, bank transaction or message id.
- ``actor``: email sender or bank payer; "" for spreadsheet edits, since
  snapshots don't record who made them.
- ``payload``: source-specific details as a dict (changed values, amounts,
  email subject and body).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

EVENT_COLUMNS = [
    "event_id",
    "timestamp",
    "time_resolution",
    "source",
    "activity",
    "case_id",
    "link_method",
    "object_id",
    "actor",
    "payload",
]


def event(
    timestamp: pd.Timestamp,
    time_resolution: str,
    source: str,
    activity: str,
    object_id: str,
    case_id: str = "",
    link_method: str = "",
    actor: str = "",
    payload: dict | None = None,
) -> dict:
    return {
        "timestamp": timestamp,
        "time_resolution": time_resolution,
        "source": source,
        "activity": activity,
        "case_id": case_id,
        "link_method": link_method if case_id else "",
        "object_id": object_id,
        "actor": actor,
        "payload": payload or {},
    }


def make_event_table(rows: list[dict]) -> pd.DataFrame:
    """Sort events by time and number them."""
    df = pd.DataFrame(rows, columns=EVENT_COLUMNS[1:])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["timestamp", "source", "object_id"], kind="stable").reset_index(drop=True)
    df.insert(0, "event_id", [f"e{i:06d}" for i in range(1, len(df) + 1)])
    return df


def save_events(events: pd.DataFrame, path: str | Path) -> None:
    out = events.copy()
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    out["payload"] = out["payload"].map(lambda p: json.dumps(p, sort_keys=True))
    out.to_csv(path, index=False, lineterminator="\n")


def load_events(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, na_filter=False)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["payload"] = df["payload"].map(json.loads)
    return df[EVENT_COLUMNS]
