"""Recommend step: rank discovered workflows by the time they cost.

Snapshots and emails show *that* work happened, not how long it took, so time
per instance is estimated from explicit per-step assumptions, and every
recommendation lists the assumptions it used. A second, observed figure comes
from the gaps between consecutive emails of the same workflow sent in one
sitting. Because a gap also contains whatever else was done in between, it is
an upper bound, not a measurement.

Measured savings come later, from shadow-mode execution data.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, fields

from shadowcost.discover import Discovery, Workflow

DAYS_PER_MONTH = 30.44
# Work set off by a free-text email needs someone (or something) to interpret it
# first, which makes it a riskier automation target.
JUDGMENT_TRIGGERS = {"email.received"}
JUDGMENT_PENALTY = 0.5
MAX_SITTING_GAP_MINUTES = 30  # emails further apart than this weren't sent in one sitting
MIN_OBSERVED_PAIRS = 5


@dataclass(frozen=True)
class TimeAssumptions:
    """Rough per-step times in minutes. Replace them with your own if you know better."""

    new_row: float = 3.0  # typing a new spreadsheet row
    row_update: float = 1.5  # editing an existing row
    templated_email: float = 4.0  # writing an email that follows a known template
    find_case: float = 2.0  # finding the right row after an outside event, e.g. a payment
    unreferenced_lookup: float = 5.0  # extra when that event carried no usable reference


@dataclass
class Recommendation:
    workflow: Workflow
    minutes_per_instance: float
    breakdown: dict[str, float]  # average minutes per instance, by assumption
    observed_minutes: float | None  # upper bound from email gaps, when there's enough data
    observed_pairs: int
    instances_per_month: float
    hours_per_month: float
    automation_score: float  # regularity x consistency, halved if it needs judgment
    addressable_hours_per_month: float  # hours_per_month x automation_score
    assumptions: list[str]
    caveats: list[str]


def recommend(
    discovery: Discovery, assumptions: TimeAssumptions | None = None
) -> list[Recommendation]:
    """Discovered workflows, the most addressable time first."""
    assumptions = assumptions or TimeAssumptions()
    recommendations = [_recommend(discovery, w, assumptions) for w in discovery.workflows]
    return sorted(recommendations, key=lambda r: -r.addressable_hours_per_month)


def _recommend(discovery: Discovery, workflow: Workflow, a: TimeAssumptions) -> Recommendation:
    events = discovery.events.set_index("event_id")
    episodes = discovery.episodes.set_index("episode_id").loc[workflow.episode_ids]
    trigger_events = workflow.trigger.detail.get("trigger_events", {})

    totals = dict.fromkeys((f.name for f in fields(TimeAssumptions)), 0.0)
    for episode_id, event_ids in episodes["event_ids"].items():
        for activity in events.loc[event_ids, "activity"]:
            if activity == "email.sent":
                totals["templated_email"] += a.templated_email
            elif activity.endswith(".add"):
                totals["new_row"] += a.new_row
            elif ".update[" in activity:
                totals["row_update"] += a.row_update
        trigger_event = trigger_events.get(episode_id)
        if trigger_event:
            totals["find_case"] += a.find_case
            if events.loc[trigger_event, "link_method"] == "amount+payer":
                totals["unreferenced_lookup"] += a.unreferenced_lookup

    n = workflow.size
    breakdown = {name: round(total / n, 2) for name, total in totals.items() if total}
    minutes = sum(breakdown.values())
    observed, pairs = _observed_minutes(discovery, workflow)
    per_month = n / discovery.period_days * DAYS_PER_MONTH
    hours = per_month * minutes / 60
    score = workflow.regularity * workflow.consistency
    caveats = []
    if workflow.trigger.detail.get("activity") in JUDGMENT_TRIGGERS:
        score *= JUDGMENT_PENALTY
        caveats.append(
            "set off by a free-text email that has to be read and interpreted "
            f"(automation score x{JUDGMENT_PENALTY:g})"
        )
    score = round(score, 3)
    return Recommendation(
        workflow=workflow,
        minutes_per_instance=round(minutes, 1),
        breakdown=breakdown,
        observed_minutes=observed,
        observed_pairs=pairs,
        instances_per_month=round(per_month, 1),
        hours_per_month=round(hours, 2),
        automation_score=score,
        addressable_hours_per_month=round(hours * score, 2),
        assumptions=[f"{name.replace('_', ' ')}: {getattr(a, name):g} min" for name in breakdown],
        caveats=caveats,
    )


def _observed_minutes(discovery: Discovery, workflow: Workflow) -> tuple[float | None, int]:
    """Median gap between consecutive sent emails that both belong to this workflow."""
    members = {e for ids in discovery.episodes.set_index("episode_id").loc[
        workflow.episode_ids, "event_ids"] for e in ids}  # fmt: skip
    sent = discovery.events[discovery.events["activity"] == "email.sent"]
    gaps = []
    previous = None
    for event_id, timestamp in zip(sent["event_id"], sent["timestamp"], strict=True):
        if previous and previous[0] in members and event_id in members:
            minutes = (timestamp - previous[1]).total_seconds() / 60
            if timestamp.date() == previous[1].date() and minutes <= MAX_SITTING_GAP_MINUTES:
                gaps.append(minutes)
        previous = (event_id, timestamp)
    if len(gaps) < MIN_OBSERVED_PAIRS:
        return None, len(gaps)
    return round(statistics.median(gaps), 1), len(gaps)
