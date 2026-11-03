"""Untrusted uploads: extract only data files, never outside the target folder, size-capped."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path, PurePosixPath

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIXES = {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".md"}


def extract_zip(data: bytes, target: Path) -> None:
    """Extract only data files, refusing any path that would escape ``target``."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if sum(m.file_size for m in members) > 4 * MAX_UPLOAD_BYTES:
            raise ValueError("zip expands to more than 200 MB")
        for member in members:
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe path in zip: {member.filename}")
            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            out = target.joinpath(*path.parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(archive.read(member))
    if not target.exists():
        raise ValueError("the zip contains no CSV, Excel or JSON files")
