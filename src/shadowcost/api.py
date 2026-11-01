"""HTTP API over the whole flow: upload, discover, test, approve, shadow, report.

    uvicorn shadowcost.api:app --reload

Datasets live under ``$SHADOWCOST_WORKSPACE/datasets`` (default ``workspace``);
the bundled sample is always available as ``sample``. Approvals and shadow
runs go to the same SQLite store the CLI uses, so the API and the CLI see the
same approvals.

Uploads are untrusted: a zip may only contain data files, may not write
outside its own folder, and is size-limited.
"""

from __future__ import annotations

import io
import os
import uuid
import zipfile
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel

from shadowcost import __version__
from shadowcost.agent.backtest import backtest
from shadowcost.agent.shadow_mode import run_shadow
from shadowcost.agent.spec import AgentSpec, SpecError
from shadowcost.agent.store import Store
from shadowcost.discover import discover
from shadowcost.ingest import ingest_folder
from shadowcost.recommend import recommend
from shadowcost.report import build_report

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIXES = {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".md"}


def workspace() -> Path:
    return Path(os.environ.get("SHADOWCOST_WORKSPACE", "workspace"))


def sample_folder() -> Path:
    return Path(os.environ.get("SHADOWCOST_SAMPLE", "data/sample"))


app = FastAPI(
    title="ShadowCost",
    version=__version__,
    description="Find repetitive spreadsheet and email work; agents earn autonomy in shadow mode.",
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


class ReportRequest(BaseModel):
    specs: list[dict]
    train_days: int = 80


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/datasets")
def list_datasets() -> list[str]:
    uploaded = workspace() / "datasets"
    names = sorted(p.name for p in uploaded.iterdir() if p.is_dir()) if uploaded.exists() else []
    return ["sample", *names]


@app.post("/datasets", status_code=201)
async def upload_dataset(file: UploadFile) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"upload is larger than {MAX_UPLOAD_BYTES // 2**20} MB")
    dataset_id = uuid.uuid4().hex[:12]
    target = workspace() / "datasets" / dataset_id
    try:
        extract_zip(data, target)
    except (zipfile.BadZipFile, ValueError) as err:
        raise HTTPException(400, str(err)) from err
    return {"dataset_id": dataset_id, **_ingest_summary(dataset_id)}


@app.get("/datasets/{dataset_id}")
def dataset_summary(dataset_id: str) -> dict:
    return _ingest_summary(dataset_id)


@app.get("/datasets/{dataset_id}/workflows")
def workflows(dataset_id: str, train_days: int = 80) -> dict:
    discovery, split = _discovery(dataset_id, train_days)
    return {
        "evidence_period_end": (split - timedelta(days=1)).isoformat(),
        "workflows": [
            {
                "workflow_id": r.workflow.workflow_id,
                "name": r.workflow.name,
                "instances": r.workflow.size,
                "trigger": r.workflow.trigger.description,
                "condition": r.workflow.condition.description if r.workflow.condition else None,
                "instances_per_month": r.instances_per_month,
                "minutes_per_instance": r.minutes_per_instance,
                "hours_per_month": r.hours_per_month,
                "automation_score": r.automation_score,
                "assumptions": r.assumptions,
                "caveats": r.caveats,
            }
            for r in recommend(discovery)
        ],
        "irregular": [w.name for w in discovery.irregular],
    }


@app.post("/datasets/{dataset_id}/backtest")
def run_backtest(dataset_id: str, request: SpecRequest) -> dict:
    spec = _spec(request.spec)
    events = _events(dataset_id)
    start, end = _period(spec, events, request.start, request.end)
    return {"from": start, "to": end, **backtest(spec, events, start, end).metrics()}


@app.post("/specs/approve")
def approve(request: ApproveRequest) -> dict:
    spec = _spec(request.spec)
    store = Store(_db())
    try:
        return {"spec_id": store.approve(spec, request.by), "approved_by": request.by}
    finally:
        store.close()


@app.post("/datasets/{dataset_id}/shadow")
def shadow(dataset_id: str, request: ShadowRequest) -> dict:
    spec = _spec(request.spec)
    store = Store(_db())
    try:
        if not store.approval(spec):
            raise HTTPException(403, "this spec has not been approved (or changed since)")
        events = _events(dataset_id)
        start, end = _period(spec, events, request.start, request.end)
        minutes = request.minutes_per_case or request.spec.get("evaluation", {}).get(
            "minutes_per_case", 0
        )
        run = run_shadow(spec, events, start, end, minutes)
        run_id = store.save_run(run)
    finally:
        store.close()
    return {
        "run_id": run_id,
        "cases": len(run.outcomes),
        "final_stage": run.final_stage.name.lower(),
        "changes": [
            {
                "day": c.day,
                "action": c.decision.action,
                "to": c.decision.next.name.lower(),
                "reason": c.decision.reason,
            }
            for c in run.changes
        ],  # fmt: skip
        "by_stage": {s.name.lower(): v for s, v in run.by_stage().items()},
        "hours_saved_estimated": round(run.minutes_saved() / 60, 2),
    }


@app.post("/datasets/{dataset_id}/report")
def report(dataset_id: str, request: ReportRequest) -> dict:
    specs = [(_spec(s), s.get("evaluation", {})) for s in request.specs]
    built = build_report(_folder(dataset_id), specs, request.train_days)
    return {"markdown": built.markdown(), "html": built.html()}


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


def _folder(dataset_id: str) -> Path:
    if dataset_id == "sample":
        return sample_folder()
    if not dataset_id.isalnum():
        raise HTTPException(404, "no such dataset")
    folder = workspace() / "datasets" / dataset_id
    if not folder.is_dir():
        raise HTTPException(404, "no such dataset")
    return folder


@lru_cache(maxsize=8)
def _ingest(folder: str):
    return ingest_folder(folder)


def _events(dataset_id: str):
    return _ingest(str(_folder(dataset_id))).events


def _ingest_summary(dataset_id: str) -> dict:
    result = _ingest(str(_folder(dataset_id)))
    events = result.events
    return {
        "files": len(result.files),
        "events": len(events),
        "first_day": events["timestamp"].min().date() if len(events) else None,
        "last_day": events["timestamp"].max().date() if len(events) else None,
        "by_source": events["source"].value_counts().to_dict(),
        "warnings": result.warnings,
    }


@lru_cache(maxsize=8)
def _discovery_cached(folder: str, train_days: int):
    events = _ingest(folder).events
    split = events["timestamp"].min().date() + timedelta(days=train_days)
    return discover(events[events["timestamp"].dt.date < split]), split


def _discovery(dataset_id: str, train_days: int):
    return _discovery_cached(str(_folder(dataset_id)), train_days)


def _spec(data: dict) -> AgentSpec:
    try:
        return AgentSpec.from_dict(data)
    except SpecError as err:
        raise HTTPException(422, {"problems": err.problems}) from err


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
