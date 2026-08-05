"""
Risk layer. This file is the difference between "learning experience" and
"account gone". Nothing here should ever be weakened casually; every limit
maps to a config value with a comment explaining it.

Responsibilities:
  1. Position sizing (cash-limited, capped % of equity, whole shares).
  2. Daily loss limit  -> flatten + halt for the rest of the day
     (requires morning capture_day_start; after-close only update_peak).
  3. Max drawdown halt -> flatten + halt until a human runs `reset-halt`.
  4. Persistent state (peak equity, halt flags, last run date) in state.json.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import date

import config


@dataclass
class BotState:
    peak_equity: float = 0.0
    day_start_equity: float = 0.0
    day_start_date: str = ""          # ISO date the day_start_equity was captured
    halted: bool = False              # hard halt (drawdown) -- needs manual reset
    halted_reason: str = ""
    day_halted_date: str = ""         # soft halt (daily loss) -- clears next day
    last_run_date: str = ""           # legacy file-store idempotency; prefer runs table
    paused: bool = False              # operator pause from dashboard (no new orders)
    watchdog_norun_sent_day: str = "" # ISO date we last emailed NO RUN (dedupe)
    # Virtual cash for allocation-scoped engines (lev_trend). Unused (0) when
    # the engine uses the full Alpaca account book (swing).
    virtual_cash: float = 0.0


def load_state() -> BotState:
    """File-backed load (local FileStore / legacy). Prefer db.Store in engine."""
    from dataclasses import fields as dc_fields

    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE) as f:
            raw = json.load(f)
        known = {fld.name for fld in dc_fields(BotState)}
        return BotState(**{k: v for k, v in raw.items() if k in known})
    return BotState()


def save_state(state: BotState) -> None:
    """File-backed save (local FileStore / legacy). Prefer db.Store in engine."""
    with open(config.STATE_FILE, "w") as f:
        json.dump(asdict(state), f, indent=2)


def capture_day_start(state: BotState, equity: float, today: date) -> BotState:
    """Morning (~9:31 ET) job: lock start-of-day equity once per trading day.

    Must NOT be called from the after-close run — that would set day_start_equity
    equal to the same equity check_limits compares against, so the daily-loss
    halt could never fire.
    """
    iso = today.isoformat()
    if state.day_start_date != iso:
        state.day_start_date = iso
        state.day_start_equity = equity
    state.peak_equity = max(state.peak_equity, equity)
    return state


def update_peak(state: BotState, equity: float) -> BotState:
    """After-close (or any) peak update without touching day_start_equity."""
    state.peak_equity = max(state.peak_equity, equity)
    return state


def roll_day(state: BotState, equity: float, today: date) -> BotState:
    """Deprecated alias for capture_day_start. Prefer capture_day_start explicitly."""
    return capture_day_start(state, equity, today)


def check_limits(
    state: BotState,
    equity: float,
    today: date,
    *,
    max_daily_loss_pct: float | None = None,
    max_drawdown_halt_pct: float | None = None,
) -> tuple[bool, str]:
    """Returns (ok_to_trade, reason). Sets halt flags on the state as needed.

    Optional pct overrides let each EngineSpec use its own halt thresholds
    without mutating global config (dual-engine path).
    """
    daily_lim = (
        config.MAX_DAILY_LOSS_PCT if max_daily_loss_pct is None else max_daily_loss_pct
    )
    dd_lim = (
        config.MAX_DRAWDOWN_HALT_PCT
        if max_drawdown_halt_pct is None
        else max_drawdown_halt_pct
    )
    iso = today.isoformat()

    if state.halted:
        return False, f"HARD HALT active: {state.halted_reason} (run `reset-halt` after review)"

    if state.day_halted_date == iso:
        return False, "Daily-loss halt active for today; trading resumes next session"

    if state.peak_equity > 0:
        dd = equity / state.peak_equity - 1.0
        if dd <= -dd_lim:
            state.halted = True
            state.halted_reason = (
                f"Drawdown {dd:.1%} breached -{dd_lim:.0%} "
                f"(equity {equity:.2f} vs peak {state.peak_equity:.2f})"
            )
            return False, state.halted_reason

    # Only evaluate daily loss when morning capture ran for this trading day.
    if state.day_start_date == iso and state.day_start_equity > 0:
        day_pnl = equity / state.day_start_equity - 1.0
        if day_pnl <= -daily_lim:
            state.day_halted_date = iso
            return False, (
                f"Daily loss {day_pnl:.2%} breached -{daily_lim:.0%}; "
                "flattening and standing down for the day"
            )

    return True, "ok"


def size_shares(
    price: float,
    equity: float,
    cash: float,
    *,
    max_position_pct: float | None = None,
    allow_margin: bool | None = None,
) -> int:
    """Whole shares, capped by MAX_POSITION_PCT of equity and by available cash.
    ALLOW_MARGIN is False: we never spend more than cash on hand."""
    if price <= 0:
        return 0
    pct = config.MAX_POSITION_PCT if max_position_pct is None else max_position_pct
    margin = config.ALLOW_MARGIN if allow_margin is None else allow_margin
    budget = min(equity * pct, cash if not margin else equity)
    return max(int(budget // price), 0)


def reset_halt() -> None:
    state = load_state()
    state.halted = False
    state.halted_reason = ""
    # Reset the peak to current reality so the next drawdown measures from here.
    state.peak_equity = 0.0
    save_state(state)
    print("Hard halt cleared. Peak equity will re-anchor on the next run.")
