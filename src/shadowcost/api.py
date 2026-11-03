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

import json
import os
import threading
import uuid
import zipfile
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shadowcost import __version__, compute
from shadowcost.agent.backtest import backtest
from shadowcost.agent.shadow_mode import run_shadow
from shadowcost.agent.spec import AgentSpec, SpecError
from shadowcost.agent.store import Store, spec_id
from shadowcost.autonomy import Stage
from shadowcost.execute import execute_day, mailbox_owner
from shadowcost.report import build_report
from shadowcost.saas.routes import router as saas_router
from shadowcost.synth import Config, simulate, write_dataset
from shadowcost.uploads import ALLOWED_SUFFIXES, MAX_UPLOAD_BYTES, extract_zip  # noqa: F401
from shadowcost.views import (
    backtest_view,
    events_view,
    execute_view,
    shadow_view,
    summary_view,
    workflows_view,
)

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
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(saas_router)


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
    return events_view(_events(dataset_id), limit, source)


# --- discovery --------------------------------------------------------------------------------


@app.get("/datasets/{dataset_id}/workflows")
def workflows(dataset_id: str, train_days: int = 80) -> dict:
    return workflows_view(*_discovery(dataset_id, train_days))


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
    return backtest_view(start, end, backtest(spec, events, start, end))


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
    return shadow_view(run, start, end, minutes, run_id)


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
    return execute_view(request.day, stage.name.lower(), result, result.queued)


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


# Shared, lock-protected caches (see compute.py); the names are kept for tests.
_ingest_uncached = compute.ingest_uncached
_ingest = compute.ingest
_discovery_cached = compute.discovery_cached


def _events(dataset_id: str):
    return _ingest(str(_folder(dataset_id))).events


def _summary(dataset_id: str) -> dict:
    folder = _folder(dataset_id)
    result = _ingest(str(folder))
    name = DATASETS.get(dataset_id, f"Upload {dataset_id}")
    return summary_view(result, folder, dataset_id, name)


def _discovery(dataset_id: str, train_days: int):
    return compute.discovery(str(_folder(dataset_id)), train_days)


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


def _db() -> Path:
    workspace().mkdir(parents=True, exist_ok=True)
    return workspace() / "shadowcost.db"
