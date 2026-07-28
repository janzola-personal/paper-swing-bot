"""
Alpaca historical minute bars with parquet cache.

Signal path must not call this module — only backtests, research, and the
intraday engine tick (outside strategy signal generation).

SIP feed when `end` is ≥15 minutes ago (Alpaca Market Data FAQ):
  https://docs.alpaca.markets/docs/market-data-faq
Stock bars API:
  https://alpaca.markets/sdks/python/api_reference/data/stock/historical.html
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

import config
from alpaca_retry import call_with_retries

_SIP_END_LAG = timedelta(minutes=16)
CACHE_DIR = Path("data/minute")


def _alpaca_end() -> datetime:
    return datetime.now(timezone.utc) - _SIP_END_LAG


def cache_path(symbol: str, day: date) -> Path:
    return CACHE_DIR / symbol / f"{day.isoformat()}.csv"


def fetch_minute_bars(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    client: Any | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Minute OHLCV for [start, end). Index tz-aware UTC, sorted."""
    if use_cache and start.date() == end.date() and start.date() < _alpaca_end().date():
        p = cache_path(symbol, start.date())
        if p.exists():
            df = pd.read_csv(p, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True)
            return df.sort_index()

    df = _fetch_alpaca_minute(symbol, start, end, client=client)
    if use_cache and len(df) and start.date() == end.date():
        p = cache_path(symbol, start.date())
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(p)
    return df


def _fetch_alpaca_minute(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    client: Any | None = None,
) -> pd.DataFrame:
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    key = os.environ.get("ALPACA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if client is None:
        if not key or not secret:
            raise SystemExit("Missing Alpaca keys for minute fetch")
        client = StockHistoricalDataClient(key, secret)

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=DataFeed.SIP,
    )
    bars = call_with_retries(client.get_stock_bars, req, label="get_stock_bars")
    rows = []
    for bar in bars.data.get(symbol, []):
        rows.append(
            {
                "timestamp": bar.timestamp,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    df.index = pd.to_datetime(df.index, utc=True)
    return df
