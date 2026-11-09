import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import main
from database import initialize_database

DEFAULTS = {
    "theme": "dark",
    "day_theme": "light",
    "night_theme": "dark",
    "day_start": "07:00",
    "night_start": "19:00",
    "text_color": "off",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f'sqlite:///{tmp_path / "test.db"}', connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "Session", sessionmaker(engine, expire_on_commit=False))
    main.app.dependency_overrides[main.require_user] = lambda: "user_a"
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        main.app.dependency_overrides.clear()
    engine.dispose()


def test_new_user_gets_defaults(client):
    assert client.get("/preferences").json() == DEFAULTS


def test_preferences_are_saved_and_updated(client):
    chosen = {**DEFAULTS, "theme": "systematic", "day_theme": "pink",
              "night_theme": "red-void", "day_start": "06:30", "text_color": "off-white"}
    assert client.put("/preferences", json=chosen).json() == chosen
    assert client.get("/preferences").json() == chosen
    assert client.put("/preferences", json={"theme": "forest"}).json() == {**DEFAULTS, "theme": "forest"}
    assert client.get("/preferences").json()["theme"] == "forest"


def test_preferences_are_private_to_each_user(client):
    client.put("/preferences", json={**DEFAULTS, "theme": "navy"})
    main.app.dependency_overrides[main.require_user] = lambda: "user_b"
    assert client.get("/preferences").json() == DEFAULTS


@pytest.mark.parametrize("bad", [
    {"theme": "rainbow"},
    {"theme": "dark", "day_theme": "systematic"},
    {"theme": "dark", "day_start": "24:00"},
    {"theme": "dark", "night_start": ""},
    {"theme": "dark", "text_color": "blue"},
    {},
])
def test_invalid_preferences_are_rejected(client, bad):
    assert client.put("/preferences", json=bad).status_code == 422
    assert client.get("/preferences").json() == DEFAULTS


def test_old_preferences_table_gets_new_columns(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "old.db"}')
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE user_preferences (owner_id VARCHAR(255) PRIMARY KEY, theme VARCHAR(32) NOT NULL)"
        ))
        connection.execute(text("INSERT INTO user_preferences VALUES ('user_a', 'pink')"))
    initialize_database(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("user_preferences")}
    assert {"day_theme", "night_theme", "day_start", "night_start", "text_color"} <= columns
    with engine.connect() as connection:
        row = connection.execute(text("SELECT theme, text_color FROM user_preferences")).one()
    assert tuple(row) == ("pink", "off")
    engine.dispose()
