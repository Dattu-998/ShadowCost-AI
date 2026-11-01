"""Report step: what the repeated work costs, what agents took over, and on what assumptions.

Savings are reported two ways and labelled as such:

- estimated: cases the agent agreed on x minutes per case from discovery's
  per-step assumptions x the share of the work the agent's stage removes;
- measured: the same, but with the minutes the person actually spent on each
  of those cases. On synthetic data those minutes come from the simulator's
  ground-truth log; in a real deployment they would come from time tracking.

Every assumption behind either number is listed in the report.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field, fields
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from shadowcost.agent.backtest import PAIR_WINDOW_DAYS
from shadowcost.agent.shadow_mode import TIME_SAVED_SHARE, ShadowRun, run_shadow
from shadowcost.agent.spec import AgentSpec
from shadowcost.autonomy import DEFAULT_POLICY
from shadowcost.discover import discover
from shadowcost.ingest import ingest_folder
from shadowcost.recommend import DAYS_PER_MONTH, TimeAssumptions, recommend


@dataclass
class Section:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    table: tuple[list[str], list[list[str]]] | None = None
    bullets: list[str] = field(default_factory=list)


@dataclass
class Report:
    title: str
    sections: list[Section]

    def markdown(self) -> str:
        out = [f"# {self.title}"]
        for s in self.sections:
            out.append(f"\n## {s.title}")
            out += [f"\n{p}" for p in s.paragraphs]
            if s.table:
                headers, rows = s.table
                out.append("\n| " + " | ".join(headers) + " |")
                out.append("|" + "---|" * len(headers))
                out += ["| " + " | ".join(row) + " |" for row in rows]
            if s.bullets:
                out.append("")
                out += [f"- {b}" for b in s.bullets]
        return "\n".join(out) + "\n"

    def html(self) -> str:
        e = html.escape
        body = [f"<h1>{e(self.title)}</h1>"]
        for s in self.sections:
            body.append(f"<h2>{e(s.title)}</h2>")
            body += [f"<p>{e(p)}</p>" for p in s.paragraphs]
            if s.table:
                headers, rows = s.table
                body.append("<table><thead><tr>" + "".join(f"<th>{e(h)}</th>" for h in headers))
                body.append("</tr></thead><tbody>")
                body += [
                    "<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>" for row in rows
                ]
                body.append("</tbody></table>")
            if s.bullets:
                body.append("<ul>" + "".join(f"<li>{e(b)}</li>" for b in s.bullets) + "</ul>")
        return _HTML.format(title=e(self.title), body="\n".join(body))


@dataclass
class AgentResult:
    spec: AgentSpec
    run: ShadowRun
    held_out: dict  # backtest metrics stored with the spec, if any
    measured_minutes: float | None


def build_report(
    folder: str | Path,
    specs: list[tuple[AgentSpec, dict]],
    train_days: int = 80,
    assumptions: TimeAssumptions | None = None,
) -> Report:
    """``specs`` pairs each spec with its ``evaluation`` block (may be empty)."""
    folder = Path(folder)
    assumptions = assumptions or TimeAssumptions()
    events = ingest_folder(folder).events
    first, last = events["timestamp"].min().date(), events["timestamp"].max().date()
    split = first + timedelta(days=train_days)
    discovery = discover(events[events["timestamp"].dt.date < split])
    recommendations = recommend(discovery, assumptions)
    minutes_by_workflow = {r.workflow.workflow_id: r.minutes_per_instance for r in recommendations}
    truth = _ground_truth_minutes(folder / "ground_truth")

    agents = []
    for spec, evaluation in specs:
        start = _after_evidence(spec, split)
        minutes = evaluation.get("minutes_per_case") or minutes_by_workflow.get(spec.workflow_id, 0)
        run = run_shadow(spec, events, start, last, minutes)
        measured = None
        if truth is not None:
            measured = sum(
                TIME_SAVED_SHARE[stage] * truth.get((o.case_id, o.human_day), 0.0)
                for o, stage in run.outcomes
                if o.agrees
            )
        agents.append(AgentResult(spec, run, evaluation.get("held_out", {}), measured))

    sections = [
        Section(
            "Data",
            [
                f"{len(events)} events from {first} to {last} in {folder.name}. Workflows were "
                f"discovered and agents drafted from the first {train_days} days ({first} to "
                f"{split - timedelta(days=1)}); everything after that is held out.",
            ],
        ),
        _work_section(recommendations),
        _agents_section(agents),
        _savings_section(agents, first, last, truth is not None),
        _assumptions_section(assumptions),
        Section(
            "Caveats",
            bullets=[
                "Agreement means the agent did what the person did. Where they differ the "
                "person isn't always right (forgotten reminders, late recording); disagreements "
                "still count against the agent, so the figures are conservative.",
                "In a replay of history, 'approved' means the person did the same thing. A live "
                "deployment should record real approve and reject decisions and review times.",
                "Workflows that need reading free text or looking across rows are out of reach "
                "of the current spec language; such agents stay in shadow by design.",
            ],
        ),
    ]
    return Report(f"ShadowCost report: {folder.name}", sections)


def load_specs(folder: str | Path) -> list[tuple[AgentSpec, dict]]:
    specs = []
    for path in sorted(Path(folder).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        specs.append((AgentSpec.from_dict(data), data.get("evaluation", {})))
    return specs


def _work_section(recommendations) -> Section:
    rows = [
        [
            r.workflow.workflow_id,
            r.workflow.name,
            r.workflow.trigger.description,
            f"{r.instances_per_month:g}",
            f"{r.minutes_per_instance:g}",
            f"{r.hours_per_month:.1f}",
            f"{r.automation_score:.2f}",
        ]
        for r in recommendations
    ]
    total = sum(r.hours_per_month for r in recommendations)
    return Section(
        "Repeated work found",
        [f"About {total:.1f} hours a month go into these workflows (estimated)."],
        (["Id", "Work", "When", "Per month", "Min each", "Hours/month", "Automation score"], rows),
    )


def _agents_section(agents: list[AgentResult]) -> Section:
    rows = []
    for a in agents:
        held = a.held_out.get("agreement")
        path = " -> ".join(
            [a.run.changes[0].decision.current.name.lower()]
            + [f"{c.decision.next.name.lower()} ({c.day})" for c in a.run.changes]
            if a.run.changes
            else ["shadow"]
        )
        rows.append(
            [
                a.spec.workflow_id,
                a.spec.name,
                f"{held:.0%}" if held is not None else "n/a",
                str(len(a.run.outcomes)),
                path,
                a.run.final_stage.name.lower(),
            ]
        )
    return Section(
        "Agents",
        [
            "Each agent was backtested on held-out days, then run in shadow mode over the "
            "same period, earning autonomy in stages: draft only, act with approval, act alone."
        ],
        (["Id", "Agent", "Backtest agreement when drafted", "Cases", "Path", "Final stage"], rows),
    )


def _savings_section(agents: list[AgentResult], first: date, last: date, measured: bool) -> Section:
    headers = ["Id", "Agent", "Agreeing cases", "Estimated hours saved"]
    if measured:
        headers.append("Measured hours saved")
    rows = []
    for a in agents:
        row = [
            a.spec.workflow_id,
            a.spec.name,
            str(sum(o.agrees for o, _ in a.run.outcomes)),
            f"{a.run.minutes_saved() / 60:.1f}",
        ]
        if measured:
            row.append(f"{(a.measured_minutes or 0) / 60:.1f}")
        rows.append(row)
    estimated = sum(a.run.minutes_saved() for a in agents) / 60
    paragraphs = [f"Estimated time saved over the held-out period: {estimated:.1f} hours."]
    if measured:
        actual = sum(a.measured_minutes or 0 for a in agents) / 60
        paragraphs.append(
            f"Measured against the minutes the person actually spent on those cases "
            f"(the simulator's ground-truth log): {actual:.1f} hours."
        )
    return Section("Savings", paragraphs, (headers, rows))


def _assumptions_section(a: TimeAssumptions) -> Section:
    steps = ", ".join(f"{f.name.replace('_', ' ')} {getattr(a, f.name):g} min" for f in fields(a))
    shares = ", ".join(f"{s.name.lower()} {v:.0%}" for s, v in TIME_SAVED_SHARE.items())
    p = DEFAULT_POLICY
    return Section(
        "Assumptions",
        bullets=[
            f"Minutes per step (estimates): {steps}.",
            f"Share of an agreeing case's time saved, by stage: {shares}.",
            f"Promotion: at least {p.min_cases} cases at the current stage and a Wilson lower "
            f"bound of agreement of {p.promote_lower_bound:.2f}; demotion when recent agreement "
            f"falls below {p.demote_below:.0%}, or straight to shadow on a critical failure.",
            f"Agent and person actions on the same case count as the same work if within "
            f"{PAIR_WINDOW_DAYS} days of each other.",
            f"A month is {DAYS_PER_MONTH} days.",
        ],
    )


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="shadowcost-report", description="Write a savings report for a dataset and its agents."
    )
    parser.add_argument("folder", type=Path)
    parser.add_argument("--specs", type=Path, default=Path("specs"))
    parser.add_argument("--train-days", type=int, default=80)
    parser.add_argument("--out", type=Path, help="write to .md or .html instead of printing")
    args = parser.parse_args(argv)

    report = build_report(args.folder, load_specs(args.specs), args.train_days)
    if args.out is None:
        print(report.markdown())
        return
    text = report.html() if args.out.suffix.lower() == ".html" else report.markdown()
    args.out.write_text(text, encoding="utf-8")
    print(f"Wrote {args.out}")


def _ground_truth_minutes(folder: Path) -> dict[tuple[str, date], float] | None:
    path = folder / "actions.csv"
    if not path.exists():
        return None
    actions = pd.read_csv(path, dtype=str, na_filter=False)
    actions = actions[(actions["case_id"] != "") & (actions["workflow"] != "ad_hoc")]
    minutes: dict[tuple[str, date], float] = {}
    for case_id, ts, m in zip(
        actions["case_id"], actions["timestamp"], actions["minutes"], strict=True
    ):
        key = (case_id, date.fromisoformat(ts[:10]))
        minutes[key] = minutes.get(key, 0.0) + float(m)
    return minutes


def _after_evidence(spec: AgentSpec, default: date) -> date:
    period = spec.source.get("evidence_period")
    return date.fromisoformat(period[1]) + timedelta(days=1) if period else default


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --fg: #1d1d1f; --bg: #ffffff; --muted: #6e6e73; --line: #e5e5ea; --head: #f5f5f7; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fg: #f5f5f7; --bg: #1c1c1e; --muted: #a1a1a6; --line: #3a3a3c; --head: #2c2c2e; }}
}}
body {{ font: 15px/1.5 system-ui, sans-serif; color: var(--fg); background: var(--bg);
  max-width: 980px; margin: 0 auto; padding: 24px 16px; }}
h1 {{ font-size: 1.6rem; }} h2 {{ font-size: 1.15rem; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; display: block; overflow-x: auto; }}
th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); }}
th {{ background: var(--head); font-weight: 600; }}
li {{ margin: 4px 0; color: var(--muted); }}
</style></head><body>
{body}
</body></html>
"""
