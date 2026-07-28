"""Idempotent run_once + SQLite store (no network, no secrets)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

import config
from db.store import MemoryStore, SQLiteStore
from engine import run_once


def _bars(
    n: int = 250,
    last_close: float = 100.0,
    *,
    end: date | None = None,
) -> pd.DataFrame:
    """Synthetic daily bars with enough history for SMA(200).

    `end` defaults to a recent session so C3 stale-data checks pass when the
    trading day is 2026-07-27.
    """
    idx = pd.bdate_range(end=pd.Timestamp(end or date(2026, 7, 27)), periods=n)
    close = np.linspace(80.0, last_close, n)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(n, 1_000_000),
        },
        index=idx,
    )


def _mock_broker(*, equity: float = 10_000.0, cash: float = 10_000.0, held=None):
    b = MagicMock()
    b.market_open_now.return_value = False
    b.equity_and_cash.return_value = (equity, cash)
    b.positions.return_value = dict(held or {})
    b.flatten_all.return_value = []
    b.submit_market.return_value = "ord-test"
    b.open_orders.return_value = []
    return b


@pytest.fixture
def day() -> date:
    return date(2026, 7, 27)


def test_second_run_same_day_skipped_duplicate_no_orders(day, monkeypatch):
    monkeypatch.setattr(config, "ACTIVE_STRATEGY", "rsi2")
    store = MemoryStore()
    broker = _mock_broker()
    bars = _bars()

    def fetch(sym: str, years: int = 2):
        return bars.copy()

    r1 = run_once(
        day,
        submit=True,
        shadow=False,
        store=store,
        broker=broker,
        fetch_bars=fetch,
    )
    assert r1.status == "ok"
    first_calls = broker.submit_market.call_count

    r2 = run_once(
        day,
        submit=True,
        shadow=False,
        store=store,
        broker=broker,
        fetch_bars=fetch,
    )
    assert r2.status == "skipped_duplicate"
    assert r2.orders_submitted == 0
    assert broker.submit_market.call_count == first_calls  # no new orders


def test_shadow_never_submits(day, monkeypatch):
    monkeypatch.setattr(config, "ACTIVE_STRATEGY", "rsi2")
    store = MemoryStore()
    broker = _mock_broker()
    r = run_once(
        day,
        submit=True,
        shadow=True,
        store=store,
        broker=broker,
        fetch_bars=lambda s, y=2: _bars(),
    )
    assert r.status == "ok"
    assert r.mode == "shadow"
    assert broker.submit_market.call_count == 0
    assert r.orders_submitted == 0


def test_sqlite_unique_claim(day):
    store = SQLiteStore(":memory:")
    c1 = store.claim_run(day, "rsi2", "shadow")
    assert c1.acquired and c1.status == "claimed"
    # Incomplete claim is reclaimable (crash recovery); completed is unique.
    c_reclaim = store.claim_run(day, "rsi2", "shadow")
    assert c_reclaim.acquired and c_reclaim.status == "reclaimed"
    store.complete_run(day, "rsi2", "ok")
    c2 = store.claim_run(day, "rsi2", "shadow")
    assert not c2.acquired and c2.status == "skipped_duplicate"


def test_sqlite_state_roundtrip(day):
    store = SQLiteStore(":memory:")
    state = store.load_state()
    state.peak_equity = 12_345.0
    state.paused = True
    state.day_start_date = day.isoformat()
    store.save_state(state)
    loaded = store.load_state()
    assert loaded.peak_equity == 12_345.0
    assert loaded.paused is True
    assert loaded.day_start_date == day.isoformat()


def test_paused_exits_without_broker_orders(day, monkeypatch):
    monkeypatch.setattr(config, "ACTIVE_STRATEGY", "rsi2")
    store = MemoryStore()
    st = store.load_state()
    st.paused = True
    store.save_state(st)
    broker = _mock_broker()
    r = run_once(day, submit=True, store=store, broker=broker, fetch_bars=lambda s, y=2: _bars())
    assert r.status == "paused"
    assert broker.equity_and_cash.call_count == 0
    assert broker.submit_market.call_count == 0
