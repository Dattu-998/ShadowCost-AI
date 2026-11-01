"""Shadow mode: the agent works alongside the person and earns autonomy.

Every outcome (see ``backtest``) is fed, in the order it becomes known, into
the autonomy ladder. Evidence restarts at each stage, so an agent has to prove
itself again after every promotion. A critical failure sends it straight back
to shadow: by default, the agent emailing a customer on its own (autonomous
stage) when the person would not have.

Time saved is credited only for outcomes where the agent agreed with the
person, at a share that depends on the stage: nothing while in shadow, part of
the work once the person only reviews a draft, most of it when they just
approve, and all of it when the agent acts alone.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from shadowcost.agent.backtest import Outcome, backtest
from shadowcost.agent.spec import AgentSpec
from shadowcost.autonomy import DEFAULT_POLICY, Decision, PromotionPolicy, Stage, evaluate

# Share of the person's time saved on an agreeing case, by stage.
TIME_SAVED_SHARE = {
    Stage.SHADOW: 0.0,  # the person still does everything
    Stage.DRAFT: 0.5,  # the person checks and sends a prepared draft
    Stage.APPROVAL: 0.8,  # the person clicks approve
    Stage.AUTONOMOUS: 1.0,
}


def emailed_customer_unasked(outcome: Outcome, stage: Stage) -> bool:
    return (
        stage == Stage.AUTONOMOUS
        and outcome.kind == "agent_only"
        and bool(outcome.agent.get("email"))
    )


@dataclass(frozen=True)
class StageChange:
    day: date
    decision: Decision


@dataclass
class ShadowRun:
    spec: AgentSpec
    start: date
    end: date
    outcomes: list[tuple[Outcome, Stage]]  # each outcome with the stage the agent was at
    changes: list[StageChange]
    minutes_per_case: float
    final_stage: Stage = Stage.SHADOW
    critical_failures: list[Outcome] = field(default_factory=list)

    def minutes_saved(self) -> float:
        return sum(
            TIME_SAVED_SHARE[stage] * self.minutes_per_case
            for outcome, stage in self.outcomes
            if outcome.agrees
        )

    def by_stage(self) -> dict[Stage, dict]:
        stats: dict[Stage, Counter] = defaultdict(Counter)
        for outcome, stage in self.outcomes:
            stats[stage]["cases"] += 1
            stats[stage]["agree"] += outcome.agrees
        return {
            stage: {"cases": s["cases"], "agreement": round(s["agree"] / s["cases"], 3)}
            for stage, s in sorted(stats.items())
        }

    def summary(self) -> str:
        lines = [
            f"Shadow run of {self.spec.workflow_id} '{self.spec.name}' "
            f"from {self.start} to {self.end}",
            f"  {len(self.outcomes)} cases; final stage {self.final_stage.name}",
        ]
        for change in self.changes:
            d = change.decision
            lines.append(
                f"  {change.day}: {d.action} {d.current.name} -> {d.next.name} "
                f"({d.reason}; n={d.n}, agreement {d.agreement:.0%})"
            )
        for stage, s in self.by_stage().items():
            lines.append(f"  at {stage.name}: {s['cases']} cases, agreement {s['agreement']:.0%}")
        if self.critical_failures:
            lines.append(
                f"  {len(self.critical_failures)} critical failures sent it back to shadow"
            )
        lines.append(
            f"  time saved: {self.minutes_saved() / 60:.1f} h "
            f"(at ~{self.minutes_per_case:g} min per case; shares by stage "
            + ", ".join(f"{s.name.lower()} {v:.0%}" for s, v in TIME_SAVED_SHARE.items())
            + ")"
        )
        return "\n".join(lines)


def run_shadow(
    spec: AgentSpec,
    events: pd.DataFrame,
    start: date,
    end: date,
    minutes_per_case: float,
    policy: PromotionPolicy = DEFAULT_POLICY,
    is_critical: Callable[[Outcome, Stage], bool] = emailed_customer_unasked,
) -> ShadowRun:
    result = backtest(spec, events, start, end)
    stage = Stage.SHADOW
    evidence: list[bool] = []
    run = ShadowRun(spec, start, end, [], [], minutes_per_case)
    for outcome in result.outcomes:  # already ordered by the day each is known
        run.outcomes.append((outcome, stage))
        evidence.append(outcome.agrees)
        critical = is_critical(outcome, stage)
        if critical:
            run.critical_failures.append(outcome)
        decision = evaluate(stage, evidence, policy, critical_failure=critical)
        if decision.action != "hold":
            run.changes.append(StageChange(outcome.resolved_on, decision))
            stage, evidence = decision.next, []
    run.final_stage = stage
    return run
