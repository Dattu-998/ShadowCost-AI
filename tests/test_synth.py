import json
from collections import Counter, defaultdict
from datetime import date, timedelta

import pandas as pd
import pytest

from shadowcost.synth import Config, simulate, write_dataset
from shadowcost.synth.simulate import CHASE_DAYS, WORKFLOWS

CONFIG = Config(seed=3, days=60)


@pytest.fixture(scope="module")
def result():
    return simulate(CONFIG)


def _row(result, day, invoice_id):
    return next(r for r in result.snapshots[day] if r["invoice_id"] == invoice_id)


def test_same_seed_gives_same_data(result):
    again = simulate(CONFIG)
    assert again.actions == result.actions
    assert again.emails == result.emails
    assert again.payments == result.payments
    assert again.snapshots == result.snapshots


def test_different_seed_gives_different_data(result):
    assert simulate(Config(seed=4, days=60)).actions != result.actions


def test_payer_mix_is_fixed_across_seeds():
    for seed in (1, 2):
        customers = simulate(Config(seed=seed, days=5)).customers
        assert Counter(c.payer_type for c in customers) == {"prompt": 10, "slow": 10, "chronic": 5}


def test_one_snapshot_per_business_day(result):
    days = [CONFIG.start + timedelta(days=i) for i in range(CONFIG.days)]
    assert list(result.snapshots) == [d for d in days if d.weekday() < 5]


def test_ledger_rows_are_internally_consistent(result):
    for rows in result.snapshots.values():
        for row in rows:
            assert row["status"] in {"sent", "overdue", "paid"}
            assert (row["status"] == "paid") == bool(row["paid_date"])
            assert 0 <= row["reminders_sent"] <= 3
            assert (row["reminders_sent"] > 0) == bool(row["last_reminder_date"])
            assert row["amount"] > 0


def test_reminders_follow_the_chasing_policy(result):
    reminders = [a for a in result.actions if a.step == "send_reminder"]
    assert reminders
    for action in reminders:
        day = action.timestamp.date()
        assert day.weekday() in CHASE_DAYS
        due = date.fromisoformat(_row(result, day, action.case_id)["due_date"])
        assert (day - due).days >= 7


def test_every_outbound_email_has_an_action(result):
    outbound = {e.message_id for e in result.emails if e.direction == "outbound"}
    emailed = {a.artifact for a in result.actions if a.artifact.startswith("msg-")}
    assert outbound == emailed


def test_recorded_payments_come_from_the_bank(result):
    payments = {p.payment_id: p for p in result.payments}
    final_day = max(result.snapshots)
    matches = [a for a in result.actions if a.step == "match_payment"]
    assert matches
    for action in matches:
        payment = payments[action.artifact]
        row = _row(result, final_day, action.case_id)
        assert row["status"] == "paid"
        assert row["amount"] == payment.amount
        assert payment.date <= action.timestamp.date()


def test_every_ledger_change_is_explained_by_ground_truth(result):
    # The key property for evaluating discovery: any row that changed between two
    # snapshots was touched by a logged action on that day.
    touched = defaultdict(set)
    for a in result.actions:
        if a.artifact == "ledger":
            touched[a.timestamp.date()].add(a.case_id)

    previous: dict[str, dict] = {}
    for day, rows in result.snapshots.items():
        current = {r["invoice_id"]: r for r in rows}
        changed = {i for i, row in current.items() if previous.get(i) != row}
        assert changed <= touched[day], day
        previous = current


def test_actions_use_declared_workflows_and_steps(result):
    steps = {wf["name"]: set(wf["steps"]) for wf in WORKFLOWS}
    for a in result.actions:
        assert a.step in steps[a.workflow]
        assert a.minutes > 0


def test_repetitive_work_dominates_but_ad_hoc_work_exists(result):
    counts = Counter(a.workflow for a in result.actions)
    assert set(counts) == set(wf["name"] for wf in WORKFLOWS)
    repetitive = sum(counts[wf["name"]] for wf in WORKFLOWS if wf["repetitive"])
    assert repetitive / sum(counts.values()) > 0.6


def test_write_dataset_round_trips(tmp_path):
    result = simulate(Config(seed=1, days=20))
    manifest = write_dataset(result, tmp_path)

    snapshots = sorted((tmp_path / "ledger").glob("invoices_*.csv"))
    assert len(snapshots) == len(result.snapshots)
    last = pd.read_csv(snapshots[-1])
    assert len(last) == manifest["counts"]["invoices"]

    actions = pd.read_csv(tmp_path / "ground_truth" / "actions.csv")
    assert len(actions) == len(result.actions)
    assert len(pd.read_excel(tmp_path / "customers.xlsx")) == len(result.customers)

    lines = (tmp_path / "email" / "messages.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(result.emails)
    assert json.loads(lines[0])["message_id"] == result.emails[0].message_id


def test_write_dataset_refuses_to_overwrite_by_default(tmp_path):
    write_dataset(simulate(Config(seed=1, days=20)), tmp_path)
    with pytest.raises(FileExistsError):
        write_dataset(simulate(Config(seed=1, days=20)), tmp_path)

    shorter = simulate(Config(seed=1, days=10))
    write_dataset(shorter, tmp_path, overwrite=True)
    # Snapshots from the longer run must not linger.
    assert len(list((tmp_path / "ledger").glob("*.csv"))) == len(shorter.snapshots)
