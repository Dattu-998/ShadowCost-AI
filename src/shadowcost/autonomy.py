"""Autonomy ladder: agents earn trust in stages from shadow-mode evidence.

Every agent starts in SHADOW. It moves up one stage at a time once it has
handled enough cases at its current stage and the Wilson lower bound of its
agreement rate clears the promotion bar. Using the lower bound rather than the
raw rate means a lucky 10/10 does not promote an agent; it has to show
agreement over enough cases to be statistically convincing.

Agents also move down: a drop in recent agreement demotes one stage, and a
critical failure (for example, an action a human had to reverse) sends the
agent straight back to SHADOW.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum


class Stage(IntEnum):
    SHADOW = 0  # runs silently; output is compared with what the human did
    DRAFT = 1  # output is shown to the human as a draft
    APPROVAL = 2  # acts once a human approves each case
    AUTONOMOUS = 3  # acts alone; outcomes are still audited


STAGES_ORDER = [stage.name.lower() for stage in Stage]


@dataclass(frozen=True)
class PromotionPolicy:
    min_cases: int = 30  # cases needed at the current stage before promotion is considered
    promote_lower_bound: float = 0.85  # Wilson lower bound of agreement needed to move up
    demote_below: float = 0.75  # recent agreement rate that triggers a one-stage demotion
    min_cases_to_demote: int = 10  # avoid demoting on a handful of unlucky cases
    window: int = 50  # only the most recent cases count toward a decision
    z: float = 1.96  # ~95% confidence


DEFAULT_POLICY = PromotionPolicy()


@dataclass(frozen=True)
class Decision:
    current: Stage
    next: Stage
    action: str  # "promote", "demote" or "hold"
    reason: str
    n: int
    agreement: float
    lower_bound: float


def wilson_lower_bound(successes: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for a binomial proportion."""
    if n == 0:
        return 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / denom


def evaluate(
    stage: Stage,
    outcomes: Sequence[bool],
    policy: PromotionPolicy = DEFAULT_POLICY,
    critical_failure: bool = False,
) -> Decision:
    """Decide whether an agent at ``stage`` should be promoted, demoted or held.

    ``outcomes`` are the agree/disagree results of cases handled at the current
    stage, oldest first. Callers reset them after each stage change so evidence
    from one stage never carries into the next.
    """
    recent = list(outcomes)[-policy.window :]
    n = len(recent)
    agreement = sum(recent) / n if n else 0.0
    lower = wilson_lower_bound(sum(recent), n, policy.z)

    def decide(action: str, nxt: Stage, reason: str) -> Decision:
        return Decision(stage, nxt, action, reason, n, agreement, lower)

    if critical_failure:
        if stage == Stage.SHADOW:
            return decide("hold", stage, "critical failure while already in shadow")
        return decide("demote", Stage.SHADOW, "critical failure: back to shadow")

    if stage > Stage.SHADOW and n >= policy.min_cases_to_demote and agreement < policy.demote_below:
        return decide(
            "demote",
            Stage(stage - 1),
            f"recent agreement {agreement:.0%} is below {policy.demote_below:.0%}",
        )

    if stage == Stage.AUTONOMOUS:
        return decide("hold", stage, "already autonomous")

    if n < policy.min_cases:
        return decide("hold", stage, f"needs {policy.min_cases - n} more cases at this stage")

    if lower >= policy.promote_lower_bound:
        return decide(
            "promote",
            Stage(stage + 1),
            f"agreement lower bound {lower:.3f} clears {policy.promote_lower_bound:.2f}",
        )

    return decide(
        "hold",
        stage,
        f"agreement lower bound {lower:.3f} is below {policy.promote_lower_bound:.2f}",
    )
