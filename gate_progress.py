"""Stage B paper gate counters (WEBUI / digest). Pure reads — no signal logic."""

from __future__ import annotations

from datetime import date
from typing import Any

_HANDLED_SUBMIT = frozenset(
    {"ok", "halt", "paused", "skipped_stale_data", "skipped_duplicate"}
)
_OVERRIDE_ACTIONS = frozenset({"FLATTEN", "PAUSE", "RESUME", "RESET_HALT"})


def paper_gate_stats(store: Any, strategy: str) -> dict[str, int | str | None]:
    """Days / trades / overrides / halts since first submit-mode run."""
    runs = _all_runs(store, strategy)
    submit_days = sorted(
        {
            r["trading_day"]
            for r in runs
            if r.get("mode") == "submit" and r.get("status") in _HANDLED_SUBMIT
        }
    )
    start = submit_days[0] if submit_days else None
    journal = _all_journal(store)
    if start:
        journal = [j for j in journal if (j.get("trading_day") or "") >= start]

    trades = sum(
        1
        for j in journal
        if str(j.get("action", "")).lower() in ("buy", "sell")
        and int(j.get("qty") or 0) > 0
        and not bool(j.get("dry_run", True))
    )
    overrides = sum(
        1
        for j in journal
        if j.get("actor")
        and str(j.get("action", "")).upper() in _OVERRIDE_ACTIONS
    )
    halts = sum(1 for j in journal if str(j.get("action", "")).lower() == "halt")
    return {
        "days": len(submit_days),
        "trades": trades,
        "overrides": overrides,
        "halts": halts,
        "paper_start": start,
        "days_target": 60,
        "trades_target": 40,
    }


def gate_progress_line(store: Any, strategy: str) -> str:
    s = paper_gate_stats(store, strategy)
    return (
        f"Gate Stage B: Days {s['days']}/{s['days_target']} · "
        f"Trades {s['trades']}/{s['trades_target']} · "
        f"Overrides {s['overrides']} (must stay 0) · Halts {s['halts']}"
    )


def is_first_submit_completion(
    store: Any, strategy: str, trading_day: date
) -> bool:
    """True when no earlier submit-mode handled run exists before trading_day."""
    iso = trading_day.isoformat()
    for r in _all_runs(store, strategy):
        if r.get("mode") != "submit":
            continue
        if r.get("status") not in _HANDLED_SUBMIT:
            continue
        day = r.get("trading_day") or ""
        if day and day < iso:
            return False
    return True


def _all_runs(store: Any, strategy: str) -> list[dict[str, Any]]:
    if hasattr(store, "list_runs"):
        return list(store.list_runs(strategy))
    # MemoryStore fallback shape
    runs = getattr(store, "runs", None)
    if isinstance(runs, dict):
        out = []
        for key, row in runs.items():
            if isinstance(key, tuple) and len(key) == 2:
                day, strat = key
                if strat != strategy:
                    continue
                out.append({**row, "trading_day": day, "strategy": strat})
        return out
    return []


def _all_journal(store: Any) -> list[dict[str, Any]]:
    if hasattr(store, "list_journal"):
        return list(store.list_journal(limit=5000))
    return list(getattr(store, "journal", []) or [])
