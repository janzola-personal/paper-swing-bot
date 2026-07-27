"""trend_positions: decisions only at month-end; carry otherwise."""

import numpy as np
import pandas as pd

from strategy import month_end_mask, trend_positions


def test_trend_positions_only_change_at_month_end():
    """Between month-ends, position is constant (ffill of last month-end decision)."""
    rng = pd.bdate_range("2024-01-02", "2025-06-30")
    # Rising so month-end decisions are long once SMA200 is warm
    close = pd.Series(100 + np.arange(len(rng)) * 0.2, index=rng)
    df = pd.DataFrame({
        "open": close, "high": close, "low": close, "close": close, "volume": 1e6,
    })
    pos = trend_positions(df, {"trend_sma": 200})
    mask = month_end_mask(df.index)

    # Any change in position must occur on a month-end bar
    for i in range(1, len(pos)):
        if pos.iloc[i] != pos.iloc[i - 1]:
            assert mask[i], f"position changed on non-month-end bar {df.index[i]}"


def test_trend_cash_when_month_end_below_sma():
    """Month-end close below SMA → go flat from that decision onward until next ME."""
    rng = pd.bdate_range("2024-01-02", "2025-03-31")
    n = len(rng)
    close_vals = 100 + np.arange(n) * 0.3
    # Crash for all of March 2025 so March month-end is below SMA200
    march = (rng.year == 2025) & (rng.month == 3)
    close_vals[march] = 50.0
    close = pd.Series(close_vals, index=rng)
    df = pd.DataFrame({
        "open": close, "high": close, "low": close, "close": close, "volume": 1e6,
    })
    pos = trend_positions(df, {"trend_sma": 200})
    # Last bar of March 2025 is month-end → should decide flat
    march_end = df.index[(df.index.year == 2025) & (df.index.month == 3)][-1]
    assert month_end_mask(df.index)[df.index.get_loc(march_end)]
    assert int(pos.loc[march_end]) == 0
