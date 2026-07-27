"""risk.check_limits and size_shares (plus halt persistence)."""

from datetime import date
from pathlib import Path

import config
import risk


def test_hard_halt_persists_until_reset():
    today = date(2026, 7, 27)
    state = risk.BotState(peak_equity=10_000.0, halted=True, halted_reason="prior")
    ok, why = risk.check_limits(state, equity=9_500.0, today=today)
    assert not ok
    assert "HARD HALT" in why


def test_drawdown_halt_at_exactly_minus_10_pct():
    today = date(2026, 7, 27)
    state = risk.BotState(peak_equity=10_000.0)
    # Float edge: 9000/10000 - 1 is slightly greater than -0.10 in IEEE floats.
    # Use equity that is clearly at/below the −10% threshold.
    ok, why = risk.check_limits(state, equity=8_999.0, today=today)
    assert not ok
    assert state.halted is True
    assert "Drawdown" in why


def test_drawdown_just_above_threshold_ok():
    today = date(2026, 7, 27)
    state = risk.BotState(peak_equity=10_000.0)
    ok, _ = risk.check_limits(state, equity=9_001.0, today=today)
    assert ok
    assert state.halted is False


def test_daily_loss_halt_persists_same_day():
    today = date(2026, 7, 27)
    state = risk.capture_day_start(risk.BotState(), 10_000.0, today)
    ok, _ = risk.check_limits(state, equity=9_700.0, today=today)
    assert not ok
    # Second check same day without re-computing PnL path
    ok2, why2 = risk.check_limits(state, equity=10_500.0, today=today)
    assert not ok2
    assert "Daily-loss halt active" in why2


def test_daily_loss_clears_next_session():
    d1 = date(2026, 7, 27)
    d2 = date(2026, 7, 28)
    state = risk.capture_day_start(risk.BotState(), 10_000.0, d1)
    risk.check_limits(state, equity=9_700.0, today=d1)
    assert state.day_halted_date == d1.isoformat()
    # Next day: capture new baseline, daily halt date no longer matches
    state = risk.capture_day_start(state, 9_700.0, d2)
    ok, _ = risk.check_limits(state, equity=9_700.0, today=d2)
    assert ok


def test_size_shares_whole_shares_cash_and_pct_cap():
    assert risk.size_shares(100.0, equity=10_000.0, cash=10_000.0) == 50
    assert risk.size_shares(100.0, equity=10_000.0, cash=3_000.0) == 30  # cash binds
    assert risk.size_shares(100.0, equity=10_000.0, cash=0.0) == 0
    assert risk.size_shares(0.0, equity=10_000.0, cash=10_000.0) == 0
    # Never fractional
    assert risk.size_shares(333.0, equity=10_000.0, cash=10_000.0) == int(5000 // 333)


def test_save_load_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    state = risk.BotState(peak_equity=1_234.0, halted=True, halted_reason="test")
    risk.save_state(state)
    loaded = risk.load_state()
    assert loaded.peak_equity == 1_234.0
    assert loaded.halted is True
    assert loaded.halted_reason == "test"
    assert Path(config.STATE_FILE).exists()
