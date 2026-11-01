"""Replay a spec over past days and compare it with what the human actually did.

For each day the agent proposes actions from the spreadsheet as it stood that
morning. The human's version of the same work is read from the data: on a
case and day, the human did this workflow if the columns they changed largely
overlap the columns the spec sets (or, for email-only specs, if they emailed
the case on the day the trigger fired).

Agent and human actions on the same case are paired when they happen within
``PAIR_WINDOW_DAYS`` of each other, since the human often records a payment a
day or two after it arrives. Each pairing, and each action left unpaired,
becomes one outcome:

- ``match``: both acted and every compared field agrees;
- ``mismatch``: both acted, but some field differs;
- ``agent_only``: the agent acted and the human didn't;
- ``human_only``: the human acted and the agent didn't.

Only ``match`` counts as agreement. Days where neither acted are not counted,
because agreeing to do nothing is easy and would inflate the rate.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from shadowcost.agent.runtime import Proposal, propose_day
from shadowcost.agent.spec import AgentSpec
from shadowcost.autonomy import wilson_lower_bound
from shadowcost.discover.episodes import RowHistory

PAIR_WINDOW_DAYS = 4
MIN_COLUMN_OVERLAP = 0.5


@dataclass(frozen=True)
class HumanAction:
    case_id: str
    day: date
    changes: dict[str, str]  # column -> new value
    emailed: bool
    subject: str = ""


@dataclass(frozen=True)
class Outcome:
    case_id: str
    kind: str  # "match", "mismatch", "agent_only" or "human_only"
    agent_day: date | None
    human_day: date | None
    rule: str = ""
    field_matches: dict[str, bool] = field(default_factory=dict)
    agent: dict = field(default_factory=dict)
    human: dict = field(default_factory=dict)

    @property
    def agrees(self) -> bool:
        return self.kind == "match"

    @property
    def resolved_on(self) -> date:
        """The day the outcome is known: once both sides acted, or the window closed."""
        days = [d for d in (self.agent_day, self.human_day) if d]
        if self.kind in {"agent_only", "human_only"}:
            return max(days) + timedelta(days=PAIR_WINDOW_DAYS)
        return max(days)


@dataclass
class BacktestResult:
    spec: AgentSpec
    start: date
    end: date
    outcomes: list[Outcome]
    errors: list[Proposal]

    def metrics(self) -> dict:
        kinds = Counter(o.kind for o in self.outcomes)
        n = len(self.outcomes)
        agent_actions = kinds["match"] + kinds["mismatch"] + kinds["agent_only"]
        human_actions = kinds["match"] + kinds["mismatch"] + kinds["human_only"]
        paired = [o for o in self.outcomes if o.kind in {"match", "mismatch"}]
        fields: dict[str, list[bool]] = defaultdict(list)
        for o in paired:
            for name, ok in o.field_matches.items():
                fields[name].append(ok)
        faster = [(o.human_day - o.agent_day).days for o in paired]
        return {
            "outcomes": n,
            "kinds": dict(kinds),
            "agreement": round(kinds["match"] / n, 3) if n else 0.0,
            "agreement_lower_bound": round(wilson_lower_bound(kinds["match"], n), 3),
            "action_precision": round(len(paired) / agent_actions, 3) if agent_actions else 0.0,
            "action_recall": round(len(paired) / human_actions, 3) if human_actions else 0.0,
            "field_agreement": {k: round(sum(v) / len(v), 3) for k, v in sorted(fields.items())},
            "median_days_ahead_of_human": statistics.median(faster) if faster else None,
            "errors": len(self.errors),
        }

    def summary(self) -> str:
        m = self.metrics()
        kinds = m["kinds"]
        lines = [
            f"Backtest of {self.spec.workflow_id} '{self.spec.name}' on {self.start} to {self.end}",
            f"  {m['outcomes']} outcomes: {kinds.get('match', 0)} match, "
            f"{kinds.get('mismatch', 0)} mismatch, {kinds.get('agent_only', 0)} agent only, "
            f"{kinds.get('human_only', 0)} human only",
            f"  agreement {m['agreement']:.1%} (95% lower bound {m['agreement_lower_bound']:.1%})",
            f"  acted when the human did: precision {m['action_precision']:.1%}, "
            f"recall {m['action_recall']:.1%}",
        ]
        if m["field_agreement"]:
            lines.append(
                "  field agreement when both acted: "
                + ", ".join(f"{k} {v:.0%}" for k, v in m["field_agreement"].items())
            )
        ahead = m["median_days_ahead_of_human"]
        if ahead is not None:
            unit = "day" if ahead == 1 else "days"
            lines.append(f"  agent acted a median {ahead:g} {unit} before the human")
        if self.errors:
            lines.append(
                f"  {len(self.errors)} proposals failed to evaluate, e.g. {self.errors[0].error}"
            )
        return "\n".join(lines)


def backtest(spec: AgentSpec, events: pd.DataFrame, start: date, end: date) -> BacktestResult:
    history = RowHistory(events)
    day_of = events["timestamp"].dt.date
    proposals: list[Proposal] = []
    day = start
    while day <= end:
        day_events = events[day_of == day]
        proposals += propose_day(spec, day, history.before(day), day_events)
        day += timedelta(days=1)
    errors = [p for p in proposals if p.error]
    good = [p for p in proposals if not p.error]
    humans = human_actions(spec, events, start, end)
    return BacktestResult(spec, start, end, pair(good, humans, history), errors)


def human_actions(
    spec: AgentSpec, events: pd.DataFrame, start: date, end: date
) -> list[HumanAction]:
    day_of = events["timestamp"].dt.date
    in_period = events[(day_of >= start) & (day_of <= end) & (events["case_id"] != "")]
    changes: dict[tuple[str, date], dict[str, str]] = defaultdict(dict)
    added: set[tuple[str, date]] = set()
    emailed: dict[tuple[str, date], str] = {}
    for row in in_period.itertuples():
        key = (row.case_id, row.timestamp.date())
        if row.activity.startswith(f"{spec.series}.update["):
            changes[key].update({col: new for col, (_, new) in row.payload["changes"].items()})
        elif row.activity == f"{spec.series}.add" and not row.payload.get("first_snapshot"):
            added.add(key)
        elif row.activity == "email.sent":
            emailed.setdefault(key, row.payload.get("subject", ""))

    target = spec.target_columns
    actions = []
    for key in sorted(set(changes) | set(emailed)):
        changed = set(changes.get(key, {}))
        if target:
            overlap = len(changed & target) / len(changed | target) if changed else 0.0
            did_it = overlap >= MIN_COLUMN_OVERLAP
        else:  # email-only work, e.g. sending the invoice for a new row
            did_it = key in emailed and (spec.trigger.kind != "new_row" or key in added)
        if did_it:
            actions.append(
                HumanAction(
                    key[0], key[1], changes.get(key, {}), key in emailed, emailed.get(key, "")
                )
            )
    return actions


def pair(
    proposals: list[Proposal], humans: list[HumanAction], history: RowHistory
) -> list[Outcome]:
    by_case_agent: dict[str, list[Proposal]] = defaultdict(list)
    by_case_human: dict[str, list[HumanAction]] = defaultdict(list)
    for p in proposals:
        by_case_agent[p.case_id].append(p)
    for h in humans:
        by_case_human[h.case_id].append(h)

    outcomes = []
    for case_id in sorted(set(by_case_agent) | set(by_case_human)):
        remaining = sorted(by_case_human[case_id], key=lambda h: h.day)
        for p in sorted(by_case_agent[case_id], key=lambda p: p.day):
            match = next(
                (h for h in remaining if abs((h.day - p.day).days) <= PAIR_WINDOW_DAYS), None
            )
            if match is None:
                outcomes.append(
                    Outcome(case_id, "agent_only", p.day, None, p.rule, agent=_agent_view(p))
                )
                continue
            remaining.remove(match)
            after = history.before(match.day + timedelta(days=1)).get(case_id, {})
            fields = {col: _same(value, after.get(col, "")) for col, value in p.updates.items()}
            fields["email"] = (p.email is not None) == match.emailed
            kind = "match" if all(fields.values()) else "mismatch"
            outcomes.append(
                Outcome(
                    case_id, kind, p.day, match.day, p.rule, fields, _agent_view(p),
                    {"changes": match.changes, "emailed": match.emailed, "subject": match.subject},
                )
            )  # fmt: skip
        for h in remaining:
            outcomes.append(
                Outcome(
                    case_id, "human_only", None, h.day,
                    human={"changes": h.changes, "emailed": h.emailed, "subject": h.subject},
                )
            )  # fmt: skip
    return sorted(outcomes, key=lambda o: (o.resolved_on, o.case_id))


def _agent_view(p: Proposal) -> dict:
    return {"updates": p.updates, "email": p.email}


def _same(a: str, b: str) -> bool:
    try:
        return math.isclose(float(a), float(b), abs_tol=0.005)
    except (TypeError, ValueError):
        return str(a).strip().casefold() == str(b).strip().casefold()
