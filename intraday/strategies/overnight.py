"""
Overnight bridge (swing-adjacent daily strategy).

At ~15:55 ET: if close > SMA(200) AND today's return <= 0, buy (MOC proxy).
Sell at next session open.

Daily backtest proxy: enter at bar t close, exit at bar t+1 open.
This is a different fill convention than rsi2 (documented in module).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config
import risk
from backtest import _stats


def overnight_signals(df: pd.DataFrame, *, trend_sma: int = 200) -> pd.Series:
    """1 on bars where we hold overnight close→next open."""
    close = df["close"]
    sma = close.rolling(trend_sma).mean()
    day_ret = close / df["open"] - 1.0
    want = (close > sma) & (day_ret <= 0) & sma.notna()
    return want.astype(int)


def run_overnight_backtest(
    df: pd.DataFrame,
    *,
    initial_cash: float | None = None,
    slippage_bps: float | None = None,
    cost_multiplier: float = 1.0,
) -> dict:
    """Close-to-next-open fills with cost multiplier on slippage."""
    cash0 = initial_cash or config.BACKTEST_INITIAL_CASH
    slip = (slippage_bps or config.SLIPPAGE_BPS) * cost_multiplier / 10_000.0
    sig = overnight_signals(df)
    cash, shares = cash0, 0
    entry_px = 0.0
    trades: list[dict] = []
    equity_rows: list[tuple] = []

    for i in range(len(df)):
        day = df.index[i]
        close = float(df["close"].iloc[i])
        if sig.iloc[i] and shares == 0:
            fill = close * (1 + slip)
            qty = risk.size_shares(fill, cash, cash)
            if qty > 0:
                cash -= qty * fill
                shares = qty
                entry_px = fill
        if shares > 0 and i + 1 < len(df):
            nxt_open = float(df["open"].iloc[i + 1])
            fill = nxt_open * (1 - slip)
            cash += shares * fill
            trades.append({"exit_date": df.index[i + 1], "pnl_pct": fill / entry_px - 1.0})
            shares = 0
        equity_rows.append((day, cash + shares * close))

    eq = pd.Series(dict(equity_rows), name="equity")
    pos = sig.astype(float)
    stats = _stats(eq, pos, trades, cash0)
    stats["kind"] = "overnight"
    return stats
