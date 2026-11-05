"""Statistics over sets of check-in dates. Pure functions, no database access."""

from datetime import date, timedelta

DAY = timedelta(days=1)


def tracking_start(created: date, days: set[date]) -> date:
    # A habit can be marked for days before it was added to the tracker.
    return min(created, *days) if days else created


def current_streak(days: set[date], today: date) -> int:
    # An unmarked today does not break the streak yet: the day is not over.
    cursor = today if today in days else today - DAY
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= DAY
    return streak


def longest_streak(days: set[date]) -> int:
    best = run = 0
    previous = None
    for day in sorted(days):
        run = run + 1 if previous is not None and day - previous == DAY else 1
        best = max(best, run)
        previous = day
    return best


def rate(days: set[date], start: date, end: date) -> float:
    """Share of days in [start, end] that have a check-in."""
    if end < start:
        return 0.0
    total = (end - start).days + 1
    done = sum(start <= day <= end for day in days)
    return round(done / total, 4)


def weekly_counts(days: set[date], today: date, weeks: int = 12) -> list[dict]:
    this_monday = today - timedelta(days=today.weekday())
    mondays = [this_monday - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]
    counts = dict.fromkeys(mondays, 0)
    for day in days:
        monday = day - timedelta(days=day.weekday())
        if monday in counts:
            counts[monday] += 1
    return [{"week_start": monday, "count": count} for monday, count in counts.items()]


def heatmap(days: set[date], today: date, weeks: int = 26) -> list[dict]:
    """Days from the Monday `weeks - 1` weeks ago through today, oldest first."""
    first = today - timedelta(days=today.weekday(), weeks=weeks - 1)
    span = (today - first).days + 1
    return [{"day": d, "done": d in days} for d in (first + n * DAY for n in range(span))]


def summary(days: set[date], created: date, today: date) -> dict:
    start = tracking_start(created, days)
    return {
        "done_today": today in days,
        "current_streak": current_streak(days, today),
        "longest_streak": longest_streak(days),
        "total": len(days),
        "rate_30": rate(days, max(start, today - 29 * DAY), today),
        "last_7": [today - n * DAY in days for n in range(6, -1, -1)],
    }


def details(days: set[date], created: date, today: date) -> dict:
    start = tracking_start(created, days)
    return summary(days, created, today) | {
        "tracked_since": start,
        "days_tracked": (today - start).days + 1,
        "rate_all": rate(days, start, today),
        "weekly": weekly_counts(days, today),
        "heatmap": heatmap(days, today),
    }


def overview(habits: list[tuple[date, set[date]]], today: date) -> dict:
    """Totals across all habits. `habits` holds (created, check-in days) pairs."""
    starts = [tracking_start(created, days) for created, days in habits]

    def day_total(day: date) -> tuple[int, int]:
        # A habit counts toward a day only once its tracking has started.
        possible = sum(start <= day for start in starts)
        done = sum(day in days for _, days in habits)
        return done, possible

    daily = []
    for n in range(29, -1, -1):
        day = today - n * DAY
        done, possible = day_total(day)
        daily.append({"day": day, "done": done, "total": possible})

    by_weekday = [[0, 0] for _ in range(7)]
    for n in range(12 * 7):
        day = today - n * DAY
        done, possible = day_total(day)
        by_weekday[day.weekday()][0] += done
        by_weekday[day.weekday()][1] += possible

    done_30 = sum(d["done"] for d in daily)
    possible_30 = sum(d["total"] for d in daily)
    streaks = [(current_streak(days, today), longest_streak(days)) for _, days in habits]
    return {
        "today": today,
        "habits": len(habits),
        "done_today": daily[-1]["done"],
        "rate_30": round(done_30 / possible_30, 4) if possible_30 else 0.0,
        "best_current_streak": max((cur for cur, _ in streaks), default=0),
        "longest_streak": max((best for _, best in streaks), default=0),
        "daily": daily,
        "weekdays": [round(done / possible, 4) if possible else 0.0 for done, possible in by_weekday],
    }
