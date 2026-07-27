"""
Market data + indicators.

Daily bars only. Backtests and live signals use the same functions so there is
no gap between what you tested and what you trade.

Data source: Yahoo Finance via yfinance (free, adjusted daily bars -- fine for
a daily-bar system). The import is inside fetch_daily() so the rest of the
codebase can be imported and unit-tested offline.
"""

import numpy as np
import pandas as pd


def fetch_daily(symbol: str, years: int = 15) -> pd.DataFrame:
    """Fetch adjusted daily OHLCV. Columns: open, high, low, close, volume."""
    import yfinance as yf

    df = yf.download(
        symbol,
        period=f"{years}y",
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if df is None or len(df) == 0:
        raise RuntimeError(f"No data returned for {symbol}")
    # Newer yfinance versions return MultiIndex columns even for one symbol.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def rsi(series: pd.Series, period: int = 2) -> pd.Series:
    """Wilder's RSI. Warm-up values are NaN; strategies must skip NaNs."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss  # avg_loss == 0 -> inf -> RSI 100 (intended)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.replace([np.inf, -np.inf], 100.0)


def add_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Attach every indicator any strategy needs. Cheap on daily bars."""
    out = df.copy()
    out["rsi2"] = rsi(out["close"], cfg.get("rsi_period", 2))
    out["sma_fast"] = sma(out["close"], cfg.get("exit_sma", 5))
    out["sma_slow"] = sma(out["close"], cfg.get("trend_sma", 200))
    return out
