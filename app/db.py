"""SQLite storage. Dates are stored as ISO strings (YYYY-MM-DD)."""

import os
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

DB_PATH = Path(os.environ.get("HABITS_DB", Path(__file__).resolve().parent.parent / "habits.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    color      TEXT NOT NULL,
    created_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkins (
    habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    day      TEXT NOT NULL,
    PRIMARY KEY (habit_id, day)
);
"""


def connect() -> sqlite3.Connection:
    # FastAPI may run a request's dependency and handler in different threads;
    # each connection still serves only one request at a time.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with closing(connect()) as conn:
        conn.executescript(SCHEMA)


def _habit(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "color": row["color"],
        "created_on": date.fromisoformat(row["created_on"]),
    }


def list_habits(conn: sqlite3.Connection) -> list[dict]:
    return [_habit(row) for row in conn.execute("SELECT * FROM habits ORDER BY id")]


def get_habit(conn: sqlite3.Connection, habit_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    return _habit(row) if row else None


def create_habit(conn: sqlite3.Connection, name: str, color: str, created_on: date) -> dict:
    with conn:
        cur = conn.execute(
            "INSERT INTO habits (name, color, created_on) VALUES (?, ?, ?)",
            (name, color, created_on.isoformat()),
        )
    return get_habit(conn, cur.lastrowid)


def update_habit(conn: sqlite3.Connection, habit_id: int, name: str, color: str) -> dict | None:
    with conn:
        conn.execute("UPDATE habits SET name = ?, color = ? WHERE id = ?", (name, color, habit_id))
    return get_habit(conn, habit_id)


def delete_habit(conn: sqlite3.Connection, habit_id: int) -> bool:
    with conn:
        return conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,)).rowcount > 0


def checkins(conn: sqlite3.Connection, habit_id: int | None = None) -> dict[int, set[date]]:
    """Check-in days per habit id, for one habit or for all of them."""
    sql, args = "SELECT habit_id, day FROM checkins", ()
    if habit_id is not None:
        sql, args = sql + " WHERE habit_id = ?", (habit_id,)
    result: dict[int, set[date]] = {}
    for row in conn.execute(sql, args):
        result.setdefault(row["habit_id"], set()).add(date.fromisoformat(row["day"]))
    return result


def set_checkin(conn: sqlite3.Connection, habit_id: int, day: date, done: bool) -> None:
    with conn:
        if done:
            conn.execute(
                "INSERT OR IGNORE INTO checkins (habit_id, day) VALUES (?, ?)",
                (habit_id, day.isoformat()),
            )
        else:
            conn.execute(
                "DELETE FROM checkins WHERE habit_id = ? AND day = ?",
                (habit_id, day.isoformat()),
            )
