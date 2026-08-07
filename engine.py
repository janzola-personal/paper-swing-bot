"""
Portable daily engine entry point.

  run_once(trading_day, *, submit, shadow, store=..., broker=..., engine=...)

No local disk writes when using PostgresStore. FileStore is optional for
local CLI. Dual schedulers rely on store.claim_run UNIQUE(trading_day, strategy).

Hardening (C3): stale bars abort, calendar holidays, partial-fill reconcile,
crash → runs.status=error (finally), Alpaca retries live in data/broker.

Look-ahead: desired_position_today uses bar t close only; fills at next open.
EngineSpec parameterization does not change signal timing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Sequence

import config
import notify
import risk
import trading_day as trading_day_mod
from config import EngineSpec
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
    engine: str = ""
    strategy: str = ""


def _day_pnl(state: risk.BotState, equity: float, today: date) -> float | None:
    if state.day_start_date == today.isoformat() and state.day_start_equity > 0:
        return equity / state.day_start_equity - 1.0
    return None


def _safe_notify(fn: Callable[[], str]) -> str:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — email must never crash the run
        return f"notify_exception:{type(exc).__name__}"


def _resolve_engine(engine: EngineSpec | str | None) -> EngineSpec:
    if isinstance(engine, EngineSpec):
        return engine
    if engine is None or str(engine) == "swing":
        # Rebuild from live config so monkeypatched SYMBOLS / risk limits
        # (and ACTIVE_STRATEGY) still apply — keeps swing bit-compatible.
        base = config.SWING_ENGINE
        signal = config.ACTIVE_STRATEGY
        if signal not in STRATEGIES:
            signal = base.signal
        # Claim key stays rsi2 for Stage B continuity when running rsi2 family.
        claim = base.strategy if signal in ("rsi2", "rsi2_tight") else signal
        return EngineSpec(
            name=base.name,
            strategy=claim,
            signal=signal,
            symbols=tuple(config.SYMBOLS),
            max_positions=config.MAX_POSITIONS,
            max_position_pct=config.MAX_POSITION_PCT,
            max_daily_loss_pct=config.MAX_DAILY_LOSS_PCT,
            max_drawdown_halt_pct=config.MAX_DRAWDOWN_HALT_PCT,
            allocation=None,
            submit_env=base.submit_env,
            shadow_env=base.shadow_env,
            label=base.label,
        )
    return config.engine_by_name(str(engine))


def _engine_book(
    spec: EngineSpec,
    state: risk.BotState,
    broker: Any,
    *,
    use_shadow: bool = False,
) -> tuple[float, float, dict[str, int]]:
    """Return (equity, cash, held) scoped to this engine.

    Swing (allocation=None): full Alpaca account equity/cash/positions filtered
    to the engine symbol universe for book management.
    Allocated engines: virtual_cash + MTM of own symbols; positions filtered.
    When ``use_shadow`` (dry-run / shadow, no broker fills), held comes from
    ``state.shadow_positions`` so overnight MTM does not collapse to leftover cash.
    """
    account_positions = broker.positions() or {}
    broker_held = {
        s: int(q)
        for s, q in account_positions.items()
        if s in spec.symbols and int(q) > 0
    }

    if spec.allocation is None:
        equity, cash = broker.equity_and_cash()
        return float(equity), float(cash), broker_held

    if use_shadow:
        held = {
            s: int(q)
            for s, q in (state.shadow_positions or {}).items()
            if s in spec.symbols and int(q) > 0
        }
    else:
        held = dict(broker_held)

    # Initialize virtual cash once for a new allocated engine.
    if state.virtual_cash <= 0 and state.peak_equity <= 0 and not held:
        state.virtual_cash = float(spec.allocation)

    # Mark-to-market engine symbols. Only accept real dict / numeric returns so
    # MagicMock auto-attributes cannot invent prices and false-halt the book.
    mtm = _mark_held_to_market(broker, held)

    cash = float(state.virtual_cash)
    equity = cash + mtm
    return equity, cash, held


def _mark_held_to_market(broker: Any, held: dict[str, int]) -> float:
    """Dollar MTM for held shares using broker helpers or test ``_mtm_prices``."""
    if not held:
        return 0.0

    pmv = getattr(broker, "position_market_values", None)
    if callable(pmv):
        values = pmv()
        if isinstance(values, dict) and values:
            total = 0.0
            missing = False
            for s, q in held.items():
                if s in values:
                    total += float(values[s])
                else:
                    missing = True
                    break
            if not missing:
                return total

    prices: dict[str, float] = {}
    lp_many = getattr(broker, "last_prices", None)
    if callable(lp_many):
        raw = lp_many(list(held.keys()))
        if isinstance(raw, dict):
            prices = {str(k): float(v) for k, v in raw.items()}

    if not prices:
        injected = getattr(broker, "_mtm_prices", None)
        if isinstance(injected, dict):
            prices = {str(k): float(v) for k, v in injected.items()}

    lp_one = getattr(broker, "last_price", None)
    total = 0.0
    for s, q in held.items():
        if s in prices:
            total += int(q) * float(prices[s])
            continue
        if callable(lp_one):
            got = lp_one(s)
            if isinstance(got, (int, float)) and not isinstance(got, bool):
                total += int(q) * float(got)
    return total


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
    engine: EngineSpec | str | None = None,
) -> RunResult:
    """After-close run: claim → risk → signals → reconcile → persist → notify.

    place_orders = submit and not shadow.
    Signals still use close-of-bar semantics; orders are DAY market (next open).
    Does not overwrite day_start_equity (morning job only).

    Look-ahead: desired_position_today uses bar t close only; no t+1 data.
    """
    assert config.PAPER_TRADING, "PAPER_TRADING must be True"
    spec = _resolve_engine(engine)
    assert spec.signal in STRATEGIES, f"Unknown signal strategy {spec.signal}"

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
                return RunResult(
                    "skipped_not_trading_day",
                    today,
                    mode,
                    [msg],
                    engine=spec.name,
                    strategy=spec.strategy,
                )

    if today is None:
        msg = "Not a trading day (ET/Alpaca calendar); skipping run."
        log.info(msg)
        return RunResult(
            "skipped_not_trading_day",
            None,
            mode,
            [msg],
            engine=spec.name,
            strategy=spec.strategy,
        )

    strategy = spec.strategy
    signal = spec.signal

    if not force:
        claim = store.claim_run(today, strategy, mode)
        if not claim.acquired:
            msg = (
                f"skipped_duplicate: run already claimed for {today.isoformat()} "
                f"/ {strategy}"
            )
            return RunResult(
                "skipped_duplicate",
                today,
                mode,
                [msg],
                orders_submitted=0,
                engine=spec.name,
                strategy=strategy,
            )

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
            strategy=strategy,
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
        state = store.load_state(strategy)

        if state.paused:
            msg = f"Operator pause active ({spec.name}); no orders."
            messages.append(msg)
            jlog("*", "info", 0, 0.0, msg, 0.0, 0.0)
            finish("paused")
            return RunResult(
                status,
                today,
                mode,
                messages,
                0,
                decisions,
                engine=spec.name,
                strategy=strategy,
            )

        if broker is None:
            from broker import PaperBroker

            broker = PaperBroker()

        if broker.market_open_now():
            messages.append(
                "NOTE: market is OPEN. Market orders will fill immediately, not at "
                "the next open like the backtest assumes. Intended usage is after close."
            )

        # Shadow book is SoT when not submitting (no broker fills). Broker is
        # SoT when place_orders=True; sync shadow from broker so a later flip
        # back to shadow cannot double-count.
        use_shadow = bool(spec.allocation is not None and not place_orders)
        if spec.allocation is not None and place_orders:
            equity, cash, held = _engine_book(
                spec, state, broker, use_shadow=False
            )
            state.shadow_positions = {
                s: int(q) for s, q in held.items() if int(q) > 0
            }
            store.save_state(state, strategy)
        else:
            equity, cash, held = _engine_book(
                spec, state, broker, use_shadow=use_shadow
            )

        open_orders: list[dict[str, Any]] = []
        if hasattr(broker, "open_orders"):
            try:
                open_orders = broker.open_orders() or []
            except Exception as exc:  # noqa: BLE001
                log.warning("open_orders check failed: %s", type(exc).__name__)
        # Only surface open orders in this engine's universe.
        open_orders = [
            o
            for o in open_orders
            if str(o.get("symbol", "")) in spec.symbols
        ]
        recon = (
            f"reconcile engine={spec.name} held={held or {}} "
            f"open_orders={len(open_orders)}"
        )
        if open_orders:
            recon += f" pending={[o.get('symbol') for o in open_orders]}"
        messages.append(recon)
        jlog("*", "reconcile", 0, 0.0, recon, equity, cash)
        log.info(recon)

        # Fetch bars before risk checks for allocated/shadow books: broker has no
        # fills to MTM, so equity must use bar-t closes (no look-ahead — still
        # the latest completed daily close only).
        wants: list[tuple[str, int, str, float, float]] = []
        closes: dict[str, float] = {}
        fetch_before_limits = bool(spec.allocation is not None)

        def _load_signals() -> RunResult | None:
            nonlocal equity, cash, day_pnl, notify_status, state
            for symbol in spec.symbols:
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
                    store.save_state(state, strategy)
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
                        engine=spec.name,
                        strategy=strategy,
                    )

                want, reason = desired_position_today(df, signal)
                last_close = float(df["close"].iloc[-1])
                closes[symbol] = last_close
                from data import rsi as _rsi

                last_rsi = float(_rsi(df["close"], 2).iloc[-1])
                wants.append((symbol, want, reason, last_close, last_rsi))

            if spec.allocation is not None:
                mtm = sum(
                    held.get(s, 0) * closes.get(s, 0.0) for s in spec.symbols
                )
                cash = float(state.virtual_cash)
                equity = cash + mtm
            return None

        if fetch_before_limits:
            early = _load_signals()
            if early is not None:
                return early

        state = risk.update_peak(state, equity)
        day_pnl = _day_pnl(state, equity, today)

        ok, why = risk.check_limits(
            state,
            equity,
            today,
            max_daily_loss_pct=spec.max_daily_loss_pct,
            max_drawdown_halt_pct=spec.max_drawdown_halt_pct,
        )
        if not ok:
            messages.append(f"RISK HALT: {why}")
            jlog("*", "halt", 0, 0.0, why, equity, cash)
            flatten_lines: list[str] = []
            for line in broker.flatten_symbols(list(spec.symbols), submit=place_orders):
                messages.append(line)
                flatten_lines.append(line)
                if place_orders and "order" in line:
                    orders += 1
                # Virtual cash: selling restores cash at unknown fill — leave
                # virtual_cash unchanged until next reconcile with prices.
            store.save_state(state, strategy)
            store.snapshot_equity(today, strategy, equity, cash, held)
            finish("halt")
            notify_status = _safe_notify(
                lambda: notify.send_halt(
                    trading_day=today,
                    reason=f"[{spec.label}] {why}",
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
                engine=spec.name,
                strategy=strategy,
            )

        if not fetch_before_limits:
            late = _load_signals()
            if late is not None:
                return late
            state = risk.update_peak(state, equity)
            day_pnl = _day_pnl(state, equity, today)

        entries = [w for w in wants if w[1] == 1 and w[0] not in held]
        # rsi2: lower RSI first. trend: no RSI meaning — stable symbol order.
        if signal == "rsi2":
            entries.sort(key=lambda w: w[4])
        else:
            entries.sort(key=lambda w: w[0])
        room = max(
            spec.max_positions - len([s for s, q in held.items() if q > 0]),
            0,
        )
        skipped_entries = {w[0] for w in entries[room:]}

        messages.append(
            f"[{mode}/{spec.name}] equity=${equity:,.2f} cash=${cash:,.2f} "
            f"held={held or 'none'}"
        )

        for symbol, want, reason, last_close, _ in wants:
            have = held.get(symbol, 0)
            if want == 1 and have == 0:
                if symbol in skipped_entries:
                    msg = f"signal yes, but MAX_POSITIONS={spec.max_positions} reached"
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
                qty = risk.size_shares(
                    last_close,
                    equity,
                    cash,
                    max_position_pct=spec.max_position_pct,
                )
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
                cost = qty * last_close
                cash -= cost
                if spec.allocation is not None:
                    state.virtual_cash = float(state.virtual_cash) - cost
                    # Persist shadow book on dry-run/shadow so next-day MTM
                    # does not see equity = leftover cash only.
                    if use_shadow:
                        state.shadow_positions[symbol] = int(qty)
                        held[symbol] = int(qty)
                jlog(symbol, "buy", qty, last_close, reason, equity, cash)
            elif want == 0 and have > 0:
                # Partial prior sell: have is remaining shares — sell all of it.
                messages.append(
                    f"  SELL  {have} {symbol} @ ~{last_close:.2f}  ({reason})"
                )
                if place_orders:
                    broker.submit_market(symbol, have, "sell")
                    orders += 1
                proceeds = have * last_close
                cash += proceeds
                if spec.allocation is not None:
                    state.virtual_cash = float(state.virtual_cash) + proceeds
                    state.shadow_positions.pop(symbol, None)
                held[symbol] = 0
                jlog(symbol, "sell", have, last_close, reason, equity, cash)
            else:
                # want==1 and have>0 (incl. partial fill) → hold; else flat
                action = "hold" if have > 0 else "flat"
                note = reason
                if want == 1 and have > 0:
                    note = f"{reason} | reconcile: already long {have} (no top-up)"
                messages.append(f"  {action.upper():5s} {symbol}  ({note})")
                jlog(symbol, action, have, last_close, note, equity, cash)

        # Recompute equity after virtual cash updates.
        if spec.allocation is not None:
            mtm = sum(held.get(s, 0) * closes.get(s, 0.0) for s in spec.symbols)
            cash = float(state.virtual_cash)
            equity = cash + mtm

        state.last_run_date = today.isoformat()
        store.save_state(state, strategy)
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
                mode=f"{mode}/{spec.name}",
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
            engine=spec.name,
            strategy=strategy,
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
            engine=spec.name,
            strategy=strategy,
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
    engine: EngineSpec | str | None = None,
) -> RunResult:
    """Morning job: lock day_start_equity for the daily-loss halt (per engine)."""
    assert config.PAPER_TRADING, "PAPER_TRADING must be True"
    spec = _resolve_engine(engine)
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
            engine=spec.name,
            strategy=spec.strategy,
        )
    if broker is None:
        from broker import PaperBroker

        broker = PaperBroker()
    state = store.load_state(spec.strategy)
    # Morning capture for allocated engines must use the same book as after-close
    # shadow runs (env: submit && !shadow → broker; else → shadow positions).

    def _env_bool(name: str, *, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None or str(raw).strip() == "":
            return default
        return str(raw).lower() in ("1", "true", "yes")

    place_orders = _env_bool(spec.submit_env, default=False) and not _env_bool(
        spec.shadow_env, default=True
    )
    use_shadow = bool(spec.allocation is not None and not place_orders)
    equity, _cash, _held = _engine_book(
        spec, state, broker, use_shadow=use_shadow
    )
    # Shadow books are absent from Alpaca — MTM with latest daily closes.
    if use_shadow and _held:
        mtm = 0.0
        for sym, qty in _held.items():
            df = fetch_daily(sym, years=1)
            if df is not None and len(df) > 0:
                mtm += int(qty) * float(df["close"].iloc[-1])
        _cash = float(state.virtual_cash)
        equity = _cash + mtm
    # For allocated engines without MTM prices yet, equity ≈ virtual_cash.
    if spec.allocation is not None and equity <= 0:
        if state.virtual_cash <= 0:
            state.virtual_cash = float(spec.allocation)
        equity = float(state.virtual_cash)
    state = risk.capture_day_start(state, equity, today)
    store.save_state(state, spec.strategy)
    msg = (
        f"[{spec.name}] Day-start equity captured for {today.isoformat()}: "
        f"${state.day_start_equity:,.2f} (peak=${state.peak_equity:,.2f})"
    )
    return RunResult(
        "ok",
        today,
        "capture",
        [msg],
        equity=equity,
        cash=_cash,
        engine=spec.name,
        strategy=spec.strategy,
    )
