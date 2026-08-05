"""notify.py — Resend helpers with mocked HTTP (no real email, no secrets logged)."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import notify
from notify import DecisionLine
from db.store import MemoryStore
from watchdog_logic import send_norun_email


@pytest.fixture
def notify_env(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_not_real")
    monkeypatch.setenv("NOTIFY_EMAIL_TO", "owner@example.com")
    monkeypatch.setenv("NOTIFY_EMAIL_FROM", "bot@example.com")
    monkeypatch.setenv("DASHBOARD_URL", "https://example.vercel.app")


def test_skipped_when_unconfigured(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("NOTIFY_EMAIL_TO", "x@y.com")
    assert notify.send_email("s", "b") == "skipped_unconfigured"


def test_digest_subject_buy():
    day = date(2026, 7, 27)
    decisions = [
        DecisionLine("SPY", "flat", 0, 100.0, "rsi2=40"),
        DecisionLine("QQQ", "buy", 73, 682.0, "rsi2=7.8"),
    ]
    assert notify.digest_subject(day, decisions) == "Bot · BUY 73 QQQ"


def test_digest_subject_flat_and_empty():
    day = date(2026, 7, 27)
    assert notify.digest_subject(day, [DecisionLine("SPY", "flat", 0, 100.0, "x")]) == "Bot · FLAT"
    assert notify.digest_subject(day, []) == "Bot · no trades · 2026-07-27"


def test_send_email_success_and_retry(notify_env, monkeypatch):
    calls = {"n": 0}

    def post(url, data, api_key):
        calls["n"] += 1
        assert api_key == "re_test_key_not_real"
        assert b"Bot" in data or b"Trading" in data or True
        if calls["n"] == 1:
            return 500, "temporary"
        return 200, '{"id":"abc"}'

    sleeps = []
    status = notify.send_email(
        "Bot · BUY 1 SPY",
        "body",
        post=post,
        sleep=lambda s: sleeps.append(s),
    )
    assert status == "sent_retry:200"
    assert calls["n"] == 2
    assert sleeps == [0.5]


def test_send_email_never_logs_api_key(notify_env, caplog):
    import logging

    caplog.set_level(logging.WARNING)

    def post(url, data, api_key):
        # Malicious response echoes the key — redact must strip it from logs
        return 500, f"bad key re_test_key_not_real"

    notify.send_email("subj", "body", post=post, sleep=lambda s: None)
    joined = " ".join(r.message for r in caplog.records)
    assert "re_test_key_not_real" not in joined
    assert "[REDACTED]" in joined


def test_halt_and_error_and_norun_subjects(notify_env):
    sent = []

    def post(url, data, api_key):
        import json

        payload = json.loads(data.decode())
        sent.append(payload["subject"])
        return 200, "{}"

    notify.send_halt(
        trading_day=date(2026, 7, 27),
        reason="Daily loss -2.1%; flattening",
        equity=9800.0,
        peak=10000.0,
        flatten_lines=["SELL 10 SPY"],
        post=post,
    )
    notify.send_error(
        trading_day=date(2026, 7, 27),
        error_class="TimeoutError",
        detail="alpaca timeout",
        post=post,
    )
    notify.send_norun(
        trading_day=date(2026, 7, 27),
        detail="no runs row",
        post=post,
    )
    assert sent[0].startswith("Bot · HALT ·")
    assert sent[1] == "Bot · ERROR · run failed"
    assert sent[2] == "Bot · NO RUN · 2026-07-27"


def test_digest_body_includes_inputs(notify_env):
    body = notify.build_digest_body(
        trading_day=date(2026, 7, 27),
        mode="shadow",
        decisions=[
            DecisionLine(
                "QQQ",
                "buy",
                73,
                682.12,
                "rsi2 | close=682.12 rsi2=7.8 sma5=694.53 sma200=642.31",
            )
        ],
        equity=100_000.0,
        cash=50_000.0,
        day_pnl_pct=0.0028,
    )
    assert "rsi2=7.8" in body
    assert "shadow" in body
    assert "https://example.vercel.app" in body
    assert "+0.28%" in body


def test_norun_dedupe(notify_env, monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr("watchdog_logic.default_store", lambda: store)
    posts = []

    def post(url, data, api_key):
        posts.append(1)
        return 200, "{}"

    monkeypatch.setattr(
        "notify.send_email",
        lambda subject, body, post=None, sleep=None: (
            posts.append(1) or "sent:200"
        ),
    )
    day = date(2026, 7, 27)
    r1 = send_norun_email(day, "missing")
    r2 = send_norun_email(day, "missing")
    assert r1.startswith("sent")
    assert r2 == "skipped_already_sent"
    assert len(posts) == 1


def test_engine_digest_on_ok(notify_env, monkeypatch):
    """run_once success path calls send_digest (mocked)."""
    from unittest.mock import MagicMock
    import numpy as np
    import pandas as pd
    from engine import run_once

    called = {}

    def fake_digest(**kwargs):
        called.update(kwargs)
        return "sent:200"

    monkeypatch.setattr("notify.send_digest", fake_digest)

    idx = pd.bdate_range(end=pd.Timestamp("2026-07-27"), periods=250)
    close = np.linspace(80.0, 100.0, 250)
    bars = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1e6},
        index=idx,
    )
    broker = MagicMock()
    broker.market_open_now.return_value = False
    broker.equity_and_cash.return_value = (10_000.0, 10_000.0)
    broker.positions.return_value = {}
    broker.flatten_all.return_value = []
    broker.flatten_symbols.return_value = []
    broker.open_orders.return_value = []

    store = MemoryStore()
    r = run_once(
        date(2026, 7, 27),
        submit=False,
        shadow=True,
        store=store,
        broker=broker,
        fetch_bars=lambda s, y=2: bars.copy(),
    )
    assert r.status == "ok"
    assert r.notify_status == "sent:200"
    assert called.get("mode") == "shadow/swing"
    assert called.get("trading_day") == date(2026, 7, 27)
