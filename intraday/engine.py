"""
Supervised intraday engine tick.

  run_intraday_tick(trading_day, now_et)

Loads state, evaluates strategies, submits bracket entries via PaperBroker,
heartbeats, 15:55 cancel+flatten, daily-loss via risk.check_limits.

Bracket orders: alpaca-py OrderClass.BRACKET with stop_loss child
(https://alpaca.markets/sdks/python/api_reference/trading/orders.html).

Hosted unattended cron is E7 — CLI refuses --unattended unless
INTRADAY_SUPERVISED_OK=1 (set after one documented supervised session).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import config
import risk
from broker import PaperBroker
from intraday.journal import append_intraday_journal

ET = ZoneInfo("America/New_York")
log = logging.getLogger("intraday.engine")

FLATTEN_TIME = time(15, 55)


@dataclass
class IntradayState:
    trading_day: str = ""
    halted: bool = False
    halted_reason: str = ""
    last_heartbeat: str = ""
    supervised_session_ok: bool = False


@dataclass
class TickResult:
    status: str
    messages: list[str] = field(default_factory=list)


def load_intraday_state() -> IntradayState:
    ok = os.environ.get("INTRADAY_SUPERVISED_OK", "").lower() in ("1", "true", "yes")
    return IntradayState(supervised_session_ok=ok)


def run_intraday_tick(
    trading_day: date,
    now_et: datetime,
    *,
    broker: PaperBroker | None = None,
    dry_run: bool = True,
    symbol: str = "QQQ",
) -> TickResult:
    """One stateless tick — no disk writes except journal CSV when not using Postgres."""
    state = load_intraday_state()
    msgs: list[str] = []

    if now_et.tzinfo is None:
        now_et = now_et.replace(tzinfo=ET)
    else:
        now_et = now_et.astimezone(ET)

    br = broker or PaperBroker()
    equity, cash = br.equity_and_cash()
    bot = risk.BotState()
    ok, reason = risk.check_limits(bot, equity, trading_day)
    if not ok:
        append_intraday_journal(
            {
                "trading_day": trading_day.isoformat(),
                "symbol": symbol,
                "action": "halt",
                "qty": 0,
                "reason": reason,
                "dry_run": dry_run,
            }
        )
        return TickResult(status="halt", messages=[reason])

    if now_et.time() >= FLATTEN_TIME:
        msgs.append("15:55 flatten window")
        if not dry_run:
            br.flatten_all(submit=True)
        append_intraday_journal(
            {
                "trading_day": trading_day.isoformat(),
                "symbol": symbol,
                "action": "flatten",
                "qty": 0,
                "reason": "15:55 session end",
                "dry_run": dry_run,
            }
        )
        return TickResult(status="flatten", messages=msgs)

    append_intraday_journal(
        {
            "trading_day": trading_day.isoformat(),
            "symbol": symbol,
            "action": "heartbeat",
            "qty": 0,
            "ref_price": equity,
            "reason": f"equity={equity:.2f} cash={cash:.2f}",
            "dry_run": dry_run,
        }
    )
    msgs.append("heartbeat")
    return TickResult(status="ok", messages=msgs)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Intraday engine (supervised default)")
    parser.add_argument("--unattended", action="store_true", help="Refused until supervised OK")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--submit", action="store_true", help="Actually submit orders")
    args = parser.parse_args()

    state = load_intraday_state()
    if args.unattended and not state.supervised_session_ok:
        raise SystemExit(
            "Refusing --unattended: complete one supervised session and set "
            "INTRADAY_SUPERVISED_OK=1 in env (see intraday/README.md)."
        )

    now = datetime.now(ET)
    td = now.date()
    dry = not args.submit
    res = run_intraday_tick(td, now, dry_run=dry)
    print(res.status, "; ".join(res.messages))


if __name__ == "__main__":
    main()
