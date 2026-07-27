"""
Daily run loop. Designed to be executed once per trading day, AFTER the close
(e.g. 5:00pm ET). Orders queue overnight and fill at the next open, matching
the backtest's execution model.

A separate morning job (capture-day-start, ~9:31 ET) locks day_start_equity so
the daily-loss halt can compare afternoon equity to open equity.

SAFETY DEFAULTS:
  - Dry-run by default: prints the plan, journals it, submits nothing.
  - `--submit` is required to actually place (paper) orders.
  - Refuses to run twice on the same date unless `--force`.
  - Halts enforced by risk.py BEFORE any signal is even computed.

Commands:
  python main.py run [--submit] [--force]
  python main.py capture-day-start
  python main.py check
  python main.py flatten [--submit]
  python main.py reset-halt
"""

import argparse
from datetime import date

from dotenv import load_dotenv

import config
import journal
import risk
import trading_day
from data import fetch_daily
from strategy import STRATEGIES, desired_position_today


def cmd_check() -> None:
    from broker import PaperBroker
    b = PaperBroker()
    equity, cash = b.equity_and_cash()
    td = trading_day.resolve_trading_day()
    print(f"Connected to PAPER account. equity=${equity:,.2f} cash=${cash:,.2f}")
    print(f"Now ET: {trading_day.now_et().isoformat(timespec='seconds')}")
    print(f"Trading day (ET/Alpaca): {td.isoformat() if td else 'none (holiday/weekend)'}")
    print(f"Market open now: {b.market_open_now()}")
    print(f"Positions: {b.positions() or 'none'}")
    print(f"Halt state: {risk.load_state()}")


def cmd_flatten(submit: bool) -> None:
    from broker import PaperBroker
    b = PaperBroker()
    for line in b.flatten_all(submit=submit):
        print(line)


def capture_day_start(session_day: date | None = None) -> None:
    """Morning job: record equity at/near open for the daily-loss baseline."""
    from broker import PaperBroker

    assert config.PAPER_TRADING, "PAPER_TRADING must be True"
    today = session_day if session_day is not None else trading_day.resolve_trading_day()
    if today is None:
        print("Not a trading day (ET/Alpaca calendar); skipping day-start capture.")
        return
    b = PaperBroker()
    equity, _cash = b.equity_and_cash()
    state = risk.load_state()
    state = risk.capture_day_start(state, equity, today)
    risk.save_state(state)
    print(
        f"Day-start equity captured for {today.isoformat()}: "
        f"${state.day_start_equity:,.2f} (peak=${state.peak_equity:,.2f})"
    )


def run_once(
    session_day: date | None = None,
    *,
    submit: bool = False,
    force: bool = False,
) -> None:
    """After-close run: risk check, signals, reconcile. Does not set day_start."""
    from broker import PaperBroker

    assert config.PAPER_TRADING, "PAPER_TRADING must be True"
    assert config.ACTIVE_STRATEGY in STRATEGIES, f"Unknown strategy {config.ACTIVE_STRATEGY}"

    today = session_day if session_day is not None else trading_day.resolve_trading_day()
    if today is None:
        print("Not a trading day (ET/Alpaca calendar); skipping run.")
        return
    state = risk.load_state()

    if state.last_run_date == today.isoformat() and not force:
        print("Already ran today. Use --force to override (avoid double-ordering).")
        return

    b = PaperBroker()
    if b.market_open_now():
        print("NOTE: market is OPEN. Market orders will fill immediately, not at "
              "the next open like the backtest assumes. Intended usage is after close.")

    equity, cash = b.equity_and_cash()
    held = b.positions()
    # Peak only — never overwrite day_start_equity here (see capture_day_start).
    state = risk.update_peak(state, equity)

    ok, why = risk.check_limits(state, equity, today)
    if not ok:
        print(f"RISK HALT: {why}")
        journal.log("*", "halt", 0, 0.0, why, equity, cash, dry_run=not submit)
        for line in b.flatten_all(submit=submit):
            print(line)
        risk.save_state(state)
        return

    # ---- compute desired book ------------------------------------------
    wants: list[tuple[str, int, str, float, float]] = []  # symbol, want, reason, close, rsi
    for symbol in config.SYMBOLS:
        df = fetch_daily(symbol, years=2)  # 2y is plenty for a 200-day SMA
        want, reason = desired_position_today(df, config.ACTIVE_STRATEGY)
        last_close = float(df["close"].iloc[-1])
        from data import rsi as _rsi
        last_rsi = float(_rsi(df["close"], 2).iloc[-1])
        wants.append((symbol, want, reason, last_close, last_rsi))

    # Cap concurrent positions: most-oversold (lowest RSI) entries win.
    entries = [w for w in wants if w[1] == 1 and w[0] not in held]
    entries.sort(key=lambda w: w[4])
    room = max(config.MAX_POSITIONS - len([s for s, q in held.items() if q > 0]), 0)
    allowed_entries = {w[0] for w in entries[:room]}
    skipped_entries = {w[0] for w in entries[room:]}

    # ---- reconcile and act ---------------------------------------------
    mode = "SUBMIT (paper)" if submit else "DRY-RUN"
    print(f"[{mode}] equity=${equity:,.2f} cash=${cash:,.2f} held={held or 'none'}")

    for symbol, want, reason, last_close, _ in wants:
        have = held.get(symbol, 0)
        if want == 1 and have == 0:
            if symbol in skipped_entries:
                msg = f"signal yes, but MAX_POSITIONS={config.MAX_POSITIONS} reached"
                print(f"  SKIP  {symbol}: {msg}")
                journal.log(symbol, "skip", 0, last_close, f"{reason} | {msg}", equity, cash, not submit)
                continue
            qty = risk.size_shares(last_close, equity, cash)
            if qty == 0:
                print(f"  SKIP  {symbol}: sized to 0 shares (cash ${cash:,.2f})")
                journal.log(symbol, "skip", 0, last_close, f"{reason} | sized to 0", equity, cash, not submit)
                continue
            print(f"  BUY   {qty} {symbol} @ ~{last_close:.2f}  ({reason})")
            if submit:
                b.submit_market(symbol, qty, "buy")
            cash -= qty * last_close  # reserve locally so the next symbol sizes honestly
            journal.log(symbol, "buy", qty, last_close, reason, equity, cash, not submit)
        elif want == 0 and have > 0:
            print(f"  SELL  {have} {symbol} @ ~{last_close:.2f}  ({reason})")
            if submit:
                b.submit_market(symbol, have, "sell")
            journal.log(symbol, "sell", have, last_close, reason, equity, cash, not submit)
        else:
            action = "hold" if have > 0 else "flat"
            print(f"  {action.upper():5s} {symbol}  ({reason})")
            journal.log(symbol, action, have, last_close, reason, equity, cash, not submit)

    if submit:
        state.last_run_date = today.isoformat()
    risk.save_state(state)
    print("Done. Decisions journaled to", config.JOURNAL_FILE)


def cmd_run(submit: bool, force: bool) -> None:
    run_once(submit=submit, force=force)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Paper swing-trading bot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="after-close: compute signals, reconcile, act")
    p_run.add_argument("--submit", action="store_true", help="actually place paper orders")
    p_run.add_argument("--force", action="store_true", help="allow second run same day")

    sub.add_parser(
        "capture-day-start",
        help="morning job: lock day_start_equity for daily-loss halt (~9:31 ET)",
    )
    sub.add_parser("check", help="connectivity and account sanity check")

    p_fl = sub.add_parser("flatten", help="sell everything (next open)")
    p_fl.add_argument("--submit", action="store_true")

    sub.add_parser("reset-halt", help="clear the hard drawdown halt after review")

    args = parser.parse_args()
    if args.cmd == "run":
        cmd_run(submit=args.submit, force=args.force)
    elif args.cmd == "capture-day-start":
        capture_day_start()
    elif args.cmd == "check":
        cmd_check()
    elif args.cmd == "flatten":
        cmd_flatten(submit=args.submit)
    elif args.cmd == "reset-halt":
        risk.reset_halt()


if __name__ == "__main__":
    main()
