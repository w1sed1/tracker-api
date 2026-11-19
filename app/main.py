import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints

from . import ai, db, stats

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    yield


app = FastAPI(title="Трекер звичок", lifespan=lifespan)


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def get_today() -> date:
    return date.today()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
Today = Annotated[date, Depends(get_today)]


class HabitIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    color: Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")] = "#4f7cff"


class GoalIn(BaseModel):
    goal: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]


def existing_habit(conn: sqlite3.Connection, habit_id: int) -> dict:
    habit = db.get_habit(conn, habit_id)
    if habit is None:
        raise HTTPException(404, "Звичку не знайдено")
    return habit


@app.get("/api/habits")
def list_habits(conn: Conn, today: Today):
    days = db.checkins(conn)
    return [
        habit | {"stats": stats.summary(days.get(habit["id"], set()), habit["created_on"], today)}
        for habit in db.list_habits(conn)
    ]


@app.post("/api/habits", status_code=201)
def create_habit(body: HabitIn, conn: Conn, today: Today):
    return db.create_habit(conn, body.name, body.color, today)


@app.put("/api/habits/{habit_id}")
def update_habit(habit_id: int, body: HabitIn, conn: Conn):
    existing_habit(conn, habit_id)
    return db.update_habit(conn, habit_id, body.name, body.color)


@app.delete("/api/habits/{habit_id}", status_code=204)
def delete_habit(habit_id: int, conn: Conn):
    if not db.delete_habit(conn, habit_id):
        raise HTTPException(404, "Звичку не знайдено")
    return Response(status_code=204)


@app.get("/api/habits/{habit_id}/stats")
def habit_stats(habit_id: int, conn: Conn, today: Today):
    habit = existing_habit(conn, habit_id)
    days = db.checkins(conn, habit_id).get(habit_id, set())
    return habit | {"stats": stats.details(days, habit["created_on"], today)}


def _set_checkin(habit_id: int, day: date, done: bool, conn: sqlite3.Connection, today: date) -> Response:
    existing_habit(conn, habit_id)
    if day > today:
        raise HTTPException(422, "Не можна відмічати майбутні дні")
    db.set_checkin(conn, habit_id, day, done)
    return Response(status_code=204)


@app.put("/api/habits/{habit_id}/checkins/{day}", status_code=204)
def mark_day(habit_id: int, day: date, conn: Conn, today: Today):
    return _set_checkin(habit_id, day, True, conn, today)


@app.delete("/api/habits/{habit_id}/checkins/{day}", status_code=204)
def unmark_day(habit_id: int, day: date, conn: Conn, today: Today):
    return _set_checkin(habit_id, day, False, conn, today)


@app.get("/api/overview")
def overview(conn: Conn, today: Today):
    days = db.checkins(conn)
    habits = [(h["created_on"], days.get(h["id"], set())) for h in db.list_habits(conn)]
    return stats.overview(habits, today)


@app.post("/api/ai/report")
def ai_report(conn: Conn, today: Today):
    days = db.checkins(conn)
    habits = db.list_habits(conn)
    if not habits:
        raise HTTPException(422, "Додайте хоча б одну звичку")
    detailed = [h | {"stats": stats.details(days.get(h["id"], set()), h["created_on"], today)} for h in habits]
    totals = stats.overview([(h["created_on"], days.get(h["id"], set())) for h in habits], today)
    try:
        return ai.report(detailed, totals)
    except ai.AIError as err:
        raise HTTPException(err.status, str(err)) from err


@app.post("/api/ai/suggest")
def ai_suggest(body: GoalIn, conn: Conn):
    try:
        return ai.suggest(body.goal, [h["name"] for h in db.list_habits(conn)])
    except ai.AIError as err:
        raise HTTPException(err.status, str(err)) from err


# Registered last so the /api routes above take precedence.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
