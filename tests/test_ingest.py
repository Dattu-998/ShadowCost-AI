import shutil
from collections import Counter

import pandas as pd
import pytest

from shadowcost.ingest import ingest_folder, load_events, save_events
from shadowcost.ingest.linking import CaseIndex, name_similarity
from shadowcost.synth import Config, simulate, write_dataset


@pytest.fixture(scope="module")
def company(tmp_path_factory):
    sim = simulate(Config(seed=3, days=60))
    root = tmp_path_factory.mktemp("company")
    write_dataset(sim, root)
    return sim, root, ingest_folder(root)


def _by_source(result, source):
    return result.events[result.events["source"] == source]


# --- against the synthetic company's ground truth -----------------------------------------


def test_detects_each_kind_of_file(company):
    sim, _, result = company
    kinds = Counter(f.kind for f in result.files)
    assert kinds == {"snapshot": len(sim.snapshots), "bank": 1, "email": 1, "table": 1}
    assert {f.series for f in result.files if f.kind == "snapshot"} == {"invoices"}
    assert set(result.tables) == {"customers"}
    assert not result.warnings


def test_ground_truth_is_never_used(company, tmp_path):
    _, root, result = company
    shutil.copytree(root, tmp_path / "copy", ignore=shutil.ignore_patterns("ground_truth"))
    without = ingest_folder(tmp_path / "copy")
    pd.testing.assert_frame_equal(without.events, result.events)


def test_spreadsheet_events_match_ground_truth_edits(company):
    sim, _, result = company
    truth = {(a.timestamp.date(), a.case_id) for a in sim.actions if a.artifact == "ledger"}
    sheet = _by_source(result, "spreadsheet")
    observed = set(zip(sheet["timestamp"].dt.date, sheet["case_id"], strict=True))
    assert observed <= truth  # no invented edits
    assert len(observed) / len(truth) >= 0.98  # only edits that changed nothing are invisible


def test_payment_recording_has_one_consistent_label(company):
    # Discovery relies on the same kind of edit getting the same activity label.
    sim, _, result = company
    recorded = {(a.timestamp.date(), a.case_id) for a in sim.actions if a.step == "match_payment"}
    sheet = _by_source(result, "spreadsheet")
    labels = Counter(
        row.activity
        for row in sheet.itertuples()
        if (row.timestamp.date(), row.case_id) in recorded
    )
    label, count = labels.most_common(1)[0]
    assert label == "invoices.update[paid_date,status]"
    assert count / sum(labels.values()) >= 0.9


def test_payments_link_to_the_right_invoice(company):
    sim, _, result = company
    truth = {a.artifact: a.case_id for a in sim.actions if a.step == "match_payment"}
    bank = _by_source(result, "bank")
    linked = dict(zip(bank["object_id"], bank["case_id"], strict=True))
    assert (bank["case_id"] != "").mean() >= 0.95
    wrong = {p: (linked[p], case) for p, case in truth.items() if linked[p] not in ("", case)}
    assert not wrong  # unlinked is acceptable; linked to the wrong invoice is not
    assert set(bank["link_method"]) == {"reference", "amount+payer"}


def test_emails_link_to_the_right_invoice(company):
    sim, _, result = company
    email = _by_source(result, "email")
    linked = dict(zip(email["object_id"], email["case_id"], strict=True))

    # Everything the office manager wrote, including "" for unrelated email.
    written = {a.artifact: a.case_id for a in sim.actions if a.artifact.startswith("msg-")}
    assert {m: linked[m] for m in written} == written

    # Customer replies inherit the invoice of their thread; newsletters link to nothing.
    thread_case = {}
    for msg in sim.emails:
        if written.get(msg.message_id):
            thread_case[msg.thread_id] = written[msg.message_id]
    for msg in sim.emails:
        if msg.direction == "inbound":
            assert linked[msg.message_id] == thread_case.get(msg.thread_id, "")


def test_email_direction_is_inferred(company):
    sim, _, result = company
    email = _by_source(result, "email")
    sent = set(email.loc[email["activity"] == "email.sent", "object_id"])
    assert sent == {m.message_id for m in sim.emails if m.direction == "outbound"}


def test_events_round_trip_through_csv(company, tmp_path):
    _, _, result = company
    save_events(result.events, tmp_path / "events.csv")
    pd.testing.assert_frame_equal(load_events(tmp_path / "events.csv"), result.events)


# --- on a layout ShadowCost has never seen -------------------------------------------------


def test_unfamiliar_layout(tmp_path):
    """Excel snapshots with different column names, and a differently shaped bank export."""
    day1 = pd.DataFrame(
        {
            "Order No": ["ORD-17", "ORD-18"],
            "Client": ["Acme Widgets Ltd", "Bolt Hardware"],
            "Total": ["120.50", "80.00"],
            "State": ["open", "open"],
        }
    )
    day2 = day1.assign(State=["open", "shipped"])
    day1.to_excel(tmp_path / "orders 2026-03-02.xlsx", index=False)
    day2.to_excel(tmp_path / "orders 2026-03-03.xlsx", index=False)
    pd.DataFrame(
        {
            "Posted Date": ["03/03/2026", "03/03/2026"],
            "Description": ["BOLT HARDWARE", "ACME WIDGETS"],
            "Value": ["80.00", "120.50"],
            "Memo": ["ord 18", ""],
        }
    ).to_csv(tmp_path / "statement.csv", index=False)
    (tmp_path / "notes.txt").write_text("not data")

    result = ingest_folder(tmp_path)

    kinds = {f.path.name: f.kind for f in result.files}
    assert kinds["statement.csv"] == "bank"
    assert kinds["notes.txt"] == "skipped"
    events = result.events
    assert set(events["activity"]) == {"orders.add", "orders.update[State]", "bank.credit"}
    update = events[events["activity"] == "orders.update[State]"].iloc[0]
    assert update["case_id"] == "ORD-18"
    assert update["payload"]["changes"] == {"State": ["open", "shipped"]}
    bank = events[events["source"] == "bank"].set_index("actor")
    assert bank.loc["BOLT HARDWARE", ["case_id", "link_method"]].tolist() == ["ORD-18", "reference"]
    assert bank.loc["ACME WIDGETS", ["case_id", "link_method"]].tolist() == [
        "ORD-17",
        "amount+payer",
    ]


# --- case linking ------------------------------------------------------------------------


@pytest.fixture
def index():
    idx = CaseIndex()
    idx.add("INV-1001", 100.00, "Alder Bakery Ltd")
    idx.add("INV-1002", 250.00, "Birch Builders Ltd")
    idx.add("INV-1003", 250.00, "Cobalt Cafe Ltd")
    return idx


@pytest.mark.parametrize(
    "reference", ["INV-1001", "inv 1001", "INV1001", "1001", "Payment INV-1001"]
)
def test_mangled_references_resolve(index, reference):
    assert index.lookup_reference(reference) == "INV-1001"


@pytest.mark.parametrize("reference", ["", "9999", "INV-1001 INV-1002"])
def test_unresolvable_references(index, reference):
    assert index.lookup_reference(reference) is None


def test_mentions_ignore_dates_and_amounts(index):
    text = "Re: INV-1002 for $1,001.00 was due on 28 Jan 2026, see also inv1003"
    assert index.mentions(text) == ["INV-1002", "INV-1003"]


def test_amount_match_uses_payer_name_to_break_ties(index):
    assert index.match_payment(250.00, "COBALT CAFE LIMITE") == "INV-1003"
    assert index.match_payment(250.00, "SOMEONE ELSE") is None
    assert index.match_payment(100.00, "UNRELATED TRADING") is None  # amount alone isn't enough
    assert index.match_payment(99.99, "ALDER BAKERY") is None


def test_name_similarity_ignores_case_and_suffixes():
    assert name_similarity("DUNE STUDIO LIMITE", "Dune Studio Ltd") == 1.0
    assert name_similarity("ALDER BAKERY", "Zephyr Optics Ltd") < 0.5
