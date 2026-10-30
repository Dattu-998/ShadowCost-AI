"""Discover and rank repeated work: ``python -m shadowcost.discover data/sample``."""

from __future__ import annotations

import argparse
from pathlib import Path

from shadowcost.discover import Discovery, discover
from shadowcost.ingest import ingest_folder
from shadowcost.recommend import Recommendation, recommend


def report(discovery: Discovery, recommendations: list[Recommendation]) -> str:
    lines = [
        f"Found {len(discovery.workflows)} repeated workflows in {discovery.period_days} days "
        f"({len(discovery.episodes)} episodes of work, "
        f"{len(discovery.templates)} email templates).",
        "Ranked by addressable time: hours per month x automation score.",
    ]
    for rank, r in enumerate(recommendations, start=1):
        w = r.workflow
        observed = (
            f"; observed upper bound {r.observed_minutes:g} min ({r.observed_pairs} email pairs)"
            if r.observed_minutes
            else ""
        )
        lines += [
            "",
            f"#{rank}  {w.workflow_id}  {w.name}",
            f"    when:      {w.trigger.description} ({w.regularity:.0%} of {w.size} instances)",
        ]
        if w.condition:
            lines.append(
                f"    condition: {w.condition.description}; covers {w.condition.support:.0%} "
                f"of instances, precision {w.condition.precision:.0%}"
            )
        lines += [
            f"    volume:    {w.instances_per_week:g}/week, {r.instances_per_month:g}/month",
            f"    time:      ~{r.minutes_per_instance:g} min each (estimated){observed}",
            f"    cost:      {r.hours_per_month:.1f} h/month; automation score "
            f"{r.automation_score:.2f} (regularity {w.regularity:.2f} x consistency "
            f"{w.consistency:.2f}) -> {r.addressable_hours_per_month:.1f} h/month addressable",
            f"    assumes:   {'; '.join(r.assumptions)}",
        ]
        lines += [f"    caveat:    {c}" for c in r.caveats]
    if discovery.irregular:
        lines += ["", "Repeated, but with no consistent trigger (poor automation targets):"]
        lines += [f"  {w.workflow_id}  {w.name} (n={w.size})" for w in discovery.irregular]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="shadowcost-discover",
        description="Find repeated spreadsheet and email work and rank it by time cost.",
    )
    parser.add_argument("folder", type=Path)
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="grade the result against the folder's ground_truth/ (synthetic data only)",
    )
    args = parser.parse_args(argv)

    discovery = discover(ingest_folder(args.folder).events)
    recommendations = recommend(discovery)
    print(report(discovery, recommendations))
    if args.evaluate:
        from shadowcost.evaluation import evaluate

        print()
        print(evaluate(discovery, recommendations, args.folder / "ground_truth").summary())


if __name__ == "__main__":
    main()
