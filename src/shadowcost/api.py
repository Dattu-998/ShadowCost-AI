"""HTTP API over the whole flow, for the web frontend and for scripts.

    uvicorn shadowcost.api:app --reload

Datasets: ``sample`` (the bundled 4 months), ``year`` (a simulated year,
generated on first use) and uploaded zips. Specs: the bundled ones in
``$SHADOWCOST_SPECS`` (default ``specs``). Approvals, shadow runs and the
approval queue go to the same SQLite store the CLI uses, under
``$SHADOWCOST_WORKSPACE`` (default ``workspace``).

Uploads are untrusted: a zip may only contain data files, may not write
outside its own folder, and is size-limited. Shadow mode and execution refuse
specs nobody has approved.

``$SHADOWCOST_CORS_ORIGINS`` is a comma-separated list of browser origins
allowed to call the API (default ``*``; the API uses no cookies).
"""

from __future__ import annotations

import io
import json
import os
import threading
import uuid
import zipfile
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shadowcost import __version__
from shadowcost.agent.backtest import backtest
from shadowcost.agent.shadow_mode import TIME_SAVED_SHARE, run_shadow
from shadowcost.agent.spec import AgentSpec, SpecError
from shadowcost.agent.store import Store, spec_id
from shadowcost.autonomy import DEFAULT_POLICY, Stage
from shadowcost.discover import discover
from shadowcost.execute import execute_day, mailbox_owner
from shadowcost.ingest import ingest_folder
from shadowcost.recommend import recommend
from shadowcost.report import build_report
from shadowcost.synth import Config, simulate, write_dataset

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIXES = {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".md"}
DATASETS = {
    "sample": "Fernhill Supplies, 4 months (bundled)",
    "year": "Fernhill Supplies, a simulated year",
}


def workspace() -> Path:
    return Path(os.environ.get("SHADOWCOST_WORKSPACE", "workspace"))


def sample_folder() -> Path:
    return Path(os.environ.get("SHADOWCOST_SAMPLE", "data/sample"))


def specs_folder() -> Path:
    return Path(os.environ.get("SHADOWCOST_SPECS", "specs"))


app = FastAPI(
    title="ShadowCost",
    version=__version__,
    description="Find repetitive spreadsheet and email work; agents earn autonomy in shadow mode.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("SHADOWCOST_CORS_ORIGINS", "*").split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class SpecRequest(BaseModel):
    spec: dict
    start: date | None = None
    end: date | None = None


class ShadowRequest(SpecRequest):
    minutes_per_case: float | None = None


class ApproveRequest(BaseModel):
    spec: dict
    by: str


class ExecuteRequest(BaseModel):
    spec: dict
    day: date
    stage: str


class DecisionRequest(BaseModel):
    approve: bool
    by: str


class ReportRequest(BaseModel):
    specs: list[dict]
    train_days: int = 80


# --- datasets -------------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/datasets")
def list_datasets() -> list[dict]:
    uploaded = workspace() / "datasets"
    names = sorted(p.name for p in uploaded.iterdir() if p.is_dir()) if uploaded.exists() else []
    return [{"id": k, "name": v} for k, v in DATASETS.items()] + [
        {"id": n, "name": f"Upload {n}"} for n in names
    ]


@app.post("/datasets", status_code=201)
async def upload_dataset(file: UploadFile) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"upload is larger than {MAX_UPLOAD_BYTES // 2**20} MB")
    dataset_id = uuid.uuid4().hex[:12]
    try:
        extract_zip(data, workspace() / "datasets" / dataset_id)
    except (zipfile.BadZipFile, ValueError) as err:
        raise HTTPException(400, str(err)) from err
    return {"dataset_id": dataset_id, **_summary(dataset_id)}


@app.get("/datasets/{dataset_id}")
def dataset_summary(dataset_id: str) -> dict:
    return _summary(dataset_id)


@app.get("/datasets/{dataset_id}/events")
def recent_events(dataset_id: str, limit: int = 50, source: str | None = None) -> list[dict]:
    events = _events(dataset_id)
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
            "detail": _event_detail(r.source, r.payload),
        }
        for r in rows.itertuples()
    ]


# --- discovery --------------------------------------------------------------------------------


@app.get("/datasets/{dataset_id}/workflows")
def workflows(dataset_id: str, train_days: int = 80) -> dict:
    discovery, split = _discovery(dataset_id, train_days)
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
                    {"steps": [_step_label(s, labels) for s in sig], "count": n}
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


# --- specs and approval -----------------------------------------------------------------------


@app.get("/specs")
def list_specs() -> list[dict]:
    store = Store(_db())
    try:
        out = []
        for path in sorted(specs_folder().glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            spec = AgentSpec.from_dict(data)
            approval = store.approval(spec)
            out.append(
                {
                    "spec_id": spec_id(spec),
                    "spec": data,
                    "approved_by": approval[0] if approval else None,
                    "approved_at": approval[1] if approval else None,
                }
            )
        return out
    finally:
        store.close()


@app.post("/specs/approve")
def approve(request: ApproveRequest) -> dict:
    spec = _spec(request.spec)
    if not request.by.strip():
        raise HTTPException(422, "say who is approving")
    store = Store(_db())
    try:
        return {"spec_id": store.approve(spec, request.by.strip()), "approved_by": request.by}
    finally:
        store.close()


@app.post("/datasets/{dataset_id}/backtest")
def run_backtest(dataset_id: str, request: SpecRequest) -> dict:
    spec = _spec(request.spec)
    events = _events(dataset_id)
    start, end = _period(spec, events, request.start, request.end)
    result = backtest(spec, events, start, end)
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


# --- shadow mode, execution, approval queue ---------------------------------------------------


@app.post("/datasets/{dataset_id}/shadow")
def shadow(dataset_id: str, request: ShadowRequest) -> dict:
    spec = _spec(request.spec)
    store = Store(_db())
    try:
        _require_approval(store, spec)
        events = _events(dataset_id)
        start, end = _period(spec, events, request.start, request.end)
        minutes = request.minutes_per_case or request.spec.get("evaluation", {}).get(
            "minutes_per_case", 0
        )
        run = run_shadow(spec, events, start, end, minutes)
        run_id = store.save_run(run)
    finally:
        store.close()

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


@app.post("/datasets/{dataset_id}/execute")
def execute(dataset_id: str, request: ExecuteRequest) -> dict:
    spec = _spec(request.spec)
    try:
        stage = Stage[request.stage.upper()]
    except KeyError as err:
        raise HTTPException(422, "stage must be shadow, draft, approval or autonomous") from err
    store = Store(_db())
    try:
        _require_approval(store, spec)
        events = _events(dataset_id)
        result = execute_day(
            spec, stage, request.day, events, workspace() / "outbox", store, mailbox_owner(events)
        )
    finally:
        store.close()
    return {
        "day": request.day,
        "stage": stage.name.lower(),
        "proposals": [
            {"case_id": p.case_id, "rule": p.rule, "updates": p.updates, "email": p.email}
            for p in result.proposals
        ],
        "drafts": len(result.drafts),
        "queued": result.queued,
        "ready": len(result.ready),
        "sheet_written": result.sheet is not None,
    }


@app.get("/actions")
def actions(status: str | None = "pending") -> list[dict]:
    store = Store(_db())
    try:
        return store.actions(status)
    finally:
        store.close()


@app.post("/actions/{action_id}/decision")
def decide(action_id: int, request: DecisionRequest) -> dict:
    store = Store(_db())
    try:
        return store.decide(action_id, request.approve, request.by)
    except KeyError as err:
        raise HTTPException(404, str(err)) from err
    except ValueError as err:
        raise HTTPException(409, str(err)) from err
    finally:
        store.close()


@app.post("/datasets/{dataset_id}/report")
def report(dataset_id: str, request: ReportRequest) -> dict:
    specs = [(_spec(s), s.get("evaluation", {})) for s in request.specs]
    built = build_report(_folder(dataset_id), specs, request.train_days)
    return {"markdown": built.markdown(), "html": built.html()}


# --- helpers ----------------------------------------------------------------------------------


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


_year_lock = threading.Lock()


def _folder(dataset_id: str) -> Path:
    if dataset_id == "sample":
        return sample_folder()
    if dataset_id == "year":
        folder = workspace() / "year"
        with _year_lock:
            if not (folder / "manifest.json").exists():
                write_dataset(simulate(Config(seed=7, days=365)), folder, overwrite=True)
        return folder
    if not dataset_id.isalnum():
        raise HTTPException(404, "no such dataset")
    folder = workspace() / "datasets" / dataset_id
    if not folder.is_dir():
        raise HTTPException(404, "no such dataset")
    return folder


# The first requests after a cold start arrive together. Without this lock each would read the
# files and run discovery on its own, multiplying memory on a small instance; with it, one does the
# work and the others wait for the cached result.
_compute_lock = threading.RLock()


@lru_cache(maxsize=8)
def _ingest_uncached(folder: str):
    return ingest_folder(folder)


def _ingest(folder: str):
    with _compute_lock:
        return _ingest_uncached(folder)


def _events(dataset_id: str):
    return _ingest(str(_folder(dataset_id))).events


def _summary(dataset_id: str) -> dict:
    result = _ingest(str(_folder(dataset_id)))
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
        "name": DATASETS.get(dataset_id, f"Upload {dataset_id}"),
        "files": kinds,
        "events": len(events),
        "first_day": events["timestamp"].min().date() if len(events) else None,
        "last_day": events["timestamp"].max().date() if len(events) else None,
        "by_source": {k: int(v) for k, v in events["source"].value_counts().items()},
        "linked_share": round(float((events["case_id"] != "").mean()), 3) if len(events) else 0,
        "weekly": weekly,
        "has_ground_truth": (_folder(dataset_id) / "ground_truth").is_dir(),
        "warnings": result.warnings,
    }


@lru_cache(maxsize=8)
def _discovery_cached(folder: str, train_days: int):
    events = _ingest(folder).events
    split = events["timestamp"].min().date() + timedelta(days=train_days)
    return discover(events[events["timestamp"].dt.date < split]), split


def _discovery(dataset_id: str, train_days: int):
    folder = str(_folder(dataset_id))
    with _compute_lock:
        return _discovery_cached(folder, train_days)


def _spec(data: dict) -> AgentSpec:
    try:
        return AgentSpec.from_dict(data)
    except SpecError as err:
        raise HTTPException(422, {"problems": err.problems}) from err


def _require_approval(store: Store, spec: AgentSpec) -> None:
    if not store.approval(spec):
        raise HTTPException(403, "this spec has not been approved (or changed since)")


def _period(spec: AgentSpec, events, start: date | None, end: date | None) -> tuple[date, date]:
    if start is None:
        period = spec.source.get("evidence_period")
        if not period:
            raise HTTPException(422, "give 'start', or a spec with source.evidence_period")
        start = date.fromisoformat(period[1]) + timedelta(days=1)
    return start, end or events["timestamp"].max().date()


def _step_label(step: str, template_labels: dict[str, str]) -> str:
    if step.startswith("email.sent:"):
        return f"email: {template_labels.get(step.split(':', 1)[1], step)}"
    return step


def _event_detail(source: str, payload: dict) -> str:
    if source == "email":
        return payload.get("subject", "")
    if source == "bank":
        return f"{payload.get('amount', '')} from {payload.get('payer', '')}"
    if "changes" in payload:
        return ", ".join(
            f"{k}: {old or '-'} > {new}" for k, (old, new) in payload["changes"].items()
        )
    return "new row"


def _db() -> Path:
    workspace().mkdir(parents=True, exist_ok=True)
    return workspace() / "shadowcost.db"
