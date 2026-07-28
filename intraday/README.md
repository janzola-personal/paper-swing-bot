# Intraday engine (Phase 2 E4–E5)

Isolated from swing `engine.py`. Paper-only via `PaperBroker`.

## Supervised walkthrough

1. Confirm `.env` has paper Alpaca keys (`PA…` account).
2. Dry-run one tick: `python -m intraday.engine --dry-run`
3. Watch `intraday_journal.csv` (local) or `intraday_journal` table (Postgres).
4. During RTH, run a manual loop (supervised):
   ```bash
   while true; do python -m intraday.engine --dry-run; sleep 60; done
   ```
5. After one full session documented in your notes, set `INTRADAY_SUPERVISED_OK=1`.
6. Only then may you attempt `--unattended` locally (hosted cron is E7).

## 15:55 flatten

`run_intraday_tick` cancels open orders and flattens when `now_et >= 15:55 ET`.

## Bracket orders

Live bracket submission is stubbed in dry-run; `--submit` uses broker flatten/cancel
at session end. Full bracket entry wiring follows alpaca-py BRACKET docs when
promoting a strategy past Stage A.

## Data

Minute history: `intraday/data_minute.py` (SIP, parquet cache under `data/minute/`).

Backtests: `intraday/backtest_intraday.py` — signal bar *t* close → fill *t+1* open.
