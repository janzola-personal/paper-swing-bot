# Phase 2 — Intraday & Aggressive Strategies (drop this file in the repo root)

Extends the repo with a second, isolated engine for shorter-horizon and
higher-aggression strategies, all governed by a pre-registered promotion gate.
Prerequisite: CURSOR_PROMPTS.md Parts A–D complete and the swing engine running
in hosted paper (auto-submit, dashboard, email).

The working assumption of this phase: **most candidates will fail the gate.**
Intraday is where retail edges are thinnest, costs dominate, and backtests
flatter hardest. A gate that reliably rejects bad strategies before they touch
real capital IS the deliverable. "I can afford to lose the $25k" removes
catastrophe; it does not lower the burden of proof — the gate decides what
deserves capital, affordability only caps the damage if the gate is wrong.

---

## 1. The Promotion Gate (create as gates.md — edit numbers, then FREEZE)

A strategy moves BENCH → BACKTEST-PASS → PAPER → LIVE-ELIGIBLE only by
passing every criterion of the stage. Numbers below are sane defaults; adjust
them before testing a strategy, never after seeing its results.

**Stage A — Backtest pass (all required):**
- Data: ≥5 years of minute bars including 2020 and 2022 if the feed's history
  allows; otherwise maximum available with the gap stated in the report.
- Sample size: ≥300 trades (intraday) / ≥100 (swing/overnight).
- Out-of-sample: parameters frozen on the first 60% of data; all pass/fail
  stats computed on the final 40% only.
- After-cost OOS: net return > 0, profit factor ≥ 1.2, max drawdown ≤ 15%
  at intended sizing.
- Cost stress: still net-positive OOS at 2× the baseline cost model
  (record the 3× result too). Baseline intraday costs: 5 bps slippage per
  side + half the average spread; market orders assumed.
- Parameter stability: perturb each key parameter ±33%; the majority of
  neighboring variants must remain profitable OOS.
- Halt compatibility: ≤5% of backtest days would have tripped the 2% daily
  loss halt at intended sizing (else resize or reject — a strategy that
  fights the kill switch is misdesigned for this account).

**Stage B — Paper pass:**
- ≥60 trading days AND ≥40 completed paper trades with `--submit`.
- Zero manual overrides of entries, exits, or halts.
- Paper net result after costs directionally consistent with the backtest's
  OOS expectation for the same window (not just "up").
- Fill-quality audit: mean paper slippage vs. the cost model; if real
  slippage exceeds the model, re-run Stage A with the measured number.

**Demotion (automatic, symmetric):**
- Any hard halt → back to BENCH pending review.
- Rolling 30-trade net loss worse than the backtest's worst comparable
  30-trade stretch → back to PAPER (if live) or BENCH (if paper).

---

## 2. Two axes of "aggressive" — keep them separate

**Signal aggression** (shorter horizon, more trades): rungs below.
**Sizing aggression** (same signals, more exposure): larger MAX_POSITION_PCT,
or substituting leveraged ETFs (QQQ→QLD/TQQQ). If you test the leveraged
route, the gate must include 2020 and 2022, and you must understand
volatility drag first: leveraged ETFs compound daily, so a choppy flat market
erodes them even when the index round-trips. They also turn the 2% daily halt
into a hair trigger — model that explicitly. Sizing changes go through the
same gate as new strategies; "same signal, 3× size" is a different strategy.

---

## 3. Strategy specs (rule level — implementation is Prompt 14)

### Rung 2 — Overnight bridge (`overnight`) — runs without the intraday engine
Documented anomaly: much of long-run index return has accrued close→open.
- At ~15:50 ET: if close(est) > 200-day SMA AND today's return ≤ 0, buy at
  15:55 (market). Sell at next open (order queued after the close).
- Not a day trade (holds overnight) → PDT-free at any account size.
- Sizing: standard cap rules. One position at a time.
- **Prediction to verify:** per-trade edge is a few bps; expect it to PASS
  raw backtest and FAIL the 2× cost stress. Running it first calibrates your
  cost model and proves the gate rejects things. If it somehow passes
  honestly, it's the safest aggressive rung you have.
- Engine change needed: a second daily run at 15:50 ET (small main.py flag).

### Rung 3a — Opening Range Breakout (`orb15`) — needs the intraday engine
The most-studied recent retail intraday claim (Zarattini & Aziz 2023, QQQ
5-minute ORB). Their headline numbers used aggressive leverage and friendly
cost assumptions and are actively debated; treat this as a hypothesis to kill.
- Symbols: QQQ (SPY as robustness check). Long-only v1.
- Opening range (OR): high/low of 9:30–9:45 ET. Sensitivity: 5-minute OR.
- Regime filter: prior daily close > 200-day SMA.
- Noise filter: skip the day if OR width < 0.3 × 14-day daily ATR.
- Entry: stop order at OR high + 1 cent; first trigger only; max one trade
  per symbol per day.
- Initial stop: OR low (sensitivity: OR midpoint). Server-side, via bracket.
- Exit: unconditional flatten at 15:55 ET (sensitivity: +2R take-profit).
- Sizing (new concept — risk-based): shares = (0.5% of equity) / (entry −
  stop), then capped by the normal MAX_POSITION_PCT and cash rules.

### Rung 3b — VWAP mean reversion (`vwap_z`) — needs the intraday engine
Thinner published evidence than ORB; expect extreme cost sensitivity.
- Session VWAP from minute bars; z = (price − VWAP) / intraday std(price−VWAP).
- Long entry: z ≤ −2.0, between 10:00–15:00 ET only, regime filter as above.
- Target: touch of VWAP. Stop: entry − 1.0 × current intraday std,
  server-side. Flatten 15:55 ET. Max 2 trades/symbol/day, one open position.

---

## 4. Intraday engine requirements (build spec for Prompt E5)

1. Separate module (`intraday/`), journal table (`intraday_journal` in Postgres
   or `intraday_journal.csv` locally). May import risk.py, config.py — never
   swing strategy or order logic, and vice versa.
2. **Stateless tick model (hosted):** each market minute invokes
   `run_intraday_tick(trading_day, now_et)` — load state from Postgres, fetch
   latest bar, evaluate, act, write state, exit. No 6.5-hour persistent loop
   required on $0 infra; see Section 8. Local supervised dev may use a terminal
   loop for debugging.
3. **Every entry is a bracket order** (entry + server-side stop, optional
   take-profit). If a tick crashes mid-session, the broker still holds the stop.
4. 15:55 ET: cancel all open orders, flatten all intraday positions,
   unconditionally (dedicated cron or final tick).
5. Daily-loss limit evaluated each tick against live equity; breach →
   cancel-all, flatten, halt (reuse risk.py semantics).
6. **Heartbeat + deadman (hosted unattended):** each tick writes
   `last_heartbeat_at` to Postgres. A separate watchdog (cron) during market
   hours: if heartbeat stale >3 minutes while an intraday position is open,
   cancel-all, flatten, alert ERROR. Replaces Ctrl-C safety from local dev.
7. **Supervised local first:** default CLI refuses `--unattended` until you
   have completed one full paper session at the terminal reading the journal.
   Unattended hosted ticks are Part E7 (paid path) or free-tier sleep-until
   hacks (Section 8) — not day one.
8. Paper-mode assertions identical to broker.py's three checks.

---

## 5. Data plan

- Minute bars via Alpaca's historical data API, cached in parquet (Actions
  artifact or Supabase Storage). yfinance intraday history is too shallow —
  don't use it here.
- Verify against current Alpaca docs (Prompt E4): free Basic plan limits,
  historical depth, rate limits (200 calls/min), paper PDT simulation.
- **Feed caveat — read carefully:**
  - **Backtests & research:** historical minute bars with `end` >15 minutes ago
    can use **SIP (consolidated)** on the free plan. Backtest reports should
    state feed and date range; 2× cost stress remains mandatory.
  - **Live streaming / recent bars:** free tier is **IEX-only** (~2.5% of
    volume). Live paper fills may not match backtest slippage assumptions —
    flag in PHASE2_REPORT.md and re-run Stage A if measured slippage exceeds
    the model (Stage B fill-quality audit).
- Do **not** blanket-label all Phase 2 data "IEX-only"; distinguish backtest
  (SIP historical) from live tick (IEX unless paid Algo Trader Plus).

---

## 6. Cursor prompts (Part E of CURSOR_PROMPTS.md)

**Prompt E3 — the gate**
> Create gates.md from Section 1 of PHASE2_INTRADAY.md, then build
> gatecheck.py: it takes a backtest results file (trades + equity curve +
> metadata incl. cost multiplier and OOS split) and prints PASS/FAIL per
> criterion with the measured value next to the threshold. Add tests with
> synthetic results engineered to fail exactly one criterion each. Nothing
> in gatecheck.py may be tunable from the command line except the input
> path — thresholds live only in gates.md/config so I can't fudge them ad hoc.

**Prompt E4 — minute data + intraday backtester**
> Build intraday/data_minute.py (Alpaca historical minute bars, parquet
> cache, explicit feed and history-depth verification against current docs —
> cite pages) and intraday/backtest_intraday.py. Execution model: signal on
> bar t close → fill at bar t+1 open ± slippage; stop orders fill at
> stop ± slippage, or at the bar's open if it gaps through the stop; costs =
> slippage bps + half-spread, with a --cost-multiplier flag for the gate's
> 2×/3× stress. Include the 15:55 forced flatten in the simulator. Tests: a
> hand-built 10-bar day where entry, stop-gap fill, and EOD flatten are
> computed manually in comments.

**Prompt E5 — the intraday engine**
> Implement intraday/engine.py per Section 4 of PHASE2_INTRADAY.md (stateless
> tick, brackets, heartbeat, 15:55 flatten, paper checks). Verify current
> alpaca-py bracket-order support against docs (cite pages). Default supervised
> local session; hosted tick handler optional stub. Walk me through one
> supervised paper session minute by minute.

**Prompt E6 — strategies through the gate**
> Implement `overnight` (second daily run ~15:50 ET), then `orb15` and
> `vwap_z` per Section 3, each behind a registry with rule tests. Run each
> through backtest → gatecheck.py → results/PHASE2_REPORT.md with honest
> verdicts. "Reject" is success. Note SIP vs IEX where relevant.

**Prompt E7 — paid hosting (only if Stage A passes)**
> For strategies that passed Stage A: implement unattended hosted ticks per
> DEPLOY.md appendix (Railway/Fly or Vercel Pro per-minute cron). Do not
> spend until E6 shows a PASS. Include sizing/leverage variants (1.5×/2×
> MAX_POSITION_PCT, QLD substitution) with 2020/2022 mandatory and daily-halt
> interaction modeled.

---

## 7. Live day-trading deltas (for the distant checklist, not for now)

- PDT: unrestricted day trading requires ≥ $25k equity maintained in a
  margin account; dip below and restrictions return. Fund a buffer (e.g.
  $30k) or size so a normal drawdown can't breach the floor.
- Margin account is standard for day trading (cash accounts create
  settlement/good-faith-violation problems at this cadence); margin *account*
  ≠ using leverage — sizing rules here stay cash-based.
- Taxes: high trade counts generate many short-term lots taxed as ordinary
  income; the journal + broker 1099-B are your audit trail. Factor tax drag
  into "worth it."
- Every item in the README go-live checklist applies per-strategy, not
  per-account: each strategy earns live status separately through the gate.

---

## 8. What $0 hosting can and cannot do (per strategy)

All **research** (gate, minute data, intraday backtester, gatecheck, reports,
supervised local engine sessions) is $0 — run on your Mac or GitHub Actions.

**Unattended live paper** during market hours needs reliable minute-precision
scheduling. Free tiers are imperfect; plan accordingly.

| Strategy | Backtest + gate | Supervised local paper | Unattended $0 paper | Needs paid host |
|----------|-----------------|------------------------|---------------------|-----------------|
| `overnight` | Yes (Actions) | Yes | **Maybe** — 2 crons/day; sleep-until-target-time in job to hit 15:50 ET; late runner skips day | If skip rate hurts Stage B |
| `orb15` | Yes | Yes | **Maybe** — 2 crons (9:46 bracket, 15:55 flatten); broker holds stop between | Same |
| `vwap_z` | Yes | Yes | **No** — needs ~300 minute evaluations/day; Actions 5-min floor + 6h cap unsuitable | Yes (~$5/mo container or Vercel Pro) |

**Sleep-until technique ($0):** schedule cron 10–15 minutes early; job polls
Alpaca clock, sleeps until target ET time, aborts if past window. Safety from
broker brackets, not from your process staying alive. Cost: occasional missed
days → slower Stage B sample, not blow-up risk.

**When to pay:** only after a strategy passes **Stage A** and you begin Stage B's
60-day unattended run — see DEPLOY.md appendix. Most strategies never get there.

*Educational material, not financial advice. The gate exists because backtests
flatter and intraday flatters most.*
