"""SQLite record of specs, approvals and shadow-mode results.

Approval is what lets a spec leave the lab: ``shadow`` refuses to run a spec
nobody has approved. Each shadow run stores every outcome with the stage the
agent was at, and every promotion or demotion, so the trail behind an agent's
autonomy can be audited later.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from shadowcost.agent.shadow_mode import ShadowRun
from shadowcost.agent.spec import AgentSpec

SCHEMA = """
CREATE TABLE IF NOT EXISTS specs (
    spec_id     TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    name        TEXT NOT NULL,
    spec_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id     TEXT NOT NULL REFERENCES specs(spec_id),
    started_at  TEXT NOT NULL,
    period_from TEXT NOT NULL,
    period_to   TEXT NOT NULL,
    final_stage TEXT NOT NULL,
    minutes_saved REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes (
    run_id      INTEGER NOT NULL REFERENCES runs(run_id),
    case_id     TEXT NOT NULL,
    kind        TEXT NOT NULL,
    stage       TEXT NOT NULL,
    agent_day   TEXT,
    human_day   TEXT,
    rule        TEXT,
    detail_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stage_changes (
    run_id      INTEGER NOT NULL REFERENCES runs(run_id),
    day         TEXT NOT NULL,
    action      TEXT NOT NULL,
    from_stage  TEXT NOT NULL,
    to_stage    TEXT NOT NULL,
    reason      TEXT NOT NULL
);
"""


def spec_id(spec: AgentSpec) -> str:
    """A content hash, so any edit to a spec needs a fresh approval."""
    body = json.dumps({k: v for k, v in spec.to_dict().items() if k != "source"}, sort_keys=True)
    return f"{spec.workflow_id}-{hashlib.sha256(body.encode()).hexdigest()[:10]}"


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def register(self, spec: AgentSpec) -> str:
        sid = spec_id(spec)
        self.db.execute(
            "INSERT OR IGNORE INTO specs (spec_id, workflow_id, name, spec_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, spec.workflow_id, spec.name, json.dumps(spec.to_dict()), _now()),
        )
        self.db.commit()
        return sid

    def approve(self, spec: AgentSpec, approved_by: str) -> str:
        sid = self.register(spec)
        self.db.execute(
            "UPDATE specs SET approved_by = ?, approved_at = ? WHERE spec_id = ?",
            (approved_by, _now(), sid),
        )
        self.db.commit()
        return sid

    def approval(self, spec: AgentSpec) -> tuple[str, str] | None:
        row = self.db.execute(
            "SELECT approved_by, approved_at FROM specs "
            "WHERE spec_id = ? AND approved_by IS NOT NULL",
            (spec_id(spec),),
        ).fetchone()
        return tuple(row) if row else None

    def save_run(self, run: ShadowRun) -> int:
        sid = self.register(run.spec)
        cursor = self.db.execute(
            "INSERT INTO runs (spec_id, started_at, period_from, period_to, final_stage, "
            "minutes_saved) VALUES (?, ?, ?, ?, ?, ?)",
            (
                sid,
                _now(),
                run.start.isoformat(),
                run.end.isoformat(),
                run.final_stage.name,
                run.minutes_saved(),
            ),
        )
        run_id = cursor.lastrowid
        self.db.executemany(
            "INSERT INTO outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    o.case_id,
                    o.kind,
                    stage.name,
                    _iso(o.agent_day),
                    _iso(o.human_day),
                    o.rule,
                    json.dumps(
                        {"fields": o.field_matches, "agent": o.agent, "human": o.human}, default=str
                    ),
                )
                for o, stage in run.outcomes
            ],
        )
        self.db.executemany(
            "INSERT INTO stage_changes VALUES (?, ?, ?, ?, ?, ?)",
            [
                (run_id, c.day.isoformat(), c.decision.action, c.decision.current.name,
                 c.decision.next.name, c.decision.reason)
                for c in run.changes
            ],
        )  # fmt: skip
        self.db.commit()
        return run_id


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _iso(day) -> str | None:
    return day.isoformat() if day else None
