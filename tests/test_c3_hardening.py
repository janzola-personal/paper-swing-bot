"""C3 failure-mode hardening — one test per mode."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

import config
from alpaca_retry import call_with_retries, is_retryable
from data import bar_stale_days, bars_are_stale, last_bar_date
from db.store import MemoryStore
from engine import run_once
from trading_day import ET, Session, resolve_trading_day
from watchdog_logic import check_run_present, run_watchdog, send_norun_email


def _session(d: date, close_hm=(16, 0)) -> Session:
    ch, cm = close_hm
    return Session(
        date=d,
        open_et=datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET),
        close_et=datetime(d.year, d.month, d.day, ch, cm, tzinfo=ET),
    )


def _bars_ending(last: date, n: int = 250, last_close: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    close = np.linspace(80.0, last_close, n)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def _broker(*, held=None):
    b = MagicMock()
    b.market_open_now.return_value = False
    b.equity_and_cash.return_value = (10_000.0, 10_000.0)
    b.positions.return_value = dict(held or {})
    b.flatten_all.return_value = []
    b.submit_market.return_value = "ord-1"
    b.open_orders.return_value = []
    return b


# ---------------------------------------------------------------------------
# 1. Stale data
# ---------------------------------------------------------------------------


def test_stale_bars_skip_journal_and_notify(monkeypatch):
    """Last bar >5 calendar days before trading day → skip, journal, ERROR notify."""
    monkeypatch.setattr(config, "ACTIVE_STRATEGY", "rsi2")
    day = date(2026, 7, 27)
    stale_last = day - timedelta(days=6)
    assert bars_are_stale(_bars_ending(stale_last), day)
    assert bar_stale_days(_bars_ending(stale_last), day) == 6
    assert last_bar_date(_bars_ending(stale_last)) == stale_last

    notified = {}

    def fake_error(**kwargs):
        notified.update(kwargs)
        return "sent:200"

    monkeypatch.setattr("notify.send_error", fake_error)

    store = MemoryStore()
    r = run_once(
        day,
        shadow=True,
        store=store,
        broker=_broker(),
        fetch_bars=lambda s, y=2: _bars_ending(stale_last),
    )
    assert r.status == "skipped_stale_data"
    assert r.notify_status == "sent:200"
    assert notified.get("error_class") == "StaleData"
    assert store.get_run(day, "rsi2")["status"] == "skipped_stale_data"
    assert any(j["action"] == "skip" and "Stale data" in (j["reason"] or "") for j in store.journal)
    assert r.orders_submitted == 0


def test_fresh_bars_within_5_calendar_days_ok(monkeypatch):
    monkeypatch.setattr(config, "ACTIVE_STRATEGY", "rsi2")
    day = date(2026, 7, 27)  # Monday — Friday bar is 3 calendar days old
    fri = date(2026, 7, 24)
    assert not bars_are_stale(_bars_ending(fri), day)
    store = MemoryStore()
    r = run_once(
        day,
        shadow=True,
        store=store,
        broker=_broker(),
        fetch_bars=lambda s, y=2: _bars_ending(fri),
    )
    assert r.status == "ok"


# ---------------------------------------------------------------------------
# 2. Alpaca timeout retry ×3
# ---------------------------------------------------------------------------


def test_alpaca_timeout_retries_three_times():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("alpaca timed out")
        return "ok"

    assert is_retryable(TimeoutError("x"))
    out = call_with_retries(flaky, attempts=3, sleep=lambda _d: None, label="test")
    assert out == "ok"
    assert calls["n"] == 3


def test_alpaca_timeout_exhausted_raises():
    def always():
        raise TimeoutError("still down")

    with pytest.raises(TimeoutError):
        call_with_retries(always, attempts=3, sleep=lambda _d: None, label="test")


# ---------------------------------------------------------------------------
# 3. Partial fill reconcile next run
# ---------------------------------------------------------------------------


def test_partial_fill_reconcile_no_topup_then_sell_remainder(monkeypatch):
    """After partial buy (held>0, want=1) → hold; want=0 → sell remaining qty."""
    monkeypatch.setattr(config, "ACTIVE_STRATEGY", "rsi2")
    monkeypatch.setattr(config, "SYMBOLS", ["SPY"])
    day = date(2026, 7, 27)
    bars = _bars_ending(day)

    # Force want==1 by stubbing desired_position_today
    monkeypatch.setattr(
        "engine.desired_position_today",
        lambda df, strategy: (1, "forced entry"),
    )
    store = MemoryStore()
    broker = _broker(held={"SPY": 3})  # partial fill from prior day
    r = run_once(
        day,
        submit=True,
        shadow=False,
        store=store,
        broker=broker,
        fetch_bars=lambda s, y=2: bars.copy(),
    )
    assert r.status == "ok"
    assert broker.submit_market.call_count == 0  # no top-up buy
    hold_rows = [j for j in store.journal if j["symbol"] == "SPY" and j["action"] == "hold"]
    assert hold_rows
    assert "already long 3" in hold_rows[0]["reason"]
    assert any(j["action"] == "reconcile" for j in store.journal)

    # Next day: exit signal — sell the 3 remaining (not an assumed full lot)
    store2 = MemoryStore()
    monkeypatch.setattr(
        "engine.desired_position_today",
        lambda df, strategy: (0, "forced exit"),
    )
    broker2 = _broker(held={"SPY": 3})
    r2 = run_once(
        date(2026, 7, 28),
        submit=True,
        shadow=False,
        store=store2,
        broker=broker2,
        fetch_bars=lambda s, y=2: bars.copy(),
    )
    assert r2.status == "ok"
    broker2.submit_market.assert_any_call("SPY", 3, "sell")


# ---------------------------------------------------------------------------
# 4. Market holidays via calendar
# ---------------------------------------------------------------------------


def test_holiday_skips_run_via_calendar(monkeypatch):
    """Presidents' Day 2026 injected calendar → skipped_not_trading_day."""
    monkeypatch.setattr(config, "ACTIVE_STRATEGY", "rsi2")
    presidents = date(2026, 2, 16)
    cal = [_session(date(2026, 2, 13)), _session(date(2026, 2, 17))]
    assert resolve_trading_day(
        datetime(2026, 2, 16, 17, 0, tzinfo=ET), calendar=cal
    ) is None

    store = MemoryStore()
    broker = _broker()
    r = run_once(
        presidents,
        shadow=True,
        store=store,
        broker=broker,
        fetch_bars=lambda s, y=2: _bars_ending(date(2026, 2, 13)),
        calendar=cal,
    )
    assert r.status == "skipped_not_trading_day"
    assert broker.equity_and_cash.call_count == 0
    assert store.get_run(presidents, "rsi2") is None  # never claimed


# ---------------------------------------------------------------------------
# 5. Crash mid-write → runs.status=error (+ reclaim)
# ---------------------------------------------------------------------------


def test_crash_mid_write_marks_run_error(monkeypatch):
    monkeypatch.setattr(config, "ACTIVE_STRATEGY", "rsi2")
    day = date(2026, 7, 27)
    store = MemoryStore()

    def boom(*_a, **_k):
        raise RuntimeError("simulated crash after claim")

    monkeypatch.setattr("notify.send_error", lambda **k: "sent:200")
    broker = _broker()
    broker.equity_and_cash.side_effect = boom

    r = run_once(
        day,
        shadow=True,
        store=store,
        broker=broker,
        fetch_bars=lambda s, y=2: _bars_ending(day),
    )
    assert r.status == "error"
    assert store.get_run(day, "rsi2")["status"] == "error"

    # Stuck 'claimed' can be reclaimed by a retrying scheduler
    store2 = MemoryStore()
    store2.claim_run(day, "rsi2", "shadow")
    assert store2.get_run(day, "rsi2")["status"] == "claimed"
    again = store2.claim_run(day, "rsi2", "shadow")
    assert again.acquired and again.status == "reclaimed"


# ---------------------------------------------------------------------------
# 6. Watchdog dedupe
# ---------------------------------------------------------------------------


def test_watchdog_norun_dedupe_once_per_day(monkeypatch):
    day = date(2026, 7, 27)
    store = MemoryStore()
    posts: list[int] = []

    monkeypatch.setattr(
        "notify.send_email",
        lambda subject, body, post=None, sleep=None: posts.append(1) or "sent:200",
    )

    assert check_run_present(day, store=store)["ok"] is False
    e1 = send_norun_email(day, "missing", store=store)
    e2 = send_norun_email(day, "missing", store=store)
    assert e1.startswith("sent")
    assert e2 == "skipped_already_sent"
    assert len(posts) == 1

    # Dual watchdog entrypoint also respects dedupe
    out = run_watchdog(day, store=store)
    assert out["run_ok"] is False
    assert out["email"] == "skipped_already_sent"
