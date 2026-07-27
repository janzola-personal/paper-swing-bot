# Cursor Playbook (Hosted)

Copy-paste these prompts into Cursor **in order**. Each phase ends with
acceptance criteria — don't move on until they pass. The `.cursorrules` file
gives Cursor standing safety rules automatically; if you start a fresh chat and
it seems to have forgotten them, paste this reminder:

> Follow .cursorrules strictly: paper trading only, never weaken risk.py,
> preserve close-signal/next-open-execution semantics, no LLM or network calls
> in the signal path, tests required for strategy/risk/broker changes,
> America/New_York trading days and Postgres in production, explain every
> change so I learn.

**Target architecture:** $0 hosted — Vercel (UI + Python functions), Supabase
(Postgres + auth), GitHub Actions (scheduler + research), Alpaca (broker +
data), Resend (email). See ARCHITECTURE.md and DEPLOY.md.

---

## Phase 0 — Environment (you, not Cursor)

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env    # Alpaca PAPER keys + local Supabase if testing DB

Create Supabase and Vercel projects when Part B starts (DEPLOY.md). Repo will
be public with MIT license before first deploy.

---

# Part A — Get it correct

Fix known defects and prove the engine with tests before anything touches the
internet.

## Prompt A1 — Orientation

> Read every file in this repo plus ARCHITECTURE.md, DEPLOY.md, WEBUI.md, and
> NOTIFICATIONS.md. Then, without changing any code: (1) confirm ARCHITECTURE.md
> matches the current code or list gaps; (2) explain how look-ahead bias is
> avoided, referencing position[t]/next-open in strategy.py and backtest.py;
> (3) verify the three documented defects (daily-loss halt, trend month-end live
> bug, backtest/live sizing mismatch) still exist in code and cite line numbers;
> (4) list the 5 most likely bugs or fragile points ranked, without fixing yet;
> (5) quiz me with 5 questions to check I understand the system.

*Accept when:* you can answer the quiz and the defect list matches your own
reading of main.py, strategy.py, and backtest.py.

## Prompt A2 — Fix the three defects

> Fix the three documented engine defects with minimal diffs and pytest tests:
>
> 1. **Daily-loss halt:** day_start_equity must be captured at market open (~9:31
>    ET), not in the same after-close run as check_limits. Split into
>    `capture_day_start()` vs after-close `run_once()`. Tests: halt fires when
>    equity drops 2% from day_start captured earlier the same trading day.
>
> 2. **Trend strategy live bug:** month-end must be calendar-derived (last
>    trading day of month from the index), not "last row is always month-end".
>    `desired_position_today` for trend must match backtest month-end semantics.
>    Test: synthetic daily frame where last bar is mid-month → no false month-end.
>
> 3. **Backtest/live sizing:** backtest must respect MAX_POSITION_PCT and
>    multi-symbol portfolio rules matching main.py, or STRATEGY.md must be updated
>    to document intentional difference — prefer fixing backtest. Test: two-symbol
>    scenario with MAX_POSITIONS=2 and 50% cap matches live sizing.
>
> Do not deploy. Explain each fix and why no look-ahead was introduced.

*Accept when:* `pytest -q` passes and you can explain all three fixes.

## Prompt A3 — Full pytest suite

> Create or extend tests/ per the original Phase 2 spec: (1) data.rsi Wilder
> RSI and sma; (2) strategy.rsi2_positions entry/exit rules and warm-up NaNs;
> (3) strategy.trend_positions month-end only; (4) risk.check_limits halts and
> size_shares; (5) backtest.run_backtest 6-bar hand-computed fills at t+1 open.
> Include tests from A2. Do not modify non-test code unless A2 left gaps.

*Accept when:* `pytest -q` passes; you've read each test and can explain it.

## Prompt A4 — Trading-day and timezone model

> Implement trading_day.py: resolve America/New_York session dates from Alpaca
> market calendar API (with test mocks and holiday/half-day handling). Replace
> date.today() in main.py/engine with trading_day helpers. Document in
> ARCHITECTURE.md if anything changed. Tests: Feb 2026 holiday, half-day early
> close, UTC server date ≠ ET trading day after 4pm ET.

*Accept when:* tests pass; no bare date.today() in the run path.

---

# Part B — Get it hosted

Postgres, Alpaca data, backtest report, shadow deploy.

## Prompt B1 — Broker verification

> broker.py was written against alpaca-py as of mid-2026. Verify against current
> official docs: TradingClient paper=True, get_account, get_clock, submit_order
> MarketOrderRequest DAY after close. Cite doc pages. Smallest diff only; never
> weaken the three paper checks. Walk me through `python main.py check`.

*Accept when:* check prints paper equity and clock.

## Prompt B2 — Alpaca market data

> Migrate data.py from yfinance to Alpaca historical daily bars (SIP feed for
> bars >15 min old per Alpaca docs — cite FAQ). Same column schema for
> strategy/backtest. Keep yfinance optional for offline dev if useful. Tests with
> mocked API responses. Update STRATEGY.md data note if needed.

*Accept when:* backtest and live use the same fetch_daily(); tests pass offline.

## Prompt B3 — Postgres state layer

> Implement db/ store: Supabase Postgres migrations for bot_state, runs (UNIQUE
> trading_day+strategy), journal, equity_snapshots per ARCHITECTURE.md. Refactor
> to run_once(trading_day, submit, shadow) with injectable store (Postgres prod,
> files optional local). Idempotency: second run same day → skipped_duplicate, no
> orders. Tests with SQLite or mocked Supabase. No secrets in repo.

*Accept when:* two run_once calls same trading_day → one submits, one skips.

## Prompt B4 — Honest backtest report

> Run backtest after B2/B3 sizing fix. Build results/REPORT.md: stats rsi2/trend/
> B&H, equity PNGs, rsi2 stability grid, OOS split, limitations. Footer defines
> CAGR, max DD, Sharpe. Do not change strategy defaults without asking.

*Accept when:* REPORT.md exists; you understand why not to pick the best grid cell.

## Prompt B5 — Deploy shadow mode

> Implement DEPLOY.md: Vercel Python handler for run_once, GitHub Actions
> workflows (after-close run, 9:31 open capture, watchdog), BOT_SHADOW_MODE=true.
> Next.js shell optional stub. Env vars per DEPLOY.md. README section "Deploy".
> Walk me through first shadow run appearing in Supabase journal.

*Accept when:* 1 trading day shadow run logged in Postgres from scheduler.

---

# Part C — Get it observable

Email, dashboard, failure hardening.

## Prompt C1 — Notifications

> Implement notify.py per NOTIFICATIONS.md (Resend): daily digest with inputs,
> HALT/ERROR/NO-RUN subjects, one retry. Wire into run_once and watchdog.
> Tests with mocked HTTP. Never log API keys.

*Accept when:* test email received; NO-RUN fires when run missing.

## Prompt C2 — Dashboard

> Implement WEBUI.md: Next.js on Vercel, Supabase Auth single user, /dashboard
> six sections, /research report viewer, /gate shell. Mutations: pause, flatten,
> reset-halt only — journal actor. No buy button. Smoke test auth redirect.

*Accept when:* login works; dashboard shows last run and journal.

## Prompt C3 — Failure-mode hardening

> One fix + test each: stale data (>5 calendar days old → skip, journal, notify);
> Alpaca timeout retry ×3; partial fill reconcile next run; market holidays via
> calendar; run crash mid-write (transaction or runs.status=error); watchdog
> dedupe. Explain each failure mode before fixing.

*Accept when:* pytest covers each; bot.log or structured logs on Vercel.

---

# Part D — Get it running

Enable submit; accumulate paper track record.

## Prompt D1 — Enable paper submit

> After 5+ shadow days match expectations: BOT_SUBMIT=true, BOT_SHADOW_MODE=false.
> Confirm orders queue after close for next open. Update gate progress tracking on
> dashboard. Email digest on first real submit.

*Accept when:* Alpaca paper dashboard shows queued/filled orders matching journal.

## Prompt D2 — 60–90 day paper discipline

> No code unless ops gaps found. Document weekly review checklist: journal vs
> email, paper vs backtest chart, halt drills. README Stage B alignment with
> PHASE2 gate Stage B criteria for swing (adapt trade count thresholds if needed).

*Accept when:* you have a written routine and calendar reminder.

---

# Part E — Research (optional, ordered)

## Prompt E1 — Strategy lab

> New variant [describe]: STRATEGIES interface, rule tests, REPORT.md extension,
> honest assessment vs incumbents on drawdown-adjusted terms. Default recommend
> against switching unless evidence clear.

## Prompt E2 — Sentiment diary (research only)

> research/sentiment_log.py: daily headlines → sentiment.csv; must NOT import
> strategy/risk/broker; trading path must not read it. After 90+ days, analyze.

## Prompt E3 — Promotion gate (Phase 2)

> Create gates.md from PHASE2_INTRADAY.md Section 1 (freeze thresholds).
> Build gatecheck.py: PASS/FAIL per criterion from backtest results file. Tests:
> synthetic results failing exactly one criterion each. Thresholds only in
> gates.md/config.

## Prompt E4 — Minute data + intraday backtester

> intraday/data_minute.py (Alpaca parquet cache, cite feed/history docs) and
> intraday/backtest_intraday.py per PHASE2 §4–5. Signal bar t → fill t+1; stops;
> 15:55 flatten; --cost-multiplier. Hand-built 10-bar day test in comments.

## Prompt E5 — Intraday engine (supervised local first)

> intraday/engine.py per PHASE2 §4 (heartbeat, brackets, 15:55 flatten, paper
> checks). Default supervised local terminal; --unattended only after paid deploy
> path documented. Walk through one supervised paper session.

## Prompt E6 — Strategies through the gate

> Implement overnight, orb15, vwap_z per PHASE2 §3. Backtest → gatecheck →
> results/PHASE2_REPORT.md with honest verdicts. "Reject" is success.

## Prompt E7 — Paid hosting upgrade (only if Stage A passes)

> Document or implement Railway/Fly container wrapping run_once loop for minute
> cron strategies per DEPLOY.md appendix. Do not spend until E6 shows a PASS.

---

## Standing learning prompts (anytime)

> Explain [file/function] like I'm a smart beginner, then quiz me.

> Before I accept this diff: worst realistic impact on paper trading, and how
> would I detect it in the journal?

> Play skeptical reviewer: argue against the change you just proposed.

> Two schedulers fire the same evening — what stops duplicate orders, and why
> must that live in Postgres not Python?

---

## Deprecated (do not use — replaced by hosted playbook)

| Old prompt | Replaced by |
|------------|-------------|
| Phase 5 OS cron / Task Scheduler | B5 + DEPLOY.md dual cron |
| Phase 6 Discord-only notify | C1 NOTIFICATIONS.md (Discord optional add-on) |
| Phase 7 Streamlit dashboard | C2 WEBUI.md Next.js |
| Old WEBUI.md FastAPI localhost | C2 WEBUI.md |
| main.py as production scheduler | run_once + Vercel/Actions |
