"""Turn a series of spreadsheet snapshots into row-level change events.

Consecutive snapshots are compared row by row, matching rows on a key column
inferred from the data. Each added, removed or edited row becomes one event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from shadowcost.ingest.detect import DetectedFile, find_column, read_table
from shadowcost.ingest.events import event
from shadowcost.ingest.linking import CaseIndex, to_amount

KEY_HINTS = ("id", "number", "no", "ref", "code", "key")
AMOUNT_HINTS = ("amount", "total", "value")
NAME_HINTS = ("customer", "client", "company", "name")


@dataclass
class SnapshotSeries:
    name: str
    key: str
    frames: list[tuple[date, pd.DataFrame]]


def load_series(root: Path, files: list[DetectedFile]) -> SnapshotSeries:
    frames = sorted(
        ((f.snapshot_date, read_table(root / f.path)) for f in files), key=lambda item: item[0]
    )
    name = files[0].series
    return SnapshotSeries(name, infer_key(name, frames), frames)


def infer_key(name: str, frames: list[tuple[date, pd.DataFrame]]) -> str:
    """The column that identifies a row: filled in and unique in every snapshot.

    Several columns can qualify by chance (amounts with cents are often unique),
    so columns that look like ids ("invoice_id", "Order No") are preferred, then
    the leftmost.
    """
    first = frames[0][1]
    candidates = [
        col
        for col in first.columns
        if all(col in df.columns and df[col].ne("").all() and df[col].is_unique for _, df in frames)
    ]
    if not candidates:
        raise ValueError(f"no column uniquely identifies the rows of every {name!r} snapshot")
    hinted = find_column(candidates, KEY_HINTS)
    return hinted or candidates[0]


def index_cases(series: SnapshotSeries, index: CaseIndex) -> None:
    """Register every row key so bank payments and emails can be linked to it."""
    columns = series.frames[-1][1].columns
    amount_col = find_column(columns, AMOUNT_HINTS)
    name_col = find_column(columns, NAME_HINTS)
    for _, df in series.frames:
        for row in df.to_dict("records"):
            amount = to_amount(row[amount_col]) if amount_col else None
            index.add(row[series.key], amount, row.get(name_col, "") if name_col else "")


def series_events(series: SnapshotSeries) -> list[dict]:
    events = []
    previous: dict[str, dict] = {}
    for i, (day, df) in enumerate(series.frames):
        timestamp = pd.Timestamp(day)
        current = {row[series.key]: row for row in df.to_dict("records")}

        def emit(key: str, verb: str, payload: dict, timestamp: pd.Timestamp = timestamp) -> None:
            events.append(
                event(
                    timestamp,
                    "day",
                    "spreadsheet",
                    f"{series.name}.{verb}",
                    object_id=f"{series.name}/{key}",
                    case_id=key,
                    link_method="key",
                    payload=payload,
                )
            )

        for key, row in current.items():
            before = previous.get(key)
            if before is None:
                # Rows in the first snapshot may predate it; flag them so they can be
                # told apart from rows that were genuinely added that day.
                emit(key, "add", {"row": row, "first_snapshot": i == 0})
                continue
            changes = {
                col: [before.get(col, ""), row.get(col, "")]
                for col in sorted(row.keys() | before.keys())
                if before.get(col, "") != row.get(col, "")
            }
            if changes:
                emit(key, f"update[{','.join(changes)}]", {"changes": changes})
        for key in sorted(previous.keys() - current.keys()):
            emit(key, "remove", {"row": previous[key]})
        previous = current
    return events
