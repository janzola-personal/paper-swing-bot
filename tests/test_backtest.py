"""backtest.run_backtest — 6-bar hand-computed next-open fills."""

import pandas as pd
import pytest

import risk
from backtest import run_backtest


def test_six_bar_hand_computed_fills_at_t_plus_1_open():
    """Signal on bar t's close → fill at bar t+1's open (no look-ahead).

    Bars (indexes 0..5):
        open:  [100, 102, 101, 105, 104, 103]
        close: [101, 100, 104, 103, 102, 106]
        pos:   [  0,   1,   1,   0,   0,   0]

    Loop starts at t=1:
      t=1: target=pos[0]=0 → no trade; equity = 0 + 0*close = cash 10000
      t=2: target=pos[1]=1 → BUY at open[2]=101
             fill=101 (slippage 0)
             qty = size_shares(101, 10000, 10000) = int(5000/101) = 49
             cash = 10000 - 49*101 = 10000 - 4949 = 5051
             equity_mtm = 5051 + 49*104 = 5051 + 5096 = 10147
      t=3: target=pos[2]=1 → hold
             equity = 5051 + 49*103 = 5051 + 5047 = 10098
      t=4: target=pos[3]=0 → SELL at open[4]=104
             cash = 5051 + 49*104 = 5051 + 5096 = 10147
             shares=0
             equity = 10147
      t=5: target=pos[4]=0 → flat
             equity = 10147

    Final equity 10147; one round-trip; pnl_pct = 104/101 - 1.
    """
    idx = pd.bdate_range("2026-01-05", periods=6)
    df = pd.DataFrame({
        "open":  [100.0, 102.0, 101.0, 105.0, 104.0, 103.0],
        "high":  [101.0, 103.0, 105.0, 106.0, 105.0, 106.0],
        "low":   [99.0, 100.0, 100.0, 103.0, 102.0, 102.0],
        "close": [101.0, 100.0, 104.0, 103.0, 102.0, 106.0],
        "volume": 1e6,
    }, index=idx)
    pos = pd.Series([0, 1, 1, 0, 0, 0], index=idx)

    qty = risk.size_shares(101.0, 10_000.0, 10_000.0)
    assert qty == 49
    expected_final = 10_000.0 - 49 * 101.0 + 49 * 104.0
    assert expected_final == pytest.approx(10_147.0)

    stats = run_backtest(df, pos, initial_cash=10_000.0, slippage_bps=0)
    assert stats["final_equity"] == pytest.approx(expected_final)
    assert stats["num_trades"] == 1
    # _stats rounds avg_trade_pct to 2 decimals
    assert stats["avg_trade_pct"] == pytest.approx(100.0 * (104.0 / 101.0 - 1.0), abs=0.01)


def test_signal_on_last_bar_does_not_fill_same_bar():
    """pos on final bar has no t+1 — no phantom same-bar fill."""
    idx = pd.bdate_range("2026-01-05", periods=3)
    df = pd.DataFrame({
        "open": [100.0, 100.0, 100.0],
        "high": 100.0,
        "low": 100.0,
        "close": [100.0, 100.0, 100.0],
        "volume": 1e6,
    }, index=idx)
    # Signal only on last close — never executed in this window
    pos = pd.Series([0, 0, 1], index=idx)
    stats = run_backtest(df, pos, initial_cash=10_000.0, slippage_bps=0)
    assert stats["num_trades"] == 0
    assert stats["final_equity"] == pytest.approx(10_000.0)


def test_slippage_widens_entry_and_narrows_exit():
    idx = pd.bdate_range("2026-01-05", periods=4)
    df = pd.DataFrame({
        "open": [100.0, 100.0, 100.0, 100.0],
        "high": 100.0,
        "low": 100.0,
        "close": [100.0, 100.0, 100.0, 100.0],
        "volume": 1e6,
    }, index=idx)
    pos = pd.Series([1, 1, 0, 0], index=idx)
    # 10 bps = 0.1%
    stats = run_backtest(df, pos, initial_cash=10_000.0, slippage_bps=10)
    buy = 100.0 * 1.001
    sell = 100.0 * 0.999
    qty = risk.size_shares(buy, 10_000.0, 10_000.0)
    expected = 10_000.0 - qty * buy + qty * sell
    assert stats["final_equity"] == pytest.approx(expected, abs=0.02)
    assert stats["final_equity"] < 10_000.0
