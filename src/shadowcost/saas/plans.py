"""Plans and what each allows. Stripe holds the prices; this module holds the limits.

Prices are looked up in Stripe by `lookup_key` (`shadowcost_<plan>_monthly`), created by
`scripts/stripe_setup.py`, so the code never hard-codes a Stripe id.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from fastapi import HTTPException

from shadowcost.saas.db import Database


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    monthly_usd: int
    members: int
    datasets: int
    approved_agents: int | None  # None: unlimited
    connectors: bool
    blurb: str


PLANS = {
    "free": Plan("free", "Free", 0, 1, 2, 1, False, "Find your repeated work and trial one agent."),
    "starter": Plan(
        "starter",
        "Starter",
        49,
        3,
        5,
        5,
        True,
        "A small office: Google Sheets and Gmail connected, five agents earning trust.",
    ),
    "growth": Plan(
        "growth",
        "Growth",
        149,
        15,
        25,
        None,
        True,
        "A finance team: every workflow, every approver, unlimited agents.",
    ),
}


def plan_of(org: dict) -> Plan:
    return PLANS.get(org.get("plan") or "free", PLANS["free"])


def usage(db: Database, org_id: str) -> dict[str, int]:
    members = len(db.select("memberships", where={"org_id": org_id}))
    pending = [i for i in db.select("invitations", where={"org_id": org_id, "accepted_at": None})]
    approved = {a["agent_id"] for a in db.select("approvals", where={"org_id": org_id})}
    return {
        "members": members + len(pending),
        "datasets": len(db.select("datasets", where={"org_id": org_id})),
        "approved_agents": len(approved),
    }


def require_room(db: Database, org: dict, resource: str) -> None:
    """Raise 402 when the workspace's plan has no room for one more of `resource`."""
    plan = plan_of(org)
    if resource == "connectors":
        if not plan.connectors:
            raise HTTPException(
                402, f"Connectors need the Starter plan or above (you're on {plan.name})."
            )
        return
    limit = getattr(plan, resource)
    if limit is not None and usage(db, org["id"])[resource] >= limit:
        label = resource.replace("_", " ")
        if limit == 1:
            label = {"members": "member", "datasets": "dataset"}.get(resource, label[:-1])
        raise HTTPException(
            402, f"The {plan.name} plan allows {limit} {label}. Upgrade to add more."
        )


def plans_view() -> list[dict]:
    return [asdict(p) for p in PLANS.values()]
