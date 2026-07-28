"""fetch_daily Alpaca path with mocked StockBars responses (offline)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.timeframe import TimeFrame

from data import _barset_to_ohlcv, fetch_daily


def _fake_bar_df() -> pd.DataFrame:
    """MultiIndex (symbol, timestamp) like alpaca-py BarSet.df."""
    idx = pd.MultiIndex.from_arrays(
        [
            ["SPY", "SPY", "SPY"],
            pd.to_datetime(
                [
                    "2026-07-23 04:00:00+00:00",
                    "2026-07-24 04:00:00+00:00",
                    "2026-07-25 04:00:00+00:00",
                ]
            ),
        ],
        names=["symbol", "timestamp"],
    )
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1_000_000, 1_100_000, 1_200_000],
            "trade_count": [10, 11, 12],
            "vwap": [100.2, 101.2, 102.2],
        },
        index=idx,
    )


def test_barset_to_ohlcv_schema_and_et_dates():
    barset = SimpleNamespace(df=_fake_bar_df())
    out = _barset_to_ohlcv(barset, "SPY")
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out.index.tz is None
    # 04:00 UTC → 00:00 America/New_York on those July dates (EDT)
    assert list(out.index) == [
        pd.Timestamp("2026-07-23"),
        pd.Timestamp("2026-07-24"),
        pd.Timestamp("2026-07-25"),
    ]
    assert out.loc[pd.Timestamp("2026-07-25"), "close"] == 102.5


def test_fetch_daily_alpaca_uses_sip_and_lagged_end(monkeypatch):
    monkeypatch.delenv("DATA_SOURCE", raising=False)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "PKTEST")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "SECRET")

    fake_client = MagicMock()
    fake_client.get_stock_bars.return_value = SimpleNamespace(df=_fake_bar_df())

    with patch("alpaca.data.historical.StockHistoricalDataClient", return_value=fake_client):
        # Inject client so we don't construct; still assert request shape
        out = fetch_daily("SPY", years=1, source="alpaca", client=fake_client)

    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert len(out) == 3

    req = fake_client.get_stock_bars.call_args.args[0]
    assert req.symbol_or_symbols == "SPY"
    assert str(req.timeframe) == str(TimeFrame.Day)  # TimeFrame has no value eq
    assert req.feed == DataFeed.SIP
    assert req.adjustment == Adjustment.ALL
    assert req.end is not None and req.start is not None
    # end must be at least ~15 minutes before "now" (we use 16)
    now = datetime.now(timezone.utc)
    end = req.end if req.end.tzinfo else req.end.replace(tzinfo=timezone.utc)
    lag_sec = (now - end.astimezone(timezone.utc)).total_seconds()
    assert lag_sec >= 15 * 60


def test_fetch_daily_empty_raises():
    fake_client = MagicMock()
    fake_client.get_stock_bars.return_value = SimpleNamespace(df=pd.DataFrame())
    with pytest.raises(RuntimeError, match="No data"):
        fetch_daily("SPY", years=1, source="alpaca", client=fake_client)


def test_unknown_source_raises():
    with pytest.raises(ValueError, match="Unknown data source"):
        fetch_daily("SPY", source="bloomberg")  # type: ignore[arg-type]
