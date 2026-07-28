# Stage B paper review — weekly checklist

Paper submit is on (`BOT_SUBMIT=true`, `BOT_SHADOW_MODE=false`). Alpaca **paper**
only — not live money. This routine keeps you honest during the 60–90 day
Stage B window for the swing engine (`rsi2`).

Set a recurring calendar reminder: **Sunday, 30 minutes**, before the week opens.

---

## Every week (≈30 min)

### 1. Journal vs email digest

- Open [dashboard](https://paper-swing-bot.vercel.app/dashboard) → **Journal**
  (filter: trades).
- Compare to the week's Resend digests in your inbox.
- **Pass:** same symbols, actions, qty, and reasons (inputs visible).
- **Fail:** missing digest, action mismatch, or silent day with no NO-RUN/HALT
  explanation → check Supabase `runs` and Vercel/Actions logs.

### 2. Paper vs backtest chart

- Dashboard → **Paper vs backtest** (same capital window as
  `BACKTEST_INITIAL_CASH`).
- **Pass:** directionally similar (not identical); no unexplained divergence
  lasting weeks.
- **Fail:** paper consistently opposite to backtest expectation → pause via
  dashboard, investigate data feed / sizing / partial fills before continuing.

### 3. Gate counters (Stage B)

Dashboard **Gate progress** card:

| Criterion | Swing target | Must |
|-----------|--------------|------|
| Trading days | 60 | Count only `runs.mode=submit` handled days |
| Completed trades | 40 | BUY/SELL with `dry_run=false` since paper start |
| Manual overrides | 0 | PAUSE/FLATTEN/RESET_HALT with actor = you |
| Halts | review | Any halt → read reason; no reset-halt until reviewed |

### 4. Halt drill (monthly, or after any HALT email)

1. Read the HALT journal row and `bot_state.halted_reason`.
2. Confirm flatten lines in journal match Alpaca paper orders.
3. Practice **Reset halt** only after you can explain why the halt fired.
4. Do **not** use pause/flatten as discretionary entries — overrides break Stage B.

### 5. Alpaca paper sanity

- Alpaca paper dashboard → positions and recent orders.
- **Pass:** DAY market orders after close queue for next open; journal matches.
- **Fail:** unexpected live account, non-PA account number, or orders while
  paused → stop and fix env keys.

---

## Stage B pass criteria (swing — PHASE2 adapted)

From [PHASE2_INTRADAY.md](PHASE2_INTRADAY.md) §1, adapted for daily-bar swing:

- ≥ **60 trading days** with submit-mode runs handled (`ok` / `halt` / etc.).
- ≥ **40 completed paper trades** (buys + sells that actually submitted).
- **Zero** manual overrides of entries, exits, or halts (dashboard actor rows).
- Paper net result **directionally consistent** with backtest OOS for the same
  window — not required to beat buy-and-hold luck.
- Fill-quality: if mean slippage exceeds backtest assumption, note it and re-run
  Stage A with measured costs before promoting further strategies.

Swing rsi2 trades ~10–20× per year per symbol — 40 trades may take most of the
60-day window. That is expected; do not force trades.

---

## When to pause (not panic)

- NO RUN email after 5:30pm ET on a trading day.
- ERROR or stale-data skip two days in a row.
- You cannot reconcile journal vs Alpaca in 15 minutes.
- Hard halt or daily-loss halt — let the bot stand down; review first.

Use dashboard **Pause trading** if you need to stop new orders while debugging.
Use **Flatten now** only in genuine emergencies (password required).

---

## What not to do during Stage B

- Change `ACTIVE_STRATEGY` or rsi2 parameters without a fresh backtest + your
  explicit typed numbers in chat.
- Manual buys (no buy button — by design).
- Flip `BOT_SUBMIT=false` to "avoid a signal" — that is an override; use Pause
  instead and journal the reason in your own notes.
- Compare weekly P&amp;L to backtest **best** grid cell — compare to OOS
  expectation band.

---

## Quick SQL (Supabase)

```sql
-- Submit-mode runs
select trading_day, status, mode, completed_at
from runs where strategy = 'rsi2' order by trading_day desc limit 20;

-- Live trades since paper start
select trading_day, symbol, action, qty, dry_run, left(reason, 60)
from journal
where action in ('buy','sell') and dry_run = false
order by id desc limit 30;

-- Overrides (must stay 0 for Stage B)
select timestamp_utc, action, actor, reason
from journal where actor is not null order by id desc;
```
