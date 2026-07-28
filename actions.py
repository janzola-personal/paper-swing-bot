"""
Dashboard mutations (pause / flatten / reset-halt).

Called from Vercel Python routes; Next.js authenticates the user then proxies
here with CRON_SECRET / HOSTED_RUN_SECRET. Every action journals `actor`.
No buy / submit-preview path — scheduled engine owns entries.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from db.store import Store, default_store
from hosted import shadow_from_env, submit_from_env
from trading_day import resolve_trading_day


def _trading_day_or_none() -> date | None:
    try:
        return resolve_trading_day()
    except Exception:  # noqa: BLE001 — calendar optional for journaling
        return None


def set_paused(
    paused: bool,
    actor: str,
    store: Store | None = None,
) -> dict[str, Any]:
    """Toggle operator pause. Paused runs skip new orders (engine.run_once)."""
    if not actor or not str(actor).strip():
        raise ValueError("actor required")
    store = store or default_store()
    state = store.load_state()
    state.paused = bool(paused)
    store.save_state(state)
    day = _trading_day_or_none()
    store.append_journal(
        trading_day=day,
        symbol="SYSTEM",
        action="PAUSE" if paused else "RESUME",
        qty=0,
        ref_price=0.0,
        reason=f"Operator set paused={paused}",
        equity=0.0,
        cash=0.0,
        dry_run=True,
        actor=actor.strip(),
    )
    return {"ok": True, "paused": state.paused, "actor": actor.strip()}


def flatten_now(
    actor: str,
    *,
    submit: bool | None = None,
    store: Store | None = None,
    broker: Any | None = None,
) -> dict[str, Any]:
    """Emergency flatten all positions (next open). Respects shadow/submit env."""
    if not actor or not str(actor).strip():
        raise ValueError("actor required")
    store = store or default_store()
    if broker is None:
        from broker import PaperBroker

        broker = PaperBroker()

    place = submit_from_env() if submit is None else bool(submit)
    if shadow_from_env():
        place = False

    equity, cash = broker.equity_and_cash()
    lines = broker.flatten_all(submit=place)
    day = _trading_day_or_none()
    for line in lines:
        store.append_journal(
            trading_day=day,
            symbol="SYSTEM",
            action="FLATTEN",
            qty=0,
            ref_price=0.0,
            reason=line,
            equity=equity,
            cash=cash,
            dry_run=not place,
            actor=actor.strip(),
        )
    if not lines:
        store.append_journal(
            trading_day=day,
            symbol="SYSTEM",
            action="FLATTEN",
            qty=0,
            ref_price=0.0,
            reason="No open positions to flatten",
            equity=equity,
            cash=cash,
            dry_run=True,
            actor=actor.strip(),
        )
    return {
        "ok": True,
        "actor": actor.strip(),
        "submitted": place,
        "shadow": shadow_from_env(),
        "lines": lines,
        "equity": equity,
        "cash": cash,
    }


def reset_hard_halt(
    actor: str,
    store: Store | None = None,
) -> dict[str, Any]:
    """Clear hard drawdown halt and re-anchor peak on next run (peak → 0)."""
    if not actor or not str(actor).strip():
        raise ValueError("actor required")
    store = store or default_store()
    state = store.load_state()
    prev_reason = state.halted_reason
    state.halted = False
    state.halted_reason = ""
    # Peak re-anchors on next equity observation (same as risk.reset_halt / CLI).
    state.peak_equity = 0.0
    store.save_state(state)
    day = _trading_day_or_none()
    store.append_journal(
        trading_day=day,
        symbol="SYSTEM",
        action="RESET_HALT",
        qty=0,
        ref_price=0.0,
        reason=(
            "Hard halt cleared; peak equity will re-anchor on next run. "
            f"Previous reason: {prev_reason or '(none)'}"
        ),
        equity=0.0,
        cash=0.0,
        dry_run=True,
        actor=actor.strip(),
    )
    return {
        "ok": True,
        "halted": False,
        "actor": actor.strip(),
        "previous_reason": prev_reason,
    }
