"""Cached heavy work (reading files, discovery), shared by the demo API and the workspace API.

The first requests after a cold start arrive together. Without the lock each would read the
files and run discovery on its own, multiplying memory on a small instance; with it, one does the
work and the others wait for the cached result. Caches are keyed by folder path, so a dataset that
changes is materialised into a new folder and never served stale.
"""

from __future__ import annotations

import threading
from datetime import date, timedelta
from functools import lru_cache

from shadowcost.discover import Discovery, discover
from shadowcost.ingest import IngestResult, ingest_folder

compute_lock = threading.RLock()


@lru_cache(maxsize=16)
def ingest_uncached(folder: str) -> IngestResult:
    return ingest_folder(folder)


def ingest(folder: str) -> IngestResult:
    with compute_lock:
        return ingest_uncached(folder)


@lru_cache(maxsize=16)
def discovery_cached(folder: str, train_days: int) -> tuple[Discovery, date]:
    events = ingest(folder).events
    split = events["timestamp"].min().date() + timedelta(days=train_days)
    return discover(events[events["timestamp"].dt.date < split]), split


def discovery(folder: str, train_days: int) -> tuple[Discovery, date]:
    with compute_lock:
        return discovery_cached(folder, train_days)
