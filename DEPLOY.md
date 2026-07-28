# Deployment Guide

How to run the paper swing bot on **$0/month** infrastructure: Vercel Hobby
(dashboard + Python functions), Supabase free (Postgres + auth), GitHub Actions
(redundant scheduler + research jobs), Alpaca paper, Resend email.

Prerequisite: Part A of CURSOR_PROMPTS.md complete (engine defects fixed, tests
passing). Do not deploy until then.

## Stack summary

| Service | Role | Cost |
|---------|------|------|
| GitHub (public repo) | Source, Actions cron, secret scanning | $0 |
| Vercel Hobby | Next.js UI, Python `run_once`, Vercel Cron | $0 |
| Supabase free | Postgres, Auth (one user) | $0 |
| Alpaca | Paper broker + SIP historical data | $0 |
| Resend | Email (daily digest + alerts) | $0 |

See ARCHITECTURE.md for data flow and WEBUI.md / NOTIFICATIONS.md for UX.

---

## 1. Supabase setup

1. Create a project at [supabase.com](https://supabase.com) (free tier).
2. **Auth:** Email + password. Create your user in the dashboard. **Disable
   public signups** (Authentication → Providers → email: allow only existing
   users / disable sign-ups per current Supabase UI).
3. **Database:** Run migrations from `supabase/migrations/` (created in Part B
   Prompt). Tables: `bot_state`, `runs`, `journal`, `equity_snapshots`.
4. Copy **Project URL**, **anon key** (browser), **service role key** (server
   only — never expose to the client).

Optional: enable TOTP MFA on your account after first login.

---

## 2. Vercel setup

1. Import the GitHub repo into Vercel (Hobby).
2. Framework: Next.js (App Router at repo root: `app/`, `lib/`, `components/`).
3. Add environment variables (see table below). Mark Alpaca and service role
   as **sensitive**; expose only `NEXT_PUBLIC_SUPABASE_URL` +
   `NEXT_PUBLIC_SUPABASE_ANON_KEY` to the browser bundle.
4. Deploy. Confirm unauthenticated `/dashboard` redirects to `/login`, then
   sign in with your single Auth user. Mutations (pause / flatten / reset-halt)
   proxy to Python `/api/engine_*` with `CRON_SECRET`.

Python engine: `api/run.py`, `api/capture.py`, `api/watchdog.py` (Vercel
Python serverless). Shared logic in `hosted.py` / `engine.py`. Bundle limit
for Python is 500 MB — pandas/numpy fit. Set `CRON_SECRET` in Vercel so Cron
requests send `Authorization: Bearer …`.

---

## 3. GitHub Actions setup

1. Repo must be **public** for unlimited free scheduled minutes (or use GitHub
   Pro on private — see paid appendix).
2. Add repository **Secrets** mirroring server-side env vars (Alpaca, Supabase
   service role, Resend).
3. Workflows (created in Part B):
   - `daily-run.yml` — after-close swing run (redundant with Vercel Cron)
   - `open-capture.yml` — ~9:31am ET day-start equity capture
   - `watchdog.yml` — late evening check for missed run
   - `research.yml` — manual dispatch for heavy backtests / minute-bar downloads

Restrict workflow triggers to `schedule` and `workflow_dispatch` only. Do not
use `pull_request_target` with secrets.

Enable **secret scanning** and **push protection** on the public repo.

---

## 4. Environment variables

| Variable | Where | Client-safe? | Purpose |
|----------|-------|--------------|---------|
| `ALPACA_API_KEY_ID` | Vercel, Actions | No | Paper trading |
| `ALPACA_API_SECRET_KEY` | Vercel, Actions | No | Paper trading |
| `SUPABASE_URL` | Vercel, Actions | Yes (URL only) | API endpoint |
| `SUPABASE_ANON_KEY` | Vercel | Yes | Auth (legacy name) |
| `NEXT_PUBLIC_SUPABASE_URL` | Vercel | Yes | Browser auth client |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Vercel | Yes | Browser auth client |
| `SUPABASE_SERVICE_ROLE_KEY` | Vercel server, Actions | **Never client** | Engine DB writes |
| `CRON_SECRET` | Vercel | No | Cron + Next→engine mutation proxy |
| `DATABASE_URL` | Vercel, Actions | No | Direct Postgres (if used) |
| `RESEND_API_KEY` | Vercel, Actions | No | Email |
| `NOTIFY_EMAIL_TO` | Vercel, Actions | No | Your inbox |
| `NOTIFY_EMAIL_FROM` | Vercel, Actions | No | Verified Resend sender |
| `BOT_SHADOW_MODE` | Vercel, Actions | No | `true` = journal only, no submit |
| `BOT_SUBMIT` | Vercel, Actions | No | `true` = place paper orders |

Local dev: copy `.env.example` to `.env` (gitignored).

Alpaca keys come from the **Paper** dashboard only. Same keys work for market
data API (SIP historical when `end` is >15 minutes ago).

---

## 5. Cron schedules (dual scheduler)

Both Vercel Cron and GitHub Actions may fire the same job. Idempotency is enforced
by Postgres `UNIQUE (trading_day, strategy)` on `runs` — the second invocation
records `skipped_duplicate` and exits without orders.

**Important:** Cron expressions are UTC. US Eastern alternates EST (UTC−5) and
EDT (UTC−4). Pick UTC times that fall safely inside the intended ET window, or
use a workflow step that computes "next run" from Alpaca calendar (preferred in
Part B implementation).

### After-close swing run (~5:15pm ET)

Target window: 5:00–5:30pm ET, Mon–Fri, only on trading days (engine skips
holidays via calendar).

Example (approximate — verify after DST changes):

| Season | UTC cron (Mon–Fri) | Notes |
|--------|-------------------|-------|
| EST | `15 22 * * 1-5` | 22:15 UTC = 5:15pm ET |
| EDT | `15 21 * * 1-5` | 21:15 UTC = 5:15pm ET |

**Vercel Hobby caveat:** cron timing is only guaranteed within ±59 minutes of
the hour. GitHub Actions is the reliability backstop; do not rely on Vercel
alone for precise timing.

### Day-start equity capture (~9:31am ET)

Separate job so daily-loss halt compares intraday equity to **open** equity, not
same-run equity.

| Season | UTC cron (Mon–Fri) |
|--------|-------------------|
| EST | `31 14 * * 1-5` |
| EDT | `31 13 * * 1-5` |

### Missed-run watchdog (~6:30pm ET)

If no successful `runs` row for today's trading day by this time → NO-RUN alert
email. See NOTIFICATIONS.md.

| Season | UTC cron (Mon–Fri) |
|--------|-------------------|
| EST | `30 23 * * 1-5` |
| EDT | `30 22 * * 1-5` |

Implement trading-day checks inside the job (skip weekends/holidays even if
cron fires).

---

## 6. Shadow mode (first hosted week)

Before enabling real paper submits:

1. Set `BOT_SHADOW_MODE=true` (or equivalent flag from Part B).
2. Schedulers run full logic: signals, sizing, journal — **no** `submit_order`.
3. Each evening, optionally run locally and compare decisions to hosted journal.
4. Accept when 5+ consecutive trading days match (or you understand every diff).

Then set `BOT_SUBMIT=true`, `BOT_SHADOW_MODE=false`. From here the bot queues
orders for the next open without you at the keyboard.

### Implemented paths (Part B5)

| Job | Vercel | GitHub Actions |
|-----|--------|----------------|
| After-close | `POST/GET /api/run` | `.github/workflows/daily-run.yml` |
| Open capture | `/api/capture` | `.github/workflows/open-capture.yml` |
| Watchdog | `/api/watchdog` | `.github/workflows/watchdog.yml` |

Shared entry: `hosted.run_after_close()` / `hosted.run_open_capture()`.
Next.js stub: repo-root `app/page.tsx` (auth dashboard in Part C).

---

## 7. Rollback

| Failure | Action |
|---------|--------|
| Bad deploy | Vercel → Deployments → Promote previous deployment |
| Runaway orders | Dashboard **Flatten now** + set `BOT_SUBMIT=false` in env |
| Corrupt state | Restore Supabase daily backup (free tier: confirm backup policy) or manual `bot_state` fix after journal review |
| Leaked key | Rotate in Alpaca/Supabase/Resend immediately; redeploy |

Never roll back by weakening paper checks or bypassing risk.py.

---

## 8. Detecting silent scheduler failure

Scheduled jobs fail quietly. You must not depend on noticing absence yourself.

1. **Watchdog workflow** — emails if no `runs.status = ok` for today's trading day.
2. **Dashboard header** — "Last run: …" turns red when stale (WEBUI.md).
3. **Weekly self-check** — glance at journal continuity (no gaps on trading days).

GitHub disables schedules after 60 days of repo inactivity — keep occasional
commits or a monthly empty workflow bump if the repo goes quiet.

---

## 9. Go-live preparation (still paper until checklist complete)

Hosted paper is not live money, but treat it as production discipline:

- 30+ consecutive trading days without a missed run
- Received and understood at least one HALT or NO-RUN email (test in Part C)
- Can explain dual-scheduler idempotency without notes

Full live checklist remains in README.md. Going live = private repo + new keys.

---

## Appendix A: Paid upgrade path (when a strategy earns it)

Upgrade when **one** of these is true (not before):

1. A strategy passes Stage A of the promotion gate and you begin Stage B's
   60-day unattended paper run (PHASE2_INTRADAY.md).
2. You need reliable **minute-precision** live sessions (`vwap_z`, or tired of
   sleep-until hacks for `orb15` / `overnight`).
3. Missed free-tier cron runs are frequent enough to corrupt sample integrity.

| Option | ~Cost | Unlocks |
|--------|-------|---------|
| **Railway Hobby** | $5/mo | Always-on container, persistent intraday loop, Postgres add-on |
| **Vercel Pro** | $20/mo | Per-minute cron precision, 800s–30min function duration |
| **GitHub Pro** (if repo must stay private) | $4/mo | Scheduled workflows on private repos |

The engine's `run_once()` design means migration is env + cron config, not a
rewrite. See ARCHITECTURE.md portability section.

Do not pay for hosting until backtests and gate results justify it — the gate
exists to reject strategies before they consume your money or attention.
