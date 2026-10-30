import random
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from shadowcost.discover import _group_signatures, discover
from shadowcost.discover.__main__ import main
from shadowcost.discover.episodes import RowHistory
from shadowcost.discover.templates import cluster_templates, mask
from shadowcost.discover.triggers import schedule_trigger
from shadowcost.evaluation import evaluate
from shadowcost.ingest import ingest_folder
from shadowcost.recommend import recommend
from shadowcost.synth import Config, emails, simulate, write_dataset


def _pipeline(tmp_path_factory, seed):
    sim = simulate(Config(seed=seed))
    root = tmp_path_factory.mktemp(f"seed{seed}")
    write_dataset(sim, root)
    discovery = discover(ingest_folder(root).events)
    recommendations = recommend(discovery)
    return SimpleNamespace(
        sim=sim,
        root=root,
        discovery=discovery,
        recommendations=recommendations,
        evaluation=evaluate(discovery, recommendations, root / "ground_truth"),
    )


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    # A development seed: the committed sample (seed 7) is kept for reporting results.
    return _pipeline(tmp_path_factory, seed=1)


def _by_label(run):
    labels = {s.workflow_id: s.label for s in run.evaluation.workflows}
    return {labels[r.workflow.workflow_id]: r for r in run.recommendations}


# --- end to end on a synthetic company ----------------------------------------------------


def test_finds_exactly_the_repetitive_workflows(run):
    e = run.evaluation
    assert (e.recall, e.precision) == (1.0, 1.0)
    assert all(s.purity == 1.0 for s in e.workflows)
    assert all(share >= 0.95 for share in e.coverage.values())


def test_infers_each_workflows_trigger(run):
    found = _by_label(run)
    assert found["send_invoice"].workflow.trigger.kind == "new_row"

    payment = found["record_payment"].workflow.trigger
    assert (payment.kind, payment.detail["activity"]) == ("event", "bank.credit")

    chase = found["chase_overdue"].workflow
    assert chase.trigger.kind == "schedule"
    assert chase.trigger.detail["weekdays"] == [0, 3]  # Mondays and Thursdays
    assert (chase.condition.column, chase.condition.min_days) == ("due_date", 7)
    assert set(chase.condition.eligible) == {"status"}  # i.e. not paid
    assert chase.condition.support >= 0.95


def test_templates_never_mix_kinds_of_email(run):
    assert run.evaluation.template_homogeneity == 1.0


def test_time_estimates_are_close_and_upper_bounds_hold(run):
    # The default per-step times are generic priors, deliberately not fitted to the
    # simulator; they run 10-25% low on it, so allow 35%.
    for t in run.evaluation.time:
        assert abs(t.estimated_hours - t.true_hours) / t.true_hours <= 0.35, t
        if t.observed_upper_hours is not None:
            assert t.observed_upper_hours >= t.true_hours, t


def test_recommendations_are_ranked_and_state_assumptions(run):
    addressable = [r.addressable_hours_per_month for r in run.recommendations]
    assert addressable == sorted(addressable, reverse=True)
    assert all(r.assumptions for r in run.recommendations)


def test_row_history_replays_to_the_last_snapshot(run):
    final_day = max(run.sim.snapshots)
    rebuilt = RowHistory(run.discovery.events).before(final_day + timedelta(days=1))
    expected = {
        row["invoice_id"]: {k: str(v) for k, v in row.items()}
        for row in run.sim.snapshots[final_day]
    }
    assert rebuilt == expected


def test_reply_handling_is_flagged_as_needing_judgment(tmp_path_factory):
    # Seed 3 has enough "note the customer's promise" episodes to form a workflow.
    run = _pipeline(tmp_path_factory, seed=3)
    flagged = [r for r in run.recommendations if r.caveats]
    assert flagged
    for r in flagged:
        assert r.workflow.trigger.detail["activity"] == "email.received"
        assert r.automation_score <= 0.5
    assert run.recommendations[-1] in flagged  # ranked below the clear-cut workflows


def test_cli_prints_ranking_and_evaluation(run, capsys):
    main([str(run.root), "--evaluate"])
    out = capsys.readouterr().out
    assert out.startswith("Found 3 repeated workflows")
    assert "workflow recall 1.00, precision 1.00" in out


# --- components ----------------------------------------------------------------------------


def test_mask_removes_what_varies_between_instances():
    text = "Dear Maple Vets, invoice INV-1008 for $1,723.74 was due on 28 Jan 2026 (3 days ago)."
    assert mask(text, "billing@maple-vets.example") == (
        "Dear <party> <party> , invoice <id> for <amount> was due on <date> ( <num> days ago)."
    )


def test_rephrased_emails_share_a_template():
    rng = random.Random(0)
    customers = ["Alder Bakery Ltd", "Birch Builders Ltd", "Cobalt Cafe Ltd", "Dune Studio Ltd"]
    rows, kinds = [], []
    for i in range(24):
        customer = customers[i % 4]
        address = "accounts@" + customer.lower().removesuffix(" ltd").replace(" ", "-") + ".example"
        invoice_id, due = f"INV-{1000 + i}", date(2026, 1, 1) + timedelta(days=i)
        if i % 2:
            subject, body = emails.reminder(rng, "first", customer, invoice_id, 100.0 + i, due, 9)
        else:
            subject, body = emails.invoice(rng, customer, invoice_id, 100.0 + i, due)
        rows.append(
            {"object_id": f"m{i}", "payload": {"subject": subject, "body": body, "to": address}}
        )
        kinds.append("reminder" if i % 2 else "invoice")

    template_of, templates = cluster_templates(pd.DataFrame(rows))
    by_kind = {
        kind: {template_of[f"m{i}"] for i, k in enumerate(kinds) if k == kind} for kind in kinds
    }
    assert len(by_kind["reminder"]) == 1 and len(by_kind["invoice"]) == 1
    assert by_kind["reminder"] != by_kind["invoice"]
    assert cluster_templates(pd.DataFrame(columns=["object_id", "payload"])) == ({}, [])


def test_schedule_needs_more_than_chance():
    def days(n):
        mondays_and_thursdays = [date(2026, 3, 2), date(2026, 3, 5)]  # a Monday and a Thursday
        return pd.DataFrame({"day": [mondays_and_thursdays[i % 2] for i in range(n)]})

    assert schedule_trigger(days(3)) is None  # 3 on two weekdays happens by luck
    trigger = schedule_trigger(days(10))
    assert trigger.description == "on Mondays and Thursdays"


def test_reminder_variants_merge_but_payments_stay_separate():
    first = ("email.sent:T02", "invoices.update[last_reminder_date,reminders_sent,status]")
    later = ("email.sent:T03", "invoices.update[last_reminder_date,reminders_sent]")
    payment = ("invoices.update[paid_date,status]",)
    groups = _group_signatures([first, later, payment], min_similarity=0.6)
    assert sorted(map(len, groups)) == [1, 2]
    assert {payment} in groups
