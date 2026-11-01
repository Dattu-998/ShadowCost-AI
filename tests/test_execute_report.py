import email
import json
from datetime import timedelta

import pandas as pd
import pytest
from test_agent import INVOICE_EMAIL, RECORD_PAYMENT

from shadowcost.agent.__main__ import main as agent_cli
from shadowcost.agent.spec import AgentSpec
from shadowcost.agent.store import Store
from shadowcost.autonomy import Stage
from shadowcost.execute import apply_approved, execute_day, mailbox_owner
from shadowcost.ingest import ingest_folder
from shadowcost.report import build_report
from shadowcost.synth import Config, simulate, write_dataset


@pytest.fixture(scope="module")
def company(tmp_path_factory):
    root = tmp_path_factory.mktemp("company")
    write_dataset(simulate(Config(seed=1, days=200)), root)
    events = ingest_folder(root).events
    start = events["timestamp"].min().date()
    return root, events, start + timedelta(days=80)


def _busy_day(events, activity, after):
    """The first day after ``after`` with an event of this kind."""
    days = events.loc[events["activity"] == activity, "timestamp"].dt.date
    return min(d for d in days if d > after)


@pytest.fixture
def ctx(company, tmp_path):
    root, events, split = company
    return (
        root,
        events,
        split,
        tmp_path / "ws",
        Store(tmp_path / "db.sqlite"),
        mailbox_owner(events),
    )


def test_shadow_stage_only_logs(ctx):
    _, events, split, ws, store, sender = ctx
    day = _busy_day(events, "invoices.add", split)
    run = execute_day(
        AgentSpec.from_dict(INVOICE_EMAIL), Stage.SHADOW, day, events, ws, store, sender
    )
    assert run.proposals and not ws.exists()


def test_draft_stage_writes_reviewable_drafts(ctx):
    _, events, split, ws, store, sender = ctx
    day = _busy_day(events, "invoices.add", split)
    run = execute_day(
        AgentSpec.from_dict(INVOICE_EMAIL), Stage.DRAFT, day, events, ws, store, sender
    )
    assert len(run.drafts) == len(run.proposals) > 0
    message = email.message_from_bytes(run.drafts[0].read_bytes())
    assert message["From"] == "accounts@fernhill.example"
    assert message["Subject"].startswith("Invoice INV-")
    assert not (ws / "outbox" / "ready").exists()  # nothing is ready to send


def test_draft_stage_suggests_cell_changes(ctx):
    _, events, split, ws, store, sender = ctx
    day = _busy_day(events, "bank.credit", split)
    run = execute_day(
        AgentSpec.from_dict(RECORD_PAYMENT), Stage.DRAFT, day, events, ws, store, sender
    )
    suggestions = pd.read_csv(run.suggestions, dtype=str)
    assert set(suggestions["column"]) == {"status", "paid_date"}
    assert run.sheet is None


def test_approval_stage_queues_and_applies_only_approved(ctx):
    _, events, split, ws, store, sender = ctx
    spec = AgentSpec.from_dict(RECORD_PAYMENT)
    day = _busy_day(events, "bank.credit", split)
    run = execute_day(spec, Stage.APPROVAL, day, events, ws, store, sender)
    assert run.queued and run.sheet is None

    store.decide(run.queued[0], True, "tester")
    for action_id in run.queued[1:]:
        store.decide(action_id, False, "tester")
    with pytest.raises(ValueError):
        store.decide(run.queued[0], False, "tester")  # can't change a decision

    applied = apply_approved(spec, events, ws, store, sender)
    sheet = pd.read_csv(applied[0].sheet, dtype=str, keep_default_na=False).set_index("invoice_id")
    approved_case = run.proposals[0].case_id
    assert sheet.loc[approved_case, "status"] == "paid"
    for p in run.proposals[1:]:
        assert sheet.loc[p.case_id, "status"] != "paid"
    assert apply_approved(spec, events, ws, store, sender) == []  # applied only once


def test_autonomous_stage_writes_new_files_only(ctx):
    root, events, split, ws, store, sender = ctx
    before = sorted(p.name for p in (root / "ledger").iterdir())
    day = _busy_day(events, "invoices.add", split)
    run = execute_day(
        AgentSpec.from_dict(INVOICE_EMAIL), Stage.AUTONOMOUS, day, events, ws, store, sender
    )
    assert run.ready and all(p.parent == ws / "outbox" / "ready" for p in run.ready)
    assert sorted(p.name for p in (root / "ledger").iterdir()) == before


def test_cli_execute_requires_approval(company, tmp_path):
    root, events, split = company
    path = tmp_path / "W1.json"
    path.write_text(json.dumps(INVOICE_EMAIL))
    day = _busy_day(events, "invoices.add", split).isoformat()
    args = ["execute", str(path), str(root), "--day", day, "--db", str(tmp_path / "db"),
            "--workspace", str(tmp_path / "ws"), "--stage", "draft"]  # fmt: skip
    assert agent_cli(args) == 2
    agent_cli(["approve", str(path), "--by", "tester", "--db", str(tmp_path / "db")])
    assert agent_cli(args) == 0


def test_report_shows_estimated_and_measured_savings(company):
    root, _, split = company
    evidence_end = (split - timedelta(days=1)).isoformat()
    specs = [
        (AgentSpec.from_dict(s | {"source": {"evidence_period": ["", evidence_end]}}), {})
        for s in (INVOICE_EMAIL, RECORD_PAYMENT)
    ]
    report = build_report(root, specs)
    text = report.markdown()
    assert "Measured against the minutes the person actually spent" in text
    assert "| W1 | Send invoice |" in text and "autonomous" in text
    assert "Minutes per step (estimates)" in text
    html = report.html()
    assert html.startswith("<!doctype html>") and "<table>" in html
    assert "<script" not in html  # values are escaped, nothing executable
