import io
import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from shadowcost import api  # noqa: E402
from shadowcost.synth import Config, simulate, write_dataset  # noqa: E402

SPECS = Path(__file__).parent.parent / "specs"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("api")
    sample = root / "sample"
    write_dataset(simulate(Config(seed=7, days=120)), sample)
    patch = pytest.MonkeyPatch()
    patch.setenv("SHADOWCOST_WORKSPACE", str(root / "workspace"))
    patch.setenv("SHADOWCOST_SAMPLE", str(sample))
    patch.setenv("SHADOWCOST_SPECS", str(SPECS))
    api._ingest.cache_clear()
    api._discovery_cached.cache_clear()
    yield TestClient(api.app)
    patch.undo()


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_health_and_datasets(client):
    assert client.get("/health").json()["status"] == "ok"
    ids = [d["id"] for d in client.get("/datasets").json()]
    assert ids[:2] == ["sample", "year"]
    summary = client.get("/datasets/sample").json()
    assert summary["files"]["snapshot"] > 50 and summary["has_ground_truth"]
    assert summary["weekly"] and set(summary["by_source"]) == {"bank", "email", "spreadsheet"}


def test_workflows_on_the_sample(client):
    body = client.get("/datasets/sample/workflows").json()
    triggers = [w["trigger"]["description"] for w in body["workflows"]]
    assert len(triggers) == 3
    assert any("bank.credit" in t for t in triggers)
    assert all(w["assumptions"] for w in body["workflows"])


def test_backtest_then_approval_gates_shadow_mode(client):
    spec = json.loads((SPECS / "W1.json").read_text())
    backtested = client.post("/datasets/sample/backtest", json={"spec": spec}).json()
    assert backtested["agreement"] == 1.0

    assert client.post("/datasets/sample/shadow", json={"spec": spec}).status_code == 403
    approved = client.post("/specs/approve", json={"spec": spec, "by": "tester"})
    assert approved.status_code == 200
    run = client.post("/datasets/sample/shadow", json={"spec": spec}).json()
    assert run["final_stage"] == "draft"  # 40 held-out days: enough for one promotion
    assert run["changes"][0]["to"] == "draft"


def test_invalid_spec_is_rejected_with_problems(client):
    response = client.post("/datasets/sample/backtest", json={"spec": {"name": "x"}})
    assert response.status_code == 422
    assert "problems" in response.json()["detail"]


def test_report(client):
    specs = [json.loads((SPECS / f"W{i}.json").read_text()) for i in (1, 2)]
    body = client.post("/datasets/sample/report", json={"specs": specs}).json()
    assert "## Savings" in body["markdown"] and body["html"].startswith("<!doctype html>")


def test_upload_a_zip(client, tmp_path):
    folder = tmp_path / "upload"
    write_dataset(simulate(Config(seed=2, days=40)), folder)
    files = {
        str(p.relative_to(folder)).replace("\\", "/"): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file()
    }
    response = client.post(
        "/datasets", files={"file": ("data.zip", _zip(files), "application/zip")}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["events"] > 0 and not body["warnings"]
    assert body["dataset_id"] in [d["id"] for d in client.get("/datasets").json()]


@pytest.mark.parametrize("name", ["../escape.csv", "/abs/escape.csv", "a/../../escape.csv"])
def test_upload_refuses_paths_outside_its_folder(client, name):
    response = client.post(
        "/datasets", files={"file": ("x.zip", _zip({name: b"a,b\n1,2\n"}), "application/zip")}
    )
    assert response.status_code == 400
    assert "unsafe path" in response.json()["detail"]


def test_upload_ignores_non_data_files(tmp_path):
    api.extract_zip(_zip({"run.exe": b"MZ", "ledger/a_2026-01-01.csv": b"id\n1\n"}), tmp_path / "t")
    assert [p.name for p in (tmp_path / "t").rglob("*") if p.is_file()] == ["a_2026-01-01.csv"]


def test_unknown_dataset_is_404(client):
    assert client.get("/datasets/nope/workflows").status_code == 404
    assert client.get("/datasets/..%2F..%2Fetc/workflows").status_code == 404


def test_cors_allows_the_browser_frontend(client):
    response = client.get("/health", headers={"Origin": "https://shadowcost.vercel.app"})
    assert response.headers["access-control-allow-origin"] in {"*", "https://shadowcost.vercel.app"}


def test_events_feed(client):
    events = client.get("/datasets/sample/events?limit=5&source=bank").json()
    assert len(events) == 5 and all(e["source"] == "bank" for e in events)
    assert " from " in events[0]["detail"]


def test_specs_list_shows_approval_state(client):
    specs = client.get("/specs").json()
    assert [s["spec"]["workflow_id"] for s in specs] == ["W1", "W2", "W3"]
    assert all("held_out" in s["spec"]["evaluation"] for s in specs)


def test_shadow_returns_a_timeline(client):
    spec = json.loads((SPECS / "W1.json").read_text())
    client.post("/specs/approve", json={"spec": spec, "by": "tester"})
    run = client.post("/datasets/sample/shadow", json={"spec": spec}).json()
    assert len(run["points"]) == run["cases"]
    assert run["points"][-1]["agreement_so_far"] == 1.0
    assert run["changes"][0]["lower_bound"] >= 0.85


def test_execute_queue_and_decide(client):
    spec = json.loads((SPECS / "W2.json").read_text())
    payment = client.get("/datasets/sample/events?limit=1&source=bank").json()[0]
    body = {"spec": spec, "day": payment["timestamp"][:10], "stage": "approval"}
    assert client.post("/datasets/sample/execute", json=body).status_code == 403
    client.post("/specs/approve", json={"spec": spec, "by": "tester"})
    result = client.post("/datasets/sample/execute", json=body).json()
    assert result["queued"] and len(result["queued"]) == len(result["proposals"])
    pending = client.get("/actions").json()
    action_id = pending[0]["action_id"]
    ok = client.post(f"/actions/{action_id}/decision", json={"approve": True, "by": "tester"})
    assert ok.json()["status"] == "approved"
    again = client.post(f"/actions/{action_id}/decision", json={"approve": False, "by": "x"})
    assert again.status_code == 409
    bad = client.post("/datasets/sample/execute", json=body | {"stage": "yolo"})
    assert bad.status_code == 422
