"""
VWAP z-score mean reversion (long-only v1).

z = (price - VWAP) / intraday std(price - VWAP).
Entry when z <= -2 between 10:00–15:00 ET, regime filter (daily close > SMA200).
Target VWAP touch; stop = entry - 1 * intraday std. Max 2 trades/day (enforced
in signal generator). Flatten 15:55.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _session_vwap_and_z(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    else:
        df.index = df.index.tz_convert("America/New_York")

    out_rows = []
    for d in pd.unique(df.index.date):
        day = df.loc[df.index.date == d].sort_index()
        if day.empty:
            continue
        tp = (day["high"] + day["low"] + day["close"]) / 3.0
        cum_vol = day["volume"].cumsum()
        cum_pv = (tp * day["volume"]).cumsum()
        vwap = cum_pv / cum_vol.replace(0, np.nan)
        dev = day["close"] - vwap
        std = dev.expanding().std().fillna(dev.abs().replace(0, np.nan))
        z = dev / std.replace(0, np.nan)
        chunk = pd.DataFrame({"vwap": vwap, "z": z, "dev_std": std}, index=day.index)
        out_rows.append(chunk)
    if not out_rows:
        return pd.DataFrame(index=bars.index, columns=["vwap", "z", "dev_std"])
    return pd.concat(out_rows).reindex(bars.index)


def vwap_z_signals(
    minute_bars: pd.DataFrame,
    daily: pd.DataFrame,
    *,
    z_entry: float = -2.0,
    max_trades_per_day: int = 2,
) -> tuple[pd.Series, pd.Series]:
    """Returns (entry_signals, stop_prices)."""
    sig = pd.Series(0, index=minute_bars.index, dtype=int)
    stops = pd.Series(np.nan, index=minute_bars.index, dtype=float)

    vz = _session_vwap_and_z(minute_bars)
    daily = daily.copy()
    daily.index = pd.to_datetime(daily.index).tz_localize(None)
    sma = daily["close"].rolling(200).mean()
    regime = daily["close"] > sma

    mb = minute_bars.copy()
    if mb.index.tz is None:
        mb.index = mb.index.tz_localize("America/New_York")
    else:
        mb.index = mb.index.tz_convert("America/New_York")

    trades_today = 0
    current_day = None
    in_pos = False

    for i, ts in enumerate(mb.index):
        d = ts.date()
        if d != current_day:
            current_day = d
            trades_today = 0
            in_pos = False

        tstr = ts.strftime("%H:%M")
        if tstr < "10:00" or tstr > "15:00":
            continue

        dkey = pd.Timestamp(d)
        if dkey not in regime.index or not regime.loc[dkey]:
            continue

        z = float(vz["z"].iloc[i]) if i < len(vz) else np.nan
        std = float(vz["dev_std"].iloc[i]) if i < len(vz) else np.nan
        close = float(mb["close"].iloc[i])
        vwap = float(vz["vwap"].iloc[i]) if i < len(vz) else np.nan

        if not in_pos and trades_today < max_trades_per_day and z <= z_entry and np.isfinite(std):
            sig.iloc[i] = 1
            stops.iloc[i] = close - std
            trades_today += 1
            in_pos = True
        elif in_pos and close >= vwap:
            sig.iloc[i] = 0
            in_pos = False

    return sig, stops
