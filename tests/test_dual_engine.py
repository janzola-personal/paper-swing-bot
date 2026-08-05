"""Dual-engine isolation: per-strategy state, scoped flatten, non-interference."""

from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

import config
from actions import flatten_now, reset_hard_halt, set_paused
from db.store import MemoryStore, SQLiteStore
from engine import run_once
from risk import BotState, check_limits, size_shares


def _bars(n: int = 250, last_close: float = 100.0, end: date | None = None) -> pd.DataFrame:
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


def _mock_broker(*, equity=10_000.0, cash=10_000.0, held=None, mtm=None):
    b = MagicMock()
    b.market_open_now.return_value = False
    b.equity_and_cash.return_value = (equity, cash)
    b.positions.return_value = dict(held or {})
    b.flatten_all.return_value = []
    b.flatten_symbols.return_value = []
    b.submit_market.return_value = "ord-test"
    b.open_orders.return_value = []
    b._mtm_prices = dict(mtm or {})
    return b


def test_engine_specs_disjoint_symbols():
    swing = config.SWING_ENGINE
    lev = config.LEV_TREND_ENGINE
    assert set(swing.symbols).isdisjoint(set(lev.symbols))
    assert swing.strategy == "rsi2"
    assert lev.strategy == "lev_trend"
    assert lev.allocation == 20_000.0


def test_per_strategy_state_isolation_memory():
    store = MemoryStore()
    a = BotState(peak_equity=100_000, paused=False)
    b = BotState(peak_equity=20_000, paused=True, virtual_cash=20_000)
    store.save_state(a, "rsi2")
    store.save_state(b, "lev_trend")
    assert store.load_state("rsi2").paused is False
    assert store.load_state("lev_trend").paused is True
    assert store.load_state("lev_trend").virtual_cash == 20_000


def test_sqlite_per_strategy_state_and_journal():
    store = SQLiteStore()
    store.save_state(BotState(peak_equity=1.0), "rsi2")
    store.save_state(BotState(peak_equity=2.0, virtual_cash=20_000), "lev_trend")
    assert store.load_state("rsi2").peak_equity == 1.0
    assert store.load_state("lev_trend").virtual_cash == 20_000
    store.append_journal(
        trading_day=date(2026, 7, 28),
        symbol="SPY",
        action="buy",
        qty=1,
        ref_price=100.0,
        reason="t",
        equity=1.0,
        cash=1.0,
        dry_run=False,
        strategy="rsi2",
    )
    store.append_journal(
        trading_day=date(2026, 7, 28),
        symbol="QLD",
        action="buy",
        qty=1,
        ref_price=50.0,
        reason="t",
        equity=2.0,
        cash=2.0,
        dry_run=False,
        strategy="lev_trend",
    )
    assert len(store.list_journal(strategy="rsi2")) == 1
    assert store.list_journal(strategy="rsi2")[0]["symbol"] == "SPY"
    assert store.list_journal(strategy="lev_trend")[0]["symbol"] == "QLD"


def test_halted_lev_trend_does_not_block_swing():
    day = date(2026, 7, 27)
    store = MemoryStore()
    store.save_state(
        BotState(halted=True, halted_reason="lev dd", peak_equity=20_000, virtual_cash=18_000),
        "lev_trend",
    )
    store.save_state(BotState(peak_equity=100_000), "rsi2")
    broker = _mock_broker(equity=100_000, cash=100_000)
    bars = _bars()

    def fetch(sym: str, years: int = 2):
        return bars.copy()

    r = run_once(
        day,
        submit=False,
        shadow=True,
        store=store,
        broker=broker,
        fetch_bars=fetch,
        engine="swing",
    )
    assert r.status == "ok"
    assert r.strategy == "rsi2"
    # lev_trend still halted
    assert store.load_state("lev_trend").halted is True


def test_check_limits_respects_engine_overrides():
    today = date(2026, 7, 27)
    state = BotState(peak_equity=10_000.0)
    # 12% drawdown: fails at 10% limit, passes at 15%
    ok_strict, _ = check_limits(
        state, equity=8_800.0, today=today, max_drawdown_halt_pct=0.10
    )
    assert not ok_strict
    state2 = BotState(peak_equity=10_000.0)
    ok_loose, _ = check_limits(
        state2, equity=8_800.0, today=today, max_drawdown_halt_pct=0.15
    )
    assert ok_loose


def test_size_shares_engine_pct_override():
    assert size_shares(100.0, 10_000.0, 10_000.0, max_position_pct=1.0) == 100
    assert size_shares(100.0, 10_000.0, 10_000.0, max_position_pct=0.5) == 50


def test_actions_scoped_to_engine():
    store = MemoryStore()
    set_paused(True, "owner@x.com", store=store, engine="lev_trend")
    assert store.load_state("lev_trend").paused is True
    assert store.load_state("rsi2").paused is False
    assert store.journal[-1]["strategy"] == "lev_trend"

    reset_hard_halt("owner@x.com", store=store, engine="lev_trend")
    assert store.load_state("lev_trend").halted is False


def test_flatten_symbols_called_for_engine(monkeypatch):
    store = MemoryStore()
    monkeypatch.setenv("BOT_SHADOW_MODE", "true")
    monkeypatch.setenv("BOT_SHADOW_MODE_LEV_TREND", "true")
    broker = MagicMock()
    broker.equity_and_cash.return_value = (100_000.0, 80_000.0)
    broker.flatten_symbols.return_value = ["[dry-run] would SELL 10 QLD"]
    out = flatten_now("a@b.co", store=store, broker=broker, engine="lev_trend")
    assert out["engine"] == "lev_trend"
    broker.flatten_symbols.assert_called_once()
    args, kwargs = broker.flatten_symbols.call_args
    assert "QLD" in args[0]


def test_swing_regression_shadow_run_unchanged_shape():
    """Swing engine still journals under strategy=rsi2 and completes ok."""
    day = date(2026, 7, 27)
    store = MemoryStore()
    broker = _mock_broker()
    bars = _bars()

    def fetch(sym: str, years: int = 2):
        return bars.copy()

    r = run_once(
        day,
        submit=False,
        shadow=True,
        store=store,
        broker=broker,
        fetch_bars=fetch,
        engine=config.SWING_ENGINE,
    )
    assert r.status == "ok"
    assert r.strategy == "rsi2"
    assert r.engine == "swing"
    assert any(j.get("strategy") == "rsi2" for j in store.journal)
    assert store.get_run(day, "rsi2")["status"] == "ok"
