"""Export the numbers the landing page shows, computed from the real pipeline.

    python scripts/export_landing_data.py

The landing page is static (the API sleeps on Render's free tier), so it reads
a snapshot instead of calling the API. Every figure in it comes from running
ShadowCost on the bundled sample and on a simulated year; nothing is typed in.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from shadowcost.agent.shadow_mode import TIME_SAVED_SHARE, run_shadow
from shadowcost.discover import discover
from shadowcost.evaluation import evaluate
from shadowcost.ingest import ingest_folder
from shadowcost.recommend import recommend
from shadowcost.report import _ground_truth_minutes, load_specs
from shadowcost.synth import Config, simulate, write_dataset

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "src" / "data" / "landing.json"
TRAIN_DAYS = 80


def main() -> None:
    sample = ROOT / "data" / "sample"
    year = ROOT / "workspace" / "year"
    if not (year / "manifest.json").exists():
        write_dataset(simulate(Config(seed=7, days=365)), year, overwrite=True)

    ingested = ingest_folder(sample)
    events = ingested.events
    split = events["timestamp"].min().date() + timedelta(days=TRAIN_DAYS)
    # Discovery as reported in docs/discovery.md: the whole held-out sample.
    discovery = discover(events)
    recommendations = recommend(discovery)
    graded = evaluate(discovery, recommendations, sample / "ground_truth")

    final = max(p for p in (sample / "ledger").glob("invoices_*.csv"))
    import pandas as pd

    ledger = pd.read_csv(final, dtype=str, keep_default_na=False)
    bank = pd.read_csv(sample / "bank" / "payments.csv", dtype=str, keep_default_na=False)
    examples = [
        bank[bank["reference"].str.fullmatch(r"INV-\d+")].iloc[0],
        bank[(bank["reference"] != "") & ~bank["reference"].str.contains("-")].iloc[0],
        bank[bank["reference"] == ""].iloc[0],
    ]

    year_events = ingest_folder(year).events
    year_end = year_events["timestamp"].max().date()
    truth = _ground_truth_minutes(year / "ground_truth")
    agents = []
    monthly: dict[str, float] = defaultdict(float)
    for spec, evaluation in load_specs(ROOT / "specs"):
        start = date.fromisoformat(spec.source["evidence_period"][1]) + timedelta(days=1)
        run = run_shadow(spec, year_events, start, year_end, evaluation["minutes_per_case"])
        stages = [("shadow", start)] + [(c.decision.next.name.lower(), c.day) for c in run.changes]
        spans = []
        for i, (stage, began) in enumerate(stages):
            ended = stages[i + 1][1] if i + 1 < len(stages) else year_end
            spans.append({"stage": stage, "from": began, "to": ended, "days": (ended - began).days})
        for outcome, stage in run.outcomes:
            if outcome.agrees and outcome.human_day:
                minutes = truth.get((outcome.case_id, outcome.human_day), 0.0)
                monthly[outcome.human_day.strftime("%Y-%m")] += TIME_SAVED_SHARE[stage] * minutes
        agents.append(
            {
                "id": spec.workflow_id,
                "name": spec.name,
                "held_out_agreement": evaluation["held_out"]["agreement"],
                "cases": len(run.outcomes),
                "agreement": round(sum(o.agrees for o, _ in run.outcomes) / len(run.outcomes), 3),
                "final_stage": run.final_stage.name.lower(),
                "spans": spans,
            }
        )

    data = {
        "company": "Fernhill Supplies",
        "sample": {
            "days": (events["timestamp"].max() - events["timestamp"].min()).days + 1,
            "snapshots": sum(f.kind == "snapshot" for f in ingested.files),
            "payments": int((events["source"] == "bank").sum()),
            "emails": int((events["source"] == "email").sum()),
            "customers": len(ingested.tables.get("customers", [])),
            "invoices": len(ledger),
            "payments_linked": round(
                float((events.loc[events["source"] == "bank", "case_id"] != "").mean()), 3
            ),
        },
        "discovery": {
            "workflows": [
                {
                    "id": r.workflow.workflow_id,
                    "name": r.workflow.name,
                    "trigger": r.workflow.trigger.description,
                    "per_month": r.instances_per_month,
                    "hours_per_month": r.hours_per_month,
                }
                for r in recommendations
            ],
            "precision": graded.precision,
            "recall": graded.recall,
            "chase_rule": next(
                (w.condition.description for w in discovery.workflows if w.condition), ""
            ),
        },
        "invoices": [
            {"id": r.invoice_id, "customer": r.customer, "amount": float(r.amount)}
            for r in ledger.itertuples()
        ],
        "bank_examples": [
            {
                "date": r["date"],
                "payer": r["payer"],
                "amount": r["amount"],
                "reference": r["reference"],
            }
            for r in examples
        ],
        "agents": agents,
        "monthly_hours_saved": [
            {"month": m, "hours": round(v / 60, 2)} for m, v in sorted(monthly.items())
        ],
        "hours_saved": {
            "measured": round(sum(monthly.values()) / 60, 1),
            "period": [str(split), str(year_end)],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
