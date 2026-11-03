"""A workspace's datasets: files in private storage, processed on the API's local disk.

Files live in the `datasets` bucket under `<org>/<dataset>/`. To process a dataset the API
downloads it into `<workspace>/cache/<dataset>/<version>/`; the version changes on every upload or
sync, so the compute caches (keyed by folder) never serve a stale result.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException

from shadowcost import compute
from shadowcost.saas.db import Database, one
from shadowcost.views import summary_view

CONTENT_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".md": "text/markdown",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}


def cache_root() -> Path:
    return Path(os.environ.get("SHADOWCOST_WORKSPACE", "workspace")) / "cache"


def sample_folder() -> Path:
    return Path(os.environ.get("SHADOWCOST_SAMPLE", "data/sample"))


def get_dataset(db: Database, org_id: str, dataset_id: str) -> dict:
    found = one(db.select("datasets", where={"id": dataset_id, "org_id": org_id}))
    if not found:
        raise HTTPException(404, "no such dataset")
    return found


def store_files(db: Database, org_id: str, dataset_id: str, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        suffix = Path(rel).suffix.lower()
        db.upload(
            f"{org_id}/{dataset_id}/{rel}",
            data,
            CONTENT_TYPES.get(suffix, "application/octet-stream"),
        )


def files_from_folder(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.suffix.lower() in CONTENT_TYPES
    }


def create_dataset(
    db: Database, org_id: str, user_id: str | None, name: str, source: str,
    files: dict[str, bytes], extra: dict | None = None,
) -> dict:  # fmt: skip
    dataset_id = str(uuid.uuid4())
    store_files(db, org_id, dataset_id, files)
    row = db.insert(
        "datasets",
        {
            "id": dataset_id,
            "org_id": org_id,
            "name": name,
            "source": source,
            "storage_prefix": f"{org_id}/{dataset_id}",
            "status": "processing",
            "summary": {"version": uuid.uuid4().hex, **(extra or {})},
            "created_by": user_id,
        },
    )[0]
    return refresh_summary(db, row)


def refresh_summary(db: Database, dataset: dict, new_version: bool = False) -> dict:
    """Process the dataset and store its summary (or the error) on the row."""
    meta = dict(dataset.get("summary") or {})
    if new_version or "version" not in meta:
        meta["version"] = uuid.uuid4().hex
    dataset = {**dataset, "summary": meta}
    try:
        folder = materialize(db, dataset)
        summary = summary_view(compute.ingest(str(folder)), folder, dataset["id"], dataset["name"])
        if not summary["events"]:
            raise ValueError(
                "no usable events: add dated spreadsheet copies, a bank export or an email log"
            )
        values = {
            "status": "ready",
            "error": None,
            "summary": json.loads(json.dumps({**meta, **summary}, default=str)),
        }
    except (ValueError, KeyError) as err:
        values = {"status": "error", "error": str(err)[:500], "summary": meta}
    return db.update("datasets", values, where={"id": dataset["id"]})[0]


def materialize(db: Database, dataset: dict) -> Path:
    """The dataset's files on local disk, downloaded once per version."""
    version = (dataset.get("summary") or {}).get("version", "v0")
    folder = cache_root() / dataset["id"] / version
    marker = folder / ".complete"
    if marker.exists():
        return folder
    parent = cache_root() / dataset["id"]
    if parent.exists():
        shutil.rmtree(parent, ignore_errors=True)  # older versions
    prefix = dataset["storage_prefix"]
    paths = db.list_files(prefix)
    if not paths:
        raise ValueError("the dataset has no files")
    for path in paths:
        target = folder / path[len(prefix) + 1 :]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(db.download(path))
    marker.write_text(version)
    return folder


def delete_dataset(db: Database, dataset: dict) -> None:
    paths = db.list_files(dataset["storage_prefix"])
    if paths:
        db.remove_files(paths)
    db.delete("datasets", where={"id": dataset["id"]})
    shutil.rmtree(cache_root() / dataset["id"], ignore_errors=True)
