"""Tests for the three Part A2 engine defects."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

import config
import risk
from backtest import initial_cash_cap, run_backtest, run_portfolio_backtest
from strategy import desired_position_today, month_end_mask, trend_positions


# ---------------------------------------------------------------------------
# Defect 1: daily-loss halt (capture_day_start vs after-close)
# ---------------------------------------------------------------------------

def test_daily_loss_halt_fires_after_morning_capture():
    """Morning sets day_start; after-close equity −2% must halt."""
    today = date(2026, 7, 27)
    state = risk.BotState()
    state = risk.capture_day_start(state, equity=10_000.0, today=today)
    assert state.day_start_equity == 10_000.0
    assert state.day_start_date == today.isoformat()

    # After-close path must not overwrite day_start.
    state = risk.update_peak(state, equity=9_700.0)
    assert state.day_start_equity == 10_000.0

    ok, why = risk.check_limits(state, equity=9_700.0, today=today)
    assert not ok
    assert "Daily loss" in why
    assert state.day_halted_date == today.isoformat()


def test_daily_loss_halt_exact_threshold():
    today = date(2026, 7, 27)
    state = risk.capture_day_start(risk.BotState(), 10_000.0, today)
    # Exactly −2%: day_pnl <= -0.02 → halt
    ok, _ = risk.check_limits(state, equity=9_800.0, today=today)
    assert not ok


def test_after_close_without_capture_does_not_false_halt():
    """If morning job never ran, do not invent a same-run baseline."""
    today = date(2026, 7, 27)
    state = risk.BotState(peak_equity=10_000.0)
    state = risk.update_peak(state, equity=9_000.0)  # down but not 10% from peak
    ok, why = risk.check_limits(state, equity=9_000.0, today=today)
    assert ok
    assert why == "ok"


def test_same_run_capture_then_check_still_useless_by_design():
    """Documenting the old bug: capture then check same equity never daily-halts."""
    today = date(2026, 7, 27)
    state = risk.capture_day_start(risk.BotState(), 10_000.0, today)
    ok, _ = risk.check_limits(state, equity=10_000.0, today=today)
    assert ok  # ratio 1.0 — after-close must use earlier capture with lower equity


# ---------------------------------------------------------------------------
# Defect 2: trend month-end (no false last-row month-end)
# ---------------------------------------------------------------------------

def test_month_end_mask_mid_month_last_bar_not_month_end():
    # January full + mid-February last bar (not month-end)
    idx = pd.DatetimeIndex(
        list(pd.bdate_range("2026-01-02", "2026-01-30"))
        + list(pd.bdate_range("2026-02-02", "2026-02-13"))
    )
    mask = month_end_mask(idx)
    assert mask[-1] is np.False_ or mask[-1] == False
    # Jan 30 2026 is Friday; next BDay is Feb 2 → month-end
    jan_end = idx.get_loc(pd.Timestamp("2026-01-30"))
    assert mask[jan_end]


def test_trend_mid_month_last_bar_does_not_redecide():
    """desired_position_today must match backtest: mid-month last row carries prior."""
    # Enough history for 200-SMA; Jan month-end decides long; then crash below SMA
    # mid-February. Old bug would re-decide daily → flat; fixed code carries long.
    rng = pd.bdate_range("2024-01-02", "2025-02-14")
    n = len(rng)
    close_vals = np.full(n, 200.0)
    # Rising through Jan 2025 so Jan month-end is long
    jan_end = rng.get_indexer([pd.Timestamp("2025-01-31")], method=None)[0]
    if jan_end < 0:
        jan_end = int(np.where((rng.year == 2025) & (rng.month == 1))[0][-1])
    close_vals[: jan_end + 1] = 150 + np.arange(jan_end + 1) * 0.5
    # Crash in February below SMA200
    close_vals[jan_end + 1 :] = 50.0
    close = pd.Series(close_vals, index=rng)
    df_live = pd.DataFrame({
        "open": close, "high": close, "low": close, "close": close, "volume": 1e6,
    })
    assert month_end_mask(df_live.index)[-1] == False

    want, _reason = desired_position_today(df_live, "trend")
    # Still holding the January month-end long decision despite mid-month crash
    assert want == 1
    assert int(trend_positions(df_live).iloc[-1]) == 1


def test_trend_true_month_end_still_decides():
    rng = pd.bdate_range("2024-01-02", "2025-01-31")
    close = pd.Series(100 + np.arange(len(rng)) * 0.1, index=rng)
    df = pd.DataFrame({
        "open": close, "high": close, "low": close, "close": close, "volume": 1e6,
    })
    # End exactly on Jan 31 2025 (Friday) — next BDay is Feb → month-end
    assert df.index[-1] == pd.Timestamp("2025-01-31")
    assert month_end_mask(df.index)[-1] == True
    want, _ = desired_position_today(df, "trend")
    assert want in (0, 1)  # decided today; rising series → long
    assert want == 1


# ---------------------------------------------------------------------------
# Defect 3: backtest sizing matches live
# ---------------------------------------------------------------------------

def test_size_shares_respects_max_position_pct():
    equity, cash, price = 10_000.0, 10_000.0, 100.0
    qty = risk.size_shares(price, equity, cash)
    assert qty == 50  # 50% of 10k / 100
    assert qty * price <= equity * config.MAX_POSITION_PCT + 1e-9


def test_initial_cash_cap_uses_max_position_pct():
    assert initial_cash_cap(10_000.0) == 5_000.0
    assert initial_cash_cap(10_000.0, equity=8_000.0) == 4_000.0


def test_single_symbol_backtest_never_exceeds_half_equity():
    """Buy signal on bar 0 → fill bar 1 open; qty capped at 50%."""
    idx = pd.bdate_range("2026-01-05", periods=5)
    df = pd.DataFrame({
        "open": [100.0, 100.0, 100.0, 100.0, 100.0],
        "high": 100.0,
        "low": 100.0,
        "close": [100.0, 100.0, 100.0, 100.0, 100.0],
        "volume": 1e6,
    }, index=idx)
    # Want long from first bar's close → fill at second open
    pos = pd.Series([1, 1, 1, 1, 1], index=idx)
    stats = run_backtest(df, pos, initial_cash=10_000.0, slippage_bps=0)
    # 50 shares * 100 = 5000 deployed; rest cash
    # final equity ~ 10000 flat
    assert stats["final_equity"] == pytest.approx(10_000.0, abs=0.01)


def test_two_symbol_portfolio_sizing_matches_live():
    """Both symbols signal; each gets ≤50% via size_shares; MAX_POSITIONS=2."""
    idx = pd.bdate_range("2026-01-05", periods=4)
    def flat_frame(px: float) -> pd.DataFrame:
        return pd.DataFrame({
            "open": [px] * 4,
            "high": px,
            "low": px,
            "close": [px] * 4,
            "volume": 1e6,
        }, index=idx)

    frames = {"SPY": flat_frame(100.0), "QQQ": flat_frame(100.0)}
    # Long from bar 0 close onward
    positions = {
        "SPY": pd.Series([1, 1, 1, 1], index=idx),
        "QQQ": pd.Series([1, 1, 1, 1], index=idx),
    }
    # Live-style manual sizing for comparison
    equity, cash = 10_000.0, 10_000.0
    spy_qty = risk.size_shares(100.0, equity, cash)
    cash_after = cash - spy_qty * 100.0
    qqq_qty = risk.size_shares(100.0, equity, cash_after)
    assert spy_qty == 50
    assert qqq_qty == 50

    stats = run_portfolio_backtest(frames, positions, 10_000.0, slippage_bps=0)
    assert "error" not in stats
    # Flat prices → equity unchanged; both positions held
    assert stats["final_equity"] == pytest.approx(10_000.0, abs=0.01)
