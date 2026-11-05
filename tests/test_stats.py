from datetime import date

from app import stats

TODAY = date(2026, 11, 6)  # Friday


def nov(*days: int) -> set[date]:
    return {date(2026, 11, d) for d in days}


def test_current_streak_does_not_break_on_unmarked_today():
    assert stats.current_streak(nov(4, 5), TODAY) == 2
    assert stats.current_streak(nov(4, 5, 6), TODAY) == 3
    assert stats.current_streak(nov(3, 5), TODAY) == 1


def test_current_streak_breaks_on_missed_yesterday():
    assert stats.current_streak(nov(4), TODAY) == 0
    assert stats.current_streak(set(), TODAY) == 0


def test_longest_streak():
    assert stats.longest_streak(nov(1, 2, 3, 5, 6)) == 3
    assert stats.longest_streak({date(2026, 10, 31), date(2026, 11, 1)}) == 2
    assert stats.longest_streak(set()) == 0


def test_rate():
    assert stats.rate(nov(1, 3, 9), date(2026, 11, 1), date(2026, 11, 4)) == 0.5
    assert stats.rate(nov(1), date(2026, 11, 2), date(2026, 11, 1)) == 0.0


def test_weekly_counts():
    days = nov(2, 6) | {date(2026, 10, 26), date(2026, 1, 1)}
    weeks = stats.weekly_counts(days, TODAY)
    assert len(weeks) == 12
    assert weeks[0]["week_start"] == date(2026, 8, 17)
    assert weeks[-2] == {"week_start": date(2026, 10, 26), "count": 1}
    assert weeks[-1] == {"week_start": date(2026, 11, 2), "count": 2}


def test_heatmap_starts_on_monday_and_ends_today():
    cells = stats.heatmap(nov(6), TODAY)
    assert cells[0] == {"day": date(2026, 5, 11), "done": False}
    assert cells[-1] == {"day": TODAY, "done": True}
    assert len(cells) == 25 * 7 + 5


def test_summary():
    s = stats.summary(nov(1, 5, 6), date(2026, 11, 1), TODAY)
    assert s == {
        "done_today": True,
        "current_streak": 2,
        "longest_streak": 2,
        "total": 3,
        "rate_30": 0.5,
        "last_7": [False, True, False, False, False, True, True],
    }


def test_details_tracks_from_earliest_checkin():
    d = stats.details(nov(1), date(2026, 11, 5), TODAY)
    assert d["tracked_since"] == date(2026, 11, 1)
    assert d["days_tracked"] == 6
    assert d["rate_all"] == 0.1667


def test_overview_counts_habits_only_after_they_start():
    habits = [(date(2026, 11, 4), nov(4, 5, 6)), (date(2026, 11, 6), set())]
    o = stats.overview(habits, TODAY)
    assert o["habits"] == 2
    assert o["done_today"] == 1
    assert o["rate_30"] == 0.75
    assert o["best_current_streak"] == 3
    assert o["longest_streak"] == 3
    assert o["daily"][-1] == {"day": TODAY, "done": 1, "total": 2}
    assert o["daily"][-4] == {"day": date(2026, 11, 3), "done": 0, "total": 0}
    assert o["weekdays"] == [0.0, 0.0, 1.0, 1.0, 0.5, 0.0, 0.0]


def test_overview_without_habits():
    o = stats.overview([], TODAY)
    assert (o["habits"], o["done_today"], o["rate_30"], o["longest_streak"]) == (0, 0, 0.0, 0)
