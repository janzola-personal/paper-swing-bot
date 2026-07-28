# Education — guided tour

Welcome. This page is your textbook for the Paper Swing Bot: what it does, how
to read the dashboard, how paper testing works, and how new ideas (including
day-trading research) must earn their way in before they touch capital.

> **You are here:** paper trading only. Alpaca keys point at a **PA…** paper
> account. Real money is months away and requires a deliberate checklist — not a
> settings toggle.

---

## Start here: what this app is

This is a **learning lab** disguised as a trading bot.

| Piece | What it is |
|-------|------------|
| **Swing engine** | Runs once per day **after the close**. Decides positions from daily bars, queues paper orders that fill at the **next open**. |
| **Dashboard** | Password-protected window into journal, equity, gate progress, and emergency controls (pause / flatten / reset-halt). **No buy button.** |
| **Email** | Daily digest + HALT / ERROR / NO-RUN alerts. |
| **Research** | Read-only backtest report (`/research`). Numbers from history — not a promise. |
| **Gate** | Promotion scoreboard (`/gate`). New strategies must pass frozen rules before paper. |
| **Intraday lab** | Separate Python package (`intraday/`) for minute-bar ideas. **Not** wired to live orders yet. |

**Honest expectation:** modest, rule-based edges on broad ETFs — not “$100/day on
$5k.” The win is learning systematic discipline: test → paper → gate → maybe
allocate small live capital someday.

---

## What happens each trading day

Times are **America/New_York** (market calendar, not server UTC).

```text
  ~9:31 AM   Open capture — lock start-of-day equity (daily-loss halt baseline)
  4:00 PM    Market closes
  ~5:15 PM   After-close run — fetch bars, compute signals, journal, submit paper orders
  ~6:30 PM   Watchdog — email if today’s run never completed
  Next open  DAY market orders from yesterday’s run execute at the open
```

**Signal timing (critical concept):** the bot decides on **bar t’s close** and
**executes at bar t+1’s open**. The backtest uses the same rule. That avoids
look-ahead bias (“using tomorrow’s open to decide today’s trade”).

---

## Key concepts

### RSI(2) mean reversion (`rsi2` — live strategy)

Connors-style rule on daily bars, long-only:

- **Regime filter:** only buy when close is **above** the 200-day SMA (uptrend).
- **Entry:** RSI(2) closes **below 10** (short-term oversold dip in an uptrend).
- **Exit:** close above 5-day SMA, or RSI(2) above 65, or **10-day time stop**.

Why it exists: simple, published, deterministic — good for learning execution
and risk, not for chasing lottery returns.

### Trend filter (`trend` — baseline)

Faber-style **month-end** rule: hold when close > 200-day SMA, else cash. Slow,
boring, hard to blow up. Used to compare “active” rsi2 against a dumb benchmark.

### Lab variant: `rsi2_tight` (not live)

Same structure with **entry RSI < 5** and **5-day** max hold. Registered for
backtests only. `ACTIVE_STRATEGY` stays `rsi2` unless evidence clearly wins
after costs and drawdown.

### Position sizing & risk (`risk.py`)

- Whole shares, **cash only**, max **2** positions, max **50%** of equity each.
- **Daily loss halt:** down ≥ **2%** from **morning** equity → flatten, no new
  trades until next session.
- **Drawdown halt:** equity ≥ **10%** below peak → flatten + **hard halt**
  until you review and use **Reset halt** on the dashboard.

These limits are load-bearing walls — not tuning knobs.

### Slippage & costs

Backtests assume **5 bps per side** (0.05%) at the open, $0 commission (Alpaca).
Intraday research uses **5 bps + half spread** per side. Real fills can be
worse on gaps and fast markets — paper trading measures that gap.

### Paper vs shadow vs submit

| Mode | Orders? | Purpose |
|------|---------|---------|
| **Shadow** | No (`dry_run=true`) | Journal only — prove scheduling and data |
| **Submit (paper)** | Yes, Alpaca **paper** | Realistic fills at next open |
| **Live** | Not supported in this repo | See go-live checklist below |

---

## Strategies you have today

| Name | Horizon | Status | Where to read rules |
|------|---------|--------|---------------------|
| `rsi2` | Daily swing | **Live paper** | `STRATEGY.md`, dashboard journal |
| `trend` | Monthly-ish | Backtest / compare | `STRATEGY.md` |
| `rsi2_tight` | Daily swing | Lab / backtest only | `config.RSI2_TIGHT` |
| `overnight` | Close → next open | Research + gate | `intraday/strategies/overnight.py` |
| `orb15` | Intraday ORB | Research + gate | `intraday/strategies/orb15.py` |
| `vwap_z` | Intraday VWAP | Research + gate | `intraday/strategies/vwap_z.py` |

Only **`rsi2`** runs on the hosted schedule. Everything else is research until
it passes the gate and you explicitly promote it.

---

## Paper testing timeline (swing / rsi2)

This is the path from “code works” to “I trust the process.”

### Phase 0 — Already done (if you’re on the dashboard with submit on)

- [x] Hosted deploy (Vercel + Supabase + cron)
- [x] Shadow runs validated scheduling
- [x] Paper submit enabled (`BOT_SUBMIT=true`, shadow off)

### Phase 1 — Stage B paper discipline (~60–90 trading days)

Track on the dashboard **Gate progress** card:

| Milestone | Target | Notes |
|-----------|--------|-------|
| Trading days | **≥ 60** | Submit-mode runs with handled status |
| Completed trades | **≥ 40** | Real BUY/SELL (`dry_run=false`) |
| Manual overrides | **0** | Pause/flatten/reset-halt only when necessary |
| Consistency | Directional | Paper vs backtest OOS — not “beat B&H luck” |

**Calendar:** set a **Sunday 30-minute** reminder. Follow
[PAPER_REVIEW.md](https://github.com/janzola-personal/paper-swing-bot/blob/main/PAPER_REVIEW.md)
(checklist in repo): journal vs email, paper vs backtest chart, halt drill.

**Typical duration:** rsi2 trades ~10–20× per year per symbol — 40 completed
trades may take most of the 60-day window. **Do not force trades.**

### Phase 2 — Decide (not automatic)

After Stage B:

- If paper matches backtest **directionally** and halts behaved → you’ve earned
  confidence in the **process**, not necessarily alpha forever.
- If divergences persist → pause, investigate data/fills/sizing before continuing.
- Promoting `rsi2_tight` or intraday strategies requires **new** backtest + gate
  + paper — not a config whim.

```text
  Backtest (history)  →  Shadow (journal)  →  Paper submit  →  Stage B  →  Review
        ↑                      ↑                    ↑              ↑
   build_report.py      BOT_SHADOW_MODE      BOT_SUBMIT      60d / 40 trades
```

---

## Weekly routine (while paper trading)

1. **Journal vs digest** — Dashboard journal matches inbox emails.
2. **Paper vs backtest chart** — Same `$5,000` window; similar shape, not identical.
3. **Gate counters** — Days, trades, overrides (target 0 overrides).
4. **Alpaca paper UI** — Positions/orders match journal (PA account only).
5. **Monthly:** read a halt scenario — know *why* before reset-halt.

---

## How to create a new strategy

**Golden rule:** deterministic rules only in the signal path — no network, no LLM,
no randomness inside `strategy.py` order logic.

### Swing strategy (daily bars)

1. **Write the rules in plain English** first (`STRATEGY.md` section).
2. **Add parameters** in `config.py` (never tune from live P&amp;L).
3. **Implement** a function returning `position` 0/1 per bar in `strategy.py`.
   - Signal on bar **t** close → position[t] applies from **t+1** open.
4. **Tests** in `tests/` — entry, exit, warm-up NaNs, max-hold.
5. **Backtest:** `python backtest.py --strategy your_name`
6. **Report:** `python build_report.py` — compare vs rsi2/trend/B&amp;H on OOS split.
7. **Gate:** produce JSON results → `python gatecheck.py results/gate_yourname.json`
8. **Do not** set `ACTIVE_STRATEGY` until gate + your explicit decision in writing.

### What not to do

- Cherry-pick the best cell on a parameter grid and call it “the strategy.”
- Change `risk.py` to “make it trade more.”
- Wire sentiment CSV or headlines into signals (research isolation rule).

---

## Day-trading strategies (intraday lab)

Intraday is **Phase 2 research** — isolated from the swing order path.

| Step | Action |
|------|--------|
| 1 | Read `PHASE2_INTRADAY.md` and `intraday/README.md` |
| 2 | Fetch minute bars locally: `intraday/data_minute.py` (SIP cache under `data/minute/`) |
| 3 | Backtest: `intraday/backtest_intraday.py` — signal t close → fill t+1 open; 3:55 PM flatten |
| 4 | Candidates: `overnight`, `orb15`, `vwap_z` in `intraday/strategies/` |
| 5 | Gate: `python build_phase2_report.py` then `python gatecheck.py results/gate_orb15.json` |
| 6 | **Expect REJECT** on thin edges — that’s success for the gate |

### Supervised engine (not hosted cron yet)

```bash
python -m intraday.engine --dry-run    # heartbeat + journal, no orders
```

`--unattended` is **blocked** until `INTRADAY_SUPERVISED_OK=1` after one full
supervised session you document. Hosted minute cron is future work (E7).

**PDT note:** pure intraday round-trips count toward day-trade rules under $25k;
`overnight` holds past the close and is swing-adjacent.

---

## The promotion gate

Strategies move: **BENCH → BACKTEST-PASS → PAPER → LIVE-ELIGIBLE**

Each stage requires **every** criterion in [`gates.md`](/gate). Highlights:

**Stage A (backtest):**

- ≥5 years data (state gaps honestly)
- ≥300 intraday trades / ≥100 swing trades (OOS)
- OOS net &gt; 0, profit factor ≥ 1.2, max DD ≤ 15%
- Still profitable at **2×** costs (record 3× too)
- Parameter stability ±33%
- ≤5% of days would trip daily-loss halt

**Stage B (paper):**

- 60 days + 40 trades + zero manual overrides
- Paper directionally matches backtest OOS
- Fill-quality audit if slippage &gt; model

**Reject is success** — the gate kills strategies before they touch capital.

---

## Paper to real money (when, how, and why not yet)

This repo **refuses** to go live accidentally:

- `PAPER_TRADING = True` in code
- `TradingClient(paper=True)` always
- Account number must start with **PA**

### Going live is NOT

- Flipping `PAPER_TRADING` to False in chat without the checklist
- Using live Alpaca keys in this public repo
- “It’s only $500” without halts understood

### Going live IS (all required)

1. **≥ 60–90 days** paper with submit, **no** discretionary overrides.
2. Paper **directionally consistent** with backtest OOS (same window).
3. You can explain every module without notes.
4. You’ve lived through a **losing streak** and at least one **halt**.
5. Capital is **money you can lose entirely**; start at **10–20%** of that.
6. You’ve read broker docs: rejects, partial fills, PDT.
7. **≥ 30** consecutive trading days without a missed scheduled run.
8. You’ve tested HALT / NO-RUN alert flow end-to-end.
9. You understand Postgres idempotency (one run per day).
10. Repo goes **private**; **all keys rotated** the same day.

If all ten are true, you won’t need permission from this app — you’ll know the
change is yours to own. Until then: **paper**.

See README **Go-live checklist** for the canonical list.

---

## Dashboard controls (what each button means)

| Control | Effect | Stage B impact |
|---------|--------|----------------|
| **Pause** | Stop new orders; keep positions | Use for debugging — journals `actor` |
| **Flatten** | Sell all at next open (password) | Emergency only — counts as override |
| **Reset halt** | Clear drawdown halt after review | Password — use only after understanding why |

There is **no buy button** by design: entries come from the strategy on schedule.

---

## Glossary

| Term | Meaning |
|------|---------|
| **Bar** | One candle (daily or minute): open, high, low, close, volume |
| **OOS** | Out-of-sample — test on data the tuning pass didn’t see |
| **Profit factor** | Gross wins ÷ gross losses |
| **Max drawdown** | Worst peak-to-trough equity drop |
| **DAY order** | Expires end of session; after-close submit queues for next open |
| **SIP** | Alpaca consolidated feed (preferred for backtests when history allows) |
| **Actor** | Your email logged on manual dashboard actions |

---

## Your first week checklist

- [ ] Log into [dashboard](/dashboard) — confirm gate progress visible
- [ ] Read **STRATEGY.md** rsi2 rules once
- [ ] After a trading day, compare **email** vs **journal**
- [ ] Open **Research** — skim backtest; note OOS vs in-sample humility
- [ ] Open **Gate** — read frozen thresholds
- [ ] Bookmark this page; schedule Sunday **PAPER_REVIEW** reminder
- [ ] Do **not** change `ACTIVE_STRATEGY` or risk limits without typed intent + backtest

---

*Educational software — not investment advice. Past backtests overstate future results.*
