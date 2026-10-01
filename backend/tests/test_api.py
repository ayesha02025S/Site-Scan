import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from database import Base, Scan
from scanner import ScanError


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f'sqlite:///{tmp_path / "test.db"}', connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "Session", sessionmaker(engine, expire_on_commit=False))
    with TestClient(main.app) as client:
        yield client
    engine.dispose()


def wait_for_scan(client, scan_id):
    for _ in range(100):
        scan = client.get("/scans/" + scan_id).json()
        if scan["status"] in ("completed", "failed"):
            return scan
        time.sleep(0.01)
    pytest.fail("Scan never finished")


def test_submit_save_retrieve_and_restart(client, monkeypatch):
    async def fake_scan(url):
        return {"score": 80, "checks": []}

    monkeypatch.setattr(main, "scan_page", fake_scan)
    response = client.post("/scans", json={"url": "example.com"})
    assert response.status_code == 202
    data = response.json()
    assert data["url"] == "https://example.com"
    saved = wait_for_scan(client, data["id"])
    assert saved["status"] == "completed"
    assert saved["result"]["score"] == 80
    assert client.get("/scans").json()[0] == saved
    with TestClient(main.app) as restarted:
        assert restarted.get("/scans/" + data["id"]).json()["result"]["score"] == 80


def test_failed_scan_is_saved(client, monkeypatch):
    async def fake_scan(url):
        raise ScanError("The website took too long to respond.")

    monkeypatch.setattr(main, "scan_page", fake_scan)
    data = client.post("/scans", json={"url": "https://example.com"}).json()
    result = wait_for_scan(client, data["id"])
    assert result["status"] == "failed"
    assert "too long" in result["error"]
    assert result["result"] is None


def test_input_errors_and_missing_scan(client):
    assert client.post("/scans", json={"url": "http://127.0.0.1"}).status_code == 422
    assert client.post("/scans", json={}).status_code == 422
    assert client.get("/scans/does-not-exist").status_code == 404
    assert client.get("/scans").json() == []


def test_restart_marks_interrupted_scan_failed(client):
    with main.Session.begin() as db:
        scan = Scan(url="https://example.com", status="running")
        db.add(scan)
        db.flush()
        scan_id = scan.id
    with TestClient(main.app) as restarted:
        result = restarted.get("/scans/" + scan_id).json()
        assert result["status"] == "failed"
        assert "restarted" in result["error"]


def test_report_export_matches_saved_result(client, monkeypatch):
    async def fake_scan(url):
        return {"score": 90, "checks": []}

    monkeypatch.setattr(main, "scan_page", fake_scan)
    scan = client.post("/scans", json={"url": "https://example.com"}).json()
    saved = wait_for_scan(client, scan["id"])
    exported = client.get("/scans/" + scan["id"] + "/export")
    assert exported.status_code == 200
    assert exported.json() == saved
    assert (
        exported.headers["content-disposition"]
        == f'attachment; filename="site-scan-{scan["id"]}.json"'
    )
    assert client.get("/scans/missing/export").status_code == 404
