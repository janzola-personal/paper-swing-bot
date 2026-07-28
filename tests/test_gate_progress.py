"""Stage B gate counters + first-submit digest."""

from datetime import date

from db.store import MemoryStore
from gate_progress import (
    gate_progress_line,
    is_first_submit_completion,
    paper_gate_stats,
)
from notify import DecisionLine, build_digest_body, digest_subject


def test_paper_gate_stats_counts_submit_days_and_live_trades():
    store = MemoryStore()
    store.runs[("2026-07-28", "rsi2")] = {
        "id": 1,
        "status": "ok",
        "mode": "submit",
    }
    store.runs[("2026-07-29", "rsi2")] = {
        "id": 2,
        "status": "ok",
        "mode": "submit",
    }
    store.journal.append(
        {
            "trading_day": "2026-07-28",
            "action": "buy",
            "qty": 10,
            "dry_run": False,
            "actor": None,
        }
    )
    store.journal.append(
        {
            "trading_day": "2026-07-28",
            "action": "FLATTEN",
            "qty": 0,
            "dry_run": True,
            "actor": "owner@x.com",
        }
    )
    stats = paper_gate_stats(store, "rsi2")
    assert stats["days"] == 2
    assert stats["trades"] == 1
    assert stats["overrides"] == 1
    assert stats["paper_start"] == "2026-07-28"
    line = gate_progress_line(store, "rsi2")
    assert "Days 2/60" in line
    assert "Overrides 1" in line


def test_first_submit_completion_flag():
    store = MemoryStore()
    assert is_first_submit_completion(store, "rsi2", date(2026, 7, 28)) is True
    store.runs[("2026-07-27", "rsi2")] = {
        "id": 1,
        "status": "ok",
        "mode": "submit",
    }
    assert is_first_submit_completion(store, "rsi2", date(2026, 7, 28)) is False


def test_first_submit_digest_banner():
    body = build_digest_body(
        trading_day=date(2026, 7, 28),
        mode="submit",
        decisions=[
            DecisionLine("QQQ", "buy", 10, 100.0, "rsi2 | rsi2=5"),
        ],
        equity=10_000,
        cash=5_000,
        day_pnl_pct=None,
        gate_line="Gate Stage B: Days 1/60 · Trades 0/40 · Overrides 0 (must stay 0) · Halts 0",
        first_submit=True,
    )
    assert "FIRST PAPER SUBMIT" in body
    assert "queues for tomorrow's open" in body
    assert "Gate Stage B" in body
    subj = digest_subject(date(2026, 7, 28), [DecisionLine("QQQ", "buy", 10, 100.0, "x")])
    assert "BUY" in subj
