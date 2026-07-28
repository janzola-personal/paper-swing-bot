"""vwap_z signal rules (unit-level)."""

import numpy as np
import pandas as pd

from intraday.strategies.vwap_z import vwap_z_signals


def test_vwap_z_no_signal_without_regime():
    idx = pd.date_range("2024-06-03 10:00", periods=30, freq="1min", tz="America/New_York")
    closes = np.linspace(400, 390, 30)
    mb = pd.DataFrame(
        {
            "open": closes,
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": [1e6] * 30,
        },
        index=idx,
    )
    daily_idx = pd.bdate_range("2024-01-02", periods=250)
    daily = pd.DataFrame(
        {
            "open": list(np.linspace(450, 350, 250)),
            "high": list(np.linspace(450, 350, 250)),
            "low": list(np.linspace(450, 350, 250)),
            "close": list(np.linspace(450, 350, 250)),
            "volume": [1e8] * 250,
        },
        index=daily_idx,
    )
    sig, _ = vwap_z_signals(mb, daily)
    assert sig.sum() == 0
