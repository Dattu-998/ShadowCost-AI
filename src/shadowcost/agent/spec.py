"""Agent specs: what an agent does, written as data rather than code.

A spec has one trigger and an ordered list of rules. When the trigger fires
for a case (a spreadsheet row), the first rule whose conditions all hold
decides what the agent does: which cells it sets and which email it sends.

    {
      "workflow_id": "W3",
      "name": "Chase overdue invoices",
      "summary": "...",
      "series": "invoices",
      "trigger": {"kind": "schedule", "weekdays": [0, 3]},
      "rules": [
        {
          "name": "first reminder",
          "when": [
            {"column": "status", "op": "in", "value": ["sent", "overdue"]},
            {"column": "reminders_sent", "op": "eq", "value": "0"},
            {"column": "due_date", "op": "days_since_at_least", "value": 7}
          ],
          "set": {"reminders_sent": "{{row.reminders_sent + 1}}",
                  "last_reminder_date": "{{today}}"},
          "email": {"to": "{{row.customer_email}}", "subject": "...", "body": "..."}
        }
      ]
    }

Trigger kinds: ``schedule`` (``weekdays``, 0 = Monday) checks every row on
those days; ``event`` (``activity``, e.g. "bank.credit") checks the case each
such event is linked to, with the event's fields available as ``event.*``;
``new_row`` checks rows added to ``series`` that day.

Condition columns name a spreadsheet column, or ``event.<field>``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from shadowcost.agent.expr import ExpressionError, check, template_problems, to_date, to_number
from shadowcost.shadow import values_match

TRIGGER_KINDS = {"schedule", "event", "new_row"}
VALUE_OPS = {"eq", "ne", "in", "not_in", "contains", "not_contains", "at_least", "at_most"}
DAY_OPS = {"days_since_at_least", "days_since_at_most"}
EMPTY_OPS = {"empty", "not_empty"}
OPS = VALUE_OPS | DAY_OPS | EMPTY_OPS


class SpecError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Condition:
    column: str
    op: str
    value: Any = None

    def holds(self, row: dict, event: dict, today) -> bool:
        if self.column.startswith("event."):
            raw = event.get(self.column[6:], "")
        else:
            raw = row.get(self.column, "")
        cell = "" if raw is None else str(raw)
        op, value = self.op, self.value
        try:
            if op == "empty":
                return cell == ""
            if op == "not_empty":
                return cell != ""
            if op in DAY_OPS:
                if not cell:
                    return False
                days = (to_date(today) - to_date(cell)).days
                return days >= value if op == "days_since_at_least" else days <= value
            if op in {"at_least", "at_most"}:
                number = to_number(cell)
                return number >= value if op == "at_least" else number <= value
        except ExpressionError:
            return False
        if op == "eq":
            return values_match(_number_or_text(cell), _number_or_text(value))
        if op == "ne":
            return not values_match(_number_or_text(cell), _number_or_text(value))
        if op in {"in", "not_in"}:
            found = any(values_match(_number_or_text(cell), _number_or_text(v)) for v in value)
            return found if op == "in" else not found
        if op in {"contains", "not_contains"}:
            found = str(value).casefold() in cell.casefold()
            return found if op == "contains" else not found
        raise SpecError([f"unknown op {op!r}"])


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


@dataclass(frozen=True)
class Rule:
    name: str
    when: tuple[Condition, ...]
    set: dict[str, str]
    email: Email | None


@dataclass(frozen=True)
class Trigger:
    kind: str
    weekdays: tuple[int, ...] = ()
    activity: str = ""


@dataclass(frozen=True)
class AgentSpec:
    workflow_id: str
    name: str
    summary: str
    series: str
    trigger: Trigger
    rules: tuple[Rule, ...]
    source: dict = field(default_factory=dict)  # how it was made: model, data period, ...

    @property
    def target_columns(self) -> set[str]:
        return {column for rule in self.rules for column in rule.set}

    def to_dict(self) -> dict:
        trigger: dict[str, Any] = {"kind": self.trigger.kind}
        if self.trigger.weekdays:
            trigger["weekdays"] = list(self.trigger.weekdays)
        if self.trigger.activity:
            trigger["activity"] = self.trigger.activity
        rules = []
        for rule in self.rules:
            entry: dict[str, Any] = {
                "name": rule.name,
                "when": [
                    {"column": c.column, "op": c.op}
                    | ({"value": c.value} if c.value is not None else {})
                    for c in rule.when
                ],
                "set": dict(rule.set),
            }
            if rule.email:
                entry["email"] = asdict(rule.email)
            rules.append(entry)
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "summary": self.summary,
            "series": self.series,
            "trigger": trigger,
            "rules": rules,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict, columns: set[str] | None = None) -> AgentSpec:
        """Build and validate a spec; raise ``SpecError`` listing every problem found."""
        problems: list[str] = []
        if not isinstance(data, dict):
            raise SpecError(["spec must be a JSON object"])

        raw_trigger = data.get("trigger") or {}
        kind = raw_trigger.get("kind")
        if kind not in TRIGGER_KINDS:
            problems.append(f"trigger.kind must be one of {sorted(TRIGGER_KINDS)}, got {kind!r}")
        weekdays = tuple(int(d) for d in raw_trigger.get("weekdays") or ())
        if kind == "schedule" and not weekdays:
            problems.append("a schedule trigger needs weekdays (0 = Monday)")
        if any(not 0 <= d <= 6 for d in weekdays):
            problems.append("weekdays must be between 0 and 6")
        activity = str(raw_trigger.get("activity") or "")
        if kind == "event" and not activity:
            problems.append("an event trigger needs an activity, e.g. 'bank.credit'")

        rules = []
        raw_rules = data.get("rules")
        if not isinstance(raw_rules, list) or not raw_rules:
            problems.append("rules must be a non-empty list")
            raw_rules = []
        for i, raw in enumerate(raw_rules, start=1):
            label = f"rule {i} ({raw.get('name', '?')})" if isinstance(raw, dict) else f"rule {i}"
            if not isinstance(raw, dict):
                problems.append(f"{label} must be an object")
                continue
            conditions = []
            for c in raw.get("when") or []:
                column, op = c.get("column", ""), c.get("op", "")
                if op not in OPS:
                    problems.append(f"{label}: unknown op {op!r}; use one of {sorted(OPS)}")
                    continue
                if (
                    columns is not None
                    and not column.startswith("event.")
                    and column not in columns
                ):
                    problems.append(f"{label}: unknown column {column!r}")
                value = c.get("value")
                if op in DAY_OPS | {"at_least", "at_most"}:
                    try:
                        value = to_number(value)
                    except ExpressionError:
                        problems.append(f"{label}: {op} needs a number, got {value!r}")
                elif op in {"in", "not_in"} and not isinstance(value, list):
                    problems.append(f"{label}: {op} needs a list value")
                elif op in EMPTY_OPS:
                    value = None
                conditions.append(Condition(column, op, value))

            updates = raw.get("set") or {}
            if not isinstance(updates, dict):
                problems.append(f"{label}: set must be an object of column -> value")
                updates = {}
            for column, value in updates.items():
                if columns is not None and column not in columns:
                    problems.append(f"{label}: set names unknown column {column!r}")
                problems += [f"{label}: {p}" for p in template_problems(str(value), columns)]

            email = None
            if raw.get("email"):
                e = raw["email"]
                missing = [k for k in ("to", "subject", "body") if not e.get(k)]
                if missing:
                    problems.append(f"{label}: email is missing {', '.join(missing)}")
                else:
                    email = Email(str(e["to"]), str(e["subject"]), str(e["body"]))
                    for part in (email.to, email.subject, email.body):
                        problems += [f"{label}: {p}" for p in template_problems(part, columns)]
            if not updates and email is None:
                problems.append(f"{label} does nothing: give it 'set' and/or 'email'")
            rules.append(
                Rule(str(raw.get("name") or f"rule {i}"), tuple(conditions), dict(updates), email)
            )

        for key in ("name", "series"):
            if not data.get(key):
                problems.append(f"{key} is required")
        if problems:
            raise SpecError(problems)
        return cls(
            workflow_id=str(data.get("workflow_id", "")),
            name=str(data["name"]),
            summary=str(data.get("summary", "")),
            series=str(data["series"]),
            trigger=Trigger(kind, weekdays, activity),
            rules=tuple(rules),
            source=dict(data.get("source") or {}),
        )


def _number_or_text(value: Any) -> Any:
    try:
        return to_number(value)
    except ExpressionError:
        return "" if value is None else str(value)


__all__ = ["AgentSpec", "Condition", "Email", "Rule", "SpecError", "Trigger", "check"]
