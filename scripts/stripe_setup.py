"""Create (or find) ShadowCost's Stripe products and monthly prices. Safe to run repeatedly.

    STRIPE_SECRET_KEY=sk_test_... python scripts/stripe_setup.py

Prices are found by lookup key (`shadowcost_<plan>_monthly`), so the API never needs a price id.
Use a test-mode key (sk_test_...) until you are ready to charge real cards.
"""

from __future__ import annotations

import os
import sys

import stripe

from shadowcost.llm import load_dotenv
from shadowcost.saas.billing import lookup_key
from shadowcost.saas.plans import PLANS


def main() -> int:
    load_dotenv()
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe.api_key:
        print("Set STRIPE_SECRET_KEY first (a test key starts with sk_test_).", file=sys.stderr)
        return 2
    for plan in PLANS.values():
        if not plan.monthly_usd:
            continue
        key = lookup_key(plan.id)
        existing = stripe.Price.list(lookup_keys=[key], limit=1).data
        if existing:
            print(f"{plan.name}: price {existing[0].id} already exists")
            continue
        product = stripe.Product.create(name=f"ShadowCost {plan.name}", description=plan.blurb)
        price = stripe.Price.create(
            product=product.id,
            unit_amount=plan.monthly_usd * 100,
            currency="usd",
            recurring={"interval": "month"},
            lookup_key=key,
        )
        print(f"{plan.name}: created {price.id} (${plan.monthly_usd}/month)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
