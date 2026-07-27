"""
Journal: every decision, with the numbers behind it, appended to journal.csv.

If it isn't journaled, it didn't happen. The journal is how you audit the bot,
debug surprises, and (later) compare live fills against backtest assumptions.
"""

import csv
import os
from datetime import datetime, timezone

import config

FIELDS = [
    "timestamp_utc",
    "symbol",
    "action",      # buy / sell / hold / skip / halt / info
    "qty",
    "ref_price",   # latest close used for sizing (not the fill price)
    "reason",
    "equity",
    "cash",
    "dry_run",
]


def log(symbol: str, action: str, qty: int, ref_price: float, reason: str,
        equity: float, cash: float, dry_run: bool) -> None:
    new_file = not os.path.exists(config.JOURNAL_FILE)
    with open(config.JOURNAL_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "symbol": symbol,
            "action": action,
            "qty": qty,
            "ref_price": f"{ref_price:.2f}" if ref_price else "",
            "reason": reason,
            "equity": f"{equity:.2f}",
            "cash": f"{cash:.2f}",
            "dry_run": dry_run,
        })
