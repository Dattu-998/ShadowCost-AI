"""Shadow-mode comparison: did the agent do what the human actually did?

An agent in shadow mode produces an output for each case but never acts on it.
Once the human handles the same case, the two outputs are compared field by
field. The resulting agree/disagree record is the evidence the autonomy ladder
(see ``autonomy.py``) uses to decide whether the agent earns more trust.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Comparison:
    field_matches: dict[str, bool]

    @property
    def score(self) -> float:
        """Fraction of compared fields that matched (1.0 when nothing was compared)."""
        if not self.field_matches:
            return 1.0
        return sum(self.field_matches.values()) / len(self.field_matches)

    @property
    def agrees(self) -> bool:
        """A case counts as agreement only if every compared field matched."""
        return all(self.field_matches.values())

    @property
    def mismatched_fields(self) -> list[str]:
        return [name for name, ok in self.field_matches.items() if not ok]


def values_match(agent: Any, human: Any, rel_tol: float = 1e-6, abs_tol: float = 0.005) -> bool:
    """Compare two values the way a person reviewing the work would.

    Numbers match within tolerance (so 19.999999 == 20.0 and cent rounding is
    ignored), strings match after trimming and case-folding, and missing values
    (None, empty string, NaN) are treated as equivalent to each other.
    """
    if _is_missing(agent) or _is_missing(human):
        return _is_missing(agent) and _is_missing(human)
    if _is_number(agent) and _is_number(human):
        return math.isclose(float(agent), float(human), rel_tol=rel_tol, abs_tol=abs_tol)
    if isinstance(agent, str) and isinstance(human, str):
        return agent.strip().casefold() == human.strip().casefold()
    if isinstance(agent, bool) != isinstance(human, bool):
        return False  # a "yes/no" field should not match the number 1 or 0
    return agent == human


def compare(
    agent_output: Mapping[str, Any],
    human_output: Mapping[str, Any],
    fields: Iterable[str] | None = None,
) -> Comparison:
    """Compare an agent's output with the human's on ``fields``.

    When ``fields`` is omitted, every field present in either output is compared,
    so a field the agent invented or forgot counts as a mismatch.
    """
    names = list(fields) if fields is not None else sorted(set(agent_output) | set(human_output))
    return Comparison(
        field_matches={
            name: values_match(agent_output.get(name), human_output.get(name)) for name in names
        }
    )


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return isinstance(value, float) and math.isnan(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
