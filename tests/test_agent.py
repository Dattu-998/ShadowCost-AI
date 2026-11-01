import copy
import json
from datetime import date, timedelta

import pytest

from shadowcost.agent.__main__ import main
from shadowcost.agent.backtest import backtest
from shadowcost.agent.expr import ExpressionError, check, evaluate, render
from shadowcost.agent.generate import generate_spec
from shadowcost.agent.runtime import propose_day
from shadowcost.agent.shadow_mode import run_shadow
from shadowcost.agent.spec import AgentSpec, Condition, SpecError
from shadowcost.agent.store import Store, spec_id
from shadowcost.autonomy import Stage
from shadowcost.discover import discover
from shadowcost.discover.episodes import RowHistory
from shadowcost.ingest import ingest_folder
from shadowcost.llm import ChatClient, InvalidJSONError, parse_json_object
from shadowcost.synth import Config, simulate, write_dataset

TRAIN_DAYS = 80

INVOICE_EMAIL = {
    "workflow_id": "W1",
    "name": "Send invoice",
    "series": "invoices",
    "trigger": {"kind": "new_row"},
    "rules": [
        {
            "name": "email invoice",
            "when": [],
            "email": {
                "to": "{{row.customer_email}}",
                "subject": "Invoice {{row.invoice_id}}",
                "body": "Invoice {{row.invoice_id}} for {{money(row.amount)}} is due "
                "{{format_date(row.due_date)}}.",
            },
        }
    ],
}
RECORD_PAYMENT = {
    "workflow_id": "W2",
    "name": "Record payments",
    "series": "invoices",
    "trigger": {"kind": "event", "activity": "bank.credit"},
    "rules": [
        {
            "name": "mark paid",
            "when": [{"column": "status", "op": "ne", "value": "paid"}],
            "set": {"status": "paid", "paid_date": "{{event.date}}"},
        }
    ],
}


@pytest.fixture(scope="module")
def company(tmp_path_factory):
    root = tmp_path_factory.mktemp("company")
    write_dataset(simulate(Config(seed=1, days=220)), root)
    events = ingest_folder(root).events
    start = events["timestamp"].min().date()
    return root, events, start + timedelta(days=TRAIN_DAYS), events["timestamp"].max().date()


# --- expressions ----------------------------------------------------------------------------


CONTEXT = {
    "row": {"amount": "1318.5", "n": "0", "due": "2026-01-21"},
    "event": {},
    "today": "2026-02-01",
}


def test_expressions_evaluate_text_cells_as_numbers_and_dates():
    assert evaluate("row.n + 1", CONTEXT) == 1
    assert evaluate("days_since(row.due)", CONTEXT) == 11
    assert render("{{money(row.amount)}} due {{format_date(row.due)}}", CONTEXT) == (
        "$1,318.50 due 21 Jan 2026"
    )
    assert render("{{row.n + 1}}", CONTEXT) == 1  # a whole-expression template keeps its type


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "row.__class__",
        "(lambda: 1)()",
        "[x for x in row]",
        "open('secrets.txt')",
        "money.__globals__",
        "money(row.amount, key=1)",
    ],
)
def test_expressions_reject_anything_outside_the_whitelist(expression):
    assert check(expression)
    with pytest.raises(ExpressionError):
        evaluate(expression, CONTEXT)


# --- specs ---------------------------------------------------------------------------------


def test_spec_validation_lists_every_problem():
    bad = copy.deepcopy(RECORD_PAYMENT)
    bad["trigger"] = {"kind": "event"}
    bad["rules"][0]["when"].append({"column": "colour", "op": "looks_like", "value": "red"})
    bad["rules"][0]["set"]["paid_date"] = "{{row.nope + 1}}"
    with pytest.raises(SpecError) as err:
        AgentSpec.from_dict(bad, columns={"status", "paid_date"})
    text = str(err.value)
    assert "needs an activity" in text
    assert "unknown op 'looks_like'" in text
    assert "unknown column 'nope'" in text


def test_spec_round_trips_through_json():
    spec = AgentSpec.from_dict(RECORD_PAYMENT)
    assert AgentSpec.from_dict(json.loads(json.dumps(spec.to_dict()))) == spec


@pytest.mark.parametrize(
    ("condition", "row", "expected"),
    [
        (Condition("n", "eq", "0"), {"n": "0"}, True),
        (Condition("n", "eq", 0), {"n": "0.0"}, True),
        (Condition("status", "in", ["sent", "overdue"]), {"status": "Overdue"}, True),
        (Condition("due", "days_since_at_least", 7), {"due": "2026-01-25"}, True),
        (Condition("due", "days_since_at_least", 7), {"due": "2026-01-26"}, False),
        (Condition("due", "days_since_at_least", 7), {"due": ""}, False),
        (Condition("notes", "not_contains", "promised"), {"notes": "Promised by Fri"}, False),
        (Condition("notes", "empty"), {"notes": ""}, True),
    ],
)
def test_conditions(condition, row, expected):
    assert condition.holds(row, {}, date(2026, 2, 1)) is expected


# --- runtime and backtest ------------------------------------------------------------------


def test_agent_never_sees_the_future(company):
    _, events, split, _ = company
    day = split + timedelta(days=(7 - split.weekday()) % 7)  # a Monday
    past = events[events["timestamp"].dt.date < day]
    assert RowHistory(events).before(day) == RowHistory(past).before(day)
    spec = AgentSpec.from_dict(RECORD_PAYMENT)
    today = events[events["timestamp"].dt.date == day]
    assert propose_day(spec, day, RowHistory(events).before(day), today) == propose_day(
        spec, day, RowHistory(past).before(day), today
    )


def test_backtest_of_a_correct_spec(company):
    _, events, split, end = company
    result = backtest(AgentSpec.from_dict(INVOICE_EMAIL), events, split, end)
    m = result.metrics()
    assert m["agreement"] == 1.0 and m["outcomes"] > 50


def test_backtest_counts_disagreements_and_timing(company):
    _, events, split, end = company
    m = backtest(AgentSpec.from_dict(RECORD_PAYMENT), events, split, end).metrics()
    assert 0.75 <= m["agreement"] < 1.0  # the person sometimes uses the recording date
    assert m["action_recall"] >= 0.95
    assert m["median_days_ahead_of_human"] >= 0  # the person records payments late


def test_an_unneeded_email_shows_up_as_mismatches(company):
    _, events, split, end = company
    noisy = copy.deepcopy(RECORD_PAYMENT)
    noisy["rules"][0]["email"] = {
        "to": "{{row.customer_email}}",
        "subject": "Thanks",
        "body": "Paid.",
    }
    m = backtest(AgentSpec.from_dict(noisy), events, split, end).metrics()
    assert m["field_agreement"]["email"] < 0.2


# --- generation with a fake LLM ------------------------------------------------------------


class FakeLLM:
    model = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def complete_json(self, messages, temperature=0.0):
        self.requests.append(copy.deepcopy(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return copy.deepcopy(reply)


@pytest.fixture(scope="module")
def payment_workflow(company):
    _, events, split, _ = company
    discovery = discover(events[events["timestamp"].dt.date < split])
    workflow = next(w for w in discovery.workflows if w.trigger.kind == "event")
    return discovery, workflow


def test_generation_feeds_validation_errors_back(payment_workflow):
    discovery, workflow = payment_workflow
    broken = copy.deepcopy(RECORD_PAYMENT)
    broken["rules"][0]["set"]["colour"] = "red"
    llm = FakeLLM([InvalidJSONError("bad"), broken, RECORD_PAYMENT])
    generation = generate_spec(discovery, workflow, llm)
    assert generation.spec is not None and generation.attempts == 3
    assert "not valid JSON" in llm.requests[1][-1]["content"]
    assert "unknown column 'colour'" in llm.requests[2][-1]["content"]
    assert generation.spec.source["generated_by"] == "fake"


def test_generation_revises_low_agreement_and_keeps_the_best(payment_workflow):
    discovery, workflow = payment_workflow
    noisy = copy.deepcopy(RECORD_PAYMENT)
    noisy["rules"][0]["email"] = {
        "to": "{{row.customer_email}}",
        "subject": "Thanks",
        "body": "Paid.",
    }
    llm = FakeLLM([noisy, RECORD_PAYMENT])
    generation = generate_spec(discovery, workflow, llm, max_attempts=2)
    assert "both acted but these fields differed" in llm.requests[1][-1]["content"]
    assert generation.spec.rules[0].email is None  # the better second draft won
    assert generation.evidence_backtest.metrics()["agreement"] >= 0.85


def test_evidence_never_includes_held_out_days(payment_workflow):
    discovery, workflow = payment_workflow
    llm = FakeLLM([RECORD_PAYMENT])
    generation = generate_spec(discovery, workflow, llm)
    last_training_day = discovery.events["timestamp"].max().date()
    assert generation.spec.source["evidence_period"][1] == last_training_day.isoformat()
    sent = json.dumps(llm.requests[0])
    later = last_training_day + timedelta(days=1)
    assert later.isoformat() not in sent


# --- shadow mode, store and CLI ------------------------------------------------------------


def test_a_reliable_agent_climbs_the_ladder(company):
    _, events, split, end = company
    run = run_shadow(AgentSpec.from_dict(INVOICE_EMAIL), events, split, end, minutes_per_case=7)
    assert [c.decision.next for c in run.changes] == [Stage.DRAFT, Stage.APPROVAL, Stage.AUTONOMOUS]
    assert run.final_stage == Stage.AUTONOMOUS
    assert 0 < run.minutes_saved() < 7 * len(run.outcomes)


def test_a_critical_failure_sends_the_agent_back_to_shadow(company):
    _, events, split, end = company
    calls = []

    def fail_once_autonomous(outcome, stage):
        calls.append(stage)
        return stage == Stage.AUTONOMOUS and calls.count(Stage.AUTONOMOUS) == 1

    run = run_shadow(
        AgentSpec.from_dict(INVOICE_EMAIL), events, split, end, 7, is_critical=fail_once_autonomous
    )
    actions = [(c.decision.action, c.decision.next) for c in run.changes]
    assert ("demote", Stage.SHADOW) in actions
    assert len(run.critical_failures) == 1


def test_store_ties_approval_to_the_exact_spec(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    spec = AgentSpec.from_dict(RECORD_PAYMENT)
    assert store.approval(spec) is None
    store.approve(spec, "tester")
    assert store.approval(spec)[0] == "tester"
    edited = copy.deepcopy(RECORD_PAYMENT)
    edited["rules"][0]["set"]["status"] = "PAID"
    assert spec_id(AgentSpec.from_dict(edited)) != spec_id(spec)
    assert store.approval(AgentSpec.from_dict(edited)) is None


def test_cli_requires_approval_before_shadow_mode(company, tmp_path, capsys):
    root, _, split, _ = company
    path = tmp_path / "W1.json"
    data = INVOICE_EMAIL | {
        "source": {"evidence_period": ["2026-01-05", (split - timedelta(days=1)).isoformat()]},
        "evaluation": {"minutes_per_case": 7},
    }
    path.write_text(json.dumps(data))
    db = tmp_path / "db.sqlite"
    assert main(["shadow", str(path), str(root), "--db", str(db)]) == 2
    assert main(["approve", str(path), "--by", "tester", "--db", str(db)]) == 0
    assert main(["shadow", str(path), str(root), "--db", str(db)]) == 0
    assert "final stage AUTONOMOUS" in capsys.readouterr().out


# --- LLM client ----------------------------------------------------------------------------


def test_json_replies_may_be_fenced():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(InvalidJSONError):
        parse_json_object("[1, 2]")


def test_cached_responses_need_no_network(tmp_path, monkeypatch):
    client = ChatClient(model="m", api_key=None, cache_dir=tmp_path)
    messages = [{"role": "user", "content": "hi"}]
    body = {
        "model": "m",
        "messages": messages,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    client._cache_file(body).write_text(json.dumps({"parsed": {"cached": True}}))
    monkeypatch.setattr(client, "_post", lambda body: pytest.fail("network used"))
    assert client.complete_json(messages) == {"cached": True}
