"""rsi2_tight lab variant: entry_rsi=5, max_hold_days=5."""

import numpy as np
import pandas as pd

import config
from strategy import rsi2_positions


def _ohlcv(closes: list[float]) -> pd.DataFrame:
    s = pd.Series(closes, dtype=float)
    idx = pd.bdate_range("2024-01-02", periods=len(closes))
    return pd.DataFrame(
        {"open": s.values, "high": s.values, "low": s.values, "close": s.values, "volume": 1e6},
        index=idx,
    )


PARAMS = config.RSI2_TIGHT.copy()
PARAMS["trend_sma"] = 20  # short fixture window


_CLIMB = list(np.linspace(100, 150, 40))


def test_tight_requires_rsi_below_5():
    """entry_rsi=5 is stricter than default rsi2 (10)."""
    # Pull to RSI ~8 — would enter rsi2 but not rsi2_tight
    df = _ohlcv(_CLIMB + [146.0, 141.0])
    pos_default = rsi2_positions(df, {**PARAMS, "entry_rsi": 10.0})
    pos_tight = rsi2_positions(df, PARAMS)
    assert int(pos_default.iloc[-1]) == 1
    assert int(pos_tight.iloc[-1]) == 0


def test_tight_entry_when_rsi_below_5():
    # Three-bar pullback: RSI(2) < 5 while close still > SMA(trend)
    df = _ohlcv(_CLIMB + [147.0, 146.0, 141.0])
    pos = rsi2_positions(df, PARAMS)
    assert int(pos.iloc[-1]) == 1


def test_tight_max_hold_5_days():
    params = {**PARAMS, "exit_rsi": 99.0}
    df = _ohlcv(_CLIMB + [147.0, 146.0, 141.0] + [140.5] * 8)
    pos = rsi2_positions(df, params)
    entry_i = int(np.where(pos.values == 1)[0][0])
    assert int(pos.iloc[entry_i + 4]) == 1
    assert int(pos.iloc[entry_i + 5]) == 0
