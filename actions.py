"""
Dashboard mutations (pause / flatten / reset-halt).

Called from Vercel Python routes; Next.js authenticates the user then proxies
here with CRON_SECRET / HOSTED_RUN_SECRET. Every action journals `actor`.
No buy / submit-preview path — scheduled engine owns entries.

Mutations accept an optional engine name (default: swing). Flatten is
symbol-scoped to that engine's universe; pass engine="all" for account-wide
emergency flatten.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import config
from db.store import Store, default_store
from hosted import shadow_from_env, submit_from_env
from trading_day import resolve_trading_day


def _trading_day_or_none() -> date | None:
    try:
        return resolve_trading_day()
    except Exception:  # noqa: BLE001 — calendar optional for journaling
        return None


def _resolve_spec(engine: str | None) -> config.EngineSpec:
    name = (engine or "swing").strip().lower()
    return config.engine_by_name(name)


def set_paused(
    paused: bool,
    actor: str,
    store: Store | None = None,
    *,
    engine: str | None = None,
) -> dict[str, Any]:
    """Toggle operator pause for one engine. Paused runs skip new orders."""
    if not actor or not str(actor).strip():
        raise ValueError("actor required")
    spec = _resolve_spec(engine)
    store = store or default_store()
    state = store.load_state(spec.strategy)
    state.paused = bool(paused)
    store.save_state(state, spec.strategy)
    day = _trading_day_or_none()
    store.append_journal(
        trading_day=day,
        symbol="SYSTEM",
        action="PAUSE" if paused else "RESUME",
        qty=0,
        ref_price=0.0,
        reason=f"Operator set paused={paused} engine={spec.name}",
        equity=0.0,
        cash=0.0,
        dry_run=True,
        actor=actor.strip(),
        strategy=spec.strategy,
    )
    return {
        "ok": True,
        "paused": state.paused,
        "actor": actor.strip(),
        "engine": spec.name,
        "strategy": spec.strategy,
    }


def flatten_now(
    actor: str,
    *,
    submit: bool | None = None,
    store: Store | None = None,
    broker: Any | None = None,
    engine: str | None = None,
) -> dict[str, Any]:
    """Flatten positions for one engine (or all if engine='all')."""
    if not actor or not str(actor).strip():
        raise ValueError("actor required")
    store = store or default_store()
    if broker is None:
        from broker import PaperBroker

        broker = PaperBroker()

    place = submit_from_env() if submit is None else bool(submit)
    if shadow_from_env():
        place = False

    eng_name = (engine or "swing").strip().lower()
    equity, cash = broker.equity_and_cash()
    day = _trading_day_or_none()

    if eng_name == "all":
        lines = broker.flatten_all(submit=place)
        journal_strategy = None
        label = "all"
    else:
        spec = _resolve_spec(eng_name)
        # Prefer engine-specific submit/shadow when flattening that engine.
        place = submit_from_env(spec) if submit is None else bool(submit)
        if shadow_from_env(spec):
            place = False
        lines = broker.flatten_symbols(list(spec.symbols), submit=place)
        journal_strategy = spec.strategy
        label = spec.name

    for line in lines:
        store.append_journal(
            trading_day=day,
            symbol="SYSTEM",
            action="FLATTEN",
            qty=0,
            ref_price=0.0,
            reason=f"[{label}] {line}",
            equity=equity,
            cash=cash,
            dry_run=not place,
            actor=actor.strip(),
            strategy=journal_strategy,
        )
    if not lines:
        store.append_journal(
            trading_day=day,
            symbol="SYSTEM",
            action="FLATTEN",
            qty=0,
            ref_price=0.0,
            reason=f"[{label}] No open positions to flatten",
            equity=equity,
            cash=cash,
            dry_run=True,
            actor=actor.strip(),
            strategy=journal_strategy,
        )
    return {
        "ok": True,
        "actor": actor.strip(),
        "submitted": place,
        "shadow": shadow_from_env(
            None if eng_name == "all" else _resolve_spec(eng_name)
        ),
        "lines": lines,
        "equity": equity,
        "cash": cash,
        "engine": label,
    }


def reset_hard_halt(
    actor: str,
    store: Store | None = None,
    *,
    engine: str | None = None,
) -> dict[str, Any]:
    """Clear hard drawdown halt for one engine; peak re-anchors on next run."""
    if not actor or not str(actor).strip():
        raise ValueError("actor required")
    spec = _resolve_spec(engine)
    store = store or default_store()
    state = store.load_state(spec.strategy)
    prev_reason = state.halted_reason
    state.halted = False
    state.halted_reason = ""
    # Peak re-anchors on next equity observation (same as risk.reset_halt / CLI).
    state.peak_equity = 0.0
    store.save_state(state, spec.strategy)
    day = _trading_day_or_none()
    store.append_journal(
        trading_day=day,
        symbol="SYSTEM",
        action="RESET_HALT",
        qty=0,
        ref_price=0.0,
        reason=(
            f"[{spec.name}] Hard halt cleared; peak equity will re-anchor on next run. "
            f"Previous reason: {prev_reason or '(none)'}"
        ),
        equity=0.0,
        cash=0.0,
        dry_run=True,
        actor=actor.strip(),
        strategy=spec.strategy,
    )
    return {
        "ok": True,
        "halted": False,
        "actor": actor.strip(),
        "previous_reason": prev_reason,
        "engine": spec.name,
        "strategy": spec.strategy,
    }
