"""Generate, test, approve and shadow-run agents.

    shadowcost-agent generate data/sample --out specs       # draft with the LLM, then backtest
    shadowcost-agent backtest specs/W2.json data/sample     # replay against the person
    shadowcost-agent approve specs/W2.json --by "Dattu"     # record a human approval
    shadowcost-agent shadow specs/W2.json data/demo-year    # work alongside the person

Specs are drafted from the first ``--train-days`` of the data only. Everything
after that is held out, for the backtest and for shadow mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from shadowcost.agent.backtest import backtest
from shadowcost.agent.generate import generate_spec
from shadowcost.agent.shadow_mode import run_shadow
from shadowcost.agent.spec import AgentSpec
from shadowcost.agent.store import Store
from shadowcost.discover import discover
from shadowcost.ingest import ingest_folder
from shadowcost.llm import ChatClient, load_dotenv
from shadowcost.recommend import recommend

DEFAULT_DB = Path("shadowcost.db")


def cmd_generate(args: argparse.Namespace) -> int:
    load_dotenv()
    events = ingest_folder(args.folder).events
    first, last = events["timestamp"].min().date(), events["timestamp"].max().date()
    split = first + timedelta(days=args.train_days)
    discovery = discover(events[events["timestamp"].dt.date < split])
    recommendations = {r.workflow.workflow_id: r for r in recommend(discovery)}
    wanted = args.workflow or list(recommendations)
    args.out.mkdir(parents=True, exist_ok=True)
    client = ChatClient()
    print(f"Drafting from {first} to {split - timedelta(days=1)}; holding out {split} to {last}.")

    failed = 0
    for workflow in discovery.workflows:
        if workflow.workflow_id not in wanted:
            continue
        generation = generate_spec(discovery, workflow, client)
        if generation.spec is None:
            failed += 1
            print(f"\n{workflow.workflow_id}: no valid spec after {generation.attempts} attempts")
            print("  " + "\n  ".join(generation.problems))
            continue
        holdout = backtest(generation.spec, events, split, last)
        data = generation.spec.to_dict()
        data["evaluation"] = {
            "minutes_per_case": recommendations[workflow.workflow_id].minutes_per_instance,
            "evidence_period": generation.evidence_backtest.metrics(),
            "held_out": {"from": split.isoformat(), "to": last.isoformat(), **holdout.metrics()},
        }
        path = args.out / f"{workflow.workflow_id}.json"
        path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"\n{path} ({generation.attempts} attempt(s) with {client.model})")
        print(holdout.summary())
    return 1 if failed else 0


def cmd_backtest(args: argparse.Namespace) -> int:
    spec = _load(args.spec)
    events = ingest_folder(args.folder).events
    start = args.start or _after_evidence(spec)
    end = args.end or events["timestamp"].max().date()
    print(backtest(spec, events, start, end).summary())
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    spec = _load(args.spec)
    store = Store(args.db)
    sid = store.approve(spec, args.by)
    store.close()
    print(f"Approved {sid} ({spec.name}) by {args.by}. Any edit to the spec needs a new approval.")
    return 0


def cmd_shadow(args: argparse.Namespace) -> int:
    spec = _load(args.spec)
    store = Store(args.db)
    if not store.approval(spec):
        print(
            f"{args.spec} has not been approved (or changed since). Review it, then run:\n"
            f'  shadowcost-agent approve {args.spec} --by "<your name>"',
            file=sys.stderr,
        )
        return 2
    events = ingest_folder(args.folder).events
    start = args.start or _after_evidence(spec)
    end = args.end or events["timestamp"].max().date()
    minutes = args.minutes or json.loads(args.spec.read_text())["evaluation"]["minutes_per_case"]
    run = run_shadow(spec, events, start, end, minutes)
    run_id = store.save_run(run)
    store.close()
    print(run.summary())
    print(f"  saved as run {run_id} in {args.db}")
    return 0


def _load(path: Path) -> AgentSpec:
    return AgentSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _after_evidence(spec: AgentSpec) -> date:
    period = spec.source.get("evidence_period")
    if not period:
        raise SystemExit("the spec has no evidence period; pass --from")
    return date.fromisoformat(period[1]) + timedelta(days=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shadowcost-agent", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("generate", help="draft specs with the LLM and backtest them")
    p.add_argument("folder", type=Path)
    p.add_argument("--out", type=Path, default=Path("specs"))
    p.add_argument("--train-days", type=int, default=80)
    p.add_argument("--workflow", action="append", help="only this workflow id (repeatable)")
    p.set_defaults(func=cmd_generate)

    for name, func, help_text in (
        ("backtest", cmd_backtest, "replay a spec against what the person did"),
        ("shadow", cmd_shadow, "run an approved spec in shadow mode"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("spec", type=Path)
        p.add_argument("folder", type=Path)
        p.add_argument("--from", dest="start", type=date.fromisoformat)
        p.add_argument("--to", dest="end", type=date.fromisoformat)
        if name == "shadow":
            p.add_argument("--db", type=Path, default=DEFAULT_DB)
            p.add_argument("--minutes", type=float, help="minutes of work per case")
        p.set_defaults(func=func)

    p = sub.add_parser("approve", help="record a human approval of a spec")
    p.add_argument("spec", type=Path)
    p.add_argument("--by", required=True)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_approve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
