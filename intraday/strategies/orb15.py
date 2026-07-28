"""
Opening Range Breakout (15-minute OR, 9:30–9:45 ET).

Long-only v1: prior daily close > SMA200, OR width >= 0.3 * 14d ATR,
entry stop at OR high + $0.01, stop at OR low, flatten 15:55.
Signal on bar t close → fill t+1 open (backtest_intraday).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _daily_regime(daily: pd.DataFrame) -> pd.Series:
    sma = daily["close"].rolling(200).mean()
    return (daily["close"] > sma).astype(int)


def _daily_atr(daily: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = daily["high"], daily["low"], daily["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def orb15_signals(
    minute_bars: pd.DataFrame,
    daily: pd.DataFrame,
    *,
    or_minutes: int = 15,
    min_or_atr_frac: float = 0.3,
) -> tuple[pd.Series, pd.Series]:
    """
    Returns (entry_signals, stop_prices) aligned to minute_bars index.
    Entry signal 1 = want long after bar close; stop at OR low while in trade.
    """
    sig = pd.Series(0, index=minute_bars.index, dtype=int)
    stops = pd.Series(np.nan, index=minute_bars.index, dtype=float)

    daily = daily.copy()
    daily.index = pd.to_datetime(daily.index).tz_localize(None)
    regime = _daily_regime(daily)
    atr = _daily_atr(daily)

    mb = minute_bars.copy()
    if mb.index.tz is None:
        mb.index = mb.index.tz_localize("America/New_York")
    else:
        mb.index = mb.index.tz_convert("America/New_York")

    triggered_today = False
    current_day = None
    or_high = or_low = None
    or_end = None

    for i, ts in enumerate(mb.index):
        d = ts.date()
        if d != current_day:
            current_day = d
            triggered_today = False
            or_high = or_low = None
            day_mask = mb.index.date == d
            day_bars = mb.loc[day_mask]
            or_bars = day_bars.between_time("09:30", "09:44")
            if len(or_bars) >= 1:
                or_high = float(or_bars["high"].max())
                or_low = float(or_bars["low"].min())
                or_end = or_bars.index[-1]

        if or_high is None or triggered_today:
            continue

        dkey = pd.Timestamp(d)
        if dkey not in regime.index and len(regime.index):
            # align to nearest prior daily row
            prior = regime.index[regime.index <= dkey]
            if len(prior) == 0 or regime.loc[prior[-1]] != 1:
                continue
        elif dkey in regime.index and regime.loc[dkey] != 1:
            continue

        atr_val = atr.loc[dkey] if dkey in atr.index else np.nan
        if pd.isna(atr_val) or (or_high - or_low) < min_or_atr_frac * atr_val:
            continue

        if ts <= or_end:
            continue

        close = float(mb["close"].iloc[i])
        entry_stop = or_high + 0.01
        # Signal when close crosses OR high (decided on this bar's close).
        if close >= entry_stop:
            sig.iloc[i] = 1
            stops.iloc[i] = or_low
            triggered_today = True

    return sig, stops
