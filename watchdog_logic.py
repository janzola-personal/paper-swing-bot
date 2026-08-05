"""Missed-run check shared by api/watchdog.py and GitHub Actions."""

from __future__ import annotations

from datetime import date
from typing import Any

import config
import notify
from db.store import default_store

# Outcomes that mean "the day was handled" — do not page NO RUN.
_HANDLED = frozenset(
    {
        "ok",
        "halt",
        "paused",
        "skipped_duplicate",
        "skipped_stale_data",
        "skipped_not_trading_day",
    }
)


def check_run_present(
    trading_day: date,
    store=None,
    *,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Return whether an after-close run recorded a usable outcome.

    NO RUN is suppressed when operator paused. A row with status ok / halt /
    skipped_duplicate / skipped_stale_data means the day was handled.
    status=claimed or error → not ok (incomplete or failed).
    """
    strategy = strategy or config.ACTIVE_STRATEGY
    store = store if store is not None else default_store()
    state = store.load_state(strategy)
    if state.paused:
        return {
            "ok": True,
            "detail": f"paused ({strategy}) — NO RUN suppressed",
            "status": "paused_operator",
            "paused": True,
            "strategy": strategy,
        }

    if hasattr(store, "get_run"):
        row = store.get_run(trading_day, strategy)
        if row is None:
            # Legacy file-store fallback
            if state.last_run_date == trading_day.isoformat():
                return {
                    "ok": True,
                    "detail": "state.last_run_date match",
                    "status": "ok",
                    "paused": False,
                    "strategy": strategy,
                }
            return {
                "ok": False,
                "detail": f"no runs row ({strategy})",
                "status": None,
                "paused": False,
                "strategy": strategy,
            }
        status = row.get("status")
        if status in _HANDLED:
            return {
                "ok": True,
                "detail": f"status={status}",
                "status": status,
                "paused": False,
                "strategy": strategy,
            }
        if status == "error":
            return {
                "ok": False,
                "detail": f"run ended in error ({strategy})",
                "status": status,
                "paused": False,
                "strategy": strategy,
            }
        return {
            "ok": False,
            "detail": f"incomplete status={status} ({strategy})",
            "status": status,
            "paused": False,
            "strategy": strategy,
        }

    if state.last_run_date == trading_day.isoformat():
        return {
            "ok": True,
            "detail": "state.last_run_date match",
            "status": "ok",
            "paused": False,
            "strategy": strategy,
        }
    return {
        "ok": False,
        "detail": f"no last_run_date for today ({strategy})",
        "status": None,
        "paused": False,
        "strategy": strategy,
    }


def send_norun_email(
    trading_day: date,
    detail: str,
    store=None,
    *,
    strategy: str = "rsi2",
) -> str:
    """Send NO RUN via notify.py with once-per-day dedupe on bot_state."""
    store = store if store is not None else default_store()
    state = store.load_state(strategy)
    if state.paused:
        return "skipped_paused"
    iso = trading_day.isoformat()
    if state.watchdog_norun_sent_day == iso:
        return "skipped_already_sent"
    result = notify.send_norun(trading_day=trading_day, detail=detail)
    if result.startswith("sent"):
        state.watchdog_norun_sent_day = iso
        store.save_state(state, strategy)
    return result


def run_watchdog(trading_day: date | None = None, store=None) -> dict[str, Any]:
    """Full watchdog pass used by Vercel + Actions (deduped email).

    Checks every configured engine strategy; emails once if any is missing.
    """
    import trading_day as trading_day_mod

    store = store if store is not None else default_store()
    today = trading_day if trading_day is not None else trading_day_mod.resolve_trading_day()
    if today is None:
        return {"status": "skip", "reason": "not_a_trading_day"}

    checks = []
    for strat in config.ENGINE_STRATEGIES:
        checks.append(check_run_present(today, store=store, strategy=strat))

    missing = [c for c in checks if not c["ok"]]
    out: dict[str, Any] = {
        "trading_day": today.isoformat(),
        "engines": checks,
        "run_ok": len(missing) == 0,
        "detail": (
            "; ".join(c["detail"] for c in missing)
            if missing
            else "all engines handled"
        ),
        "run_status": missing[0].get("status") if missing else "ok",
    }
    if missing:
        # Dedupe email on the first missing strategy's state row.
        out["email"] = send_norun_email(
            today,
            out["detail"],
            store=store,
            strategy=missing[0].get("strategy") or "rsi2",
        )
    else:
        out["email"] = None
    return out
