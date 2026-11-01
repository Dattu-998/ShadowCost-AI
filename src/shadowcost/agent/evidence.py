"""Summarise a discovered workflow as evidence an LLM can turn into a spec.

The LLM never sees raw data dumps. It gets measured facts, each with its
support, so its job is to turn them into rules and email wording rather than
to guess:

- the trigger and date condition that discovery found;
- per variant (e.g. first vs later reminders): how the rows looked before the
  work, as categorical value counts and days-since ranges for date columns;
- per changed column: which simple explanations of the new value hold, such as
  "equals today" (97%), "previous value + 1" (100%), "equals the trigger
  event's date" (95%) or a constant;
- a few real example emails with the row they were written for.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from shadowcost.discover import Discovery, Workflow
from shadowcost.discover.episodes import RowHistory

MAX_VARIANTS = 4
MIN_VARIANT_INSTANCES = 2  # a variant seen once is listed, not described: one-offs make bad rules
MAX_EXAMPLES = 2
CATEGORICAL_MAX_VALUES = 6
MIN_HYPOTHESIS_SUPPORT = 0.6
_TRIGGER_DETAILS = {"weekdays", "activity", "median_lag_days"}


def build_evidence(discovery: Discovery, workflow: Workflow) -> dict:
    history = RowHistory(discovery.events)
    events = discovery.events.set_index("event_id")
    episodes = discovery.episodes.set_index("episode_id").loc[workflow.episode_ids]
    trigger_events = workflow.trigger.detail.get("trigger_events", {})
    series = _series(workflow)
    columns = _columns(discovery, series)
    # Judge which columns are categorical across every row, not the few examples.
    everything = history.before(discovery.events["timestamp"].max().date() + timedelta(days=1))
    cardinality = {c: len({row.get(c, "") for row in everything.values()}) for c in columns}

    variants = []
    common = [(sig, n) for sig, n in workflow.variants if n >= MIN_VARIANT_INSTANCES][:MAX_VARIANTS]
    rare = [(sig, n) for sig, n in workflow.variants if (sig, n) not in common]
    for signature, count in common:
        members = episodes[episodes["signature"] == signature]
        befores, afters, contexts = [], [], []
        for episode_id, row in members.iterrows():
            before = history.before(row["day"]).get(row["case_id"])
            after = history.before(row["day"] + timedelta(days=1)).get(row["case_id"], {})
            event = {}
            if episode_id in trigger_events:
                trigger = events.loc[trigger_events[episode_id]]
                event = {"date": trigger["timestamp"].date().isoformat(), **trigger["payload"]}
            befores.append(before)
            afters.append(after)
            contexts.append((row["day"], event, list(row["event_ids"])))
        variants.append(
            {
                "instances": count,
                "steps": list(signature),
                "row_before": _profile(
                    [b for b in befores if b],
                    [c[0] for c, b in zip(contexts, befores, strict=True) if b],
                    cardinality,
                ),
                "changed_columns": _explain_changes(signature, befores, afters, contexts),
                "example_emails": _examples(events, befores, afters, contexts),
            }
        )  # fmt: skip

    evidence = {
        "workflow_id": workflow.workflow_id,
        "description": workflow.name,
        "series": series,
        "columns": columns,
        "instances": workflow.size,
        "instances_per_week": workflow.instances_per_week,
        "trigger": {
            "kind": workflow.trigger.kind,
            "description": workflow.trigger.description,
            "share_of_instances_explained": round(workflow.trigger.support, 3),
            **{k: v for k, v in workflow.trigger.detail.items() if k in _TRIGGER_DETAILS},
        },
        "variants": variants,
        "rare_variants_not_to_model": [
            {"instances": n, "steps": list(sig)} for sig, n in rare
        ],
    }  # fmt: skip
    if workflow.trigger.kind == "event":
        sample = next(iter(trigger_events.values()), None)
        if sample:
            evidence["trigger"]["event_fields"] = ["date", *events.loc[sample, "payload"].keys()]
    if workflow.condition:
        c = workflow.condition
        evidence["date_condition"] = {
            "description": c.description,
            "share_of_instances_meeting_it": c.support,
            "share_of_eligible_rows_meeting_it_that_were_worked_on": c.precision,
        }
    return evidence


def _series(workflow: Workflow) -> str:
    for signature, _ in workflow.variants:
        for step in signature:
            if not step.startswith("email."):
                return step.split(".", 1)[0]
    return ""


def _columns(discovery: Discovery, series: str) -> list[str]:
    sheet = discovery.events[discovery.events["activity"] == f"{series}.add"]
    return list(sheet.iloc[0]["payload"]["row"]) if len(sheet) else []


def _profile(rows: list[dict], days: list[date], cardinality: dict[str, int]) -> dict:
    """Categorical value counts and days-since ranges for the rows before the work."""
    profile = {}
    for column in rows[0] if rows else []:
        values = [r.get(column, "") for r in rows]
        ages = [(day - d).days for day, v in zip(days, values, strict=True) if (d := _date(v))]
        if len(ages) >= 0.8 * len(values):
            profile[column] = {
                "days_since": {
                    "min": min(ages),
                    "median": sorted(ages)[len(ages) // 2],
                    "max": max(ages),
                },
                "empty": sum(1 for v in values if not v),
            }  # fmt: skip
        elif cardinality.get(column, 0) <= CATEGORICAL_MAX_VALUES:
            profile[column] = {"values": dict(Counter(values).most_common())}
    return profile


def _explain_changes(signature, befores, afters, contexts) -> dict:
    changed = sorted(
        {c for s in signature if ".update[" in s for c in s.split("[", 1)[1].rstrip("]").split(",")}
    )
    explanations = {}
    for column in changed:
        tests: Counter = Counter()
        news = []
        n = 0
        for before, after, (day, event, _) in zip(befores, afters, contexts, strict=True):
            if not before:
                continue
            n += 1
            old, new = before.get(column, ""), after.get(column, "")
            news.append(new)
            tests["equals today"] += new == day.isoformat()
            if event.get("date"):
                tests["equals the trigger event's date"] += new == event["date"]
            if _int(old) is not None and _int(new) is not None:
                tests["previous value + 1"] += _int(new) == _int(old) + 1
        value, count = Counter(news).most_common(1)[0] if news else ("", 0)
        tests[f"always {value!r}"] = count
        found = {
            k: round(v / n, 3) for k, v in tests.items() if n and v / n >= MIN_HYPOTHESIS_SUPPORT
        }
        transitions = Counter(
            f"{b.get(column, '')!r} -> {a.get(column, '')!r}"
            for b, a in zip(befores, afters, strict=True)
            if b
        )
        explanations[column] = {
            "explanations": found or "no simple explanation",
            "common_transitions": dict(transitions.most_common(3)),
        }  # fmt: skip
    return explanations


def _examples(events, befores, afters, contexts) -> list[dict]:
    examples = []
    for before, after, (day, _, event_ids) in zip(befores, afters, contexts, strict=True):
        sent = [e for e in event_ids if events.loc[e, "activity"] == "email.sent"]
        if not sent:
            continue
        payload = events.loc[sent[0], "payload"]
        examples.append(
            {
                "date": day.isoformat(),
                "row_before": before or after,
                "to": payload["to"],
                "subject": payload["subject"],
                "body": payload["body"],
            }
        )
        if len(examples) == MAX_EXAMPLES:
            break
    return examples


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _int(value: str) -> int | None:
    try:
        return int(str(value))
    except ValueError:
        return None
