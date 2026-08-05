"""
CLI entry for the paper swing bot.

Portable logic lives in engine.run_once(trading_day, submit=..., shadow=...).
This file only parses args and prints results.

Commands:
  python main.py run [--submit] [--shadow] [--force]
  python main.py capture-day-start
  python main.py check
  python main.py flatten [--submit]
  python main.py reset-halt
"""

import argparse
import os

from dotenv import load_dotenv

import trading_day
from db.store import default_store
from engine import capture_day_start, run_once


def cmd_check() -> None:
    from broker import PaperBroker

    b = PaperBroker()
    equity, cash = b.equity_and_cash()
    clock = b.get_clock()
    td = trading_day.resolve_trading_day()
    store = default_store()
    print(f"Connected to PAPER account. equity=${equity:,.2f} cash=${cash:,.2f}")
    print(f"Now ET: {trading_day.now_et().isoformat(timespec='seconds')}")
    print(f"Trading day (ET/Alpaca): {td.isoformat() if td else 'none (holiday/weekend)'}")
    print(
        f"Clock: is_open={bool(clock.is_open)} "
        f"next_open={clock.next_open} next_close={clock.next_close}"
    )
    print(f"Positions: {b.positions() or 'none'}")
    print(f"Halt state: {store.load_state()}")
    print(f"Store backend: {type(store).__name__}")


def cmd_flatten(submit: bool) -> None:
    from broker import PaperBroker

    b = PaperBroker()
    for line in b.flatten_all(submit=submit):
        print(line)


def cmd_reset_halt() -> None:
    store = default_store()
    state = store.load_state()
    state.halted = False
    state.halted_reason = ""
    state.peak_equity = 0.0
    store.save_state(state)
    print("Hard halt cleared. Peak equity will re-anchor on the next run.")


def cmd_run(submit: bool, shadow: bool, force: bool, engine: str) -> None:
    # Env defaults for hosted path (CLI flags override when set)
    if not submit and os.environ.get("BOT_SUBMIT", "").lower() == "true":
        submit = True
    if not shadow and os.environ.get("BOT_SHADOW_MODE", "").lower() == "true":
        shadow = True
    if engine == "all":
        from hosted import run_after_close, results_to_dict
        import json

        # Hosted path honors per-engine env flags; CLI --submit/--shadow apply to swing only.
        results = run_after_close()
        print(json.dumps(results_to_dict(results), indent=2))
        return
    result = run_once(submit=submit, shadow=shadow, force=force, engine=engine)
    for line in result.messages:
        print(line)
    print(
        f"result: status={result.status} day={result.trading_day} "
        f"mode={result.mode} orders={result.orders_submitted} "
        f"engine={result.engine}"
    )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Paper swing-trading bot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="after-close: compute signals, reconcile, act")
    p_run.add_argument("--submit", action="store_true", help="place paper orders (unless --shadow)")
    p_run.add_argument(
        "--shadow",
        action="store_true",
        help="full journal/state path but never submit orders",
    )
    p_run.add_argument("--force", action="store_true", help="bypass claim_run idempotency (local only)")
    p_run.add_argument(
        "--engine",
        choices=["swing", "lev_trend", "all"],
        default="swing",
        help="which engine to run (default: swing)",
    )

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
        cmd_run(args.submit, args.shadow, args.force, args.engine)
    elif args.cmd == "capture-day-start":
        from hosted import run_open_capture, results_to_dict
        import json

        results = run_open_capture()
        print(json.dumps(results_to_dict(results), indent=2))
    elif args.cmd == "check":
        cmd_check()
    elif args.cmd == "flatten":
        cmd_flatten(submit=args.submit)
    elif args.cmd == "reset-halt":
        cmd_reset_halt()


if __name__ == "__main__":
    main()
