# Paper Swing Bot

A small, readable, daily-bar trading bot that paper-trades US ETFs through
Alpaca. Built as a learning project: mechanical rules, honest backtesting,
and a risk layer that treats capital preservation as the feature.

**Read this first — expectations.** This bot will not make $100/day on $5,000.
Nothing legitimate will; that's a ~2%/day return, far beyond what professional
funds sustain. The realistic goals here, in order: (1) learn how systematic
trading actually works end-to-end, (2) build the discipline of testing before
trusting, (3) maybe, eventually, run a small live allocation that beats cash
without blowing up. The strategies included are published, well-studied rules
chosen for robustness and simplicity — not secret alpha. Their documented
historical edge is modest and may continue to decay. That is the honest state
of retail algo trading. Everything here is educational, not financial advice.

## What it does

Once per trading day, after the close, it:
1. Loads account state and enforces risk limits (halts first, questions later).
2. Fetches daily bars, computes signals from deterministic rules (STRATEGY.md).
3. Reconciles desired vs. held positions, sizes orders (whole shares, cash only).
4. Journals every decision and (when enabled) queues paper market orders that
   fill at the next open — the same execution timing model the backtest uses.

Two strategies ship with it: `rsi2` (short-term mean reversion, the "active"
one) and `trend` (slow month-end trend filter, the boring baseline). See
STRATEGY.md for the exact rules and why they're built this way.

**Hosted operation:** the bot runs on a schedule (Vercel + GitHub Actions), not
on your Mac. You get a daily email and a password-protected dashboard to review
positions, compare paper to backtest, pause, or flatten in emergencies. There
is no buy button — see WEBUI.md.

## Repo map

Engine (Python):

    config.py          every tunable number, including risk limits
    data.py            daily bars (Alpaca SIP when hosted) + indicators
    strategy.py        the rules -> desired position series
    risk.py            sizing, daily-loss halt, drawdown kill switch
    broker.py          Alpaca wrapper, paper-mode enforced three ways
    backtest.py        transparent next-open backtester with slippage
    main.py            local CLI (dev); production uses run_once + schedulers
    journal.py         local CSV (dev); production uses Postgres

Documentation:

    STRATEGY.md        plain-English rules, rationale, failure modes
    ARCHITECTURE.md    hosted data flow, trading-day model, Postgres schema
    DEPLOY.md          Vercel, Supabase, Actions, shadow mode, cron
    WEBUI.md           Next.js dashboard spec (auth, no buy button)
    NOTIFICATIONS.md   email digest + HALT / ERROR / NO-RUN alerts
    CURSOR_PROMPTS.md  phased build playbook (Parts A–E)
    PHASE2_INTRADAY.md optional intraday research + promotion gate
    .cursorrules       safety invariants Cursor must respect

Infrastructure (created during Part B/C — see CURSOR_PROMPTS.md):

    app/                   Next.js dashboard (Vercel App Router)
    lib/ components/       Auth, dashboard UI, server helpers
    api/*.py               Python serverless (run / capture / watchdog / mutations)
    content/               REPORT.md + gate shell for /research and /gate
    supabase/migrations/   Postgres schema
    .github/workflows/     scheduled runs + watchdog + research

## Quickstart — local development

Use this to backtest and debug before or alongside hosted deploy.

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env      # Alpaca PAPER keys

    python backtest.py --symbols SPY QQQ --strategy both
    python main.py check
    python main.py run          # dry-run locally
    python main.py run --submit # manual paper submit (after 4pm ET)

Follow **CURSOR_PROMPTS.md Part A** first (fix engine defects, tests, trading-day
model). Do not deploy until Part A passes.

## Quickstart — deployed ($0/month)

See **DEPLOY.md** for full steps. Summary:

1. Public GitHub repo (MIT LICENSE), secret scanning enabled.
2. Supabase: Postgres + Auth (one user, signups off).
3. Vercel: Next.js stub + Python `api/run` / `api/capture` / `api/watchdog`.
4. GitHub Actions: after-close run, 9:31am day-start capture, watchdog.
5. Resend: daily digest email (Part C polish).
6. **Shadow week:** `BOT_SHADOW_MODE=true` — journal only, no orders.
7. **Go live on paper:** `BOT_SUBMIT=true`, `BOT_SHADOW_MODE=false` — auto-submit
   Alpaca **paper** market DAY orders after close (fill next open).

**Dashboard:** your Vercel URL (e.g. `https://paper-swing-bot.vercel.app`).
Login with the single Supabase Auth user (email + password). Public signups
must stay disabled. Unauthenticated visits to `/dashboard` redirect to `/login`.

Local UI:

```bash
npm install
# .env.local needs NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY
npm run dev
```

Auth smoke test: `npx playwright install chromium && npm run test:auth-smoke`

There is **no buy button**. The bot enters on the after-close schedule; the UI
only pauses, flattens in emergencies, or clears a hard halt (each journals your
email as `actor`).

## Deploy (shadow mode)

Hosted entrypoint is `hosted.run_after_close()` → `engine.run_once(..., shadow=True)`
by default. Dual schedulers are safe: Postgres `UNIQUE (trading_day, strategy)`.

| Piece | Path |
|-------|------|
| Vercel after-close | `api/run.py` + cron `15 21 * * 1-5` (≈5:15pm ET in EDT) |
| Vercel open capture | `api/capture.py` + cron `31 13 * * 1-5` (≈9:31am ET in EDT) |
| Vercel watchdog | `api/watchdog.py` + cron `30 22 * * 1-5` (≈6:30pm ET in EDT) |
| Actions after-close | `.github/workflows/daily-run.yml` |
| Actions open capture | `.github/workflows/open-capture.yml` |
| Actions watchdog | `.github/workflows/watchdog.yml` |
| Next.js UI | `/dashboard` (six sections), `/research`, `/gate`, mutations → `api/engine_*` |

**Required secrets** (Vercel + GitHub Actions): see DEPLOY.md §4 — at least
`ALPACA_*`, `DATABASE_URL`, `BOT_SHADOW_MODE=true`, `BOT_SUBMIT=false`.
Set `CRON_SECRET` on Vercel (Cron sends `Authorization: Bearer …`).

**First shadow run checklist**

1. Confirm env: `BOT_SHADOW_MODE=true`, `BOT_SUBMIT=false`, `STATE_BACKEND` → Postgres via `DATABASE_URL`.
2. Trigger Actions → **daily-run** → Run workflow (or wait for cron / call `/api/run` with the bearer secret).
3. In Supabase SQL: `select * from runs order by started_at desc limit 5;` — expect `mode=shadow`, `status=ok` (or `skipped_duplicate` if dual-fired).
4. `select trading_day, symbol, action, qty, reason, dry_run from journal order by id desc limit 20;` — decisions with `dry_run=true`.
5. Second trigger same day → `skipped_duplicate`, no new orders (always zero orders while shadowed).

Re-run locally against Postgres:

```bash
STATE_BACKEND=postgres BOT_SHADOW_MODE=true BOT_SUBMIT=false \
  python -c "from hosted import run_after_close, result_to_dict; import json; print(json.dumps(result_to_dict(run_after_close()), indent=2))"
```

## Stage B paper discipline (Part D)

Paper submit is enabled when `BOT_SUBMIT=true` and `BOT_SHADOW_MODE=false`.
See **[PAPER_REVIEW.md](PAPER_REVIEW.md)** for the weekly checklist (journal vs
email, paper vs backtest chart, gate counters, halt drill).

**Swing Stage B targets** (from PHASE2 §1, adapted for daily rsi2):

| Criterion | Threshold |
|-----------|-----------|
| Trading days | ≥ 60 with submit-mode runs |
| Completed trades | ≥ 40 (actual BUY/SELL, not dry-run) |
| Manual overrides | 0 (pause/flatten/reset-halt only when needed; each journals actor) |
| Consistency | Paper directionally matches backtest OOS over same window |

Track progress on the dashboard **Gate progress** card. Calendar reminder:
Sunday 30 min review.

## Safety rails (risk.py — the load-bearing walls)

- Paper enforced three ways: config flag, `paper=True` client, and an account
  number check ("PA…") before any order.
- Hosted: auto-submit on schedule; dashboard can **pause**, **flatten**, or
  **reset-halt** only — no manual buys.
- Max 2 positions, max 50% of equity each, whole shares, cash only, long only.
- Daily loss ≥ 2% of **start-of-day** equity → flatten, stand down until next
  session (requires 9:31am open capture — Part A fix).
- Drawdown ≥ 10% from peak → flatten, hard halt until reset-halt after review.
- Same-day duplicate runs blocked via Postgres `UNIQUE (trading_day, strategy)`
  (dual schedulers safe).
- Journal of every decision with the numbers behind it.

## Go-live checklist (months away — resist the urge)

Going live is a deliberate decision, not a config flip, and this repo
intentionally refuses to do it. Before even considering it, all of:

1. ≥ 60–90 calendar days of paper trading with `--submit`, no manual overrides.
2. Paper results roughly consistent with the backtest over the same window
   (direction and magnitude — not luck-of-the-draw outperformance).
3. You can explain every file in this repo to another person without notes.
4. You've watched the bot handle at least one losing streak and one halt.
5. You'd fund it only with money whose total loss changes nothing about your
   life, sized at 10–20% of that amount to start.
6. You've read your broker's live-API docs yourself, including order rejects,
   partial fills, and the pattern-day-trader rule.

**Additional hosted-paper requirements (before real money):**

7. ≥ 30 consecutive trading days with no missed scheduled run (watchdog clean).
8. You have received and acted on at least one HALT or NO-RUN test alert.
9. You can explain dual-scheduler idempotency (Postgres unique constraint) without notes.
10. Repo is **private** and all API keys rotated the same day you go live.

If all items are true, you won't need this repo's permission — you'll be
qualified to make the change and own it. Until then: paper.

## License

MIT — see LICENSE. Public while learning; go private before live trading.

## Disclaimer

Educational software. Not investment advice, not a recommendation to trade.
Markets involve risk of loss; backtests overstate real results. You are
responsible for anything you run.
