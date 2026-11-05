from contextlib import closing
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app, get_today

TODAY = date(2026, 11, 6)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    app.dependency_overrides[get_today] = lambda: TODAY
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def create(client, name="Читання", **extra):
    res = client.post("/api/habits", json={"name": name, **extra})
    assert res.status_code == 201
    return res.json()


def stats_of(client, habit_id):
    return client.get(f"/api/habits/{habit_id}/stats").json()["stats"]


def test_create_and_list(client):
    habit = create(client, "  Читання  ", color="#10b981")
    assert habit == {"id": habit["id"], "name": "Читання", "color": "#10b981", "created_on": "2026-11-06"}

    [listed] = client.get("/api/habits").json()
    assert listed["name"] == "Читання"
    assert listed["stats"]["done_today"] is False
    assert listed["stats"]["last_7"] == [False] * 7


@pytest.mark.parametrize("body", [
    {"name": ""},
    {"name": "   "},
    {"name": "x" * 101},
    {"name": "Біг", "color": "red"},
    {"name": "Біг", "color": "#12345"},
    {},
])
def test_create_rejects_invalid_input(client, body):
    assert client.post("/api/habits", json=body).status_code == 422


def test_default_color(client):
    assert create(client)["color"] == "#4f7cff"


def test_mark_and_unmark_days(client):
    hid = create(client)["id"]
    url = f"/api/habits/{hid}/checkins"

    assert client.put(f"{url}/2026-11-06").status_code == 204
    assert client.put(f"{url}/2026-11-06").status_code == 204  # idempotent
    assert client.put(f"{url}/2026-11-05").status_code == 204
    s = stats_of(client, hid)
    assert (s["done_today"], s["total"], s["current_streak"]) == (True, 2, 2)

    assert client.delete(f"{url}/2026-11-06").status_code == 204
    s = stats_of(client, hid)
    assert (s["done_today"], s["total"], s["current_streak"]) == (False, 1, 1)


def test_rejects_future_and_malformed_days(client):
    hid = create(client)["id"]
    assert client.put(f"/api/habits/{hid}/checkins/2026-11-07").status_code == 422
    assert client.put(f"/api/habits/{hid}/checkins/2026-13-01").status_code == 422
    assert stats_of(client, hid)["total"] == 0


def test_unknown_habit_returns_404(client):
    assert client.put("/api/habits/99/checkins/2026-11-06").status_code == 404
    assert client.delete("/api/habits/99/checkins/2026-11-06").status_code == 404
    assert client.put("/api/habits/99", json={"name": "x"}).status_code == 404
    assert client.delete("/api/habits/99").status_code == 404
    assert client.get("/api/habits/99/stats").status_code == 404


def test_update(client):
    hid = create(client)["id"]
    res = client.put(f"/api/habits/{hid}", json={"name": "Читання 30 хв", "color": "#000000"})
    assert res.status_code == 200
    assert res.json()["name"] == "Читання 30 хв"
    assert res.json()["color"] == "#000000"


def test_delete_removes_history(client):
    hid = create(client)["id"]
    client.put(f"/api/habits/{hid}/checkins/2026-11-06")

    assert client.delete(f"/api/habits/{hid}").status_code == 204
    assert client.get("/api/habits").json() == []
    with closing(db.connect()) as conn:
        assert db.checkins(conn) == {}


def test_habit_stats_details(client):
    hid = create(client)["id"]
    client.put(f"/api/habits/{hid}/checkins/2026-11-01")

    s = stats_of(client, hid)
    assert s["tracked_since"] == "2026-11-01"
    assert s["days_tracked"] == 6
    assert s["rate_all"] == 0.1667
    assert len(s["weekly"]) == 12
    assert s["heatmap"][-1] == {"day": "2026-11-06", "done": False}


def test_overview(client):
    a = create(client, "Вода")["id"]
    create(client, "Зарядка")
    client.put(f"/api/habits/{a}/checkins/2026-11-06")

    o = client.get("/api/overview").json()
    assert o["today"] == "2026-11-06"
    assert (o["habits"], o["done_today"], o["rate_30"]) == (2, 1, 0.5)
    assert o["daily"][-1] == {"day": "2026-11-06", "done": 1, "total": 2}


def test_serves_web_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Трекер звичок" in res.text
