# Research utilities (not on the trading path)

- **`sentiment_log.py`** — daily headline diary → `sentiment.csv` (gitignored).
  Run manually or via a personal cron. **Do not analyze until 90+ days** of rows;
  never wire into `engine.py` or strategy signals.

Import guard: `tests/test_sentiment_isolation.py` ensures this package never
loads `strategy`, `risk`, `broker`, or `engine`.
