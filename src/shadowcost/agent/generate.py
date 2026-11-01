"""Draft an agent spec for a discovered workflow with an LLM.

The LLM gets the workflow's evidence (``evidence.py``) and a description of the
spec format, and answers with a spec as JSON. Each reply then goes through two
checks, and the model is shown what failed and asked to revise:

1. Validation: unknown columns, operators that don't exist, expressions that
   won't parse or that fail on real rows.
2. A backtest on the evidence period (the same data the evidence came from,
   never later data): if agreement with what the human did is below
   ``TARGET_AGREEMENT``, the model sees a summary of the disagreements.

The best valid spec across attempts is kept. It is still only a draft: it has
to pass a backtest on later data and a human's approval before it runs.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

from shadowcost.agent.backtest import BacktestResult, backtest
from shadowcost.agent.evidence import build_evidence
from shadowcost.agent.spec import OPS, AgentSpec, SpecError
from shadowcost.discover import Discovery, Workflow
from shadowcost.llm import InvalidJSONError, JSONChat

MAX_ATTEMPTS = 3
TARGET_AGREEMENT = 0.85
MAX_EXAMPLES_PER_KIND = 3

SYSTEM_PROMPT = f"""You turn evidence about a repeated office workflow into an agent spec.

The agent will do the work a person currently does by hand, so the spec must
reproduce what that person did, as shown by the evidence. Answer with one JSON
object and nothing else, with these keys:

- "name": a short name for the workflow, e.g. "Chase overdue invoices".
- "summary": two sentences on what the agent does and when.
- "series": the spreadsheet name given in the evidence.
- "trigger": one of
    {{"kind": "schedule", "weekdays": [0, 3]}}   (0 = Monday; checks every row on those days)
    {{"kind": "event", "activity": "bank.credit"}} (checks the row each such event is linked to)
    {{"kind": "new_row"}}                          (checks rows added that day)
  Use the trigger kind, weekdays and activity from the evidence.
- "rules": an ordered list. For each row the trigger brings up, the FIRST rule
  whose conditions all hold decides what happens; if none hold, nothing
  happens. Each rule is
    {{"name": "...", "when": [conditions], "set": {{"column": "value"}},
     "email": {{"to": "...", "subject": "...", "body": "..."}}}}
  "set" and "email" are optional, but a rule needs at least one of them.
- "notes": a list of short strings on anything uncertain.

Conditions: {{"column": "<column>", "op": "<op>", "value": ...}}. Ops: {sorted(OPS)}.
"in"/"not_in" take a list; "days_since_at_least"/"days_since_at_most" take a
number of days since the date in that column; "empty"/"not_empty" take no
value; "contains"/"not_contains" test for text. A column can also be
"event.<field>" for event triggers. All cell values are text, e.g. "0", not 0.

Values in "set" and in the email are text with {{{{ expressions }}}}:
  row.<column>, event.<field>, today, numbers, + - *, and the functions
  money(x) -> "$1,234.50", format_date(x) -> "21 Jan 2026", days_since(x),
  add_days(x, n), round(x, n), int(x).
  Examples: "{{{{today}}}}", "{{{{row.reminders_sent + 1}}}}", "{{{{event.date}}}}",
  "Invoice {{{{row.invoice_id}}}} for {{{{money(row.amount)}}}}".
Nothing else is allowed in expressions.

How to read the evidence:
- Each variant is one way the work was done (e.g. a first reminder vs a later
  one). Usually write one rule per variant. Do not write rules for
  "rare_variants_not_to_model": they are one-offs.
- "row_before" shows how the rows looked before the work: categorical values
  and the range of days since each date. Use it to write conditions that pick
  out the same rows, e.g. reminders_sent "0" and due_date at least the minimum
  days_since seen. Add guards so a rule cannot fire on rows already done.
  Keep conditions as loose as the evidence allows: an extra condition that the
  evidence doesn't need makes the agent miss work.
- "changed_columns" lists explanations of each new value with their support;
  follow the best supported one ("equals today" -> "{{{{today}}}}",
  "previous value + 1" -> "{{{{row.col + 1}}}}", "always 'x'" -> "x",
  "equals the trigger event's date" -> "{{{{event.date}}}}").
- Write emails as one reusable template in the company's voice, based on the
  examples, with expressions in place of anything specific to one customer.
  Only add an email to a rule if the variant's steps include email.sent.
- Use only the columns listed in the evidence.
"""


@dataclass
class Generation:
    spec: AgentSpec | None
    attempts: int
    evidence_backtest: BacktestResult | None = None
    problems: list[str] = field(default_factory=list)  # from the last attempt, if it failed
    evidence: dict = field(default_factory=dict)


def generate_spec(
    discovery: Discovery, workflow: Workflow, client: JSONChat, max_attempts: int = MAX_ATTEMPTS
) -> Generation:
    evidence = build_evidence(discovery, workflow)
    columns = set(evidence["columns"])
    period = (
        discovery.events["timestamp"].min().date(),
        discovery.events["timestamp"].max().date(),
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Evidence:\n" + json.dumps(evidence, indent=1, default=str)},
    ]
    best: Generation | None = None
    problems: list[str] = []
    temperature = 0.0
    for attempt in range(1, max_attempts + 1):
        try:
            data = client.complete_json(messages, temperature=temperature)
        except InvalidJSONError:
            # Retrying the same request would fail the same way; nudge it instead.
            problems = ["the reply was not valid JSON"]
            temperature = 0.3
            if attempt < max_attempts:
                messages.append(
                    {
                        "role": "user",
                        "content": "Your reply was not valid JSON. Answer again with one valid "
                        "JSON object; escape newlines in strings as \n.",
                    }
                )
            continue
        data["workflow_id"] = workflow.workflow_id
        data.setdefault("series", evidence["series"])
        data["source"] = {
            "generated_by": client.model,
            "workflow": workflow.name,
            "evidence_period": [period[0].isoformat(), period[1].isoformat()],
            "attempts": attempt,
            "notes": data.pop("notes", []),
        }
        feedback = ""
        try:
            spec = AgentSpec.from_dict(data, columns)
            result = backtest(spec, discovery.events, *period)
            problems = sorted(
                {f"rule {p.rule!r} failed on a real row: {p.error}" for p in result.errors}
            )
        except SpecError as err:
            spec, result, problems = None, None, err.problems

        if problems:
            feedback = "That spec has problems:\n- " + "\n- ".join(problems[:15])
        else:
            agreement = result.metrics()["agreement"]
            if best is None or agreement > best.evidence_backtest.metrics()["agreement"]:
                best = Generation(spec, attempt, result, [], evidence)
            if agreement >= TARGET_AGREEMENT:
                break
            feedback = disagreement_feedback(result)
        if attempt < max_attempts:
            messages += [
                {"role": "assistant", "content": json.dumps(data)},
                {"role": "user", "content": feedback + "\nReturn the full revised spec as JSON."},
            ]
    if best is None:
        return Generation(None, max_attempts, None, problems, evidence)
    best.attempts = attempt
    best.spec.source["attempts"] = attempt
    return best


def disagreement_feedback(result: BacktestResult) -> str:
    """Describe where the spec disagreed with the human on the evidence period."""
    m = result.metrics()
    lines = [
        f"Replayed on the evidence period, the spec agreed with the person on "
        f"{m['agreement']:.0%} of {m['outcomes']} cases: {m['kinds']}.",
        "Revise it to agree more often. Some disagreements are the person's own "
        "inconsistency (late or forgotten work) and cannot be fixed; focus on systematic ones.",
    ]
    by_kind: dict[str, list] = {}
    for o in result.outcomes:
        if o.kind != "match":
            by_kind.setdefault(o.kind, []).append(o)
    explain = {
        "agent_only": "the agent acted but the person did not",
        "human_only": "the person did the work but no rule fired",
        "mismatch": "both acted but these fields differed",
    }
    for kind, outcomes in by_kind.items():
        lines.append(f"\n{len(outcomes)} times {explain[kind]}. Examples:")
        rules = Counter(o.rule for o in outcomes if o.rule)
        if rules:
            lines.append(f"  by rule: {dict(rules)}")
        for o in outcomes[:MAX_EXAMPLES_PER_KIND]:
            detail = {
                "case": o.case_id,
                "agent_day": str(o.agent_day),
                "human_day": str(o.human_day),
            }
            if kind == "mismatch":
                detail["differing_fields"] = [f for f, ok in o.field_matches.items() if not ok]
                detail["agent"] = o.agent
                detail["person"] = o.human
            elif kind == "agent_only":
                detail["agent_did"] = o.agent
            else:
                detail["person_did"] = o.human
            lines.append("  " + json.dumps(detail, default=str))
    return "\n".join(lines)
