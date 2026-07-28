"""
Intraday backtester.

Execution model (no look-ahead):
  - Signal evaluated on bar t's CLOSE.
  - Entry/exit at bar t+1 OPEN ± slippage (+ half-spread when cost model on).
  - Intrabar stop: if bar low <= stop, fill at stop − slippage; gap through
    open uses the open (worse for long stop).
  - Forced flatten at session end (default 15:55 ET bar).

Costs: slippage_bps per side + half_spread_bps (one-way on entry and exit).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

import config


@dataclass
class IntradayTrade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_px: float
    exit_px: float
    qty: int
    pnl: float
    reason: str


@dataclass
class IntradayBacktestResult:
    trades: list[IntradayTrade] = field(default_factory=list)
    equity_curve: pd.Series | None = None
    net_return_pct: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    num_trades: int = 0


def run_intraday_backtest(
    bars: pd.DataFrame,
    signals: pd.Series,
    *,
    initial_cash: float = 10_000.0,
    slippage_bps: float | None = None,
    half_spread_bps: float | None = None,
    cost_multiplier: float = 1.0,
    stop_series: pd.Series | None = None,
    flatten_time: str = "15:55",
    qty_fn: Callable[[float, float, float], int] | None = None,
) -> IntradayBacktestResult:
    """
    bars: minute OHLCV indexed by timestamp (tz-aware ET or UTC).
    signals: 1 = want long after bar close, 0 = flat (decided on bar t close).
    stop_series: optional stop price active while long (evaluated on bar t).
    """
    slip_bps = slippage_bps if slippage_bps is not None else config.GATE_STAGE_A["intraday_slippage_bps"]
    hs_bps = half_spread_bps if half_spread_bps is not None else config.GATE_STAGE_A["intraday_half_spread_bps"]
    slip = (slip_bps * cost_multiplier) / 10_000.0
    half_sp = (hs_bps * cost_multiplier) / 10_000.0

    if len(bars) < 2:
        return IntradayBacktestResult()

    idx = bars.index
    cash = initial_cash
    shares = 0
    entry_px = 0.0
    stop_px = None
    trades: list[IntradayTrade] = []
    equity_rows: list[tuple[pd.Timestamp, float]] = []
    size_fn = qty_fn or (lambda price, equity, c: max(int(c // price), 0))

    def _flatten(ts: pd.Timestamp, px: float, reason: str) -> None:
        nonlocal cash, shares, entry_px, stop_px
        if shares <= 0:
            return
        fill = px * (1 - slip - half_sp)
        pnl = shares * (fill - entry_px)
        trades.append(
            IntradayTrade(ts, ts, entry_px, fill, shares, pnl, reason)
        )
        cash += shares * fill
        shares = 0
        entry_px = 0.0
        stop_px = None

    for i in range(1, len(bars)):
        t_prev = idx[i - 1]
        t = idx[i]
        bar = bars.iloc[i]
        prev_sig = int(signals.iloc[i - 1]) if i - 1 < len(signals) else 0
        open_px = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        # Stop check on bar i while holding (stop set from prior bar).
        if shares > 0 and stop_px is not None:
            if open_px <= stop_px:
                _flatten(t, open_px, "stop_gap")
            elif low <= stop_px:
                _flatten(t, stop_px, "stop")

        # Session flatten at configured minute (compare local time if tz-aware).
        ts_local = pd.Timestamp(t)
        if ts_local.tz is not None:
            ts_local = ts_local.tz_convert("America/New_York")
        hhmm = ts_local.strftime("%H:%M")
        if hhmm >= flatten_time and shares > 0:
            _flatten(t, open_px, "session_flatten")

        equity = cash + shares * close
        equity_rows.append((t, equity))

        target = prev_sig
        if target == 1 and shares == 0:
            fill = open_px * (1 + slip + half_sp)
            eq = cash
            qty = size_fn(fill, eq, cash)
            if qty > 0:
                cash -= qty * fill
                shares = qty
                entry_px = fill
                if stop_series is not None and i - 1 < len(stop_series):
                    stop_px = float(stop_series.iloc[i - 1]) if pd.notna(stop_series.iloc[i - 1]) else None
        elif target == 0 and shares > 0:
            _flatten(t, open_px, "signal_exit")

    eq = pd.Series(dict(equity_rows), name="equity") if equity_rows else pd.Series(dtype=float)
    net = (eq.iloc[-1] / initial_cash - 1.0) * 100 if len(eq) else 0.0
    wins = sum(t.pnl for t in trades if t.pnl > 0)
    losses = abs(sum(t.pnl for t in trades if t.pnl < 0))
    pf = wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)
    dd = 0.0
    if len(eq) > 1:
        dd = float((eq / eq.cummax() - 1.0).min() * 100)
    return IntradayBacktestResult(
        trades=trades,
        equity_curve=eq,
        net_return_pct=round(net, 2),
        profit_factor=round(pf, 2),
        max_drawdown_pct=round(abs(dd), 2),
        num_trades=len(trades),
    )
