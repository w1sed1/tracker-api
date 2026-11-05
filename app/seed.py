"""Fill an empty database with demo habits and 90 days of history: python -m app.seed"""

import random
from contextlib import closing
from datetime import date, timedelta

from . import db

DEMO = [
    ("Вода 2 літри", "#3b82f6", 0.85),
    ("Читання 20 хвилин", "#10b981", 0.65),
    ("Зарядка", "#f59e0b", 0.5),
    ("Без соцмереж після 22:00", "#8b5cf6", 0.35),
]


def main() -> None:
    db.init()
    with closing(db.connect()) as conn:
        if db.list_habits(conn):
            print(f"{db.DB_PATH} вже містить звички, демо-дані не додано.")
            return
        rng = random.Random(42)
        today = date.today()
        start = today - timedelta(days=89)
        for name, color, chance in DEMO:
            habit = db.create_habit(conn, name, color, start)
            for n in range(90):
                if rng.random() < chance:
                    db.set_checkin(conn, habit["id"], start + timedelta(days=n), True)
    print(f"Додано {len(DEMO)} демо-звички в {db.DB_PATH}")


if __name__ == "__main__":
    main()
