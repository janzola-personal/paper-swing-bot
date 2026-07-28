"""
Strategies. Each returns a pd.Series of desired position (0 or 1) per bar.

SEMANTICS (critical -- this is how look-ahead bias is avoided):
    position[t] == 1  means  "hold the position starting at the NEXT bar's open"
Signals are computed on bar t's close; execution happens at bar t+1's open.
The backtester and the live loop both honor this convention.

Rules are deterministic and fully specified in STRATEGY.md. No discretion,
no network calls, no LLMs inside the signal path.
"""

import numpy as np
import pandas as pd

import config
from data import add_indicators


def rsi2_positions(df: pd.DataFrame, params: dict | None = None) -> pd.Series:
    """Connors-style RSI(2) mean reversion, long-only, regime-filtered.

    Enter (at next open) when, at today's close:
        RSI(2) < entry_rsi  AND  close > SMA(trend_sma)
    Exit (at next open) when, at today's close, ANY of:
        close > SMA(exit_sma)
        RSI(2) > exit_rsi
        held for max_hold_days bars
    """
    p = params or config.RSI2
    d = add_indicators(df, p)
    close, r = d["close"], d["rsi2"]
    fast, slow = d["sma_fast"], d["sma_slow"]

    pos = np.zeros(len(d), dtype=int)
    holding, bars_held = 0, 0
    for i in range(len(d)):
        if np.isnan(slow.iloc[i]) or np.isnan(r.iloc[i]) or np.isnan(fast.iloc[i]):
            pos[i] = 0
            continue
        if holding == 0:
            if r.iloc[i] < p["entry_rsi"] and close.iloc[i] > slow.iloc[i]:
                holding, bars_held = 1, 0
        else:
            bars_held += 1
            if (
                close.iloc[i] > fast.iloc[i]
                or r.iloc[i] > p["exit_rsi"]
                or bars_held >= p["max_hold_days"]
            ):
                holding = 0
        pos[i] = holding
    return pd.Series(pos, index=d.index, name="position")


def trend_positions(df: pd.DataFrame, params: dict | None = None) -> pd.Series:
    """Faber-style trend filter, evaluated at month-end only.

    On the last trading day of each month: if close > SMA(trend_sma), hold
    from the next open; otherwise hold cash. Between month-ends, carry the
    previous decision. Slow, boring, hard to blow up -- the baseline.
    """
    p = params or config.TREND
    d = df.copy()
    slow = d["close"].rolling(p["trend_sma"]).mean()
    raw = (d["close"] > slow).astype(float)
    raw[slow.isna()] = np.nan

    is_month_end = month_end_mask(d.index)
    decided = raw.where(pd.Series(is_month_end, index=d.index))
    pos = decided.ffill().fillna(0.0).astype(int)
    pos.name = "position"
    return pos


def month_end_mask(index: pd.DatetimeIndex) -> np.ndarray:
    """True on the last trading day of each month present in the index.

    A bar is month-end when the next bar (if any) is in a different month.
    The final bar of a truncated series is month-end only if the next business
    day falls in a new month — so a live mid-month last row does NOT re-decide.
    (BDay skips weekends; US holiday calendar can refine this later.)
    """
    from pandas.tseries.offsets import BDay

    n = len(index)
    mask = np.zeros(n, dtype=bool)
    if n == 0:
        return mask
    months = index.month
    years = index.year
    mask[:-1] = (months[:-1] != months[1:]) | (years[:-1] != years[1:])
    last = pd.Timestamp(index[-1])
    nxt = last + BDay(1)
    mask[-1] = (nxt.month != last.month) or (nxt.year != last.year)
    return mask


STRATEGIES = {
    "rsi2": rsi2_positions,
    "rsi2_tight": rsi2_positions,  # same fn; params from config.RSI2_TIGHT in lab
    "trend": trend_positions,
}


def strategy_params(name: str) -> dict:
    """Parameter dict for a registered strategy name."""
    if name == "rsi2":
        return config.RSI2
    if name == "rsi2_tight":
        return config.RSI2_TIGHT
    if name == "trend":
        return config.TREND
    raise KeyError(f"Unknown strategy {name!r}")


def desired_position_today(df: pd.DataFrame, strategy_name: str) -> tuple[int, str]:
    """For the live loop: desired position (0/1) based on the latest close,
    plus a human-readable reason string for the journal."""
    fn = STRATEGIES[strategy_name]
    params = strategy_params(strategy_name)
    pos = fn(df, params)
    cfg = params if "entry_rsi" in params else config.RSI2
    d = add_indicators(df, cfg)
    last = d.iloc[-1]
    reason = (
        f"{strategy_name} | close={last['close']:.2f} rsi2={last['rsi2']:.1f} "
        f"sma{cfg['exit_sma']}={last['sma_fast']:.2f} "
        f"sma{cfg['trend_sma']}={last['sma_slow']:.2f}"
    )
    return int(pos.iloc[-1]), reason
