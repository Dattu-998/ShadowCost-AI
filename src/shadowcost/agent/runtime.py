"""Run a spec for one day: which cases it acts on, and what it would do to each.

The agent sees exactly what the office manager sees that morning: the
spreadsheet as it stood at the end of the previous day, plus the day's bank
credits or incoming email. It never sees the future, and never what the human
does that day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from shadowcost.agent.expr import ExpressionError, format_value, render
from shadowcost.agent.spec import AgentSpec


@dataclass(frozen=True)
class Proposal:
    case_id: str
    day: date
    rule: str
    updates: dict[str, str]  # column -> new value
    email: dict | None  # {"to", "subject", "body"}
    error: str = ""  # set when the spec could not be evaluated for this case


def propose_day(
    spec: AgentSpec, day: date, rows_before: dict[str, dict], day_events: pd.DataFrame
) -> list[Proposal]:
    proposals = []
    for case_id, row, event in _candidates(spec, day, rows_before, day_events):
        context = {"row": row, "event": event, "today": day}
        for rule in spec.rules:
            if not all(c.holds(row, event, day) for c in rule.when):
                continue
            try:
                updates = {col: format_value(render(v, context)) for col, v in rule.set.items()}
                email = (
                    {
                        "to": format_value(render(rule.email.to, context)),
                        "subject": format_value(render(rule.email.subject, context)),
                        "body": format_value(render(rule.email.body, context)),
                    }
                    if rule.email
                    else None
                )
                proposals.append(Proposal(case_id, day, rule.name, updates, email))
            except (ExpressionError, ZeroDivisionError, TypeError) as err:
                proposals.append(Proposal(case_id, day, rule.name, {}, None, error=str(err)))
            break  # the first matching rule decides
    return proposals


def _candidates(spec: AgentSpec, day: date, rows_before: dict[str, dict], day_events: pd.DataFrame):
    trigger = spec.trigger
    if trigger.kind == "schedule":
        if day.weekday() in trigger.weekdays:
            for case_id in sorted(rows_before):
                yield case_id, rows_before[case_id], {}
    elif trigger.kind == "event":
        seen = set()
        matching = day_events[
            (day_events["activity"] == trigger.activity) & (day_events["case_id"] != "")
        ]
        for case_id, timestamp, payload in zip(
            matching["case_id"], matching["timestamp"], matching["payload"], strict=True
        ):
            if case_id in seen or case_id not in rows_before:
                continue
            seen.add(case_id)
            yield case_id, rows_before[case_id], {"date": timestamp.date().isoformat(), **payload}
    elif trigger.kind == "new_row":
        added = day_events[day_events["activity"] == f"{spec.series}.add"]
        for case_id, payload in zip(added["case_id"], added["payload"], strict=True):
            if not payload.get("first_snapshot"):
                yield case_id, payload["row"], {}
