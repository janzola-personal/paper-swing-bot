"""
Portable daily engine entry point.

  run_once(trading_day, *, submit, shadow, store=..., broker=...)

No local disk writes when using PostgresStore. FileStore is optional for
local CLI. Dual schedulers rely on store.claim_run UNIQUE(trading_day, strategy).

Hardening (C3): stale bars abort, calendar holidays, partial-fill reconcile,
crash → runs.status=error (finally), Alpaca retries live in data/broker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Sequence

import config
import notify
import risk
import trading_day as trading_day_mod
from data import bars_are_stale, bar_stale_days, fetch_daily, last_bar_date
from db.store import Store, default_store
from gate_progress import gate_progress_line, is_first_submit_completion
from notify import DecisionLine
from strategy import STRATEGIES, desired_position_today
from trading_day import Session

log = logging.getLogger("bot")


@dataclass
class RunResult:
    status: str  # ok | halt | paused | error | skipped_* …
    trading_day: date | None
    mode: str
    messages: list[str] = field(default_factory=list)
    orders_submitted: int = 0
    decisions: list[DecisionLine] = field(default_factory=list)
    equity: float = 0.0
    cash: float = 0.0
    day_pnl_pct: float | None = None
    notify_status: str = ""


def _day_pnl(state: risk.BotState, equity: float, today: date) -> float | None:
    if state.day_start_date == today.isoformat() and state.day_start_equity > 0:
        return equity / state.day_start_equity - 1.0
    return None


def _safe_notify(fn: Callable[[], str]) -> str:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — email must never crash the run
        return f"notify_exception:{type(exc).__name__}"


def run_once(
    trading_day: date | None = None,
    *,
    submit: bool = False,
    shadow: bool = False,
    store: Store | None = None,
    broker: Any | None = None,
    force: bool = False,
    fetch_bars: Callable[[str, int], Any] | None = None,
    calendar: Sequence[Session] | None = None,
    calendar_client: Any | None = None,
) -> RunResult:
    """After-close run: claim → risk → signals → reconcile → persist → notify.

    place_orders = submit and not shadow.
    Signals still use close-of-bar semantics; orders are DAY market (next open).
    Does not overwrite day_start_equity (morning job only).

    Look-ahead: desired_position_today uses bar t close only; no t+1 data.
    """
    assert config.PAPER_TRADING, "PAPER_TRADING must be True"
    assert config.ACTIVE_STRATEGY in STRATEGIES, f"Unknown strategy {config.ACTIVE_STRATEGY}"

    store = store if store is not None else default_store()
    fetch = fetch_bars or (lambda sym, years: fetch_daily(sym, years=years))

    place_orders = bool(submit) and not bool(shadow)
    if shadow:
        mode = "shadow"
    elif submit:
        mode = "submit"
    else:
        mode = "dry_run"

    if trading_day is None:
        # Hosted/default path: ET wall date × Alpaca calendar (holidays → None).
        today = trading_day_mod.resolve_trading_day(
            calendar=calendar, client=calendar_client
        )
    else:
        today = trading_day
        # Explicit day: still reject holidays when a calendar/client is provided
        # (tests inject a fixture; live force-checks can pass calendar_client).
        if calendar is not None or calendar_client is not None:
            if not trading_day_mod.is_trading_day(
                today, calendar=calendar, client=calendar_client
            ):
                msg = (
                    f"Not a trading day per Alpaca calendar "
                    f"({today.isoformat()}); skipping run."
                )
                log.info(msg)
                return RunResult("skipped_not_trading_day", today, mode, [msg])

    if today is None:
        msg = "Not a trading day (ET/Alpaca calendar); skipping run."
        log.info(msg)
        return RunResult("skipped_not_trading_day", None, mode, [msg])

    strategy = config.ACTIVE_STRATEGY

    if not force:
        claim = store.claim_run(today, strategy, mode)
        if not claim.acquired:
            msg = (
                f"skipped_duplicate: run already claimed for {today.isoformat()} "
                f"/ {strategy}"
            )
            return RunResult("skipped_duplicate", today, mode, [msg], orders_submitted=0)

    messages: list[str] = []
    decisions: list[DecisionLine] = []
    orders = 0
    status = "ok"
    equity = 0.0
    cash = 0.0
    day_pnl: float | None = None
    notify_status = ""
    finalized = False

    def jlog(
        symbol: str,
        action: str,
        qty: int,
        ref_price: float,
        reason: str,
        eq: float,
        ca: float,
    ) -> None:
        store.append_journal(
            trading_day=today,
            symbol=symbol,
            action=action,
            qty=qty,
            ref_price=ref_price,
            reason=reason,
            equity=eq,
            cash=ca,
            dry_run=not place_orders,
        )
        decisions.append(
            DecisionLine(
                symbol=symbol,
                action=action,
                qty=qty,
                ref_price=ref_price,
                reason=reason,
            )
        )

    def finish(run_status: str) -> None:
        nonlocal finalized, status
        status = run_status
        if not finalized:
            store.complete_run(today, strategy, run_status)
            finalized = True

    try:
        state = store.load_state()

        if state.paused:
            msg = "Operator pause active; no orders."
            messages.append(msg)
            jlog("*", "info", 0, 0.0, msg, 0.0, 0.0)
            finish("paused")
            return RunResult(status, today, mode, messages, 0, decisions)

        if broker is None:
            from broker import PaperBroker

            broker = PaperBroker()

        if broker.market_open_now():
            messages.append(
                "NOTE: market is OPEN. Market orders will fill immediately, not at "
                "the next open like the backtest assumes. Intended usage is after close."
            )

        equity, cash = broker.equity_and_cash()
        held = broker.positions()
        # Partial-fill reconcile: broker positions are source of truth next run.
        # want==1 & have>0 → hold (no top-up); want==0 & have>0 → sell remainder.
        open_orders: list[dict[str, Any]] = []
        if hasattr(broker, "open_orders"):
            try:
                open_orders = broker.open_orders() or []
            except Exception as exc:  # noqa: BLE001
                log.warning("open_orders check failed: %s", type(exc).__name__)
        recon = f"reconcile held={held or {}} open_orders={len(open_orders)}"
        if open_orders:
            recon += f" pending={[o.get('symbol') for o in open_orders]}"
        messages.append(recon)
        jlog("*", "reconcile", 0, 0.0, recon, equity, cash)
        log.info(recon)

        state = risk.update_peak(state, equity)
        day_pnl = _day_pnl(state, equity, today)

        ok, why = risk.check_limits(state, equity, today)
        if not ok:
            messages.append(f"RISK HALT: {why}")
            jlog("*", "halt", 0, 0.0, why, equity, cash)
            flatten_lines: list[str] = []
            for line in broker.flatten_all(submit=place_orders):
                messages.append(line)
                flatten_lines.append(line)
                if place_orders and "order" in line:
                    orders += 1
            store.save_state(state)
            store.snapshot_equity(today, strategy, equity, cash, held)
            finish("halt")
            notify_status = _safe_notify(
                lambda: notify.send_halt(
                    trading_day=today,
                    reason=why,
                    equity=equity,
                    peak=state.peak_equity,
                    flatten_lines=flatten_lines,
                )
            )
            return RunResult(
                status,
                today,
                mode,
                messages,
                orders,
                decisions,
                equity,
                cash,
                day_pnl,
                notify_status,
            )

        wants: list[tuple[str, int, str, float, float]] = []
        for symbol in config.SYMBOLS:
            df = fetch(symbol, 2)
            if bars_are_stale(df, today):
                age = bar_stale_days(df, today)
                last = last_bar_date(df)
                detail = (
                    f"Stale data for {symbol}: last bar {last.isoformat()} is "
                    f"{age} calendar days before trading day {today.isoformat()} "
                    f"(limit {config.MAX_BAR_STALE_DAYS}). Skipping run."
                )
                log.error(detail)
                messages.append(detail)
                jlog(symbol, "skip", 0, 0.0, detail, equity, cash)
                store.save_state(state)
                finish("skipped_stale_data")
                notify_status = _safe_notify(
                    lambda d=detail: notify.send_error(
                        trading_day=today,
                        error_class="StaleData",
                        detail=d,
                    )
                )
                return RunResult(
                    status,
                    today,
                    mode,
                    messages,
                    orders,
                    decisions,
                    equity,
                    cash,
                    day_pnl,
                    notify_status,
                )

            want, reason = desired_position_today(df, strategy)
            last_close = float(df["close"].iloc[-1])
            from data import rsi as _rsi

            last_rsi = float(_rsi(df["close"], 2).iloc[-1])
            wants.append((symbol, want, reason, last_close, last_rsi))

        entries = [w for w in wants if w[1] == 1 and w[0] not in held]
        entries.sort(key=lambda w: w[4])
        room = max(config.MAX_POSITIONS - len([s for s, q in held.items() if q > 0]), 0)
        skipped_entries = {w[0] for w in entries[room:]}

        messages.append(
            f"[{mode}] equity=${equity:,.2f} cash=${cash:,.2f} held={held or 'none'}"
        )

        for symbol, want, reason, last_close, _ in wants:
            have = held.get(symbol, 0)
            if want == 1 and have == 0:
                if symbol in skipped_entries:
                    msg = f"signal yes, but MAX_POSITIONS={config.MAX_POSITIONS} reached"
                    messages.append(f"  SKIP  {symbol}: {msg}")
                    jlog(
                        symbol,
                        "skip",
                        0,
                        last_close,
                        f"{reason} | {msg}",
                        equity,
                        cash,
                    )
                    continue
                qty = risk.size_shares(last_close, equity, cash)
                if qty == 0:
                    messages.append(f"  SKIP  {symbol}: sized to 0 shares")
                    jlog(
                        symbol,
                        "skip",
                        0,
                        last_close,
                        f"{reason} | sized to 0",
                        equity,
                        cash,
                    )
                    continue
                messages.append(
                    f"  BUY   {qty} {symbol} @ ~{last_close:.2f}  ({reason})"
                )
                if place_orders:
                    broker.submit_market(symbol, qty, "buy")
                    orders += 1
                cash -= qty * last_close
                jlog(symbol, "buy", qty, last_close, reason, equity, cash)
            elif want == 0 and have > 0:
                # Partial prior sell: have is remaining shares — sell all of it.
                messages.append(
                    f"  SELL  {have} {symbol} @ ~{last_close:.2f}  ({reason})"
                )
                if place_orders:
                    broker.submit_market(symbol, have, "sell")
                    orders += 1
                jlog(symbol, "sell", have, last_close, reason, equity, cash)
            else:
                # want==1 and have>0 (incl. partial fill) → hold; else flat
                action = "hold" if have > 0 else "flat"
                note = reason
                if want == 1 and have > 0:
                    note = f"{reason} | reconcile: already long {have} (no top-up)"
                messages.append(f"  {action.upper():5s} {symbol}  ({note})")
                jlog(symbol, action, have, last_close, note, equity, cash)

        state.last_run_date = today.isoformat()
        store.save_state(state)
        store.snapshot_equity(today, strategy, equity, cash, held)
        first_submit = mode == "submit" and is_first_submit_completion(
            store, strategy, today
        )
        finish("ok")
        messages.append("Done.")
        if mode == "submit" and place_orders and orders:
            messages.append(
                "Orders submitted as Alpaca PAPER market DAY — queue for next open."
            )
        gate_line = (
            gate_progress_line(store, strategy) if mode == "submit" else None
        )
        notify_status = _safe_notify(
            lambda: notify.send_digest(
                trading_day=today,
                mode=mode,
                decisions=decisions,
                equity=equity,
                cash=cash,
                day_pnl_pct=day_pnl,
                gate_line=gate_line,
                first_submit=first_submit,
            )
        )
        return RunResult(
            status,
            today,
            mode,
            messages,
            orders,
            decisions,
            equity,
            cash,
            day_pnl,
            notify_status,
        )

    except Exception as exc:  # noqa: BLE001 — persist error status for schedulers
        log.exception("run_once failed")
        messages.append(f"ERROR: {type(exc).__name__}")
        try:
            finish("error")
        except Exception:
            finalized = True  # avoid finally double-fault loops
        notify_status = _safe_notify(
            lambda: notify.send_error(
                trading_day=today,
                error_class=type(exc).__name__,
                detail=str(exc),
            )
        )
        return RunResult(
            status,
            today,
            mode,
            messages,
            orders,
            decisions,
            equity,
            cash,
            day_pnl,
            notify_status,
        )
    finally:
        # Crash / unexpected exit mid-write: never leave status stuck at 'claimed'.
        if not finalized:
            try:
                store.complete_run(today, strategy, "error")
                log.error("run finalized as error in finally (incomplete write path)")
            except Exception:
                pass


def capture_day_start(
    session_day: date | None = None,
    *,
    store: Store | None = None,
    broker: Any | None = None,
    calendar: Sequence[Session] | None = None,
    calendar_client: Any | None = None,
) -> RunResult:
    """Morning job: lock day_start_equity for the daily-loss halt."""
    assert config.PAPER_TRADING, "PAPER_TRADING must be True"
    store = store if store is not None else default_store()
    if session_day is None:
        today = trading_day_mod.resolve_trading_day(
            calendar=calendar, client=calendar_client
        )
    else:
        today = session_day
        if calendar is not None or calendar_client is not None:
            if not trading_day_mod.is_trading_day(
                today, calendar=calendar, client=calendar_client
            ):
                today = None
    if today is None:
        return RunResult(
            "skipped_not_trading_day",
            None,
            "capture",
            ["Not a trading day; skipping day-start capture."],
        )
    if broker is None:
        from broker import PaperBroker

        broker = PaperBroker()
    equity, _cash = broker.equity_and_cash()
    state = store.load_state()
    state = risk.capture_day_start(state, equity, today)
    store.save_state(state)
    msg = (
        f"Day-start equity captured for {today.isoformat()}: "
        f"${state.day_start_equity:,.2f} (peak=${state.peak_equity:,.2f})"
    )
    return RunResult("ok", today, "capture", [msg], equity=equity, cash=_cash)
