import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import explain
import main
from database import Base, Scan


def check(key, status="failed", severity="medium", elements=0):
    return {
        "id": key,
        "category": "accessibility",
        "title": key.title(),
        "status": status,
        "severity": severity,
        "evidence": f"{key} evidence",
        "fix": f"{key} fix",
        "element_count": elements,
    }


RESULT = {
    "final_url": "https://example.com/",
    "title": "Example",
    "score": 60,
    "scores": {"performance": 80, "accessibility": 40, "security": 60},
    "checks": [
        check("low", severity="low"),
        check("contrast", elements=12),
        check("alt", severity="high"),
        check("csp", severity="high", elements=1),
        check("lang", status="passed", severity="high"),
    ],
}


def run(coro):
    return asyncio.run(coro)


def test_rule_based_ranking_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = run(explain.explain_scan(RESULT))
    assert result["source"] == "rules"
    assert "GEMINI_API_KEY" in result["note"]
    assert [f["check_id"] for f in result["top_fixes"]] == ["csp", "alt", "contrast"]


def test_no_failures_needs_no_ai(monkeypatch):
    async def fail(*args):
        pytest.fail("Gemini should not be called")

    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(explain, "ask_gemini", fail)
    result = run(explain.explain_scan({"checks": [check("lang", status="passed")]}))
    assert result["top_fixes"] == []


def test_ai_answer_is_limited_to_failed_checks(monkeypatch):
    async def fake(prompt, api_key, model):
        assert '"check_id": "lang"' not in prompt
        return {
            "summary": "Contrast is the biggest problem.",
            "top_fixes": [
                {"check_id": "contrast", "why": "Hard to read.", "how": "Darken text."},
                {"check_id": "made-up", "why": "x", "how": "y"},
                {"check_id": "lang", "why": "x", "how": "y"},
                {"check_id": "contrast", "why": "dup", "how": "dup"},
                {"check_id": "alt", "why": "Screen readers.", "how": "Add alt."},
                {"check_id": "low", "why": "Minor.", "how": "Tweak."},
            ],
        }

    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(explain, "ask_gemini", fake)
    result = run(explain.explain_scan(RESULT))
    assert result["source"] == "ai"
    assert [f["check_id"] for f in result["top_fixes"]] == ["contrast", "alt", "low"]
    assert result["top_fixes"][0]["title"] == "Contrast"
    assert result["top_fixes"][0]["how"] == "Darken text."


@pytest.mark.parametrize(
    "answer",
    [
        RuntimeError("Gemini returned HTTP 429"),
        {"summary": "Only made-up checks.", "top_fixes": [{"check_id": "x"}]},
        {"summary": "", "top_fixes": []},
    ],
)
def test_bad_ai_answers_fall_back(monkeypatch, answer):
    async def fake(prompt, api_key, model):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(explain, "ask_gemini", fake)
    result = run(explain.explain_scan(RESULT))
    assert result["source"] == "rules"
    assert len(result["top_fixes"]) == 3


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f'sqlite:///{tmp_path / "test.db"}', connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "Session", sessionmaker(engine, expire_on_commit=False))
    main.app.dependency_overrides[main.require_user] = lambda: "user_test"
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        main.app.dependency_overrides.clear()
    engine.dispose()


def add_scan(status="completed", result=RESULT):
    with main.Session.begin() as db:
        scan = Scan(owner_id="user_test", url="https://example.com/", status=status, result=result)
        db.add(scan)
        db.flush()
        return scan.id


def test_explain_endpoint_caches_ai_result(client, monkeypatch):
    calls = []

    async def fake(prompt, api_key, model):
        calls.append(model)
        return {
            "summary": "Summary.",
            "top_fixes": [
                {"check_id": key, "why": "Why.", "how": "How."}
                for key in ("csp", "alt", "contrast")
            ],
        }

    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(explain, "ask_gemini", fake)
    scan_id = add_scan()
    first = client.post(f"/scans/{scan_id}/explain").json()
    second = client.post(f"/scans/{scan_id}/explain").json()
    assert first == second
    assert first["source"] == "ai"
    assert len(calls) == 1
    saved = client.get(f"/scans/{scan_id}").json()["result"]
    assert saved["explanation"] == first
    assert saved["checks"] == RESULT["checks"]


def test_explain_endpoint_does_not_cache_fallback(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    scan_id = add_scan()
    assert client.post(f"/scans/{scan_id}/explain").json()["source"] == "rules"
    assert "explanation" not in client.get(f"/scans/{scan_id}").json()["result"]


def test_explain_endpoint_errors(client):
    assert client.post("/scans/missing/explain").status_code == 404
    scan_id = add_scan(status="running", result=None)
    assert client.post(f"/scans/{scan_id}/explain").status_code == 409
