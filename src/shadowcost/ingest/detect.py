"""Work out what each uploaded file is.

A small company's upload is a folder of whatever it has: a spreadsheet saved
every day, a bank export, a mailbox dump and some reference lists. Files are
classified from their names and column headers only, so the same code handles
layouts it has never seen, such as "Posted Date / Description / Value" bank
exports or snapshots saved as Excel.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from fnmatch import fnmatch
from pathlib import Path

import pandas as pd

TABULAR = {".csv", ".xlsx", ".xls"}
EMAIL_LOGS = {".jsonl", ".json"}
# Synthetic datasets keep their answer key next to the data; it must never be read.
DEFAULT_EXCLUDE = ("ground_truth/*", "*.md", "manifest.json", ".*")

BANK_DATE = ("date", "posted", "booking")
BANK_AMOUNT = ("amount", "credit", "value")
BANK_PAYER = ("payer", "counterparty", "description", "name")
BANK_REFERENCE = ("reference", "ref", "memo", "narrative")
EMAIL_SUBJECT = ("subject",)
EMAIL_FROM = ("from_addr", "from", "sender")

_DATE_IN_NAME = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})")


@dataclass(frozen=True)
class DetectedFile:
    path: Path  # relative to the upload folder
    kind: str  # "snapshot", "bank", "email", "table" or "skipped"
    series: str = ""  # for snapshots: the spreadsheet's name, e.g. "invoices"
    snapshot_date: date | None = None
    note: str = ""


def detect_files(root: str | Path, exclude: Iterable[str] = DEFAULT_EXCLUDE) -> list[DetectedFile]:
    root = Path(root)
    exclude = tuple(exclude)
    detected: list[DetectedFile] = []
    # Tabular files grouped by folder and name-without-date: a group of dated files
    # is a series of snapshots of one spreadsheet.
    groups: dict[tuple[Path, str], list[Path]] = defaultdict(list)

    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if any(
            fnmatch(rel.as_posix(), pattern) or fnmatch(path.name, pattern) for pattern in exclude
        ):
            continue
        suffix = path.suffix.lower()
        if suffix in TABULAR:
            stem = _DATE_IN_NAME.sub("", path.stem).strip(" _-")
            groups[(rel.parent, stem)].append(rel)
        elif suffix in EMAIL_LOGS:
            if _looks_like_email(_first_record(path).keys()):
                detected.append(DetectedFile(rel, "email"))
            else:
                detected.append(DetectedFile(rel, "skipped", note="JSON that isn't an email log"))
        else:
            detected.append(DetectedFile(rel, "skipped", note=f"unsupported file type {suffix!r}"))

    for (parent, stem), members in groups.items():
        dates = [date_in_name(rel.name) for rel in members]
        if len(members) >= 2 and all(dates):
            series = stem or parent.name
            for rel, day in zip(members, dates, strict=True):
                detected.append(DetectedFile(rel, "snapshot", series=series, snapshot_date=day))
            continue
        for rel in members:
            columns = list(read_table(root / rel, nrows=0).columns)
            detected.append(DetectedFile(rel, _classify_table(columns)))

    return sorted(detected, key=lambda f: f.path.as_posix())


def read_table(path: Path, nrows: int | None = None) -> pd.DataFrame:
    """Read a CSV or Excel file with every cell as a stripped string ("" when empty).

    Keeping values as text means snapshots are compared exactly as they were
    saved, without float rounding or date parsing changing them.
    """
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str, na_filter=False, nrows=nrows)
    else:
        df = pd.read_excel(path, dtype=str, nrows=nrows).fillna("")
    return df.map(lambda v: v.strip() if isinstance(v, str) else v)


def find_column(columns: Iterable[str], keywords: Iterable[str], exact: bool = False) -> str | None:
    """The first column matching a keyword, trying keywords in priority order.

    A column matches when its normalized name equals the keyword or, unless
    ``exact``, contains it as a word ("Posted Date" matches "date").
    """
    normalized = {col: _normalize(col) for col in columns}
    for keyword in keywords:
        for col, norm in normalized.items():
            if norm == keyword or (not exact and keyword in norm.split("_")):
                return col
    return None


def date_in_name(name: str) -> date | None:
    match = _DATE_IN_NAME.search(name)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _classify_table(columns: list[str]) -> str:
    if (
        find_column(columns, BANK_DATE)
        and find_column(columns, BANK_AMOUNT)
        and (find_column(columns, BANK_PAYER) or find_column(columns, BANK_REFERENCE))
    ):
        return "bank"
    if _looks_like_email(columns):
        return "email"
    return "table"


def _looks_like_email(columns: Iterable[str]) -> bool:
    columns = list(columns)
    return bool(
        find_column(columns, EMAIL_SUBJECT, exact=True)
        and find_column(columns, EMAIL_FROM, exact=True)
    )


def _first_record(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            if path.suffix.lower() == ".jsonl":
                line = next((line for line in fh if line.strip()), "{}")
                record = json.loads(line)
            else:
                data = json.load(fh)
                record = data[0] if isinstance(data, list) and data else data
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return record if isinstance(record, dict) else {}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
