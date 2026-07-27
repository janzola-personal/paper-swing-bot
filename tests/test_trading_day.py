"""trading_day.py — ET session dates, holidays, half-days (mocked calendar)."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from trading_day import (
    ET,
    Session,
    et_calendar_date,
    fetch_sessions,
    is_half_day,
    is_trading_day,
    now_et,
    resolve_trading_day,
    session_from_alpaca_row,
)

# Presidents' Day 2026 = third Monday in February
PRESIDENTS_DAY_2026 = date(2026, 2, 16)


def _session(d: date, open_hm=(9, 30), close_hm=(16, 0)) -> Session:
    oh, om = open_hm
    ch, cm = close_hm
    return Session(
        date=d,
        open_et=datetime(d.year, d.month, d.day, oh, om, tzinfo=ET),
        close_et=datetime(d.year, d.month, d.day, ch, cm, tzinfo=ET),
    )


# Fri Feb 13, Mon Feb 16 holiday, Tue Feb 17
FEB_2026_CAL = [
    _session(date(2026, 2, 13)),
    _session(date(2026, 2, 17)),
    _session(date(2026, 2, 18)),
]


def test_presidents_day_2026_not_a_trading_day():
    assert PRESIDENTS_DAY_2026.weekday() == 0  # Monday
    assert not is_trading_day(PRESIDENTS_DAY_2026, calendar=FEB_2026_CAL)
    noon_et = datetime(2026, 2, 16, 12, 0, tzinfo=ET)
    assert resolve_trading_day(noon_et, calendar=FEB_2026_CAL) is None
    # Adjacent sessions still resolve
    assert is_trading_day(date(2026, 2, 13), calendar=FEB_2026_CAL)
    assert is_trading_day(date(2026, 2, 17), calendar=FEB_2026_CAL)


def test_half_day_early_close():
    """Early close (e.g. day before Independence Day) closes before 4pm ET."""
    half = _session(date(2026, 7, 2), close_hm=(13, 0))  # 1:00pm ET
    full = _session(date(2026, 7, 1), close_hm=(16, 0))
    cal = [full, half]
    assert half.is_half_day
    assert not full.is_half_day
    assert is_half_day(date(2026, 7, 2), calendar=cal)
    assert not is_half_day(date(2026, 7, 1), calendar=cal)
    # Still a trading day — just shorter
    assert is_trading_day(date(2026, 7, 2), calendar=cal)
    assert resolve_trading_day(
        datetime(2026, 7, 2, 17, 0, tzinfo=ET), calendar=cal
    ) == date(2026, 7, 2)


def test_utc_server_date_differs_from_et_trading_day_after_4pm():
    """After ~8pm ET, UTC calendar date has rolled; trading day must stay on ET session.

    Mon 2026-07-27 21:00 EDT == Tue 2026-07-28 01:00 UTC.
    """
    session = _session(date(2026, 7, 27))
    cal = [session]
    now_utc = datetime(2026, 7, 28, 1, 0, 0, tzinfo=timezone.utc)
    assert now_utc.date() == date(2026, 7, 28)  # UTC wall date already Tuesday
    assert et_calendar_date(now_utc) == date(2026, 7, 27)
    assert resolve_trading_day(now_utc, calendar=cal) == date(2026, 7, 27)
    assert now_et(now_utc).hour == 21


def test_naive_datetime_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        now_et(datetime(2026, 7, 27, 17, 0, 0))


def test_fetch_sessions_uses_injected_client():
    """Mock Alpaca get_calendar — no network."""

    class FakeClient:
        def get_calendar(self, filters=None):
            # Mimic alpaca Calendar: naive open/close on session date
            d = date(2026, 2, 17)
            return [
                SimpleNamespace(
                    date=d,
                    open=datetime(2026, 2, 17, 9, 30),
                    close=datetime(2026, 2, 17, 16, 0),
                )
            ]

    sessions = fetch_sessions(date(2026, 2, 17), date(2026, 2, 17), client=FakeClient())
    assert len(sessions) == 1
    assert sessions[0].date == date(2026, 2, 17)
    assert sessions[0].open_et.tzinfo == ET
    assert sessions[0].close_et.hour == 16


def test_session_from_alpaca_row_half_day():
    row = SimpleNamespace(
        date=date(2026, 11, 27),
        open=datetime(2026, 11, 27, 9, 30),
        close=datetime(2026, 11, 27, 13, 0),
    )
    s = session_from_alpaca_row(row)
    assert s.is_half_day


def test_main_has_no_date_today_in_run_path():
    """Acceptance: run path must not call date.today()."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # date.today()
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "today"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "date"
            ):
                pytest.fail(f"main.py still calls date.today() at line {node.lineno}")
