"""
Market data + indicators.

Daily bars only. Backtests and live signals use the same functions so there is
no gap between what you tested and what you trade.

Default source: Alpaca historical stock bars, SIP feed, with `end` at least
15 minutes in the past so free-plan SIP access works (Market Data FAQ).
Optional offline fallback: yfinance via source="yfinance" or DATA_SOURCE=yfinance.

Docs:
  https://docs.alpaca.markets/docs/market-data-faq
  https://alpaca.markets/sdks/python/
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

import numpy as np
import pandas as pd

import config
from alpaca_retry import call_with_retries

# Keep end this far in the past so SIP historical queries stay outside the
# free-plan "recent SIP" window (FAQ: end must be ≥15 minutes old).
_SIP_END_LAG = timedelta(minutes=16)

SourceName = Literal["alpaca", "yfinance"]


def last_bar_date(df: pd.DataFrame) -> date:
    """Calendar date of the last bar (naive index treated as ET session dates)."""
    if df is None or len(df) == 0:
        raise ValueError("empty bar frame")
    ts = pd.Timestamp(df.index[-1])
    return ts.date()


def bar_stale_days(df: pd.DataFrame, as_of: date) -> int:
    """Calendar days between last bar and as_of (trading day). Negative if future."""
    return (as_of - last_bar_date(df)).days


def bars_are_stale(
    df: pd.DataFrame,
    as_of: date,
    *,
    max_age_days: int | None = None,
) -> bool:
    """True when last bar is older than max_age_days calendar days vs as_of."""
    limit = config.MAX_BAR_STALE_DAYS if max_age_days is None else max_age_days
    return bar_stale_days(df, as_of) > limit


def fetch_daily(
    symbol: str,
    years: int = 15,
    *,
    source: SourceName | None = None,
    client: Any | None = None,
) -> pd.DataFrame:
    """Fetch adjusted daily OHLCV. Columns: open, high, low, close, volume.

    Same function for backtest and live. Default source is Alpaca SIP.
    Pass source="yfinance" (or set DATA_SOURCE=yfinance) for offline/dev.
    `client` is an injectable StockHistoricalDataClient (tests).
    """
    src = (source or os.environ.get("DATA_SOURCE") or "alpaca").lower()
    if src == "yfinance":
        return _fetch_daily_yfinance(symbol, years=years)
    if src == "alpaca":
        return _fetch_daily_alpaca(symbol, years=years, client=client)
    raise ValueError(f"Unknown data source {src!r}; use 'alpaca' or 'yfinance'")


def _fetch_daily_alpaca(
    symbol: str,
    years: int,
    *,
    client: Any | None = None,
) -> pd.DataFrame:
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    if client is None:
        key = os.environ.get("ALPACA_API_KEY_ID")
        secret = os.environ.get("ALPACA_API_SECRET_KEY")
        if not key or not secret:
            raise SystemExit(
                "Missing ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY for Alpaca data. "
                "Set them in .env, or use source='yfinance' / DATA_SOURCE=yfinance for offline."
            )
        client = StockHistoricalDataClient(key, secret)

    end = datetime.now(timezone.utc) - _SIP_END_LAG
    # calendar years ≈ enough trading days; API wants datetimes
    start = end - timedelta(days=int(years * 365.25) + 7)

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.SIP,
        adjustment=Adjustment.ALL,  # splits + dividends ≈ yfinance auto_adjust
    )
    barset = call_with_retries(
        client.get_stock_bars,
        request,
        label=f"get_stock_bars:{symbol}",
    )
    return _barset_to_ohlcv(barset, symbol)


def _barset_to_ohlcv(barset: Any, symbol: str) -> pd.DataFrame:
    """Normalize Alpaca BarSet / .df into strategy schema (naive ET dates)."""
    df = getattr(barset, "df", barset)
    if df is None or len(df) == 0:
        raise RuntimeError(f"No data returned for {symbol}")

    if isinstance(df.index, pd.MultiIndex):
        names = list(df.index.names)
        if "symbol" in names:
            df = df.xs(symbol, level="symbol")
        else:
            # first level is usually symbol
            df = df.droplevel(0)

    cols = {c.lower(): c for c in df.columns}
    need = ["open", "high", "low", "close", "volume"]
    missing = [c for c in need if c not in cols]
    if missing:
        raise RuntimeError(f"Alpaca bars missing columns {missing}; got {list(df.columns)}")

    out = df[[cols[c] for c in need]].copy()
    out.columns = need
    out = out.dropna()

    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("America/New_York")
    out.index = idx.tz_localize(None).normalize()
    out.index.name = None
    return out


def _fetch_daily_yfinance(symbol: str, years: int = 15) -> pd.DataFrame:
    """Optional offline path; not used by hosted/live default."""
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
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
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
