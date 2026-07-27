# Notifications

Email is the primary daily interface. The dashboard is for thinking; the inbox
is for ten-second confirmation that the bot ran and what it decided.

Provider: **Resend** (free tier). Config via environment variables — off when
`RESEND_API_KEY` is unset (local dev without email is fine).

**Hard rule:** no notification body may contain API keys, tokens, or full
account numbers. Equity and P&L numbers are OK (your inbox, your risk).

---

## Configuration

| Variable | Purpose |
|----------|---------|
| `RESEND_API_KEY` | Resend API key (server-side only) |
| `NOTIFY_EMAIL_TO` | Your address |
| `NOTIFY_EMAIL_FROM` | Verified sender domain in Resend |

Implement in `notify.py` (Part C Prompt): one short retry on failure, then log
and continue — email must never crash the trading run.

---

## 1. Daily digest (every successful after-close run)

**Subject line pattern:**

- Action day: `Bot · BUY 12 SPY` (or `SELL`, `FLAT`, `HOLD ALL` if nothing traded)
- No trades: `Bot · no trades · 2026-07-27`

**Body must include:**

1. Trading day (America/New_York session date)
2. Run timestamp (ET) and mode (`paper`, `shadow`, or `dry-run`)
3. Per symbol: action, quantity if any, **inputs** behind the decision (not just the verdict)
4. Equity, cash, day P&L %
5. Gate progress snippet if in Stage B paper (days / trades / overrides / halts)
6. Link to dashboard (no secrets in URL)

**Example:**

```text
Subject: Bot · BUY 12 SPY

Trading day 2026-07-27 · ran 17:04 ET · paper

  BUY  12 SPY @ ~580.12  → fills at tomorrow's open
       rsi2 = 7.3   (entry needs < 10) ✓
       close 580.12 > sma200 551.30    ✓

  FLAT QQQ
       rsi2 = 44.1  (entry needs < 10) ✗

  Equity $5,014.22  (+0.28% today)   Cash $4,318.00
  Paper day 12 of 60 · 3 completed trades of 40

  → https://your-app.vercel.app
```

**Why show inputs:** after ~30 emails you internalize what RSI(2) < 10 feels like
without opening the dashboard. Teaching goal from .cursorrules.

---

## 2. Alert classes (separate subjects — never bury in digest)

### HALT

**When:** hard drawdown halt, daily-loss halt, or risk flatten triggered.

**Subject:** `Bot · HALT · [reason short]`

**Body:** full `halted_reason`, equity vs peak, flatten actions taken, reminder
that hard halt needs dashboard reset-halt after human review. Link to journal
filtered to halt rows.

### ERROR

**When:** uncaught exception, Alpaca auth failure, empty/stale data abort, DB
write failure.

**Subject:** `Bot · ERROR · run failed`

**Body:** trading day, error class (not full stack trace to email — stack in logs),
whether any partial orders might exist (should be none if design holds), link to
dashboard. Run row in `runs` should have `status = error`.

### NO RUN

**When:** watchdog fires and no `runs.status = ok` exists for today's trading day
by ~6:30pm ET (see DEPLOY.md).

**Subject:** `Bot · NO RUN · 2026-07-27`

**Body:** "No successful run recorded for trading day …". Possible causes: both
schedulers failed, holiday misconfiguration, deploy broken. **This is the most
important alert** — silence means you might think the bot traded when it didn't.

---

## 3. Missed-run watchdog

Implemented as a scheduled job (GitHub Actions or Vercel Cron) **after** the
latest expected after-close run window.

Logic:

1. Resolve today's trading day via Alpaca calendar. If not a trading day, exit 0.
2. Query `runs` for `(trading_day, active_strategy)` with `status = ok`.
3. If missing → send NO RUN alert once per day (dedupe via `watchdog_sent` flag
   in `bot_state` or a small `alerts` table).

Do not send NO RUN if `paused = true` in `bot_state` (operator intentionally stopped).

---

## 4. Optional notifications (later)

- Weekly summary email (equity curve thumbnail, trade count, vs backtest band)
- Discord webhook (CURSOR_PROMPTS Part C optional extension) — same content
  rules, no keys

Intraday Phase 2 (paid path): bracket placed, stop hit, 15:55 flatten — separate
spec when engine exists.

---

## 5. Testing (Part C acceptance)

Before enabling `BOT_SUBMIT`:

1. Force a test ERROR (bad key in staging env) — confirm alert, no crash loop.
2. Force a test HALT in paper (or mock state) — confirm subject and copy.
3. Simulate NO RUN (skip manual run, fire watchdog) — confirm email within minutes.

Quiz yourself: **Why is NO RUN a different subject from ERROR?** (A failed run
might still have journaled partial state; a missing run means you have no
decision record at all and may miss the next open.)
