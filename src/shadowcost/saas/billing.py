"""Stripe subscriptions: Checkout to subscribe, the Customer Portal to manage, webhooks to sync.

The plan a workspace is on is only ever changed by a signed Stripe webhook, never by the browser,
so a user can't grant themselves a plan by calling the API.
"""

from __future__ import annotations

from datetime import UTC, datetime

import stripe
from fastapi import HTTPException

from shadowcost.saas.config import settings
from shadowcost.saas.db import Database, one
from shadowcost.saas.plans import PLANS

ACTIVE = {"active", "trialing", "past_due"}


def _client() -> None:
    s = settings()
    if not s.billing_enabled:
        raise HTTPException(503, "billing is not configured on this server")
    stripe.api_key = s.stripe_secret_key


def lookup_key(plan: str) -> str:
    return f"shadowcost_{plan}_monthly"


def price_id(plan: str) -> str:
    prices = stripe.Price.list(lookup_keys=[lookup_key(plan)], active=True, limit=1)
    if not prices.data:
        raise HTTPException(503, f"no Stripe price for {plan}; run scripts/stripe_setup.py")
    return prices.data[0].id


def checkout_url(org: dict, plan: str, email: str) -> str:
    if plan not in PLANS or plan == "free":
        raise HTTPException(422, "choose starter or growth")
    _client()
    site = settings().site_url
    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id(plan), "quantity": 1}],
        "success_url": f"{site}/app/settings?tab=billing&checkout=success",
        "cancel_url": f"{site}/app/settings?tab=billing&checkout=cancelled",
        "client_reference_id": org["id"],
        "metadata": {"org_id": org["id"], "plan": plan},
        "subscription_data": {"metadata": {"org_id": org["id"], "plan": plan}},
        "allow_promotion_codes": True,
    }
    if org.get("stripe_customer_id"):
        params["customer"] = org["stripe_customer_id"]
    else:
        params["customer_email"] = email
    return stripe.checkout.Session.create(**params).url


def portal_url(org: dict) -> str:
    _client()
    if not org.get("stripe_customer_id"):
        raise HTTPException(409, "this workspace has no subscription yet")
    session = stripe.billing_portal.Session.create(
        customer=org["stripe_customer_id"],
        return_url=f"{settings().site_url}/app/settings?tab=billing",
    )
    return session.url


def parse_event(payload: bytes, signature: str | None) -> dict:
    s = settings()
    if not s.stripe_webhook_secret:
        raise HTTPException(503, "billing is not configured on this server")
    try:
        event = stripe.Webhook.construct_event(payload, signature or "", s.stripe_webhook_secret)
        return event.to_dict()  # plain dicts from here on (StripeObject isn't one since v16)
    except (ValueError, stripe.SignatureVerificationError) as err:
        raise HTTPException(400, "invalid Stripe signature") from err


def handle_event(db: Database, event: dict) -> str:
    """Apply one Stripe event to the workspace it belongs to. Returns what was done."""
    kind = event["type"]
    obj = event["data"]["object"]
    if kind == "checkout.session.completed":
        org_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("org_id")
        if not org_id:
            return "ignored: no workspace"
        db.update(
            "organizations",
            {
                "stripe_customer_id": obj.get("customer"),
                "stripe_subscription_id": obj.get("subscription"),
                "plan": (obj.get("metadata") or {}).get("plan", "starter"),
                "subscription_status": "active",
            },
            where={"id": org_id},
        )
        return f"subscribed {org_id}"

    if kind in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        org = one(db.select("organizations", where={"stripe_subscription_id": obj["id"]})) or one(
            db.select("organizations", where={"id": (obj.get("metadata") or {}).get("org_id", "")})
        )
        if not org:
            return "ignored: unknown subscription"
        status = obj.get("status", "canceled")
        plan = "free"
        if kind != "customer.subscription.deleted" and status in ACTIVE:
            plan = _plan_from_items(obj) or org.get("plan") or "starter"
        end = obj.get("current_period_end") or _item_period_end(obj)
        db.update(
            "organizations",
            {
                "plan": plan,
                "subscription_status": status
                if kind != "customer.subscription.deleted"
                else "canceled",
                "stripe_subscription_id": obj["id"],
                "stripe_customer_id": obj.get("customer") or org.get("stripe_customer_id"),
                "current_period_end": (
                    datetime.fromtimestamp(end, UTC).isoformat() if end else None
                ),
            },
            where={"id": org["id"]},
        )
        return f"{org['id']} is on {plan} ({status})"
    return f"ignored: {kind}"


def _plan_from_items(subscription: dict) -> str | None:
    for item in (subscription.get("items") or {}).get("data", []):
        key = (item.get("price") or {}).get("lookup_key") or ""
        for plan in PLANS:
            if key == lookup_key(plan):
                return plan
    return (subscription.get("metadata") or {}).get("plan")


def _item_period_end(subscription: dict) -> int | None:
    for item in (subscription.get("items") or {}).get("data", []):
        if item.get("current_period_end"):
            return item["current_period_end"]
    return None
