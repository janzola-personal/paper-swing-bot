"""rsi2_positions: entry/exit rules and warm-up NaNs."""

import numpy as np
import pandas as pd

from strategy import rsi2_positions


def _ohlcv(closes: list[float]) -> pd.DataFrame:
    s = pd.Series(closes, dtype=float)
    idx = pd.bdate_range("2024-01-02", periods=len(closes))
    return pd.DataFrame(
        {"open": s.values, "high": s.values, "low": s.values, "close": s.values, "volume": 1e6},
        index=idx,
    )


# Short trend window so fixtures stay small; entry/exit thresholds match config defaults.
PARAMS = dict(
    rsi_period=2,
    entry_rsi=10.0,
    trend_sma=20,
    exit_sma=5,
    exit_rsi=65.0,
    max_hold_days=10,
)

# linspace climb leaves SMA20 well below spot so a sharp pullback can still be
# above the regime filter while RSI(2) dips under 10.
_CLIMB = list(np.linspace(100, 150, 40))


def test_warmup_nans_force_position_zero():
    """Until SMA(trend) / RSI warm up, position must stay 0."""
    # Only 10 bars — trend_sma=20 never warms up
    df = _ohlcv(list(np.linspace(100, 110, 10)))
    pos = rsi2_positions(df, PARAMS)
    assert (pos == 0).all()


def test_no_entry_below_trend_sma():
    """RSI may be < entry_rsi, but close below SMA(trend) → no entry."""
    # Deep crash: RSI low but below SMA20
    df = _ohlcv(_CLIMB + [146.0, 130.0])
    pos = rsi2_positions(df, PARAMS)
    assert int(pos.iloc[-1]) == 0


def test_no_entry_when_rsi_not_oversold():
    df = _ohlcv(_CLIMB + [151.0, 152.0])  # RSI(2) ~ 100
    pos = rsi2_positions(df, PARAMS)
    assert int(pos.iloc[-1]) == 0


def test_entry_when_rsi_below_threshold_and_above_trend_sma():
    # Hand-checked: pull [146, 141] → RSI≈8.4 < 10 and close > SMA20
    df = _ohlcv(_CLIMB + [146.0, 141.0])
    pos = rsi2_positions(df, PARAMS)
    assert int(pos.iloc[-1]) == 1
    assert int(pos.iloc[-2]) == 0  # prior bar RSI too high


def test_exit_on_rsi_above_exit_rsi():
    # Enter at 141, next bar hard bounce → RSI > 65
    df = _ohlcv(_CLIMB + [146.0, 141.0, 148.0])
    pos = rsi2_positions(df, PARAMS)
    assert int(pos.iloc[-2]) == 1
    assert int(pos.iloc[-1]) == 0


def test_exit_on_close_above_exit_sma():
    """Isolate SMA exit by raising exit_rsi so RSI rule does not fire first."""
    params = {**PARAMS, "exit_rsi": 99.0}
    # After entry, grind up through SMA5 while RSI stays < 99
    df = _ohlcv(_CLIMB + [146.0, 141.0, 141.5, 142.0, 142.5, 143.0, 144.0])
    pos = rsi2_positions(df, params)
    # Must have entered
    assert pos.max() == 1
    # Eventually flat after close > SMA5
    assert int(pos.iloc[-1]) == 0
    # Find first exit after entry
    entered = False
    exited = False
    for i in range(len(pos)):
        if pos.iloc[i] == 1:
            entered = True
        elif entered and pos.iloc[i] == 0:
            exited = True
            break
    assert exited


def test_exit_on_max_hold_days():
    # Keep exit_sma warmable; decline so close stays below SMA5; exit_rsi high
    # so only the time stop fires. (exit_sma=1000 would NaN-block all bars.)
    params = {**PARAMS, "max_hold_days": 3, "exit_rsi": 99.0}
    df = _ohlcv(_CLIMB + [146.0, 141.0, 140.0, 139.5, 139.0, 138.5])
    pos = rsi2_positions(df, params)
    entry_i = int(np.where(pos.values == 1)[0][0])
    # entry day bars_held=0; exit when bars_held >= 3 → flat on entry_i+3
    assert int(pos.iloc[entry_i]) == 1
    assert int(pos.iloc[entry_i + 1]) == 1
    assert int(pos.iloc[entry_i + 2]) == 1
    assert int(pos.iloc[entry_i + 3]) == 0
