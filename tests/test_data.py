"""Hand-checked Wilder RSI and SMA (data.py)."""

import numpy as np
import pandas as pd
import pytest

from data import rsi, sma


def test_sma_rolling_mean():
    s = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    out = sma(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    # (10+11+12)/3 = 11, (11+12+13)/3 = 12, (12+13+14)/3 = 13
    assert out.iloc[2] == pytest.approx(11.0)
    assert out.iloc[3] == pytest.approx(12.0)
    assert out.iloc[4] == pytest.approx(13.0)


def test_rsi_wilder_period_2_hand_computed():
    """Wilder RSI(2) via ewm(alpha=1/2), matching data.rsi.

    closes: 10, 11, 10, 12, 11, 13
    deltas:  —,  1, -1,  2, -1,  2
    gains:   —,  1,  0,  2,  0,  2
    losses:  —,  0,  1,  0,  1,  0

    avg_gain / avg_loss with alpha=0.5, min_periods=2, adjust=False:
      i=2: avg_g=0.5, avg_l=0.5 → RS=1 → RSI=50
      i=3: avg_g=1.25, avg_l=0.25 → RS=5 → RSI=100 - 100/6 ≈ 83.333
      i=4: avg_g=0.625, avg_l=0.625 → RS=1 → RSI=50
      i=5: avg_g=1.3125, avg_l=0.3125 → RS=4.2 → RSI≈80.769
    """
    s = pd.Series([10.0, 11.0, 10.0, 12.0, 11.0, 13.0])
    out = rsi(s, period=2)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(50.0)
    assert out.iloc[3] == pytest.approx(100.0 - 100.0 / 6.0)
    assert out.iloc[4] == pytest.approx(50.0)
    assert out.iloc[5] == pytest.approx(100.0 - 100.0 / (1.0 + 4.2))


def test_rsi_all_gains_is_100():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = rsi(s, 2)
    assert out.dropna().eq(100.0).all()
