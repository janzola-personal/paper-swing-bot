"""orb15 signal rules (unit-level)."""

import pandas as pd

from intraday.strategies.orb15 import orb15_signals


def test_orb15_skips_narrow_range():
    idx = pd.date_range("2024-06-03 09:30", periods=20, freq="1min", tz="America/New_York")
    mb = pd.DataFrame(
        {
            "open": [400.0] * 20,
            "high": [400.05] * 20,
            "low": [399.95] * 20,
            "close": [400.0] * 20,
            "volume": [1e6] * 20,
        },
        index=idx,
    )
    daily_idx = pd.bdate_range("2024-01-02", periods=250)
    daily = pd.DataFrame(
        {
            "open": [380.0] * 250,
            "high": [405.0] * 250,
            "low": [375.0] * 250,
            "close": [400.0] * 250,
            "volume": [1e8] * 250,
        },
        index=daily_idx,
    )
    sig, _ = orb15_signals(mb, daily)
    assert sig.sum() == 0
