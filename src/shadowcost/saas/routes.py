"""The signed-in product API, under /v1. Every route checks the caller's workspace role first.

Responses use the same shapes as the public demo API (see views.py), so the web app renders a
customer's data with the same screens as the demo.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import tempfile
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from shadowcost import compute
from shadowcost.agent.backtest import backtest
from shadowcost.agent.generate import generate_spec
from shadowcost.agent.shadow_mode import run_shadow
from shadowcost.agent.spec import AgentSpec, SpecError
from shadowcost.agent.store import spec_id as spec_hash
from shadowcost.autonomy import STAGES_ORDER, Stage
from shadowcost.execute import execute_day, mailbox_owner
from shadowcost.llm import ChatClient
from shadowcost.recommend import recommend
from shadowcost.report import build_report, load_specs
from shadowcost.saas import billing, data, google
from shadowcost.saas.auth import RANK, User, current_user, membership
from shadowcost.saas.config import settings
from shadowcost.saas.db import Database, DBError, SupabaseDB, one
from shadowcost.saas.notify import notify
from shadowcost.saas.plans import plan_of, plans_view, require_room, usage
from shadowcost.uploads import MAX_UPLOAD_BYTES, extract_zip
from shadowcost.views import (
    backtest_view,
    events_view,
    execute_view,
    shadow_view,
    workflows_view,
)

router = APIRouter(prefix="/v1", tags=["workspaces"])
_db: Database | None = None
MAX_TRAIN_DAYS = 80
MIN_TRAIN_DAYS = 21


def get_db() -> Database:
    global _db
    if _db is None:
        s = settings()
        if not s.auth_enabled:
            raise HTTPException(503, "accounts are not configured on this server")
        _db = SupabaseDB(s.supabase_url, s.supabase_secret_key)
    return _db


DB = Depends(get_db)
CURRENT = Depends(current_user)


class NewOrg(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class Invite(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = "approver"


class RoleChange(BaseModel):
    role: str


class Token(BaseModel):
    token: str


class DatasetRef(BaseModel):
    dataset_id: str


class RunDay(DatasetRef):
    day: date
    stage: str


class Decision(BaseModel):
    approve: bool


class Checkout(BaseModel):
    plan: str


class GoogleSettings(BaseModel):
    spreadsheet: str = ""
    sheet_range: str = "A1:Z5000"
    gmail_query: str = "newer_than:90d"


# --- me and workspaces ---------------------------------------------------------------------------


@router.get("/me")
def me(user: User = CURRENT, db: Database = DB) -> dict:
    memberships = db.select("memberships", where={"user_id": user.id})
    orgs = {
        o["id"]: o
        for o in db.select(
            "organizations", where={"id": ("in", [m["org_id"] for m in memberships] or [""])}
        )
    }
    return {
        "user": {"id": user.id, "email": user.email},
        "workspaces": [
            {
                "id": m["org_id"],
                "name": orgs[m["org_id"]]["name"],
                "role": m["role"],
                "plan": orgs[m["org_id"]].get("plan") or "free",
            }
            for m in memberships
            if m["org_id"] in orgs
        ],
        "features": settings().features(),
    }


@router.post("/orgs", status_code=201)
def create_org(body: NewOrg, user: User = CURRENT, db: Database = DB) -> dict:
    owned = [
        m for m in db.select("memberships", where={"user_id": user.id}) if m["role"] == "owner"
    ]
    if len(owned) >= 3:
        raise HTTPException(409, "you can own up to 3 workspaces")
    org = db.insert("organizations", {"name": body.name.strip(), "created_by": user.id})[0]
    db.insert(
        "memberships",
        {"org_id": org["id"], "user_id": user.id, "email": user.email, "role": "owner"},
    )
    return org_view(db, org, "owner")


@router.get("/orgs/{org_id}")
def get_org(org_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    m = membership(db, org_id, user)
    return org_view(db, _org(db, org_id), m["role"])


@router.patch("/orgs/{org_id}")
def rename_org(org_id: str, body: NewOrg, user: User = CURRENT, db: Database = DB) -> dict:
    m = membership(db, org_id, user, "admin")
    db.update("organizations", {"name": body.name.strip()}, where={"id": org_id})
    return org_view(db, _org(db, org_id), m["role"])


@router.get("/plans")
def list_plans() -> list[dict]:
    return plans_view()


def org_view(db: Database, org: dict, role: str) -> dict:
    plan = plan_of(org)
    return {
        "id": org["id"],
        "name": org["name"],
        "role": role,
        "plan": plan.id,
        "plan_name": plan.name,
        "subscription_status": org.get("subscription_status"),
        "current_period_end": org.get("current_period_end"),
        "limits": {
            "members": plan.members,
            "datasets": plan.datasets,
            "approved_agents": plan.approved_agents,
            "connectors": plan.connectors,
        },
        "usage": usage(db, org["id"]),
        "features": settings().features(),
    }


# --- members and invitations ---------------------------------------------------------------------


@router.get("/orgs/{org_id}/members")
def list_members(org_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    m = membership(db, org_id, user)
    members = db.select("memberships", where={"org_id": org_id}, order="created_at.asc")
    invites = []
    if RANK[m["role"]] >= RANK["admin"]:
        invites = [
            {k: i[k] for k in ("id", "email", "role", "created_at", "expires_at")}
            for i in db.select("invitations", where={"org_id": org_id, "accepted_at": None})
        ]
    return {
        "members": [{k: x[k] for k in ("user_id", "email", "role", "created_at")} for x in members],
        "invitations": invites,
    }


@router.post("/orgs/{org_id}/invitations", status_code=201)
def invite(org_id: str, body: Invite, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "admin")
    if body.role not in {"admin", "approver", "viewer"}:
        raise HTTPException(422, "invite as admin, approver or viewer")
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "that isn't an email address")
    if any(m["email"] == email for m in db.select("memberships", where={"org_id": org_id})):
        raise HTTPException(409, f"{email} is already in this workspace")
    org = _org(db, org_id)
    require_room(db, org, "members")
    token = secrets.token_urlsafe(32)
    row = db.insert(
        "invitations",
        {
            "org_id": org_id,
            "email": email,
            "role": body.role,
            "token_hash": _hash(token),
            "invited_by": user.id,
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
    )[0]
    link = f"/invite?token={token}"
    sent = notify(
        db, org_id, "invitation", f"You're invited to {org['name']} on ShadowCost",
        [f"{user.email} invited you to the {org['name']} workspace as {body.role}.",
         "The link works for 7 days."],
        link, to=[email],
    )  # fmt: skip
    return {
        "id": row["id"],
        "email": email,
        "role": body.role,
        "invite_url": f"{settings().site_url}{link}",
        "emailed": sent["delivered"],
    }


@router.delete("/orgs/{org_id}/invitations/{invitation_id}")
def revoke_invitation(org_id: str, invitation_id: str, user: User = CURRENT, db: Database = DB):
    membership(db, org_id, user, "admin")
    db.delete("invitations", where={"id": invitation_id, "org_id": org_id})
    return {"revoked": invitation_id}


@router.post("/invitations/accept")
def accept_invitation(body: Token, user: User = CURRENT, db: Database = DB) -> dict:
    found = one(db.select("invitations", where={"token_hash": _hash(body.token)}))
    if not found or found.get("accepted_at"):
        raise HTTPException(404, "this invitation doesn't exist or was already used")
    if datetime.fromisoformat(str(found["expires_at"])) < datetime.now(UTC):
        raise HTTPException(410, "this invitation has expired; ask for a new one")
    if found["email"] != user.email:
        raise HTTPException(
            403, f"this invitation is for {found['email']}; sign in with that email"
        )
    if not one(db.select("memberships", where={"org_id": found["org_id"], "user_id": user.id})):
        db.insert(
            "memberships",
            {
                "org_id": found["org_id"],
                "user_id": user.id,
                "email": user.email,
                "role": found["role"],
            },
        )
    db.update(
        "invitations", {"accepted_at": datetime.now(UTC).isoformat()}, where={"id": found["id"]}
    )
    return {"org_id": found["org_id"], "role": found["role"]}


@router.patch("/orgs/{org_id}/members/{member_id}")
def change_role(
    org_id: str, member_id: str, body: RoleChange, user: User = CURRENT, db: Database = DB
) -> dict:
    mine = membership(db, org_id, user, "admin")
    target = one(db.select("memberships", where={"org_id": org_id, "user_id": member_id}))
    if not target:
        raise HTTPException(404, "no such member")
    if body.role not in RANK:
        raise HTTPException(422, "unknown role")
    if "owner" in (target["role"], body.role) and mine["role"] != "owner":
        raise HTTPException(403, "only the owner can hand over or change ownership")
    if target["role"] == "owner" and body.role != "owner":
        owners = [
            m for m in db.select("memberships", where={"org_id": org_id}) if m["role"] == "owner"
        ]
        if len(owners) == 1:
            raise HTTPException(409, "a workspace needs an owner; make someone else owner first")
    db.update("memberships", {"role": body.role}, where={"org_id": org_id, "user_id": member_id})
    return {"user_id": member_id, "role": body.role}


@router.delete("/orgs/{org_id}/members/{member_id}")
def remove_member(org_id: str, member_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    leaving_self = member_id == user.id
    mine = membership(db, org_id, user, "viewer" if leaving_self else "admin")
    target = one(db.select("memberships", where={"org_id": org_id, "user_id": member_id}))
    if not target:
        raise HTTPException(404, "no such member")
    if target["role"] == "owner":
        raise HTTPException(409, "the owner can't be removed; hand over ownership first")
    if not leaving_self and RANK[target["role"]] >= RANK[mine["role"]]:
        raise HTTPException(403, "you can only remove members below your own role")
    db.delete("memberships", where={"org_id": org_id, "user_id": member_id})
    return {"removed": member_id}


# --- datasets ------------------------------------------------------------------------------------


@router.get("/orgs/{org_id}/datasets")
def list_datasets(org_id: str, user: User = CURRENT, db: Database = DB) -> list[dict]:
    membership(db, org_id, user)
    return [
        _dataset_view(d)
        for d in db.select("datasets", where={"org_id": org_id}, order="created_at.desc")
    ]


@router.post("/orgs/{org_id}/datasets", status_code=201)
async def upload_dataset(
    org_id: str,
    files: list[UploadFile] = File(...),  # noqa: B008
    name: str = "Uploaded files",
    user: User = CURRENT,
    db: Database = DB,
) -> dict:
    membership(db, org_id, user, "admin")
    require_room(db, _org(db, org_id), "datasets")
    collected: dict[str, bytes] = {}
    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        for upload in files:
            content = await upload.read(MAX_UPLOAD_BYTES + 1)
            total += len(content)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"uploads are limited to {MAX_UPLOAD_BYTES // 2**20} MB")
            filename = Path(upload.filename or "file").name
            if filename.lower().endswith(".zip"):
                try:
                    extract_zip(content, Path(tmp) / filename[:-4])
                except (zipfile.BadZipFile, ValueError) as err:
                    raise HTTPException(400, str(err)) from err
            else:
                (Path(tmp) / "files").mkdir(exist_ok=True)
                (Path(tmp) / "files" / filename).write_bytes(content)
        collected = data.files_from_folder(Path(tmp))
    if not collected:
        raise HTTPException(400, "no CSV, Excel or JSON files in the upload")
    dataset = data.create_dataset(
        db, org_id, user.id, name[:80] or "Uploaded files", "upload", collected
    )
    return _dataset_view(dataset)


@router.post("/orgs/{org_id}/datasets/sample", status_code=201)
def add_sample(org_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "admin")
    require_room(db, _org(db, org_id), "datasets")
    files = data.files_from_folder(data.sample_folder())
    dataset = data.create_dataset(
        db, org_id, user.id, "Fernhill Supplies (sample)", "upload", files, {"sample": True}
    )
    return _dataset_view(dataset)


@router.get("/orgs/{org_id}/datasets/{dataset_id}")
def dataset_summary(org_id: str, dataset_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user)
    dataset = data.get_dataset(db, org_id, dataset_id)
    _require_ready(dataset)
    return {**(dataset["summary"] or {}), "dataset_id": dataset_id, "name": dataset["name"]}


@router.get("/orgs/{org_id}/datasets/{dataset_id}/events")
def dataset_events(
    org_id: str, dataset_id: str, limit: int = 50, source: str | None = None,
    user: User = CURRENT, db: Database = DB,
) -> list[dict]:  # fmt: skip
    membership(db, org_id, user)
    return events_view(_events(db, org_id, dataset_id), limit, source)


@router.get("/orgs/{org_id}/datasets/{dataset_id}/workflows")
def dataset_workflows(
    org_id: str, dataset_id: str, user: User = CURRENT, db: Database = DB
) -> dict:
    membership(db, org_id, user)
    folder, days = _folder_and_days(db, org_id, dataset_id)
    return workflows_view(*compute.discovery(str(folder), days))


@router.delete("/orgs/{org_id}/datasets/{dataset_id}")
def delete_dataset(org_id: str, dataset_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "admin")
    data.delete_dataset(db, data.get_dataset(db, org_id, dataset_id))
    return {"deleted": dataset_id}


@router.post("/orgs/{org_id}/datasets/{dataset_id}/report")
def dataset_report(org_id: str, dataset_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user)
    folder, days = _folder_and_days(db, org_id, dataset_id)
    specs = [
        (AgentSpec.from_dict(a["spec"]), a.get("evaluation") or {})
        for a in db.select("agents", where={"org_id": org_id, "dataset_id": dataset_id})
    ]
    report = build_report(folder, specs, days)
    return {"markdown": report.markdown(), "html": report.html()}


# --- agents --------------------------------------------------------------------------------------


@router.get("/orgs/{org_id}/agents")
def list_agents(
    org_id: str, dataset_id: str | None = None, user: User = CURRENT, db: Database = DB
) -> list[dict]:
    membership(db, org_id, user)
    where = {"org_id": org_id, **({"dataset_id": dataset_id} if dataset_id else {})}
    agents = db.select("agents", where=where, order="workflow_id.asc")
    approvals = db.select("approvals", where={"org_id": org_id})
    return [_agent_view(a, approvals) for a in agents]


@router.post("/orgs/{org_id}/datasets/{dataset_id}/agents/draft", status_code=201)
def draft_agents(org_id: str, dataset_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "admin")
    dataset = data.get_dataset(db, org_id, dataset_id)
    folder, days = _folder_and_days(db, org_id, dataset_id)
    events = compute.ingest(str(folder)).events
    discovery, split = compute.discovery(str(folder), days)
    last = events["timestamp"].max().date()
    minutes = {r.workflow.workflow_id: r.minutes_per_instance for r in recommend(discovery)}

    drafted: list[tuple[dict, dict]] = []
    problems: list[str] = []
    if (dataset.get("summary") or {}).get("sample"):
        # The bundled specs were drafted from this exact sample; reuse them without an LLM call.
        drafted = [(s.to_dict(), ev) for s, ev in load_specs(Path("specs"))]
    else:
        s = settings()
        if not s.llm_enabled:
            raise HTTPException(
                503, "drafting agents needs an LLM key on the server (GROQ_API_KEY)"
            )
        client = ChatClient(api_key=s.groq_api_key, cache_dir=data.cache_root() / "llm")
        for workflow in discovery.workflows:
            generation = generate_spec(discovery, workflow, client)
            if generation.spec is None:
                problems.append(f"{workflow.workflow_id}: {'; '.join(generation.problems[:2])}")
                continue
            held = backtest(generation.spec, events, split, last)
            drafted.append(
                (
                    generation.spec.to_dict(),
                    {
                        "minutes_per_case": minutes.get(workflow.workflow_id, 0),
                        "evidence_period": generation.evidence_backtest.metrics(),
                        "held_out": {
                            "from": split.isoformat(),
                            "to": last.isoformat(),
                            **held.metrics(),
                        },
                    },
                )
            )

    existing = {a["spec_hash"] for a in db.select("agents", where={"org_id": org_id})}
    created = []
    for spec_dict, evaluation in drafted:
        h = spec_hash(AgentSpec.from_dict(spec_dict))
        if h in existing:
            continue
        created.append(
            db.insert(
                "agents",
                {
                    "org_id": org_id,
                    "dataset_id": dataset_id,
                    "workflow_id": spec_dict["workflow_id"],
                    "name": spec_dict["name"],
                    "spec": spec_dict,
                    "spec_hash": h,
                    "evaluation": json.loads(json.dumps(evaluation, default=str)),
                },
            )[0]
        )
    return {"created": len(created), "skipped": len(drafted) - len(created), "problems": problems}


@router.post("/orgs/{org_id}/agents/{agent_id}/approve")
def approve_agent(org_id: str, agent_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "approver")
    agent = _agent(db, org_id, agent_id)
    if _approval(db, agent):
        raise HTTPException(409, "this agent is already approved")
    require_room(db, _org(db, org_id), "approved_agents")
    db.insert(
        "approvals",
        {
            "org_id": org_id,
            "agent_id": agent_id,
            "spec_hash": agent["spec_hash"],
            "approved_by": user.id,
            "approved_email": user.email,
        },
    )
    return _agent_view(agent, db.select("approvals", where={"org_id": org_id}))


@router.post("/orgs/{org_id}/agents/{agent_id}/backtest")
def backtest_agent(
    org_id: str, agent_id: str, body: DatasetRef, user: User = CURRENT, db: Database = DB
) -> dict:
    membership(db, org_id, user)
    spec = _spec(_agent(db, org_id, agent_id))
    events = _events(db, org_id, body.dataset_id)
    start, end = _held_out(spec, events)
    return backtest_view(start, end, backtest(spec, events, start, end))


@router.post("/orgs/{org_id}/agents/{agent_id}/shadow")
def shadow_agent(
    org_id: str, agent_id: str, body: DatasetRef, user: User = CURRENT, db: Database = DB
) -> dict:
    membership(db, org_id, user)
    agent = _agent(db, org_id, agent_id)
    if not _approval(db, agent):
        raise HTTPException(403, "this agent has not been approved (or changed since)")
    spec = _spec(agent)
    events = _events(db, org_id, body.dataset_id)
    start, end = _held_out(spec, events)
    minutes = (agent.get("evaluation") or {}).get("minutes_per_case") or 0
    run = run_shadow(spec, events, start, end, minutes)
    previous = one(
        db.select("shadow_runs", where={"agent_id": agent_id}, order="created_at.desc", limit=1)
    )
    view = shadow_view(run, start, end, minutes, None)
    row = db.insert(
        "shadow_runs",
        {
            "org_id": org_id,
            "agent_id": agent_id,
            "dataset_id": body.dataset_id,
            "final_stage": view["final_stage"],
            "minutes_saved": run.minutes_saved(),
            "result": json.loads(
                json.dumps({k: view[k] for k in ("cases", "changes", "by_stage")}, default=str)
            ),
        },
    )[0]
    before = previous["final_stage"] if previous else "shadow"
    if STAGES_ORDER.index(view["final_stage"]) > STAGES_ORDER.index(before):
        notify(
            db, org_id, "promotion", f"{agent['name']} reached {view['final_stage']}",
            [f"In shadow mode, {agent['name']} agreed with the person often enough to move up "
             f"to the {view['final_stage']} stage ({view['cases']} cases replayed)."],
            "/app/shadow", min_role="approver",
        )  # fmt: skip
    return {**view, "run_id": row["id"]}


@router.post("/orgs/{org_id}/agents/{agent_id}/execute")
def execute_agent(
    org_id: str, agent_id: str, body: RunDay, user: User = CURRENT, db: Database = DB
) -> dict:
    membership(db, org_id, user, "approver")
    agent = _agent(db, org_id, agent_id)
    if not _approval(db, agent):
        raise HTTPException(403, "this agent has not been approved (or changed since)")
    try:
        stage = Stage[body.stage.upper()]
    except KeyError as err:
        raise HTTPException(422, "stage must be shadow, draft, approval or autonomous") from err
    events = _events(db, org_id, body.dataset_id)
    queue = _OrgQueue(db, org_id, agent_id)
    result = execute_day(
        _spec(agent), stage, body.day, events, data.cache_root() / "outbox" / org_id, queue,
        mailbox_owner(events),
    )  # fmt: skip
    if queue.queued:
        notify(
            db, org_id, "approval_needed",
            f"{len(queue.queued)} actions from {agent['name']} wait for approval",
            [f"{agent['name']} proposed {len(queue.queued)} actions for {body.day.isoformat()}. "
             "Nothing happens until someone approves them."],
            "/app/execute",
        )  # fmt: skip
    return execute_view(body.day, stage.name.lower(), result, queue.queued)


class _OrgQueue:
    """Stands in for the CLI's SQLite store: queued actions go to the workspace's table."""

    def __init__(self, db: Database, org_id: str, agent_id: str):
        self.db, self.org_id, self.agent_id = db, org_id, agent_id
        self.queued: list[int] = []

    def queue_action(self, spec: AgentSpec, proposal: dict) -> int:
        row = self.db.insert(
            "actions",
            {
                "org_id": self.org_id,
                "agent_id": self.agent_id,
                "case_id": proposal["case_id"],
                "day": proposal["day"],
                "proposal": proposal,
            },
        )[0]
        self.queued.append(row["id"])
        return row["id"]


@router.get("/orgs/{org_id}/actions")
def list_actions(
    org_id: str, status: str | None = "pending", user: User = CURRENT, db: Database = DB
) -> list[dict]:
    membership(db, org_id, user)
    where = {"org_id": org_id, **({"status": status} if status else {})}
    return [
        {
            "action_id": a["id"],
            "spec_id": a["agent_id"],
            "case_id": a["case_id"],
            "day": a["day"],
            "proposal": a["proposal"],
            "status": a["status"],
            "decided_by": a.get("decided_email"),
        }
        for a in db.select("actions", where=where, order="id.asc", limit=200)
    ]


@router.post("/orgs/{org_id}/actions/{action_id}/decision")
def decide(
    org_id: str, action_id: int, body: Decision, user: User = CURRENT, db: Database = DB
) -> dict:
    membership(db, org_id, user, "approver")
    action = one(db.select("actions", where={"id": action_id, "org_id": org_id}))
    if not action:
        raise HTTPException(404, "no such action")
    if action["status"] != "pending":
        raise HTTPException(409, f"action {action_id} was already {action['status']}")
    status = "approved" if body.approve else "rejected"
    db.update(
        "actions",
        {
            "status": status,
            "decided_by": user.id,
            "decided_email": user.email,
            "decided_at": datetime.now(UTC).isoformat(),
        },
        where={"id": action_id, "status": "pending"},
    )
    return {"action_id": action_id, "status": status, "decided_by": user.email}


@router.get("/orgs/{org_id}/notifications")
def list_notifications(org_id: str, user: User = CURRENT, db: Database = DB) -> list[dict]:
    membership(db, org_id, user)
    return db.select("notifications", where={"org_id": org_id}, order="created_at.desc", limit=50)


# --- billing -------------------------------------------------------------------------------------


@router.post("/orgs/{org_id}/billing/checkout")
def checkout(org_id: str, body: Checkout, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "owner")
    return {"url": billing.checkout_url(_org(db, org_id), body.plan, user.email)}


@router.post("/orgs/{org_id}/billing/portal")
def portal(org_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "owner")
    return {"url": billing.portal_url(_org(db, org_id))}


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request, stripe_signature: str | None = Header(default=None), db: Database = DB
) -> dict:
    event = billing.parse_event(await request.body(), stripe_signature)
    return {"result": billing.handle_event(db, event)}


# --- Google connector ----------------------------------------------------------------------------


@router.get("/orgs/{org_id}/connectors")
def list_connectors(org_id: str, user: User = CURRENT, db: Database = DB) -> list[dict]:
    membership(db, org_id, user)
    return [_connection_view(c) for c in db.select("connections", where={"org_id": org_id})]


@router.post("/orgs/{org_id}/connectors/google/start")
def google_start(org_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "admin")
    if not settings().google_enabled:
        raise HTTPException(503, "the Google connector is not configured on this server")
    require_room(db, _org(db, org_id), "connectors")
    return {"url": google.auth_url(google.sign_state({"org": org_id, "user": user.id}))}


@router.get("/connectors/google/callback", include_in_schema=False)
def google_callback(
    code: str = "", state: str = "", error: str = "", db: Database = DB
) -> RedirectResponse:
    site = settings().site_url
    if error or not code:
        return RedirectResponse(f"{site}/app/data?google=cancelled")
    payload = google.verify_state(state)
    org_id, user_id = payload["org"], payload["user"]
    member = one(db.select("memberships", where={"org_id": org_id, "user_id": user_id}))
    if not member or RANK[member["role"]] < RANK["admin"]:
        raise HTTPException(403, "you are no longer an admin of that workspace")
    tokens = google.exchange_code(code)
    if not tokens.get("refresh_token"):
        return RedirectResponse(f"{site}/app/data?google=no-refresh-token")
    values = {
        "account_email": google.id_token_email(tokens.get("id_token")),
        "scopes": tokens.get("scope", "").split(),
        "refresh_token_encrypted": google.encrypt(tokens["refresh_token"]),
        "last_error": None,
    }
    if one(db.select("connections", where={"org_id": org_id, "provider": "google"})):
        db.update("connections", values, where={"org_id": org_id, "provider": "google"})
    else:
        db.insert(
            "connections", {"org_id": org_id, "provider": "google", "created_by": user_id, **values}
        )
    return RedirectResponse(f"{site}/app/data?google=connected")


@router.patch("/orgs/{org_id}/connectors/google")
def google_settings(
    org_id: str, body: GoogleSettings, user: User = CURRENT, db: Database = DB
) -> dict:
    membership(db, org_id, user, "admin")
    connection = _connection(db, org_id)
    new = {
        **(connection.get("settings") or {}),
        "spreadsheet_id": google.spreadsheet_id_from(body.spreadsheet) if body.spreadsheet else "",
        "sheet_range": body.sheet_range or "A1:Z5000",
        "gmail_query": body.gmail_query,
    }
    db.update("connections", {"settings": new}, where={"id": connection["id"]})
    return _connection_view({**connection, "settings": new})


@router.post("/orgs/{org_id}/connectors/google/sync")
def google_sync(org_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "admin")
    return sync_google(db, _connection(db, org_id), user.id)


@router.delete("/orgs/{org_id}/connectors/google")
def google_disconnect(org_id: str, user: User = CURRENT, db: Database = DB) -> dict:
    membership(db, org_id, user, "admin")
    db.delete("connections", where={"org_id": org_id, "provider": "google"})
    return {"disconnected": "google"}


@router.post("/cron/sync", include_in_schema=False)
def cron_sync(x_cron_secret: str | None = Header(default=None), db: Database = DB) -> dict:
    secret = settings().cron_secret
    if not secret or not x_cron_secret or not secrets.compare_digest(secret, x_cron_secret):
        raise HTTPException(401, "bad cron secret")
    results = {}
    for connection in db.select("connections", where={"provider": "google"}):
        try:
            results[connection["org_id"]] = sync_google(db, connection, None)["dataset_id"]
        except HTTPException as err:
            db.update(
                "connections", {"last_error": str(err.detail)}, where={"id": connection["id"]}
            )
            results[connection["org_id"]] = f"error: {err.detail}"
    return {"synced": results}


def sync_google(
    db: Database, connection: dict, user_id: str | None, today: date | None = None
) -> dict:
    """Snapshot the sheet as today's dated copy and merge new Gmail messages into the log."""
    today = today or date.today()
    conf = connection.get("settings") or {}
    if not conf.get("spreadsheet_id") and not conf.get("gmail_query"):
        raise HTTPException(409, "choose a spreadsheet or a Gmail search first")
    token = google.access_token(google.decrypt(connection["refresh_token_encrypted"]))
    org_id = connection["org_id"]
    files: dict[str, bytes] = {}
    title = "Google"
    if conf.get("spreadsheet_id"):
        title, values = google.fetch_sheet(
            token, conf["spreadsheet_id"], conf.get("sheet_range", "A1:Z5000")
        )
        files[f"ledger/{google.slug(title)}_{today.isoformat()}.csv"] = google.sheet_to_csv(
            values
        ).encode()

    dataset = one(db.select("datasets", where={"org_id": org_id, "source": "google"}))
    if conf.get("gmail_query"):
        records = google.gmail_to_records(google.fetch_gmail(token, conf["gmail_query"]))
        known = {}
        if dataset:
            try:
                previous = db.download(f"{dataset['storage_prefix']}/email/messages.jsonl")
                known = {
                    r["message_id"]: r for r in map(json.loads, previous.decode().splitlines()) if r
                }
            except DBError:
                known = {}
        known.update({r["message_id"]: r for r in records})
        ordered = sorted(known.values(), key=lambda r: r["timestamp"])
        files["email/messages.jsonl"] = "\n".join(json.dumps(r) for r in ordered).encode() + b"\n"

    if dataset:
        data.store_files(db, org_id, dataset["id"], files)
        dataset = data.refresh_summary(db, dataset, new_version=True)
    else:
        require_room(db, _org(db, org_id), "datasets")
        dataset = data.create_dataset(db, org_id, user_id, f"Google: {title}", "google", files)
    db.update(
        "connections",
        {"last_synced_at": datetime.now(UTC).isoformat(), "last_error": None},
        where={"id": connection["id"]},
    )
    return {"dataset_id": dataset["id"], "status": dataset["status"], "files": sorted(files)}


# --- helpers -------------------------------------------------------------------------------------


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _org(db: Database, org_id: str) -> dict:
    org = one(db.select("organizations", where={"id": org_id}))
    if not org:
        raise HTTPException(404, "no such workspace")
    return org


def _require_ready(dataset: dict) -> None:
    if dataset["status"] == "error":
        raise HTTPException(422, dataset.get("error") or "this dataset couldn't be read")
    if dataset["status"] != "ready":
        raise HTTPException(409, "this dataset is still being processed")


def _folder_and_days(db: Database, org_id: str, dataset_id: str) -> tuple[Path, int]:
    dataset = data.get_dataset(db, org_id, dataset_id)
    _require_ready(dataset)
    folder = data.materialize(db, dataset)
    events = compute.ingest(str(folder)).events
    span = (events["timestamp"].max() - events["timestamp"].min()).days + 1
    return folder, max(MIN_TRAIN_DAYS, min(MAX_TRAIN_DAYS, span * 2 // 3))


def _events(db: Database, org_id: str, dataset_id: str):
    folder, _ = _folder_and_days(db, org_id, dataset_id)
    return compute.ingest(str(folder)).events


def _agent(db: Database, org_id: str, agent_id: str) -> dict:
    agent = one(db.select("agents", where={"id": agent_id, "org_id": org_id}))
    if not agent:
        raise HTTPException(404, "no such agent")
    return agent


def _spec(agent: dict) -> AgentSpec:
    try:
        return AgentSpec.from_dict(agent["spec"])
    except SpecError as err:
        raise HTTPException(422, {"problems": err.problems}) from err


def _approval(db: Database, agent: dict) -> dict | None:
    return one(
        db.select("approvals", where={"agent_id": agent["id"], "spec_hash": agent["spec_hash"]})
    )


def _held_out(spec: AgentSpec, events) -> tuple[date, date]:
    end = events["timestamp"].max().date()
    period = spec.source.get("evidence_period")
    start = (
        date.fromisoformat(period[1]) + timedelta(days=1) if period else end - timedelta(days=30)
    )
    return min(start, end), end


def _agent_view(agent: dict, approvals: list[dict]) -> dict:
    approval = next(
        (
            a
            for a in approvals
            if a["agent_id"] == agent["id"] and a["spec_hash"] == agent["spec_hash"]
        ),
        None,
    )
    return {
        "spec_id": agent["id"],
        "agent_id": agent["id"],
        "dataset_id": agent.get("dataset_id"),
        "spec": {**agent["spec"], "evaluation": agent.get("evaluation") or {}},
        "approved_by": approval["approved_email"] if approval else None,
        "approved_at": approval["approved_at"] if approval else None,
    }


def _dataset_view(dataset: dict) -> dict:
    summary = dataset.get("summary") or {}
    return {
        "id": dataset["id"],
        "name": dataset["name"],
        "source": dataset["source"],
        "status": dataset["status"],
        "error": dataset.get("error"),
        "events": summary.get("events"),
        "first_day": summary.get("first_day"),
        "last_day": summary.get("last_day"),
        "sample": bool(summary.get("sample")),
        "created_at": dataset.get("created_at"),
    }


def _connection(db: Database, org_id: str) -> dict:
    connection = one(db.select("connections", where={"org_id": org_id, "provider": "google"}))
    if not connection:
        raise HTTPException(404, "Google isn't connected")
    return connection


def _connection_view(connection: dict) -> dict:
    return {
        "provider": connection["provider"],
        "account_email": connection.get("account_email"),
        "settings": connection.get("settings") or {},
        "last_synced_at": connection.get("last_synced_at"),
        "last_error": connection.get("last_error"),
    }
