"""overnight: close> SMA200 and day ret <= 0 → hold overnight."""

import numpy as np
import pandas as pd

from intraday.strategies.overnight import overnight_signals, run_overnight_backtest


def _daily(n: int, *, trend_up: bool = True) -> pd.DataFrame:
    if trend_up:
        closes = list(np.linspace(100, 200, n))
    else:
        closes = list(np.linspace(200, 100, n))
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": 1e6,
        },
        index=idx,
    )


def test_no_entry_when_below_sma200():
    df = _daily(250, trend_up=False)
    df.loc[df.index[-1], "close"] = 95
    df.loc[df.index[-1], "open"] = 96
    sig = overnight_signals(df)
    assert int(sig.iloc[-1]) == 0


def test_entry_red_day_above_trend():
    df = _daily(250, trend_up=True)
    df.loc[df.index[-1], "open"] = 200
    df.loc[df.index[-1], "close"] = 198  # red day, still above SMA200
    sig = overnight_signals(df)
    assert int(sig.iloc[-1]) == 1


def test_backtest_produces_trades():
    df = _daily(260, trend_up=True)
    # Inject several red close days
    for i in range(-5, 0):
        df.loc[df.index[i], "open"] = float(df["close"].iloc[i]) * 1.01
    stats = run_overnight_backtest(df, slippage_bps=5)
    assert stats["num_trades"] >= 1
