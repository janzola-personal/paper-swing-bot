"""
Shared helpers for hosted schedulers (Vercel Cron + GitHub Actions).

Defaults are safe for shadow week: BOT_SHADOW_MODE=true, BOT_SUBMIT=false.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from engine import RunResult, capture_day_start, run_once


def shadow_from_env() -> bool:
    """Default True when unset/blank — shadow week fail-safe."""
    raw = os.environ.get("BOT_SHADOW_MODE")
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).lower() in ("1", "true", "yes")


def submit_from_env() -> bool:
    """Default False when unset/blank — never submit by accident."""
    raw = os.environ.get("BOT_SUBMIT")
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).lower() in ("1", "true", "yes")


def run_after_close(trading_day: date | None = None) -> RunResult:
    """After-close swing run. Shadow by default — no submit_order."""
    return run_once(
        trading_day,
        submit=submit_from_env(),
        shadow=shadow_from_env(),
    )


def run_open_capture(trading_day: date | None = None) -> RunResult:
    return capture_day_start(trading_day)


def result_to_dict(result: RunResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "trading_day": result.trading_day.isoformat() if result.trading_day else None,
        "mode": result.mode,
        "orders_submitted": result.orders_submitted,
        "messages": result.messages,
        "notify_status": result.notify_status,
    }


def authorize_cron(headers: dict[str, str]) -> bool:
    """Vercel Cron sends Authorization: Bearer $CRON_SECRET when configured."""
    secret = os.environ.get("CRON_SECRET") or os.environ.get("HOSTED_RUN_SECRET")
    if not secret:
        # Fail closed in production-like envs; allow local if unset + ALLOW_UNAUTH_CRON
        if os.environ.get("ALLOW_UNAUTH_CRON", "").lower() in ("1", "true"):
            return True
        return False
    auth = headers.get("Authorization") or headers.get("authorization") or ""
    if auth == f"Bearer {secret}":
        return True
    # Also accept x-hosted-secret for Actions→Vercel manual pokes
    if (headers.get("x-hosted-secret") or headers.get("X-Hosted-Secret")) == secret:
        return True
    return False


def json_response(handler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
