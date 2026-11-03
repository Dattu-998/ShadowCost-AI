"""JSON views shared by the public demo API and the signed-in workspace API.

Both surfaces return exactly the same shapes, so the web app renders a demo dataset and a
customer's own dataset with the same screens.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from shadowcost.agent.backtest import BacktestResult
from shadowcost.agent.shadow_mode import TIME_SAVED_SHARE, ShadowRun
from shadowcost.autonomy import DEFAULT_POLICY
from shadowcost.discover import Discovery
from shadowcost.execute import Execution
from shadowcost.ingest import IngestResult
from shadowcost.recommend import recommend


def summary_view(result: IngestResult, folder: Path, dataset_id: str, name: str) -> dict:
    events = result.events
    kinds: dict[str, int] = {}
    for f in result.files:
        kinds[f.kind] = kinds.get(f.kind, 0) + 1
    weekly = []
    if len(events):
        week = events["timestamp"].dt.to_period("W-SUN").dt.start_time.dt.date
        counts = events.groupby([week, events["source"]]).size().unstack(fill_value=0)
        weekly = [
            {"week": wk, **{src: int(n) for src, n in row.items()}} for wk, row in counts.iterrows()
        ]
    return {
        "dataset_id": dataset_id,
        "name": name,
        "files": kinds,
        "events": len(events),
        "first_day": events["timestamp"].min().date() if len(events) else None,
        "last_day": events["timestamp"].max().date() if len(events) else None,
        "by_source": {k: int(v) for k, v in events["source"].value_counts().items()},
        "linked_share": round(float((events["case_id"] != "").mean()), 3) if len(events) else 0,
        "weekly": weekly,
        "has_ground_truth": (folder / "ground_truth").is_dir(),
        "warnings": result.warnings,
    }


def events_view(events: pd.DataFrame, limit: int = 50, source: str | None = None) -> list[dict]:
    if source:
        events = events[events["source"] == source]
    rows = events.tail(max(1, min(limit, 500))).iloc[::-1]
    return [
        {
            "event_id": r.event_id,
            "timestamp": r.timestamp.isoformat(),
            "source": r.source,
            "activity": r.activity,
            "case_id": r.case_id,
            "link_method": r.link_method,
            "actor": r.actor,
            "detail": event_detail(r.source, r.payload),
        }
        for r in rows.itertuples()
    ]


def workflows_view(discovery: Discovery, split: date) -> dict:
    labels = {t.template_id: t.label for t in discovery.templates}
    return {
        "evidence_from": discovery.events["timestamp"].min().date(),
        "evidence_to": split - timedelta(days=1),
        "episodes": len(discovery.episodes),
        "templates": len(discovery.templates),
        "workflows": [
            {
                "workflow_id": r.workflow.workflow_id,
                "name": r.workflow.name,
                "instances": r.workflow.size,
                "instances_per_week": r.workflow.instances_per_week,
                "instances_per_month": r.instances_per_month,
                "trigger": {
                    "kind": r.workflow.trigger.kind,
                    "description": r.workflow.trigger.description,
                    "support": round(r.workflow.trigger.support, 3),
                },
                "condition": (
                    {
                        "description": r.workflow.condition.description,
                        "support": r.workflow.condition.support,
                        "precision": r.workflow.condition.precision,
                    }
                    if r.workflow.condition
                    else None
                ),
                "variants": [
                    {"steps": [step_label(s, labels) for s in sig], "count": n}
                    for sig, n in r.workflow.variants[:4]
                ],
                "regularity": r.workflow.regularity,
                "consistency": r.workflow.consistency,
                "minutes_per_instance": r.minutes_per_instance,
                "observed_minutes": r.observed_minutes,
                "hours_per_month": r.hours_per_month,
                "automation_score": r.automation_score,
                "addressable_hours_per_month": r.addressable_hours_per_month,
                "assumptions": r.assumptions,
                "caveats": r.caveats,
            }
            for r in recommend(discovery)
        ],
        "irregular": [{"name": w.name, "instances": w.size} for w in discovery.irregular],
    }


def backtest_view(start: date, end: date, result: BacktestResult) -> dict:
    return {
        "from": start,
        "to": end,
        **result.metrics(),
        "examples": [
            {
                "case_id": o.case_id,
                "kind": o.kind,
                "agent_day": o.agent_day,
                "human_day": o.human_day,
                "rule": o.rule,
                "differing": [f for f, ok in o.field_matches.items() if not ok],
            }
            for o in [o for o in result.outcomes if o.kind != "match"][:8]
        ],
    }


def shadow_view(run: ShadowRun, start: date, end: date, minutes: float, run_id) -> dict:
    agreed = 0
    points = []
    for i, (outcome, stage) in enumerate(run.outcomes, start=1):
        agreed += outcome.agrees
        points.append(
            {
                "day": outcome.resolved_on,
                "stage": stage.name.lower(),
                "agrees": outcome.agrees,
                "kind": outcome.kind,
                "agreement_so_far": round(agreed / i, 3),
            }
        )
    return {
        "run_id": run_id,
        "from": start,
        "to": end,
        "cases": len(run.outcomes),
        "final_stage": run.final_stage.name.lower(),
        "changes": [
            {
                "day": c.day,
                "action": c.decision.action,
                "from": c.decision.current.name.lower(),
                "to": c.decision.next.name.lower(),
                "reason": c.decision.reason,
                "cases": c.decision.n,
                "agreement": round(c.decision.agreement, 3),
                "lower_bound": round(c.decision.lower_bound, 3),
            }
            for c in run.changes
        ],
        "by_stage": {s.name.lower(): v for s, v in run.by_stage().items()},
        "points": points,
        "minutes_per_case": minutes,
        "hours_saved_estimated": round(run.minutes_saved() / 60, 2),
        "policy": {
            "min_cases": DEFAULT_POLICY.min_cases,
            "promote_lower_bound": DEFAULT_POLICY.promote_lower_bound,
            "time_saved_share": {s.name.lower(): v for s, v in TIME_SAVED_SHARE.items()},
        },
    }


def execute_view(day: date, stage_name: str, result: Execution, queued: list) -> dict:
    return {
        "day": day,
        "stage": stage_name,
        "proposals": [
            {"case_id": p.case_id, "rule": p.rule, "updates": p.updates, "email": p.email}
            for p in result.proposals
        ],
        "drafts": len(result.drafts),
        "queued": queued,
        "ready": len(result.ready),
        "sheet_written": result.sheet is not None,
    }


def step_label(step: str, template_labels: dict[str, str]) -> str:
    if step.startswith("email.sent:"):
        return f"email: {template_labels.get(step.split(':', 1)[1], step)}"
    return step


def event_detail(source: str, payload: dict) -> str:
    if source == "email":
        return payload.get("subject", "")
    if source == "bank":
        return f"{payload.get('amount', '')} from {payload.get('payer', '')}"
    if "changes" in payload:
        changes = payload["changes"].items()
        return ", ".join(f"{k}: {old or '-'} > {new}" for k, (old, new) in changes)
    return "new row"
