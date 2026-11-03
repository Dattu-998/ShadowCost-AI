"""Database and file storage for the hosted product.

`SupabaseDB` talks to Supabase over HTTP (PostgREST for tables, the Storage API for files) with
the server's secret key, which bypasses row-level security; the API therefore checks workspace
membership itself before every read and write. `MemoryDB` implements the same interface in memory
for tests.

Filters are `{column: value}` for equality, or `{column: (op, value)}` with op one of
"in", "is", "gt", "lt", "neq".
"""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

BUCKET = "datasets"
Where = dict[str, Any]


class DBError(RuntimeError):
    pass


class Database(Protocol):
    def select(
        self, table: str, *, where: Where | None = None, order: str | None = None,
        limit: int | None = None,
    ) -> list[dict]: ...  # fmt: skip

    def insert(self, table: str, rows: dict | list[dict]) -> list[dict]: ...

    def update(self, table: str, values: dict, *, where: Where) -> list[dict]: ...

    def delete(self, table: str, *, where: Where) -> list[dict]: ...

    def upload(
        self, path: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None: ...

    def list_files(self, prefix: str) -> list[str]: ...

    def download(self, path: str) -> bytes: ...

    def remove_files(self, paths: list[str]) -> None: ...


def one(rows: list[dict]) -> dict | None:
    return rows[0] if rows else None


# --- Supabase ------------------------------------------------------------------------------------


class SupabaseDB:
    def __init__(self, url: str, secret_key: str, timeout: float = 30.0):
        headers = {"apikey": secret_key}
        if secret_key.startswith("eyJ"):  # a legacy service-role JWT also goes in Authorization
            headers["Authorization"] = f"Bearer {secret_key}"
        self.http = httpx.Client(base_url=url.rstrip("/"), headers=headers, timeout=timeout)

    def select(self, table, *, where=None, order=None, limit=None):
        params = {"select": "*", **_filters(where)}
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        return self._json(self.http.get(f"/rest/v1/{table}", params=params))

    def insert(self, table, rows):
        response = self.http.post(
            f"/rest/v1/{table}", json=rows, headers={"Prefer": "return=representation"}
        )
        return self._json(response)

    def update(self, table, values, *, where):
        response = self.http.patch(
            f"/rest/v1/{table}", params=_filters(where), json=values,
            headers={"Prefer": "return=representation"},
        )  # fmt: skip
        return self._json(response)

    def delete(self, table, *, where):
        response = self.http.delete(
            f"/rest/v1/{table}", params=_filters(where), headers={"Prefer": "return=representation"}
        )
        return self._json(response)

    def upload(self, path, data, content_type="application/octet-stream"):
        response = self.http.post(
            f"/storage/v1/object/{BUCKET}/{path}", content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )  # fmt: skip
        self._json(response)

    def list_files(self, prefix):
        found: list[str] = []
        pending = [prefix.rstrip("/")]
        while pending:
            folder = pending.pop()
            offset = 0
            while True:
                response = self.http.post(
                    f"/storage/v1/object/list/{BUCKET}",
                    json={"prefix": folder + "/", "limit": 1000, "offset": offset},
                )
                entries = self._json(response)
                for entry in entries:
                    path = f"{folder}/{entry['name']}"
                    (found if entry.get("id") else pending).append(path)
                if len(entries) < 1000:
                    break
                offset += 1000
        return sorted(found)

    def download(self, path):
        response = self.http.get(f"/storage/v1/object/{BUCKET}/{path}")
        if response.status_code >= 400:
            raise DBError(f"storage download failed ({response.status_code}): {path}")
        return response.content

    def remove_files(self, paths):
        for start in range(0, len(paths), 500):
            response = self.http.request(
                "DELETE",
                f"/storage/v1/object/{BUCKET}",
                json={"prefixes": paths[start : start + 500]},
            )
            self._json(response)

    @staticmethod
    def _json(response: httpx.Response):
        if response.status_code >= 400:
            raise DBError(f"Supabase error {response.status_code}: {response.text[:300]}")
        return response.json() if response.content else []


def _filters(where: Where | None) -> dict[str, str]:
    params = {}
    for column, condition in (where or {}).items():
        if isinstance(condition, tuple):
            op, value = condition
            if op == "in":
                params[column] = "in.(" + ",".join(str(v) for v in value) + ")"
            elif op == "is":
                params[column] = f"is.{'null' if value is None else str(value).lower()}"
            else:
                params[column] = f"{op}.{value}"
        elif condition is None:
            params[column] = "is.null"
        elif isinstance(condition, bool):
            params[column] = f"eq.{str(condition).lower()}"
        else:
            params[column] = f"eq.{condition}"
    return params


# --- in memory, for tests ------------------------------------------------------------------------

_IDENTITY_TABLES = {"actions", "notifications", "leads"}
# Column defaults from supabase/migrations, so tests see what Postgres would store.
_DEFAULTS = {
    "organizations": {"plan": "free", "subscription_status": None, "stripe_customer_id": None,
                      "stripe_subscription_id": None, "current_period_end": None},
    "invitations": {"accepted_at": None},
    "datasets": {"status": "ready", "error": None},
    "actions": {"status": "pending", "decided_by": None, "decided_email": None, "decided_at": None},
    "connections": {"settings": {}, "scopes": [], "last_synced_at": None, "last_error": None},
    "notifications": {"delivered": False},
}  # fmt: skip


class MemoryDB:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}
        self.files: dict[str, bytes] = {}
        self._next_identity: dict[str, int] = {}

    def select(self, table, *, where=None, order=None, limit=None):
        rows = [copy.deepcopy(r) for r in self.tables.get(table, []) if _matches(r, where)]
        if order:
            column, _, direction = order.partition(".")
            rows.sort(
                key=lambda r: (r.get(column) is None, r.get(column)), reverse=direction == "desc"
            )
        return rows[:limit] if limit else rows

    def insert(self, table, rows):
        rows = rows if isinstance(rows, list) else [rows]
        stored = []
        for row in rows:
            row = {**copy.deepcopy(_DEFAULTS.get(table, {})), **copy.deepcopy(row)}
            if table in _IDENTITY_TABLES:
                self._next_identity[table] = self._next_identity.get(table, 0) + 1
                row.setdefault("id", self._next_identity[table])
            elif table not in {"memberships"}:
                row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", datetime.now(UTC).isoformat())
            if table == "approvals":
                row.setdefault("approved_at", row["created_at"])
            self._check_unique(table, row)
            self.tables.setdefault(table, []).append(row)
            stored.append(copy.deepcopy(row))
        return stored

    def update(self, table, values, *, where):
        changed = []
        for row in self.tables.get(table, []):
            if _matches(row, where):
                row.update(copy.deepcopy(values))
                changed.append(copy.deepcopy(row))
        return changed

    def delete(self, table, *, where):
        keep, gone = [], []
        for row in self.tables.get(table, []):
            (gone if _matches(row, where) else keep).append(row)
        self.tables[table] = keep
        return gone

    def upload(self, path, data, content_type="application/octet-stream"):
        self.files[path] = bytes(data)

    def list_files(self, prefix):
        prefix = prefix.rstrip("/") + "/"
        return sorted(p for p in self.files if p.startswith(prefix))

    def download(self, path):
        if path not in self.files:
            raise DBError(f"no such file: {path}")
        return self.files[path]

    def remove_files(self, paths):
        for path in paths:
            self.files.pop(path, None)

    _UNIQUE = {
        "memberships": [("org_id", "user_id")],
        "agents": [("org_id", "spec_hash")],
        "approvals": [("agent_id", "spec_hash")],
        "connections": [("org_id", "provider")],
        "invitations": [("token_hash",)],
    }

    def _check_unique(self, table, row):
        for columns in self._UNIQUE.get(table, []):
            key = tuple(row.get(c) for c in columns)
            if any(tuple(r.get(c) for c in columns) == key for r in self.tables.get(table, [])):
                raise DBError(f"duplicate key in {table}: {dict(zip(columns, key, strict=True))}")


def _matches(row: dict, where: Where | None) -> bool:
    for column, condition in (where or {}).items():
        value = row.get(column)
        if isinstance(condition, tuple):
            op, target = condition
            if op == "in" and value not in target:
                return False
            if op == "is" and value is not target:
                return False
            if op == "neq" and value == target:
                return False
            if op == "gt" and not (value is not None and value > target):
                return False
            if op == "lt" and not (value is not None and value < target):
                return False
        elif value != condition:
            return False
    return True
