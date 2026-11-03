"""The hosted product end to end, on an in-memory database: no Supabase, Stripe or Google needed.

Login tokens are real ES256 JWTs signed by a test key, Stripe webhooks carry real signatures, and
the Google API is replaced by fakes at the HTTP-call boundary.
"""

import hashlib
import hmac
import io
import json
import time
import zipfile
from datetime import date

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from shadowcost import api  # noqa: E402
from shadowcost.saas import auth, google, notify, routes  # noqa: E402
from shadowcost.saas.config import settings  # noqa: E402
from shadowcost.saas.db import MemoryDB  # noqa: E402

WEBHOOK_SECRET = "whsec_test"
KEY = ec.generate_private_key(ec.SECP256R1())


def token(user_id: str, email: str) -> dict:
    claims = {"sub": user_id, "email": email, "aud": "authenticated", "exp": int(time.time()) + 600}
    return {"Authorization": f"Bearer {jwt.encode(claims, KEY, algorithm='ES256')}"}


OWNER = token("u-owner", "owner@acme.example")
STRANGER = token("u-stranger", "stranger@else.example")
FRIEND = token("u-friend", "friend@acme.example")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWCOST_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "test-token-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GROQ_API_KEY", "")
    settings.cache_clear()
    db = MemoryDB()
    sent: list[tuple[list[str], str]] = []
    api.app.dependency_overrides[routes.get_db] = lambda: db
    auth.set_verifier(
        lambda t: jwt.decode(t, KEY.public_key(), algorithms=["ES256"], audience="authenticated")
    )
    notify.set_sender(lambda to, subject, body: sent.append((to, subject)) or True)
    yield TestClient(api.app), db, sent
    api.app.dependency_overrides.clear()
    auth.set_verifier(None)
    notify.set_sender(notify.resend_sender)
    settings.cache_clear()


def workspace(client) -> str:
    response = client.post("/v1/orgs", json={"name": "Acme Ltd"}, headers=OWNER)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def stripe_event(client, event: dict):
    payload = json.dumps(event)
    t = int(time.time())
    sig = hmac.new(WEBHOOK_SECRET.encode(), f"{t}.{payload}".encode(), hashlib.sha256).hexdigest()
    return client.post(
        "/v1/stripe/webhook", content=payload,
        headers={"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"},
    )  # fmt: skip


def upgrade(client, org: str, plan: str = "starter"):
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": org, "customer": "cus_1", "subscription": "sub_1",
                            "metadata": {"org_id": org, "plan": plan}}},
    }  # fmt: skip
    assert stripe_event(client, event).status_code == 200


# --- accounts and workspaces ---------------------------------------------------------------------


def test_requests_need_a_valid_session(env):
    client, _, _ = env
    assert client.get("/v1/me").status_code == 401
    forged = jwt.encode(
        {"sub": "x", "email": "x@y.z", "aud": "authenticated", "exp": int(time.time()) + 60},
        ec.generate_private_key(ec.SECP256R1()), algorithm="ES256",
    )  # fmt: skip
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_creating_a_workspace_makes_you_its_owner(env):
    client, _, _ = env
    org = workspace(client)
    me = client.get("/v1/me", headers=OWNER).json()
    assert me["workspaces"] == [{"id": org, "name": "Acme Ltd", "role": "owner", "plan": "free"}]
    detail = client.get(f"/v1/orgs/{org}", headers=OWNER).json()
    assert detail["limits"]["datasets"] == 2 and detail["usage"]["members"] == 1


def test_other_users_cannot_see_a_workspace(env):
    client, _, _ = env
    org = workspace(client)
    assert client.get(f"/v1/orgs/{org}", headers=STRANGER).status_code == 404
    assert client.get(f"/v1/orgs/{org}/datasets", headers=STRANGER).status_code == 404


# --- data, agents, shadow mode -------------------------------------------------------------------


@pytest.fixture
def sample(env):
    client, db, sent = env
    org = workspace(client)
    dataset = client.post(f"/v1/orgs/{org}/datasets/sample", headers=OWNER).json()
    assert dataset["status"] == "ready", dataset
    return client, db, sent, org, dataset["id"]


def test_sample_data_is_processed_and_discovered(sample):
    client, _, _, org, ds = sample
    summary = client.get(f"/v1/orgs/{org}/datasets/{ds}", headers=OWNER).json()
    assert summary["events"] > 500 and summary["files"]["snapshot"] > 50
    workflows = client.get(f"/v1/orgs/{org}/datasets/{ds}/workflows", headers=OWNER).json()
    assert len(workflows["workflows"]) == 3
    events = client.get(f"/v1/orgs/{org}/datasets/{ds}/events?limit=3", headers=OWNER).json()
    assert len(events) == 3


def test_plan_limits_datasets(sample):
    client, _, _, org, _ = sample
    assert client.post(f"/v1/orgs/{org}/datasets/sample", headers=OWNER).status_code == 201
    third = client.post(f"/v1/orgs/{org}/datasets/sample", headers=OWNER)
    assert third.status_code == 402 and "Upgrade" in third.json()["detail"]


def test_agents_need_approval_and_respect_the_plan(sample):
    client, db, sent, org, ds = sample
    drafted = client.post(f"/v1/orgs/{org}/datasets/{ds}/agents/draft", headers=OWNER).json()
    assert drafted["created"] == 3
    agents = {
        a["spec"]["workflow_id"]: a
        for a in client.get(f"/v1/orgs/{org}/agents", headers=OWNER).json()
    }
    w1, w2 = agents["W1"]["agent_id"], agents["W2"]["agent_id"]

    blocked = client.post(
        f"/v1/orgs/{org}/agents/{w1}/shadow", json={"dataset_id": ds}, headers=OWNER
    )
    assert blocked.status_code == 403

    approved = client.post(f"/v1/orgs/{org}/agents/{w1}/approve", headers=OWNER).json()
    assert approved["approved_by"] == "owner@acme.example"
    assert client.post(f"/v1/orgs/{org}/agents/{w1}/approve", headers=OWNER).status_code == 409
    assert client.post(f"/v1/orgs/{org}/agents/{w2}/approve", headers=OWNER).status_code == 402

    run = client.post(
        f"/v1/orgs/{org}/agents/{w1}/shadow", json={"dataset_id": ds}, headers=OWNER
    ).json()
    assert run["final_stage"] == "draft" and len(run["points"]) == run["cases"]
    assert db.select("shadow_runs", where={"agent_id": w1})
    assert sent and "reached draft" in sent[-1][1] and sent[-1][0] == ["owner@acme.example"]


def test_approval_queue(sample):
    client, _, sent, org, ds = sample
    client.post(f"/v1/orgs/{org}/datasets/{ds}/agents/draft", headers=OWNER)
    w1 = next(
        a
        for a in client.get(f"/v1/orgs/{org}/agents", headers=OWNER).json()
        if a["spec"]["workflow_id"] == "W1"
    )
    client.post(f"/v1/orgs/{org}/agents/{w1['agent_id']}/approve", headers=OWNER)
    add = next(
        e
        for e in client.get(
            f"/v1/orgs/{org}/datasets/{ds}/events?limit=500&source=spreadsheet", headers=OWNER
        ).json()
        if e["activity"] == "invoices.add" and e["timestamp"] > "2026-04"
    )
    body = {"dataset_id": ds, "day": add["timestamp"][:10], "stage": "approval"}
    result = client.post(
        f"/v1/orgs/{org}/agents/{w1['agent_id']}/execute", json=body, headers=OWNER
    ).json()
    assert result["queued"]
    assert any("wait for approval" in subject for _, subject in sent)
    pending = client.get(f"/v1/orgs/{org}/actions", headers=OWNER).json()
    action = pending[0]["action_id"]
    assert (
        client.post(
            f"/v1/orgs/{org}/actions/{action}/decision", json={"approve": True}, headers=OWNER
        ).json()["status"]
        == "approved"
    )
    assert (
        client.post(
            f"/v1/orgs/{org}/actions/{action}/decision", json={"approve": False}, headers=OWNER
        ).status_code
        == 409
    )


def test_report(sample):
    client, _, _, org, ds = sample
    client.post(f"/v1/orgs/{org}/datasets/{ds}/agents/draft", headers=OWNER)
    report = client.post(f"/v1/orgs/{org}/datasets/{ds}/report", headers=OWNER).json()
    assert "## Savings" in report["markdown"]


def test_uploads_accept_files_and_reject_unsafe_zips(env):
    client, _, _ = env
    org = workspace(client)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.csv", "a,b\n1,2\n")
    bad = client.post(
        f"/v1/orgs/{org}/datasets",
        files=[("files", ("x.zip", buffer.getvalue(), "application/zip"))],
        headers=OWNER,
    )
    assert bad.status_code == 400
    csv = b"date,description,amount,reference\n2026-01-02,ALDER LTD,10.00,INV-1\n"
    ok = client.post(
        f"/v1/orgs/{org}/datasets", files=[("files", ("bank.csv", csv, "text/csv"))], headers=OWNER
    )
    assert ok.status_code == 201 and ok.json()["status"] in {"ready", "error"}


# --- teams ---------------------------------------------------------------------------------------


def test_invitations_respect_plan_email_and_single_use(env):
    client, _, sent = env
    org = workspace(client)
    invite = {"email": "Friend@acme.example", "role": "viewer"}
    assert client.post(f"/v1/orgs/{org}/invitations", json=invite, headers=OWNER).status_code == 402
    upgrade(client, org)
    created = client.post(f"/v1/orgs/{org}/invitations", json=invite, headers=OWNER).json()
    assert sent[-1][0] == ["friend@acme.example"]
    tok = created["invite_url"].split("token=")[1]
    assert (
        client.post("/v1/invitations/accept", json={"token": tok}, headers=STRANGER).status_code
        == 403
    )
    assert (
        client.post("/v1/invitations/accept", json={"token": tok}, headers=FRIEND).json()["role"]
        == "viewer"
    )
    assert (
        client.post("/v1/invitations/accept", json={"token": tok}, headers=FRIEND).status_code
        == 404
    )
    # a viewer can read but not change anything
    assert client.get(f"/v1/orgs/{org}", headers=FRIEND).json()["role"] == "viewer"
    assert client.post(f"/v1/orgs/{org}/datasets/sample", headers=FRIEND).status_code == 403


def test_roles_protect_ownership(env):
    client, _, _ = env
    org = workspace(client)
    upgrade(client, org)
    tok = (
        client.post(
            f"/v1/orgs/{org}/invitations",
            json={"email": "friend@acme.example", "role": "admin"},
            headers=OWNER,
        )
        .json()["invite_url"]
        .split("token=")[1]
    )
    client.post("/v1/invitations/accept", json={"token": tok}, headers=FRIEND)
    assert (
        client.patch(
            f"/v1/orgs/{org}/members/u-friend", json={"role": "owner"}, headers=FRIEND
        ).status_code
        == 403
    )
    assert client.delete(f"/v1/orgs/{org}/members/u-owner", headers=FRIEND).status_code == 409
    assert (
        client.patch(
            f"/v1/orgs/{org}/members/u-owner", json={"role": "viewer"}, headers=OWNER
        ).status_code
        == 409
    )


# --- billing -------------------------------------------------------------------------------------


def test_only_signed_stripe_events_change_the_plan(env):
    client, db, _ = env
    org = workspace(client)
    forged = client.post(
        "/v1/stripe/webhook", content=json.dumps({"type": "checkout.session.completed"}),
        headers={"Stripe-Signature": "t=1,v1=bad"},
    )  # fmt: skip
    assert forged.status_code == 400
    upgrade(client, org, "growth")
    assert client.get(f"/v1/orgs/{org}", headers=OWNER).json()["plan"] == "growth"
    deleted = {"id": "evt_2", "type": "customer.subscription.deleted",
               "data": {"object": {"id": "sub_1", "status": "canceled", "customer": "cus_1"}}}  # fmt: skip
    assert stripe_event(client, deleted).status_code == 200
    assert client.get(f"/v1/orgs/{org}", headers=OWNER).json()["plan"] == "free"


def test_checkout_is_owner_only(env):
    client, _, _ = env
    org = workspace(client)
    upgrade(client, org)
    tok = (
        client.post(
            f"/v1/orgs/{org}/invitations",
            json={"email": "friend@acme.example", "role": "admin"},
            headers=OWNER,
        )
        .json()["invite_url"]
        .split("token=")[1]
    )
    client.post("/v1/invitations/accept", json={"token": tok}, headers=FRIEND)
    assert (
        client.post(
            f"/v1/orgs/{org}/billing/checkout", json={"plan": "growth"}, headers=FRIEND
        ).status_code
        == 403
    )


# --- Google connector ----------------------------------------------------------------------------


def test_oauth_state_and_token_encryption(env):
    state = google.sign_state({"org": "o1", "user": "u1"})
    assert google.verify_state(state)["org"] == "o1"
    body, sig = state.rsplit(".", 1)
    with pytest.raises(HTTPException):
        google.verify_state(f"{body}.{'0' * len(sig)}")
    blob = google.encrypt("refresh-123")
    assert "refresh-123" not in blob and google.decrypt(blob) == "refresh-123"


def test_connectors_need_a_paid_plan(env):
    client, _, _ = env
    org = workspace(client)
    assert client.post(f"/v1/orgs/{org}/connectors/google/start", headers=OWNER).status_code == 402
    upgrade(client, org)
    url = client.post(f"/v1/orgs/{org}/connectors/google/start", headers=OWNER).json()["url"]
    assert "spreadsheets.readonly" in url and "gmail.readonly" in url


def test_google_sync_builds_dated_snapshots(env, monkeypatch):
    client, db, _ = env
    org = workspace(client)
    upgrade(client, org)
    db.insert("connections", {
        "org_id": org, "provider": "google", "account_email": "owner@acme.example",
        "refresh_token_encrypted": google.encrypt("r"),
        "settings": {"spreadsheet_id": "sheet1", "sheet_range": "A1:D10", "gmail_query": "newer_than:90d"},
    })  # fmt: skip
    rows = [["invoice_id", "customer", "amount", "status"], ["INV-1", "Alder Ltd", "10.00", "sent"]]
    monkeypatch.setattr(google, "access_token", lambda refresh: "access")
    monkeypatch.setattr(google, "fetch_sheet", lambda *a: ("Invoices 2026", rows))
    message = {"id": "m1", "threadId": "t1", "snippet": "Invoice INV-1 attached",
               "payload": {"headers": [{"name": "From", "value": "Acme <ap@acme.example>"},
                                       {"name": "To", "value": "alder@alder.example"},
                                       {"name": "Subject", "value": "Invoice INV-1"},
                                       {"name": "Date", "value": "Mon, 2 Mar 2026 10:00:00 +0000"}]}}  # fmt: skip
    monkeypatch.setattr(google, "fetch_gmail", lambda *a: [message])
    connection = db.select("connections")[0]
    first = routes.sync_google(db, connection, "u-owner", today=date(2026, 3, 2))
    second = routes.sync_google(db, connection, "u-owner", today=date(2026, 3, 3))
    assert first["dataset_id"] == second["dataset_id"]
    files = db.list_files(f"{org}/{first['dataset_id']}")
    assert any(f.endswith("ledger/invoices-2026_2026-03-02.csv") for f in files)
    assert any(f.endswith("ledger/invoices-2026_2026-03-03.csv") for f in files)
    log = db.download(f"{org}/{first['dataset_id']}/email/messages.jsonl").decode().splitlines()
    assert len(log) == 1 and json.loads(log[0])["from_addr"] == "ap@acme.example"


def test_sheet_csv_pads_ragged_rows():
    assert google.sheet_to_csv([["a", "b", "c"], ["1"]]) == "a,b,c\n1,,\n"
    assert (
        google.spreadsheet_id_from("https://docs.google.com/spreadsheets/d/AbC_123-x/edit#gid=0")
        == "AbC_123-x"
    )
