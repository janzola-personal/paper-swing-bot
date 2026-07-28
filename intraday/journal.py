"""
Local intraday journal (CSV fallback). Postgres table: intraday_journal.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

INTRADAY_JOURNAL_FILE = Path("intraday_journal.csv")


def append_intraday_journal(
    row: dict,
    *,
    path: Path | None = None,
) -> None:
    fields = [
        "trading_day",
        "timestamp_utc",
        "symbol",
        "action",
        "qty",
        "ref_price",
        "reason",
        "dry_run",
    ]
    p = path or INTRADAY_JOURNAL_FILE
    write_header = not p.exists() or p.stat().st_size == 0
    out = {k: row.get(k, "") for k in fields}
    if not out.get("timestamp_utc"):
        out["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            w.writeheader()
        w.writerow(out)
