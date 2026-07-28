"""
Hand-built 10-bar day — expected fills documented inline.

Signal on bar t close → fill bar t+1 open (no look-ahead).
"""

import pandas as pd
import pytest

from intraday.backtest_intraday import run_intraday_backtest


def _ten_bar_day() -> pd.DataFrame:
    # One synthetic session 09:30–09:39 ET (10 one-minute bars)
    idx = pd.date_range("2024-06-03 09:30", periods=10, freq="1min", tz="America/New_York")
    # Bar:           0    1    2    3    4    5    6    7    8    9
    opens  = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100]
    highs  = [101, 101, 101, 101, 101, 101, 101, 101, 101, 101]
    lows   = [ 99,  99,  99,  99,  99,  99,  99,  99,  99,  99]
    closes = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1e6] * 10},
        index=idx,
    ).astype({"open": float, "high": float, "low": float, "close": float})


def test_no_signal_no_trades():
    bars = _ten_bar_day()
    sig = pd.Series(0, index=bars.index)
    res = run_intraday_backtest(bars, sig, initial_cash=10_000, slippage_bps=0, half_spread_bps=0)
    assert res.num_trades == 0


def test_signal_bar2_fill_bar3_open():
    """
    sig[1]=1 (decided on bar 1 close) → enter at bar 2 open (100).
    sig[4]=0 → exit at bar 5 open (100). Zero slip → flat PnL.
    """
    bars = _ten_bar_day()
    sig = pd.Series([0, 1, 1, 1, 0, 0, 0, 0, 0, 0], index=bars.index)
    res = run_intraday_backtest(
        bars,
        sig,
        initial_cash=10_000,
        slippage_bps=0,
        half_spread_bps=0,
        qty_fn=lambda price, eq, cash: 10,
    )
    assert res.num_trades == 1
    t = res.trades[0]
    assert t.entry_px == 100.0
    assert t.exit_px == 100.0
    assert t.pnl == 0.0


def test_stop_gap_through_open():
    """Long from bar2; stop=99; bar3 opens at 98 → fill at open (gap through)."""
    bars = _ten_bar_day()
    bars.loc[bars.index[3], "open"] = 98.0
    bars.loc[bars.index[3], "low"] = 97.5
    sig = pd.Series([0, 1, 1, 1, 0, 0, 0, 0, 0, 0], index=bars.index)
    stops = pd.Series([float("nan"), 99.0, 99.0, 99.0, float("nan")] + [float("nan")] * 5, index=bars.index)
    res = run_intraday_backtest(
        bars,
        sig,
        initial_cash=10_000,
        slippage_bps=0,
        half_spread_bps=0,
        stop_series=stops,
        qty_fn=lambda price, eq, cash: 10,
    )
    assert res.num_trades >= 1
    assert res.trades[0].exit_px == 98.0
    assert res.trades[0].reason == "stop_gap"
