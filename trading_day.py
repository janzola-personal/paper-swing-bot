"""
Trading-day helpers (America/New_York).

All session dates for the bot come from here — never date.today() on a server.
Uses Alpaca's market calendar (open/close times, including early closes).
Calendar fetch is injectable so unit tests never hit the network.

Docs: alpaca-py TradingClient.get_calendar / GetCalendarRequest
https://alpaca.markets/sdks/python/
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol, Sequence
from zoneinfo import ZoneInfo

from alpaca.trading.requests import GetCalendarRequest

ET = ZoneInfo("America/New_York")
REGULAR_CLOSE = time(16, 0)  # 4:00pm Eastern on a full session


@dataclass(frozen=True)
class Session:
    """One NYSE/Nasdaq equity session in America/New_York."""

    date: date
    open_et: datetime  # tz-aware ET
    close_et: datetime  # tz-aware ET

    @property
    def is_half_day(self) -> bool:
        """True when the session closes before the regular 4:00pm ET close."""
        local_close = self.close_et.astimezone(ET).time()
        return local_close < REGULAR_CLOSE


class CalendarClient(Protocol):
    def get_calendar(self, filters: GetCalendarRequest | None = None) -> Sequence[object]:
        ...


def now_et(now: datetime | None = None) -> datetime:
    """Current time (or `now`) expressed in America/New_York."""
    if now is None:
        return datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (pass UTC or ET explicitly)")
    return now.astimezone(ET)


def et_calendar_date(now: datetime | None = None) -> date:
    """Wall-clock calendar date in America/New_York (not the UTC date)."""
    return now_et(now).date()


def _as_et(session_date: date, wall: datetime) -> datetime:
    """Alpaca Calendar open/close are naive local ET datetimes — attach ET tz."""
    if wall.tzinfo is not None:
        return wall.astimezone(ET)
    return datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        wall.hour,
        wall.minute,
        wall.second,
        tzinfo=ET,
    )


def session_from_alpaca_row(row: object) -> Session:
    d = row.date if isinstance(row.date, date) else date.fromisoformat(str(row.date))
    return Session(date=d, open_et=_as_et(d, row.open), close_et=_as_et(d, row.close))


def sessions_from_rows(rows: Sequence[object]) -> list[Session]:
    return [session_from_alpaca_row(r) for r in rows]


def fetch_sessions(
    start: date,
    end: date,
    *,
    client: CalendarClient | None = None,
) -> list[Session]:
    """Load sessions from Alpaca between start and end (inclusive)."""
    c = client or _trading_client()
    rows = c.get_calendar(GetCalendarRequest(start=start, end=end))
    return sessions_from_rows(rows)


def _trading_client():
    """Paper TradingClient for calendar only (no order path)."""
    from alpaca.trading.client import TradingClient

    key = os.environ.get("ALPACA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError(
            "Missing ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY for calendar fetch"
        )
    return TradingClient(key, secret, paper=True)


def _index_sessions(sessions: Sequence[Session]) -> dict[date, Session]:
    return {s.date: s for s in sessions}


def get_session(
    day: date,
    *,
    calendar: Sequence[Session] | None = None,
    client: CalendarClient | None = None,
) -> Session | None:
    """Return the Session for `day`, or None if holiday/weekend / not listed."""
    if calendar is not None:
        return _index_sessions(calendar).get(day)
    # Narrow live fetch around the date
    rows = fetch_sessions(day - timedelta(days=3), day + timedelta(days=3), client=client)
    return _index_sessions(rows).get(day)


def is_trading_day(
    day: date,
    *,
    calendar: Sequence[Session] | None = None,
    client: CalendarClient | None = None,
) -> bool:
    return get_session(day, calendar=calendar, client=client) is not None


def is_half_day(
    day: date,
    *,
    calendar: Sequence[Session] | None = None,
    client: CalendarClient | None = None,
) -> bool:
    s = get_session(day, calendar=calendar, client=client)
    return bool(s and s.is_half_day)


def resolve_trading_day(
    now: datetime | None = None,
    *,
    calendar: Sequence[Session] | None = None,
    client: CalendarClient | None = None,
) -> date | None:
    """Session date for bot state keys (idempotency, day-start, journal).

    Uses the America/New_York wall-clock date, then looks it up on the Alpaca
    calendar. Returns None on weekends/holidays (caller should no-op).

    Critical for hosted runs: after ~8pm ET the UTC *calendar* date has already
    rolled forward, but the trading day is still the ET session date.
    """
    et_day = et_calendar_date(now)
    if calendar is None and client is None:
        # Live path: fetch a small window around ET today
        calendar = fetch_sessions(et_day - timedelta(days=5), et_day + timedelta(days=2))
    return et_day if is_trading_day(et_day, calendar=calendar, client=client) else None


def require_trading_day(
    now: datetime | None = None,
    *,
    calendar: Sequence[Session] | None = None,
    client: CalendarClient | None = None,
) -> date:
    """Like resolve_trading_day but raises if markets are closed today (ET)."""
    d = resolve_trading_day(now, calendar=calendar, client=client)
    if d is None:
        et = et_calendar_date(now)
        raise RuntimeError(f"Not a US equity trading day (ET date={et.isoformat()})")
    return d
