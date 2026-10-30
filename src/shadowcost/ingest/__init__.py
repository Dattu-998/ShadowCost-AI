"""Upload step: turn a folder of a small company's files into one event table."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from shadowcost.ingest.bank import bank_events
from shadowcost.ingest.detect import DEFAULT_EXCLUDE, DetectedFile, detect_files, read_table
from shadowcost.ingest.events import EVENT_COLUMNS, load_events, make_event_table, save_events
from shadowcost.ingest.linking import CaseIndex
from shadowcost.ingest.mail import email_events
from shadowcost.ingest.snapshots import index_cases, load_series, series_events

__all__ = [
    "EVENT_COLUMNS",
    "IngestResult",
    "ingest_folder",
    "load_events",
    "save_events",
]


@dataclass
class IngestResult:
    root: Path
    events: pd.DataFrame
    tables: dict[str, pd.DataFrame]  # reference data such as a customer list
    files: list[DetectedFile]
    warnings: list[str]

    def summary(self) -> str:
        kinds = defaultdict(int)
        for f in self.files:
            kinds[f.kind] += 1
        series = sorted({f.series for f in self.files if f.kind == "snapshot"})
        lines = [
            f"Ingested {self.root}",
            "  files:  "
            + ", ".join(
                [
                    f"{kinds['snapshot']} snapshots ({', '.join(series) or 'none'})",
                    f"{kinds['bank']} bank export(s)",
                    f"{kinds['email']} email log(s)",
                    f"{kinds['table']} reference table(s)",
                    f"{kinds['skipped']} skipped",
                ]
            ),
        ]
        if len(self.events):
            by_source = self.events.groupby("source")
            counts = by_source.size()
            linked = by_source["case_id"].apply(lambda s: (s != "").mean())
            lines.append("  events: " + ", ".join(f"{src} {n}" for src, n in counts.items()))
            lines.append(
                "  linked to a case: "
                + ", ".join(f"{src} {rate:.0%}" for src, rate in linked.items())
            )
        lines += [f"  warning: {w}" for w in self.warnings]
        return "\n".join(lines)


def ingest_folder(root: str | Path, exclude: Iterable[str] = DEFAULT_EXCLUDE) -> IngestResult:
    root = Path(root)
    files = detect_files(root, exclude)
    warnings = [f"skipped {f.path}: {f.note}" for f in files if f.kind == "skipped"]
    index = CaseIndex()
    rows: list[dict] = []

    # Spreadsheets first: their row keys are what payments and emails get linked to.
    by_series: dict[str, list[DetectedFile]] = defaultdict(list)
    for f in files:
        if f.kind == "snapshot":
            by_series[f.series].append(f)
    for name, members in by_series.items():
        try:
            series = load_series(root, members)
        except ValueError as err:
            warnings.append(f"snapshot series {name!r} skipped: {err}")
            continue
        index_cases(series, index)
        rows += series_events(series)

    for f in files:
        if f.kind == "bank":
            new_rows, new_warnings = bank_events(root, f, index)
        elif f.kind == "email":
            new_rows, new_warnings = email_events(root, f, index)
        else:
            continue
        rows += new_rows
        warnings += new_warnings

    tables = {f.path.stem: read_table(root / f.path) for f in files if f.kind == "table"}
    return IngestResult(root, make_event_table(rows), tables, files, warnings)
