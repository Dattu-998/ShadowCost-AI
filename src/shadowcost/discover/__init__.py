"""Discover step: find repeated workflows in the event table.

1. Sent emails are clustered into templates (``templates``).
2. Work is grouped into episodes: everything done on one case on one day
   (``episodes``).
3. Episode signatures that change largely the same spreadsheet columns are
   merged, so a first reminder (which also flips the status) and a later
   reminder count as one workflow with two variants.
4. Each group with enough instances gets a trigger (``triggers``). Groups
   that a trigger explains are workflows; the rest are reported as irregular
   repeated work, which is a poor automation target.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations

import pandas as pd

from shadowcost.discover.episodes import RowHistory, build_episodes
from shadowcost.discover.templates import DEFAULT_DISTANCE, Template, cluster_templates
from shadowcost.discover.triggers import Condition, Trigger, date_condition, infer_trigger

__all__ = ["Discovery", "Workflow", "discover"]

MIN_SUPPORT = 8  # fewer instances than this is treated as one-off work
MIN_REGULARITY = 0.6  # share of instances the trigger must explain
MERGE_SIMILARITY = 0.6  # Jaccard similarity of changed columns needed to merge signatures


@dataclass
class Workflow:
    workflow_id: str
    name: str
    variants: list[tuple[tuple[str, ...], int]]  # signature and count, most common first
    episode_ids: list[str]
    trigger: Trigger
    condition: Condition | None
    regularity: float  # share of instances the trigger explains
    consistency: float  # share of instances covered by the three most common variants
    instances_per_week: float

    @property
    def size(self) -> int:
        return len(self.episode_ids)


@dataclass
class Discovery:
    events: pd.DataFrame
    episodes: pd.DataFrame
    templates: list[Template]
    template_of: dict[str, str]  # sent email's object id -> template id
    workflows: list[Workflow]  # repeated and explained by a trigger
    irregular: list[Workflow]  # repeated, but no trigger explains when
    period_days: int


def discover(
    events: pd.DataFrame,
    min_support: int = MIN_SUPPORT,
    min_regularity: float = MIN_REGULARITY,
    merge_similarity: float = MERGE_SIMILARITY,
    template_distance: float = DEFAULT_DISTANCE,
) -> Discovery:
    sent = events[events["activity"] == "email.sent"]
    template_of, templates = cluster_templates(sent, template_distance)
    labels = {t.template_id: t.label for t in templates}
    episodes = build_episodes(events, template_of)
    history = RowHistory(events)
    period_days = max(1, (events["timestamp"].max() - events["timestamp"].min()).days + 1)

    found: list[Workflow] = []
    for signatures in _group_signatures(list(episodes["signature"].unique()), merge_similarity):
        members = episodes[episodes["signature"].map(lambda s, sigs=signatures: s in sigs)]
        if len(members) < min_support:
            continue
        trigger = infer_trigger(members, events)
        condition = date_condition(members, history) if trigger.kind == "schedule" else None
        variants = Counter(members["signature"]).most_common()
        found.append(
            Workflow(
                workflow_id="",
                name=describe(variants[0][0], labels),
                variants=variants,
                episode_ids=members["episode_id"].tolist(),
                trigger=trigger,
                condition=condition,
                regularity=round(trigger.support, 3),
                consistency=round(sum(n for _, n in variants[:3]) / len(members), 3),
                instances_per_week=round(len(members) / period_days * 7, 2),
            )
        )

    found.sort(key=lambda w: -w.size)
    workflows = [w for w in found if w.regularity >= min_regularity]
    irregular = [w for w in found if w.regularity < min_regularity]
    for prefix, group in (("W", workflows), ("X", irregular)):
        for i, workflow in enumerate(group, start=1):
            workflow.workflow_id = f"{prefix}{i}"
    return Discovery(events, episodes, templates, template_of, workflows, irregular, period_days)


def describe(signature: tuple[str, ...], template_labels: dict[str, str]) -> str:
    """A readable name for an episode signature."""
    adds, emails, updates, other = [], [], [], []
    for step in signature:
        if step.startswith("email.sent:"):
            emails.append(f"send '{template_labels.get(step.split(':', 1)[1], step)}'")
            continue
        series, verb = step.split(".", 1)
        if verb == "add":
            adds.append(f"add a row to {series}")
        elif verb.startswith("update["):
            updates.append(f"update {series} [{verb[7:-1].replace(',', ', ')}]")
        else:
            other.append(f"{verb} a row in {series}")
    return " + ".join(adds + emails + updates + other)


def _fingerprint(signature: tuple[str, ...]) -> frozenset[str]:
    """What an episode does to the spreadsheet, or its email templates if nothing."""
    parts: set[str] = set()
    for step in signature:
        if step.startswith("email.sent:"):
            continue
        series, verb = step.split(".", 1)
        if verb.startswith("update["):
            parts |= {f"{series}.{column}" for column in verb[7:-1].split(",")}
        else:
            parts.add(f"{series}.<{verb}>")
    return frozenset(parts or signature)


def _group_signatures(
    signatures: list[tuple[str, ...]], min_similarity: float
) -> list[set[tuple[str, ...]]]:
    """Merge signatures whose fingerprints overlap (union-find on Jaccard similarity)."""
    parent = list(range(len(signatures)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    prints = [_fingerprint(s) for s in signatures]
    for i, j in combinations(range(len(signatures)), 2):
        overlap = len(prints[i] & prints[j]) / len(prints[i] | prints[j])
        if overlap >= min_similarity:
            parent[root(i)] = root(j)

    groups: dict[int, set[tuple[str, ...]]] = {}
    for i, signature in enumerate(signatures):
        groups.setdefault(root(i), set()).add(signature)
    return list(groups.values())
