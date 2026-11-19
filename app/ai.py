"""AI analysis of habit statistics through the Google Gemini Interactions API.

Plain REST over the standard library: one POST per request, JSON in and out.
Docs: https://ai.google.dev/gemini-api/docs (Interactions API, structured output).
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
API_REVISION = "2026-05-20"
# The second model is a fallback for when the first one is overloaded or rate-limited.
MODELS = ("gemini-3.8-flash", "gemini-3.5-flash-lite")
RETRYABLE = {429, 500, 503, 504}
TIMEOUT = 60

COACH = """Ти — уважний коуч зі звичок. Отримуєш статистику трекера звичок у JSON.
Пиши українською, коротко й конкретно, звертайся до користувача на «ви».
Спирайся лише на цифри з даних: серії, відсоток виконання, тижні, дні тижня.
Не вигадуй фактів, яких немає в даних. Не давай медичних порад."""

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Загальна оцінка, 2–3 речення."},
        "strengths": {
            "type": "array",
            "description": "Що вже виходить добре.",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        },
        "habits": {
            "type": "array",
            "description": "Порада для кожної звички з даних.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "id звички з даних."},
                    "status": {"type": "string", "enum": ["стабільно", "нестабільно", "під загрозою"]},
                    "advice": {"type": "string", "description": "Одна конкретна порада, 1–2 речення."},
                },
                "required": ["id", "status", "advice"],
            },
        },
        "focus": {"type": "string", "description": "Одна головна дія на наступний тиждень."},
    },
    "required": ["summary", "strengths", "habits", "focus"],
}

SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "habits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Назва звички, до 40 символів, з мірою: «Прогулянка 20 хвилин»."},
                    "why": {"type": "string", "description": "Чому вона допоможе досягти цілі, одне речення."},
                },
                "required": ["name", "why"],
            },
            "minItems": 3,
            "maxItems": 3,
        },
    },
    "required": ["habits"],
}


class AIError(Exception):
    """The analysis could not be produced; the message is safe to show to the user."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def api_key() -> str | None:
    """GEMINI_API_KEY from the environment, or from a GEMINI_API_KEY=... line in .env."""
    if key := os.environ.get("GEMINI_API_KEY"):
        return key
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "GEMINI_API_KEY":
                return value.strip().strip("\"'") or None
    return None


def _post(model: str, body: dict, key: str) -> dict:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps({"model": model, **body}).encode(),
        headers={
            "x-goog-api-key": key,
            "Content-Type": "application/json",
            "Api-Revision": API_REVISION,
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def _output_text(interaction: dict) -> str:
    return "".join(
        block.get("text", "")
        for step in interaction.get("steps", [])
        if step.get("type") == "model_output"
        for block in step.get("content", [])
        if block.get("type") == "text"
    )


def ask(prompt: str, schema: dict) -> tuple[dict, dict]:
    """Sends one prompt with a JSON schema; returns (parsed answer, meta about the call)."""
    key = api_key()
    if not key:
        raise AIError("Не задано GEMINI_API_KEY — AI-функції вимкнені", 503)
    body = {
        "system_instruction": COACH,
        "input": prompt,
        "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
        "store": False,
    }
    started = time.perf_counter()
    for model in MODELS:
        try:
            interaction = _post(model, body, key)
        except urllib.error.HTTPError as err:
            if err.code in RETRYABLE:
                continue
            raise AIError(f"Gemini API відхилив запит ({err.code})") from err
        except (urllib.error.URLError, TimeoutError):
            continue
        try:
            answer = json.loads(_output_text(interaction))
        except json.JSONDecodeError:
            continue
        usage = interaction.get("usage", {})
        return answer, {
            "model": model,
            "seconds": round(time.perf_counter() - started, 1),
            "input_tokens": usage.get("total_input_tokens", 0),
            "output_tokens": usage.get("total_output_tokens", 0) + usage.get("total_thought_tokens", 0),
        }
    raise AIError("Gemini зараз недоступний або перевантажений, спробуйте за хвилину", 503)


def report(habits: list[dict], overview: dict) -> dict:
    """`habits` are habits with detailed stats, `overview` is stats.overview()."""
    data = {
        "today": overview["today"],
        "overall": {
            "rate_30": overview["rate_30"],
            "done_today": f'{overview["done_today"]} з {overview["habits"]}',
            "weekday_rates": dict(zip(["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"], overview["weekdays"])),
        },
        "habits": [
            {
                "id": h["id"],
                "name": h["name"],
                "days_tracked": h["stats"]["days_tracked"],
                "current_streak": h["stats"]["current_streak"],
                "longest_streak": h["stats"]["longest_streak"],
                "rate_30": h["stats"]["rate_30"],
                "rate_all": h["stats"]["rate_all"],
                "last_7_days": h["stats"]["last_7"],
                "per_week_last_12": [w["count"] for w in h["stats"]["weekly"]],
            }
            for h in habits
        ],
    }
    prompt = (
        "Проаналізуй мою статистику звичок і дай поради. "
        "Частки rate_* — від 0 до 1, per_week_last_12 — відмітки за тиждень (з 7), від старого до нового.\n"
        + json.dumps(data, ensure_ascii=False, default=str)
    )
    answer, meta = ask(prompt, REPORT_SCHEMA)
    names = {h["id"]: h["name"] for h in habits}
    # The model may echo an id that is not in the data; such advice has nothing to attach to.
    answer["habits"] = [item | {"name": names[item["id"]]} for item in answer["habits"] if item["id"] in names]
    return answer | {"meta": meta}


def suggest(goal: str, existing: list[str]) -> dict:
    prompt = (
        f"Моя ціль: {goal}\n"
        f"Звички, які я вже відстежую: {', '.join(existing) or 'немає'}.\n"
        "Запропонуй 3 нові щоденні звички, які легко відмітити як виконані чи ні."
    )
    answer, meta = ask(prompt, SUGGEST_SCHEMA)
    # maxLength is not enforced by the API, and the tracker stores names up to 100 characters.
    habits = [{"name": h["name"].strip()[:100], "why": h["why"]} for h in answer["habits"] if h["name"].strip()]
    return {"habits": habits, "meta": meta}
