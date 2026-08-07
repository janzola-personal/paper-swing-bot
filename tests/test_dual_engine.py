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


def test_shadow_buy_survives_overnight_without_false_drawdown_halt():
    """Allocated shadow buy must MTM via shadow_positions next day (not ~$24 halt).

    Look-ahead: signals still use bar-t close only; this only persists the
    simulated fill book when the broker never receives an order.
    """
    day1 = date(2026, 7, 27)
    day2 = date(2026, 7, 28)
    px = 90.0
    store = MemoryStore()
    store.save_state(
        BotState(peak_equity=20_000.0, virtual_cash=20_000.0),
        "lev_trend",
    )
    # Broker never fills shadow orders — empty held both days.
    broker = _mock_broker(equity=100_000, cash=100_000, held={}, mtm={"QLD": px})
    bars = _bars(n=250, last_close=px, end=day1)

    def fetch(sym: str, years: int = 2):
        return bars.copy()

    r1 = run_once(
        day1,
        submit=False,
        shadow=True,
        store=store,
        broker=broker,
        fetch_bars=fetch,
        engine="lev_trend",
    )
    assert r1.status == "ok", r1.messages
    st1 = store.load_state("lev_trend")
    assert "QLD" in st1.shadow_positions
    qty = st1.shadow_positions["QLD"]
    assert qty > 0
    assert st1.virtual_cash < 20_000.0
    # Leftover cash alone would look like a wipeout without the shadow book.
    assert st1.virtual_cash < 20_000.0 * 0.10

    bars2 = _bars(n=250, last_close=px, end=day2)

    def fetch2(sym: str, years: int = 2):
        return bars2.copy()

    r2 = run_once(
        day2,
        submit=False,
        shadow=True,
        store=store,
        broker=broker,
        fetch_bars=fetch2,
        engine="lev_trend",
    )
    assert r2.status == "ok", r2.messages
    st2 = store.load_state("lev_trend")
    assert not st2.halted
    expected = st2.virtual_cash + qty * px
    assert r2.equity == pytest.approx(expected, rel=1e-6, abs=1.0)
    assert r2.equity > 15_000.0  # near allocation, not leftover ~$24


def test_submit_lev_trend_uses_broker_held_not_stale_shadow():
    """place_orders syncs shadow from broker; sizing/halts use broker book."""
    day = date(2026, 7, 27)
    px = 100.0
    store = MemoryStore()
    # Stale shadow book must not inflate equity when submitting for real.
    store.save_state(
        BotState(
            peak_equity=20_000.0,
            virtual_cash=10_000.0,
            shadow_positions={"QLD": 999},
        ),
        "lev_trend",
    )
    broker = _mock_broker(
        equity=100_000,
        cash=100_000,
        held={"QLD": 100},
        mtm={"QLD": px},
    )
    bars = _bars(n=250, last_close=px, end=day)

    def fetch(sym: str, years: int = 2):
        return bars.copy()

    r = run_once(
        day,
        submit=True,
        shadow=False,
        store=store,
        broker=broker,
        fetch_bars=fetch,
        engine="lev_trend",
    )
    assert r.status == "ok", r.messages
    st = store.load_state("lev_trend")
    assert st.shadow_positions == {"QLD": 100}
    # Equity = virtual_cash + broker qty * px = 10k + 10k
    assert r.equity == pytest.approx(20_000.0, abs=1.0)


def test_sqlite_shadow_positions_roundtrip():
    store = SQLiteStore()
    store.save_state(
        BotState(virtual_cash=24.0, shadow_positions={"QLD": 220}, peak_equity=20_000),
        "lev_trend",
    )
    loaded = store.load_state("lev_trend")
    assert loaded.shadow_positions == {"QLD": 220}
    assert loaded.virtual_cash == 24.0
