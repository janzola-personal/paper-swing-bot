# Web UI Specification (Hosted)

Next.js dashboard on **Vercel Hobby**, authenticated via **Supabase Auth**
(email + password, single user, signups disabled). Read-mostly: the bot trades
on schedule; you observe, pause, or intervene in emergencies.

**Not** a localhost FastAPI + single HTML file. See DEPLOY.md for hosting;
ARCHITECTURE.md for boundaries (TypeScript never recomputes signals).

---

## Four design rules (non-negotiable)

1. **No buy button, ever.** The only mutating controls: Pause trading, Flatten
   now, Reset halt (when halted). Manual entries would break Stage B's "zero
   overrides" rule and invite discretion during drawdowns.

2. **Every verdict shows its inputs.** Not "HOLD" alone — "HOLD because rsi2
   44.1, entry needs < 10". Same teaching goal as NOTIFICATIONS.md digest.

3. **Absence is louder than presence.** Header shows last successful run time;
   turns red if today's trading day has no `runs.status = ok` after the expected
   window. Complements the NO-RUN email watchdog.

4. **Reality never without expectation.** Paper equity charts always include
   backtest expectation for the same window and capital (Stage B criterion on
   the front page).

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Framework | Next.js (App Router), TypeScript |
| Styling | Tailwind CSS |
| Charts | Lightweight chart lib (e.g. Chart.js or Recharts) |
| Auth | Supabase Auth — `@supabase/ssr` for cookies |
| Data | Supabase Postgres (read journal, state, equity); server routes call Python engine for mutations |
| Hosting | Vercel Hobby |

Python engine exposed as Vercel serverless routes (e.g. `/api/engine/flatten`)
that import existing modules — no duplicated logic in TS.

---

## Authentication

- Login page: email + password only (no public signup link).
- Middleware: all `/dashboard/*` and `/api/*` (except health) require session.
- Optional later: TOTP MFA in Supabase (free on all plans).
- Session timeout: default Supabase; refresh on activity.

**Security:** Alpaca keys never reach the browser. Dashboard API routes use
service role or engine env on the server only.

---

## Pages

### `/` → redirect

Authenticated → `/dashboard`. Else → `/login`.

### `/dashboard` (main — desktop-dense, single scroll)

#### A. Status strip (always visible)

| Element | Source |
|---------|--------|
| Equity, day P&L % | Latest `equity_snapshots` or live broker read (cached) |
| Cash | Same |
| Market open/closed | Alpaca clock via server route |
| Last run | `runs.completed_at` for today's trading day — **red if missing/stale** |
| Halt banner | `bot_state.halted` or day halt — red, full reason text |
| Pause indicator | `bot_state.paused` — yellow |

Actions (right side):

- **Pause trading** — toggles `paused`; confirm dialog; journals actor
- **Flatten now** — confirm + re-auth password prompt; calls engine flatten
- **Reset halt** — visible only when `halted`; confirm + explains peak re-anchor

#### B. Today's decision (card)

Table per symbol (SPY, QQQ):

| Column | Content |
|--------|---------|
| Symbol | |
| Action | BUY / SELL / HOLD / FLAT / SKIP |
| Qty | If applicable |
| Inputs | rsi2, sma200, sma5, close — with ✓/✗ vs thresholds |
| Note | e.g. "queued · fills at tomorrow's open" |

Data: latest journal rows for today's trading day, or last run output JSON.

#### C. Paper vs backtest (chart card, side-by-side with D)

Line chart, log scale optional toggle:

- Paper equity from `equity_snapshots`
- Backtest expectation curve (precomputed or fetched from `/api/backtest-window`)
- Buy-and-hold benchmark (dashed)

Same date range and starting capital as config `BACKTEST_INITIAL_CASH`.

#### D. Gate progress (card — Stage B paper)

Progress bars:

- Days: N / 60
- Trades: N / 40
- Manual overrides: must stay 0 (red if >0)
- Halts: count + link to journal

Hidden or collapsed until paper submit mode enabled.

#### E. Open positions (card)

Per position:

- Symbol, qty, entry date/price, mark, unrealized P&L
- For rsi2: bars held / max_hold_days; distance to nearest exit rule
  (e.g. "needs close > sma5 584.20, now 580.12")

#### F. Journal (table)

Last 50 rows, newest first. Columns: time (ET), symbol, action, qty, price,
reason (truncated with expand). Filter: all / trades / halts / errors.

Auto-refresh every 60s when tab focused (not 24/7 polling).

---

### `/research` (backtest report viewer)

Renders `results/REPORT.md` content (or DB-stored report JSON from Part B):

- Stats table: rsi2, trend, buy-and-hold per symbol
- Equity curve PNGs or interactive charts
- Parameter stability grid summary
- Out-of-sample split paragraph
- Limitations section

Read-only. "Re-run backtest" triggers GitHub Actions `workflow_dispatch` (not
inline on Vercel — long jobs belong in Actions).

---

### `/gate` (Phase 2 scoreboard)

Renders `gates.md` thresholds vs latest `gate_results`:

| Strategy | Stage badge | Criterion | Threshold | Measured | Pass/Fail |
|----------|-------------|-----------|-----------|----------|-----------|

Color: green pass, red fail. Strategies: BENCH → BACKTEST-PASS → PAPER →
LIVE-ELIGIBLE per PHASE2_INTRADAY.md.

Empty state: "No gate runs yet — complete Part E Prompt 11."

---

## API routes (Next.js server)

All require authenticated session unless noted.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/status` | Equity, positions, clock, halt, pause, last run |
| GET | `/api/journal` | Query params: `limit`, `trading_day` |
| GET | `/api/equity` | Snapshots for chart |
| GET | `/api/backtest-window` | Expected curve for paper comparison |
| POST | `/api/pause` | Toggle pause; body `{ paused: boolean }`; journal actor |
| POST | `/api/flatten` | Emergency flatten; require password re-entry in body |
| POST | `/api/reset-halt` | Clear hard halt; require confirm + password |

**No** `/api/run/submit` or `/api/buy`. Scheduled engine owns submissions.

Python implementation may live in `api/` or `engine/handlers.py` invoked by
Next.js route handlers — same `run_once` and `risk`/`broker` paths as cron.

---

## Cursor prompt (Part C — dashboard)

> Read WEBUI.md, ARCHITECTURE.md, and NOTIFICATIONS.md. Implement the Next.js
> app per spec: Supabase Auth with signups disabled, middleware on all dashboard
> and API routes, the six dashboard sections on `/dashboard`, read-only
> `/research` and `/gate` shells (gate populated when Part E exists). Mutating
> routes call the Python engine with server-side Alpaca keys; journal every
> action with `actor` from Supabase user email. No buy or preview-submit flow.
> Add pytest or Playwright smoke test for "unauthenticated → login redirect".
> Update README with dashboard URL and auth note. Walk me through login and
> explain why there is no buy button.

---

## Local development

```bash
npm install && npm run dev
```

App Router lives at repo root (`app/`, `lib/`, `components/`). Requires
`.env.local` with `NEXT_PUBLIC_SUPABASE_*` plus server vars for API routes.
Locally, mutations invoke Python `actions.py` inline when not on Vercel;
on Vercel, Next proxies to `/api/engine_*` with `CRON_SECRET`.

---

## What this UI deliberately omits

- Streamlit (old Prompt 7) — replaced by Next.js for auth and layout control
- Manual "preview then submit" flow (old WEBUI.md) — auto-submit on schedule;
  shadow mode replaces preview during first hosted week
- Order buttons, strategy parameter editors, config.py editors in browser

Parameter changes remain: edit config.py, re-backtest, deploy — intentional
friction from STRATEGY.md.
