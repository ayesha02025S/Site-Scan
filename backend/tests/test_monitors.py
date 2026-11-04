import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import main
import monitors
from auth import session_email
from database import Monitor, Notification, Scan
from scanner import ScanError


def report(**statuses):
    return {
        "scanner_version": "3.1",
        "scoring_version": "3.0",
        "score": 80,
        "checks": [
            {
                "id": f"page-{rule}",
                "rule_id": rule,
                "title": rule,
                "severity": "high",
                "status": status,
                "page_url": "https://example.com/",
            }
            for rule, status in statuses.items()
        ],
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f'sqlite:///{tmp_path / "test.db"}', connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "Session", sessionmaker(engine, expire_on_commit=False))
    main.app.dependency_overrides[main.require_user] = lambda: "user_test"
    main.app.dependency_overrides[session_email] = lambda: "owner@example.com"
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        main.app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def emails(monkeypatch):
    sent = []

    async def fake_send(to, subject, body):
        sent.append((to, subject, body))

    monkeypatch.setattr(main, "send_email", fake_send)
    return sent


def queue_results(monkeypatch, results):
    async def fake_scan(url):
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(main, "scan_website", fake_scan)


def settle():
    for _ in range(200):
        if not main.tasks:
            return
        time.sleep(0.01)
    pytest.fail("Scans never finished")


def create(client, url="https://example.com/"):
    response = client.post("/monitors", json={"url": url, "frequency": "daily"})
    assert response.status_code == 201
    settle()
    return response.json()


def run_again(client, monitor_id):
    with main.Session.begin() as db:
        db.get(Monitor, monitor_id).next_run_at = datetime.now(
            timezone.utc
        ) - timedelta(minutes=1)
    client.portal.call(run_due_in_loop)
    settle()


async def run_due_in_loop():
    main.run_due_monitors()


def test_new_monitor_scans_now_and_schedules_next_run(client, monkeypatch, emails):
    queue_results(monkeypatch, [report(title="passed")])
    monitor = create(client)
    assert monitor["email"] == "owner@example.com"
    assert datetime.fromisoformat(monitor["next_run_at"]) > datetime.now(
        timezone.utc
    ) + timedelta(hours=23)
    assert [scan["status"] for scan in client.get("/scans").json()] == ["completed"]
    assert client.get("/notifications").json() == [] and emails == []


def test_regression_creates_notification_and_email(client, monkeypatch, emails):
    queue_results(
        monkeypatch,
        [report(title="passed", alt="failed"), report(title="failed", alt="failed")],
    )
    monitor = create(client)
    run_again(client, monitor["id"])
    [notification] = client.get("/notifications").json()
    assert notification["kind"] == "new_issues" and notification["read"] is False
    assert notification["title"] == "1 new issue on example.com"
    assert "title" in notification["body"] and "alt" not in notification["body"]
    latest = client.get("/scans").json()[0]
    assert notification["scan_id"] == latest["id"]
    assert emails[0][0] == "owner@example.com"
    assert client.post("/notifications/read").status_code == 200
    assert client.get("/notifications").json()[0]["read"] is True


def test_slow_fetch_alone_does_not_alert(client, monkeypatch, emails):
    queue_results(
        monkeypatch,
        [
            report(**{"response-time": "passed"}),
            report(**{"response-time": "failed"}),
        ],
    )
    monitor = create(client)
    run_again(client, monitor["id"])
    assert client.get("/notifications").json() == []


def test_one_failure_retries_soon_without_alert(client, monkeypatch, emails):
    queue_results(monkeypatch, [ScanError("Down")])
    monitor = create(client)
    assert client.get("/notifications").json() == []
    with main.Session() as db:
        next_run = db.get(Monitor, monitor["id"]).next_run_at.replace(
            tzinfo=timezone.utc
        )
    assert next_run < datetime.now(timezone.utc) + timedelta(minutes=16)


def test_repeated_failure_alerts_once_then_recovery(client, monkeypatch, emails):
    queue_results(
        monkeypatch,
        [ScanError("Down"), ScanError("Down"), ScanError("Down"), report(a="passed")],
    )
    monitor = create(client)
    for _ in range(3):
        run_again(client, monitor["id"])
    kinds = [item["kind"] for item in client.get("/notifications").json()]
    assert sorted(kinds) == ["recovered", "scan_failed"]
    assert len(emails) == 2


def test_monitor_limits_and_validation(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_MONITORS_PER_USER", 2)
    queue_results(monkeypatch, [report(a="passed"), report(a="passed")])
    create(client)
    create(client, "https://example.org/")
    duplicate = {"url": "example.com", "frequency": "daily"}
    assert client.post("/monitors", json=duplicate).status_code == 409
    full = {"url": "https://example.net/", "frequency": "daily"}
    assert client.post("/monitors", json=full).status_code == 409
    private = {"url": "http://127.0.0.1/", "frequency": "daily"}
    assert client.post("/monitors", json=private).status_code == 422
    hourly = {"url": "https://example.net/", "frequency": "hourly"}
    assert client.post("/monitors", json=hourly).status_code == 422


def test_paused_monitor_does_not_run_and_owner_isolation(client, monkeypatch):
    queue_results(monkeypatch, [report(a="passed")])
    monitor = create(client)
    path = f'/monitors/{monitor["id"]}'
    assert client.patch(path, json={"active": False}).json()["active"] is False
    run_again(client, monitor["id"])
    assert len(client.get("/scans").json()) == 1
    main.app.dependency_overrides[main.require_user] = lambda: "user_other"
    assert client.get("/monitors").json() == []
    assert client.patch(path, json={"active": True}).status_code == 404
    assert client.delete(path).status_code == 404
    main.app.dependency_overrides[main.require_user] = lambda: "user_test"
    assert client.delete(path).json() == {"deleted": True}
    assert client.get("/monitors").json() == []


def test_deleted_monitor_scan_finishes_without_alert(client, monkeypatch, emails):
    with main.Session.begin() as db:
        scan = Scan(url="https://example.com/", owner_id="user_test", status="failed")
        db.add(scan)
        db.flush()
        scan_id = scan.id
    asyncio.run(main.finish_monitor_run("missing", scan_id))
    with main.Session() as db:
        assert db.scalars(select(Notification)).all() == []


def test_incompatible_versions_and_unseen_checks_do_not_alert():
    current = report(a="failed", b="failed")
    assert monitors.new_issues(current, report(a="inconclusive")) == []
    older = {**report(a="passed"), "scanner_version": "3.0"}
    assert monitors.new_issues(current, older) == []


def test_email_skipped_without_configuration(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert asyncio.run(monitors.send_email("a@example.com", "s", "b")) is False


def test_startup_catches_up_on_overdue_monitor(client, monkeypatch, emails):
    queue_results(monkeypatch, [report(a="passed")])
    with main.Session.begin() as db:
        db.add(
            Monitor(
                owner_id="user_test",
                url="https://example.com/",
                frequency="daily",
                next_run_at=datetime.now(timezone.utc) - timedelta(days=3),
            )
        )
    with TestClient(main.app) as restarted:
        for _ in range(200):
            scans = restarted.get("/scans").json()
            if scans and scans[0]["status"] == "completed":
                break
            time.sleep(0.01)
        assert [scan["status"] for scan in scans] == ["completed"]


def test_interrupted_scan_is_rescheduled_without_counting_as_failure(client, emails):
    far = datetime.now(timezone.utc) + timedelta(days=6)
    url = "https://example.com/"
    with main.Session.begin() as db:
        for owner, active in [("user_test", True), ("user_paused", False), ("user_other", True)]:
            db.add(
                Monitor(
                    id=owner, owner_id=owner, url=url, frequency="weekly",
                    active=active, next_run_at=far,
                )
            )
        db.add(Scan(owner_id="user_test", url=url, status="running"))
        db.add(Scan(owner_id="user_paused", url=url, status="running"))
    with TestClient(main.app):
        pass
    limit = datetime.now(timezone.utc) + timedelta(minutes=16)
    with main.Session() as db:
        due = {
            m.owner_id: m.next_run_at.replace(tzinfo=timezone.utc)
            for m in db.scalars(select(Monitor))
        }
        rescheduled = db.get(Monitor, "user_test")
        assert rescheduled.failures == 0
        assert db.scalars(select(Notification)).all() == []
    assert due["user_test"] < limit
    assert due["user_paused"] > limit and due["user_other"] > limit
