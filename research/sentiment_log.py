"""
Research-only sentiment diary. Fetches daily headlines and appends rows to
research/sentiment.csv (gitignored). Never import strategy/risk/broker/engine.

Analyze only after 90+ days of rows — not for live signals.
"""

from __future__ import annotations

import csv
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

SENTIMENT_CSV = Path(__file__).resolve().parent / "sentiment.csv"
FORBIDDEN_PREFIXES = ("strategy", "risk", "broker", "engine")


def _assert_research_isolated() -> None:
    """Runtime guard: this module must not pull in the trading stack."""
    import sys

    for name in list(sys.modules):
        base = name.split(".")[0]
        if base in FORBIDDEN_PREFIXES:
            raise ImportError(f"sentiment_log must not load trading module {name!r}")


def fetch_headlines(query: str = "stock market", *, max_items: int = 5) -> list[str]:
    """Fetch headlines via Google News RSS (stdlib only). Returns title strings."""
    _assert_research_isolated()
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": "paper-bot-research/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        return [f"(fetch error: {e})"]

    # Minimal RSS parse without xml.etree dependency on untrusted huge docs.
    titles: list[str] = []
    for chunk in xml.split("<item>"):
        if "<title>" not in chunk:
            continue
        start = chunk.index("<title>") + len("<title>")
        end = chunk.index("</title>", start)
        title = chunk[start:end].strip()
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= max_items:
            break
    return titles or ["(no headlines parsed)"]


def append_sentiment_row(
    trading_day: date | None = None,
    *,
    query: str = "stock market",
    csv_path: Path | None = None,
) -> dict:
    """Fetch headlines and append one CSV row. Returns the row dict."""
    _assert_research_isolated()
    day = trading_day or datetime.now(timezone.utc).date()
    headlines = fetch_headlines(query=query)
    row = {
        "trading_day": day.isoformat(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "headline_count": len(headlines),
        "headlines_json": json.dumps(headlines),
    }
    path = csv_path or SENTIMENT_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)
    return row


def main() -> None:
    row = append_sentiment_row()
    print(f"Appended sentiment row for {row['trading_day']} ({row['headline_count']} headlines)")


if __name__ == "__main__":
    main()
