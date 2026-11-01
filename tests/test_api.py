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
    assert "sample" in client.get("/datasets").json()


def test_workflows_on_the_sample(client):
    body = client.get("/datasets/sample/workflows").json()
    triggers = [w["trigger"] for w in body["workflows"]]
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
    assert body["dataset_id"] in client.get("/datasets").json()


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
