import io
import json
import urllib.error
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import ai, db
from app.main import app, get_today

TODAY = date(2026, 11, 6)


def interaction(answer: dict) -> dict:
    return {
        "status": "completed",
        "steps": [
            {"type": "thought", "signature": "x"},
            {"type": "model_output", "content": [{"type": "text", "text": json.dumps(answer, ensure_ascii=False)}]},
        ],
        "usage": {"total_input_tokens": 900, "total_output_tokens": 300, "total_thought_tokens": 50},
    }


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(ai.API_URL, code, "error", {}, io.BytesIO(b"{}"))


@pytest.fixture
def gemini(tmp_path, monkeypatch):
    """Replaces the HTTP call; set `.replies` to answers or exceptions, one per call."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai, "ENV_FILE", tmp_path / ".env")
    calls = []

    def fake_post(model, body, key):
        calls.append({"model": model, "body": body, "key": key})
        reply = fake_post.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return interaction(reply)

    fake_post.calls = calls
    fake_post.replies = []
    monkeypatch.setattr(ai, "_post", fake_post)
    return fake_post


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    app.dependency_overrides[get_today] = lambda: TODAY
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


REPORT = {
    "summary": "Добрий старт.",
    "strengths": ["Вода щодня"],
    "habits": [
        {"id": 1, "status": "стабільно", "advice": "Так тримати."},
        {"id": 99, "status": "під загрозою", "advice": "Звички з таким id немає."},
    ],
    "focus": "Читати перед сном.",
}


def test_report_sends_stats_and_attaches_names(client, gemini):
    hid = client.post("/api/habits", json={"name": "Вода"}).json()["id"]
    client.put(f"/api/habits/{hid}/checkins/2026-11-06")
    gemini.replies = [REPORT]

    res = client.post("/api/ai/report")
    assert res.status_code == 200
    body = res.json()
    assert body["habits"] == [{"id": 1, "status": "стабільно", "advice": "Так тримати.", "name": "Вода"}]
    assert body["meta"] | {"seconds": 0} == {
        "model": "gemini-3.8-flash", "seconds": 0, "input_tokens": 900, "output_tokens": 350,
    }

    [call] = gemini.calls
    assert call["key"] == "test-key"
    assert call["body"]["response_format"]["schema"] == ai.REPORT_SCHEMA
    sent = json.loads(call["body"]["input"].split("\n", 1)[1])
    assert sent["habits"][0] | {"per_week_last_12": None} == {
        "id": hid, "name": "Вода", "days_tracked": 1, "current_streak": 1, "longest_streak": 1,
        "rate_30": 1.0, "rate_all": 1.0, "last_7_days": [False] * 6 + [True], "per_week_last_12": None,
    }
    assert sent["overall"]["done_today"] == "1 з 1"


def test_report_needs_habits(client, gemini):
    assert client.post("/api/ai/report").status_code == 422
    assert gemini.calls == []


def test_falls_back_to_second_model_when_first_is_overloaded(client, gemini):
    client.post("/api/habits", json={"name": "Вода"})
    gemini.replies = [http_error(503), REPORT]

    res = client.post("/api/ai/report")
    assert res.status_code == 200
    assert [c["model"] for c in gemini.calls] == list(ai.MODELS)
    assert res.json()["meta"]["model"] == ai.MODELS[1]


def test_all_models_unavailable(client, gemini):
    client.post("/api/habits", json={"name": "Вода"})
    gemini.replies = [http_error(429), urllib.error.URLError("offline")]
    res = client.post("/api/ai/report")
    assert res.status_code == 503
    assert "недоступний" in res.json()["detail"]


def test_rejected_request_is_not_retried(client, gemini):
    client.post("/api/habits", json={"name": "Вода"})
    gemini.replies = [http_error(403)]
    res = client.post("/api/ai/report")
    assert res.status_code == 502
    assert len(gemini.calls) == 1


def test_missing_key(client, gemini, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    client.post("/api/habits", json={"name": "Вода"})
    res = client.post("/api/ai/report")
    assert res.status_code == 503
    assert "GEMINI_API_KEY" in res.json()["detail"]
    assert gemini.calls == []


def test_key_from_env_file(gemini, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    ai.ENV_FILE.write_text("# comment\nOTHER=1\nGEMINI_API_KEY='from-file'\n")
    assert ai.api_key() == "from-file"


def test_suggest(client, gemini):
    client.post("/api/habits", json={"name": "Вода"})
    gemini.replies = [{"habits": [
        {"name": "  Прогулянка 20 хвилин ", "why": "Рух вдень."},
        {"name": "x" * 150, "why": "Задовга назва."},
        {"name": " ", "why": "Порожня назва."},
    ]}]

    res = client.post("/api/ai/suggest", json={"goal": "краще спати"})
    assert res.status_code == 200
    names = [h["name"] for h in res.json()["habits"]]
    assert names == ["Прогулянка 20 хвилин", "x" * 100]
    prompt = gemini.calls[0]["body"]["input"]
    assert "краще спати" in prompt and "Вода" in prompt


@pytest.mark.parametrize("goal", ["", "  а ", "x" * 201])
def test_suggest_validates_goal(client, gemini, goal):
    assert client.post("/api/ai/suggest", json={"goal": goal}).status_code == 422
    assert gemini.calls == []


def test_output_text_joins_model_text_only():
    reply = {"steps": [
        {"type": "user_input", "content": [{"type": "text", "text": "питання"}]},
        {"type": "model_output", "content": [{"type": "text", "text": '{"a":'}, {"type": "text", "text": "1}"}]},
    ]}
    assert ai._output_text(reply) == '{"a":1}'
