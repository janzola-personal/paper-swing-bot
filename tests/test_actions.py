"""Dashboard mutations: pause / flatten / reset-halt journal actor."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from actions import flatten_now, reset_hard_halt, set_paused
from db.store import MemoryStore
from risk import BotState


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


def test_set_paused_journals_actor(store: MemoryStore):
    out = set_paused(True, "owner@example.com", store=store)
    assert out["paused"] is True
    assert store.load_state().paused is True
    assert store.journal[-1]["action"] == "PAUSE"
    assert store.journal[-1]["actor"] == "owner@example.com"

    out2 = set_paused(False, "owner@example.com", store=store)
    assert out2["paused"] is False
    assert store.load_state().paused is False
    assert store.journal[-1]["action"] == "RESUME"


def test_set_paused_requires_actor(store: MemoryStore):
    with pytest.raises(ValueError, match="actor"):
        set_paused(True, "  ", store=store)


def test_reset_hard_halt_clears_and_reanchors(store: MemoryStore):
    st = BotState(halted=True, halted_reason="Drawdown -12%", peak_equity=100_000)
    store.save_state(st)
    out = reset_hard_halt("owner@example.com", store=store)
    loaded = store.load_state()
    assert out["halted"] is False
    assert loaded.halted is False
    assert loaded.halted_reason == ""
    assert loaded.peak_equity == 0.0
    assert store.journal[-1]["action"] == "RESET_HALT"
    assert store.journal[-1]["actor"] == "owner@example.com"
    assert "re-anchor" in store.journal[-1]["reason"].lower()


def test_flatten_now_dry_run_journals(store: MemoryStore, monkeypatch):
    monkeypatch.setenv("BOT_SHADOW_MODE", "true")
    monkeypatch.setenv("BOT_SUBMIT", "false")

    broker = MagicMock()
    broker.equity_and_cash.return_value = (10_000.0, 4_000.0)
    broker.flatten_symbols.return_value = ["[dry-run] would SELL 10 SPY"]

    out = flatten_now("owner@example.com", store=store, broker=broker, engine="swing")
    assert out["ok"] is True
    assert out["submitted"] is False
    broker.flatten_symbols.assert_called_once()
    assert store.journal[-1]["action"] == "FLATTEN"
    assert store.journal[-1]["actor"] == "owner@example.com"
    assert store.journal[-1]["dry_run"] is True
    assert store.journal[-1]["strategy"] == "rsi2"


def test_flatten_empty_positions_still_journals(store: MemoryStore, monkeypatch):
    monkeypatch.setenv("BOT_SHADOW_MODE", "true")
    broker = MagicMock()
    broker.equity_and_cash.return_value = (10_000.0, 10_000.0)
    broker.flatten_symbols.return_value = []
    flatten_now("a@b.co", store=store, broker=broker, engine="swing")
    assert "No open positions" in store.journal[-1]["reason"]
