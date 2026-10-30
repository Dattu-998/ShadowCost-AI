"""Explain what sets each kind of work off.

Three kinds of trigger are tested, and the one that explains the most
instances wins:

- event: an outside event on the same case shortly before, such as a payment
  arriving or a customer's email;
- new_row: the work creates the case, such as a new invoice row;
- schedule: the work happens on a fixed set of weekdays.

Scheduled work on existing rows also gets a date condition: a one-column
decision stump such as "due_date at least 7 days ago", reported with how
precisely it picks out the rows that were actually worked on.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from math import comb

import numpy as np
import pandas as pd
from scipy.stats import binom

from shadowcost.discover.episodes import RowHistory

TRIGGER_WINDOW_DAYS = 4  # an outside event at most this many calendar days before the work
MAX_SCHEDULE_DAYS = 2  # a schedule is at most two weekdays...
MIN_SCHEDULE_SHARE = 0.9  # ...that account for at least 90% of instances...
MAX_SCHEDULE_P_VALUE = 0.01  # ...more often than chance would explain
MIN_CONDITION_INSTANCES = 5
CATEGORICAL_MAX_VALUES = 10
MIN_FILTER_EFFECT = 0.1  # a row filter must rule out at least 10% of candidate rows
_WEEKDAYS = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]


@dataclass(frozen=True)
class Trigger:
    kind: str  # "event", "new_row", "schedule" or "none"
    description: str
    support: float  # share of instances the trigger explains
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Condition:
    column: str
    min_days: int
    support: float  # share of instances that met the condition
    precision: float  # share of eligible rows meeting it that were worked on that day
    eligible: dict[str, list[str]]  # row values seen in instances, e.g. {"status": [...]}
    description: str


def infer_trigger(episodes: pd.DataFrame, events: pd.DataFrame) -> Trigger:
    candidates = [
        t
        for t in (
            event_trigger(episodes, events),
            new_row_trigger(episodes),
            schedule_trigger(episodes),
        )
        if t is not None
    ]
    if not candidates:
        return Trigger("none", "no consistent trigger found", 0.0)
    # max() keeps the first of equal candidates, so ties prefer event > new_row > schedule.
    return max(candidates, key=lambda t: t.support)


def event_trigger(episodes: pd.DataFrame, events: pd.DataFrame) -> Trigger | None:
    external = events[
        ((events["source"] == "bank") | (events["activity"] == "email.received"))
        & (events["case_id"] != "")
    ]
    by_case: dict[str, list[tuple[date, str, str]]] = defaultdict(list)
    for case_id, ts, activity, event_id in zip(
        external["case_id"], external["timestamp"], external["activity"], external["event_id"],
        strict=True,
    ):  # fmt: skip
        by_case[case_id].append((ts.date(), activity, event_id))

    hits: dict[str, dict[str, tuple[str, int]]] = defaultdict(dict)
    for episode_id, case_id, day in zip(
        episodes["episode_id"], episodes["case_id"], episodes["day"], strict=True
    ):
        before = [
            e for e in by_case.get(case_id, []) if 0 <= (day - e[0]).days <= TRIGGER_WINDOW_DAYS
        ]
        if before:
            happened, activity, event_id = max(before)  # the most recent
            hits[activity][episode_id] = (event_id, (day - happened).days)
    if not hits:
        return None
    activity, matched = max(hits.items(), key=lambda item: len(item[1]))
    lag = statistics.median(lag for _, lag in matched.values())
    return Trigger(
        "event",
        f"after a {activity} on the same case (median {lag:g} day{'' if lag == 1 else 's'} later)",
        len(matched) / len(episodes),
        {
            "activity": activity,
            "median_lag_days": lag,
            "trigger_events": {ep: event_id for ep, (event_id, _) in matched.items()},
        },
    )


def new_row_trigger(episodes: pd.DataFrame) -> Trigger | None:
    adds = [next((s for s in sig if s.endswith(".add")), None) for sig in episodes["signature"]]
    created = [a for a in adds if a]
    if not created:
        return None
    series = max(set(created), key=created.count).split(".")[0]
    return Trigger(
        "new_row",
        f"a new {series} row is created",
        len(created) / len(episodes),
        {"series": series},
    )


def schedule_trigger(episodes: pd.DataFrame) -> Trigger | None:
    """Work concentrated on one or two weekdays, more than chance would explain.

    With few instances, landing on two weekdays is likely by luck, so the
    concentration must also pass a binomial test against work spread evenly
    over the week (Bonferroni-corrected for picking the busiest days).
    """
    days_seen = [d.weekday() for d in episodes["day"]]
    week = 7 if any(d >= 5 for d in days_seen) else 5
    weekdays = pd.Series(days_seen).value_counts()
    n = len(days_seen)
    for k in range(1, MAX_SCHEDULE_DAYS + 1):
        hits = int(weekdays.iloc[:k].sum())
        if hits / n < MIN_SCHEDULE_SHARE:
            continue
        p_value = binom.sf(hits - 1, n, k / week) * comb(week, k)
        if p_value >= MAX_SCHEDULE_P_VALUE:
            return None
        days = sorted(weekdays.index[:k])
        return Trigger(
            "schedule",
            "on " + " and ".join(_WEEKDAYS[d] for d in days),
            hits / n,
            {"weekdays": [int(d) for d in days], "p_value": float(p_value)},
        )
    return None


def date_condition(episodes: pd.DataFrame, history: RowHistory) -> Condition | None:
    """Fit "<date column> at least N days ago" to the rows that were worked on.

    The population is every row that existed before a day on which this work
    happened, narrowed to rows whose low-cardinality columns (status-like
    fields) take values seen in the instances. N is the 5th percentile of the
    instances' offsets, so the condition covers ~95% of them; the column whose
    condition selects worked-on rows most precisely is kept.
    """
    acted = set(zip(episodes["day"], episodes["case_id"], strict=True))
    instances = [
        (day, row)
        for day, case_id in acted
        if (row := history.before(day).get(case_id)) is not None
    ]
    if len(instances) < MIN_CONDITION_INSTANCES:
        return None
    population = [
        (day, case_id, row)
        for day in sorted({day for day, _ in acted})
        for case_id, row in history.before(day).items()
    ]
    columns = sorted({c for _, row in instances for c in row})
    # Only dates that nearly every instance has can explain nearly every instance.
    date_columns = [c for c in columns if _mostly_dates([row.get(c, "") for _, row in instances])]
    eligible = {}
    for c in columns:
        if c in date_columns:
            continue
        if len({row.get(c, "") for _, _, row in population}) > CATEGORICAL_MAX_VALUES:
            continue
        values = sorted({row.get(c, "") for _, row in instances})
        excluded = sum(row.get(c, "") not in values for _, _, row in population)
        # Keep a filter only if it rules out a real share of rows (e.g. paid invoices).
        if excluded >= MIN_FILTER_EFFECT * len(population):
            eligible[c] = values
    population = [
        p for p in population if all(p[2].get(c, "") in values for c, values in eligible.items())
    ]

    best: Condition | None = None
    for column in date_columns:
        offsets = [
            (day - d).days for day, row in instances if (d := _parse_date(row.get(column, "")))
        ]
        min_days = int(np.floor(np.percentile(offsets, 5)))
        if min_days < 1:
            continue
        meeting = [
            (day, case_id)
            for day, case_id, row in population
            if (d := _parse_date(row.get(column, ""))) and (day - d).days >= min_days
        ]
        if not meeting:
            continue
        precision = sum(m in acted for m in meeting) / len(meeting)
        support = sum(o >= min_days for o in offsets) / len(instances)
        if best is None or precision > best.precision:
            filters = "; ".join(f"{c} in {{{', '.join(v)}}}" for c, v in eligible.items())
            best = Condition(
                column,
                min_days,
                round(support, 3),
                round(precision, 3),
                eligible,
                f"{column} at least {min_days} days ago"
                + (f" (where {filters})" if filters else ""),
            )
    return best


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _mostly_dates(values: list[str]) -> bool:
    return bool(values) and sum(_parse_date(v) is not None for v in values) / len(values) >= 0.95
