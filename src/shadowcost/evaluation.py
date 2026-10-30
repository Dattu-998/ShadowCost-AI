"""Score discovery against a synthetic dataset's ground truth.

Discovery and recommendation never see ``ground_truth/``. This module is the
only code that reads it, and only to grade their output:

- each discovered workflow is labelled with the ground-truth workflow most of
  its episodes belong to, and its purity is the share that do;
- recall: the share of repetitive ground-truth workflows found by at least one
  pure (>= 80%) discovered workflow; precision: the share of discovered
  workflows that are pure and repetitive;
- coverage: the share of each repetitive workflow's instances (case, day)
  that discovery found;
- time: estimated hours against the true minutes logged in the ground truth;
- templates: homogeneity and completeness of email templates against the
  true step that produced each email.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sklearn.metrics import homogeneity_completeness_v_measure

from shadowcost.discover import Discovery
from shadowcost.recommend import Recommendation

MIN_PURITY = 0.8


@dataclass
class WorkflowScore:
    workflow_id: str
    name: str
    size: int
    label: str  # the ground-truth workflow most of its episodes belong to
    purity: float


@dataclass
class TimeScore:
    workflow: str  # ground-truth workflow
    true_hours: float
    estimated_hours: float  # from per-step assumptions, over the instances found
    observed_upper_hours: float | None  # from email gaps


@dataclass
class Evaluation:
    workflows: list[WorkflowScore]
    irregular: list[WorkflowScore]
    recall: float
    precision: float
    coverage: dict[str, float]
    time: list[TimeScore]
    template_homogeneity: float
    template_completeness: float

    def summary(self) -> str:
        lines = [
            "Evaluation against ground truth",
            f"  workflow recall {self.recall:.2f}, precision {self.precision:.2f}",
            f"  email templates: homogeneity {self.template_homogeneity:.3f}, "
            f"completeness {self.template_completeness:.3f}",
        ]
        for s in self.workflows + self.irregular:
            lines.append(f"  {s.workflow_id} -> {s.label} (purity {s.purity:.2f}, n={s.size})")
        for name, share in self.coverage.items():
            lines.append(f"  coverage of {name}: {share:.1%}")
        for t in self.time:
            observed = f"{t.observed_upper_hours:.1f}" if t.observed_upper_hours else "n/a"
            lines.append(
                f"  hours for {t.workflow}: true {t.true_hours:.1f}, estimated "
                f"{t.estimated_hours:.1f}, observed upper bound {observed}"
            )
        return "\n".join(lines)


def evaluate(
    discovery: Discovery, recommendations: list[Recommendation], ground_truth: str | Path
) -> Evaluation:
    ground_truth = Path(ground_truth)
    actions = pd.read_csv(ground_truth / "actions.csv", dtype=str, na_filter=False)
    actions["minutes"] = actions["minutes"].astype(float)
    actions["day"] = pd.to_datetime(actions["timestamp"]).dt.date
    definitions = json.loads((ground_truth / "workflows.json").read_text(encoding="utf-8"))
    repetitive = [d["name"] for d in definitions if d["repetitive"]]

    by_message = {
        row.artifact: row.workflow
        for row in actions.itertuples()
        if row.artifact.startswith("msg-")
    }
    by_cell: dict[tuple, Counter] = defaultdict(Counter)
    for row in actions[actions["artifact"] == "ledger"].itertuples():
        by_cell[(row.day, row.case_id)][row.workflow] += 1

    events = discovery.events.set_index("event_id")

    def episode_label(event_ids: list[str]) -> str:
        votes: Counter = Counter()
        for event_id in event_ids:
            event = events.loc[event_id]
            if event["source"] == "email":
                if event["object_id"] in by_message:
                    votes[by_message[event["object_id"]]] += 1
            else:
                votes.update(by_cell.get((event["timestamp"].date(), event["case_id"]), {}))
        return votes.most_common(1)[0][0] if votes else "unknown"

    label_of = {
        row.episode_id: episode_label(row.event_ids) for row in discovery.episodes.itertuples()
    }

    def score(workflow) -> WorkflowScore:
        votes = Counter(label_of[e] for e in workflow.episode_ids)
        label, count = votes.most_common(1)[0]
        return WorkflowScore(
            workflow.workflow_id,
            workflow.name,
            workflow.size,
            label,
            round(count / workflow.size, 3),
        )

    scores = [score(w) for w in discovery.workflows]
    pure = [s for s in scores if s.purity >= MIN_PURITY and s.label in repetitive]
    found = {s.label for s in pure}

    episodes = discovery.episodes.set_index("episode_id")
    coverage = {}
    for name in repetitive:
        truth = set(
            zip(
                *(actions.loc[actions["workflow"] == name, c] for c in ("case_id", "day")),
                strict=True,
            )
        )
        mine = {
            (episodes.at[e, "case_id"], episodes.at[e, "day"])
            for w, s in zip(discovery.workflows, scores, strict=True)
            if s.label == name
            for e in w.episode_ids
        }
        coverage[name] = round(len(truth & mine) / len(truth), 3) if truth else 0.0

    time = []
    for name in repetitive:
        matched = [
            r for r in recommendations
            if next(s for s in scores if s.workflow_id == r.workflow.workflow_id).label == name
        ]  # fmt: skip
        observed = [r.observed_minutes * r.workflow.size for r in matched if r.observed_minutes]
        time.append(
            TimeScore(
                name,
                round(actions.loc[actions["workflow"] == name, "minutes"].sum() / 60, 2),
                round(sum(r.minutes_per_instance * r.workflow.size for r in matched) / 60, 2),
                round(sum(observed) / 60, 2) if observed else None,
            )
        )

    sent = discovery.events[discovery.events["activity"] == "email.sent"]
    step_of = dict(zip(actions["artifact"], actions["step"], strict=True))
    truth_steps = [step_of.get(o, "unknown") for o in sent["object_id"]]
    templates = [discovery.template_of[o] for o in sent["object_id"]]
    homogeneity, completeness, _ = homogeneity_completeness_v_measure(truth_steps, templates)

    return Evaluation(
        workflows=scores,
        irregular=[score(w) for w in discovery.irregular],
        recall=round(len(found) / len(repetitive), 3),
        precision=round(len(pure) / len(scores), 3) if scores else 0.0,
        coverage=coverage,
        time=time,
        template_homogeneity=round(homogeneity, 3),
        template_completeness=round(completeness, 3),
    )
