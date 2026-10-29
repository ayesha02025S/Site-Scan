import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import auth
import main
from database import Scan, initialize_database


@pytest.fixture
def secured(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "Session", sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setenv("CLERK_ISSUER_URL", "https://issuer.example")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "http://localhost:3000")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth, "key_client", lambda issuer: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))

    def headers(user="user_alice", **overrides):
        now = int(time.time())
        claims = dict(sub=user, iss="https://issuer.example", azp="http://localhost:3000", sid="sess_test", iat=now, nbf=now, exp=now+60)
        claims.update(overrides)
        return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256")}

    with TestClient(main.app) as client:
        yield client, headers
    engine.dispose()


def test_authentication_and_isolation(secured, monkeypatch):
    client, headers = secured
    async def fake_scan(url):
        return {"score": 80, "checks": []}
    monkeypatch.setattr(main, "scan_website", fake_scan)
    assert client.get("/health").status_code == 200
    for path in ["/scans", "/scans/missing", "/scans/missing/export"]:
        assert client.get(path).status_code == 401
    assert client.post("/scans", json={"url": "https://example.com"}).status_code == 401
    assert client.post("/scans/missing/explain").status_code == 401
    created = client.post("/scans", headers=headers(), json={"url": "https://example.com", "owner_id": "user_bob"})
    assert created.status_code == 202
    scan_id = created.json()["id"]
    assert client.get("/scans", headers=headers()).json()[0]["id"] == scan_id
    assert client.get("/scans", headers=headers("user_bob")).json() == []
    for suffix in ["", "/export"]:
        response = client.get(f"/scans/{scan_id}{suffix}", headers=headers("user_bob"))
        assert response.status_code == 404
        assert response.headers["cache-control"] == "private, no-store"
    assert client.post(f"/scans/{scan_id}/explain", headers=headers("user_bob")).status_code == 404
    assert client.get(f"/scans/{scan_id}/export", headers=headers()).status_code == 200
    with main.Session.begin() as db:
        assert db.get(Scan, scan_id).owner_id == "user_alice"
        db.add(Scan(url="https://legacy.example", status="completed", owner_id=None))
    assert len(client.get("/scans", headers=headers()).json()) == 1


@pytest.mark.parametrize("changes", [{"exp": 1}, {"iss": "https://attacker.example"}, {"azp": "https://attacker.example"}, {"sts": "pending"}, {"sub": ""}, {"nbf": 9999999999}])
def test_invalid_claims(secured, changes):
    client, headers = secured
    assert client.get("/scans", headers=headers(**changes)).status_code == 401


def test_forged_token(secured):
    client, _ = secured
    assert client.get("/scans", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_legacy_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE scans (id VARCHAR PRIMARY KEY, url VARCHAR, status VARCHAR, created_at DATETIME, result JSON, error TEXT)"))
        conn.execute(text("INSERT INTO scans(id, url, status) VALUES ('legacy', 'https://example.com', 'completed')"))
    initialize_database(engine)
    initialize_database(engine)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, owner_id FROM scans")).one()
        assert row == ("legacy", None)
    engine.dispose()
