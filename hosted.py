"""
Shared helpers for hosted schedulers (Vercel Cron + GitHub Actions).

Defaults are safe for shadow week: BOT_SHADOW_MODE=true, BOT_SUBMIT=false.
Leveraged trend stays shadow-only until Stage A passes (BOT_SUBMIT_LEV_TREND).
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import config
from config import EngineSpec
from engine import RunResult, capture_day_start, run_once


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).lower() in ("1", "true", "yes")


def shadow_from_env(engine: EngineSpec | None = None) -> bool:
    """Default True when unset/blank — shadow week fail-safe."""
    if engine is None:
        return _env_bool("BOT_SHADOW_MODE", default=True)
    return _env_bool(engine.shadow_env, default=True)


def submit_from_env(engine: EngineSpec | None = None) -> bool:
    """Default False when unset/blank — never submit by accident."""
    if engine is None:
        return _env_bool("BOT_SUBMIT", default=False)
    return _env_bool(engine.submit_env, default=False)


def run_after_close(trading_day: date | None = None) -> list[RunResult]:
    """After-close: run swing then lev_trend sequentially (disjoint symbols)."""
    results: list[RunResult] = []
    for name in ("swing", "lev_trend"):
        spec = config.engine_by_name(name)
        results.append(
            run_once(
                trading_day,
                submit=submit_from_env(spec),
                shadow=shadow_from_env(spec),
                engine=spec,
            )
        )
    return results


def run_open_capture(trading_day: date | None = None) -> list[RunResult]:
    """Morning capture for every engine (per-strategy day_start_equity)."""
    results: list[RunResult] = []
    for name in ("swing", "lev_trend"):
        spec = config.engine_by_name(name)
        results.append(capture_day_start(trading_day, engine=spec))
    return results


def result_to_dict(result: RunResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "trading_day": result.trading_day.isoformat() if result.trading_day else None,
        "mode": result.mode,
        "orders_submitted": result.orders_submitted,
        "messages": result.messages,
        "notify_status": result.notify_status,
        "engine": result.engine,
        "strategy": result.strategy,
    }


def results_to_dict(results: list[RunResult] | RunResult) -> dict[str, Any]:
    if isinstance(results, RunResult):
        return result_to_dict(results)
    return {
        "engines": [result_to_dict(r) for r in results],
        "status": (
            "ok"
            if all(r.status in ("ok", "paused", "skipped_not_trading_day", "skipped_duplicate") for r in results)
            else "error"
        ),
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
