# Strategy Specification

This document is the answer to "what do I buy, when, and why." Every rule the
bot follows is written here in plain English; `strategy.py` is just this page
translated to pandas. If the code and this page ever disagree, that's a bug.

## First, an honest note about where these rules came from

You asked for my own analysis on the theory that an AI can spot opportunities
a human can't. Here's the truthful version of what I can and can't do:

- I **cannot** predict prices or see patterns invisible to the market. Every
  widely known signal is also known to firms with more capital, better data,
  and faster execution. Public patterns that survive do so because they're
  modest, uncomfortable to hold, or too small for big firms to bother with.
- I **can** know the published, peer-studied strategy literature broadly,
  translate it into correct, testable code, and — maybe most valuably — refuse
  to let excitement skip the boring steps (backtest → paper → small).

So the sophisticated move isn't "AI intuition picks stocks." It's a boring,
fully-specified ruleset executed with discipline. The two strategies below are
classics from that literature: short-term mean reversion (popularized by Larry
Connors' RSI(2) research) and long-term trend following (Meb Faber's timing
model). Both have decades of published study. Both have **modest** documented
edges that have decayed over time and may keep decaying. They're chosen
because they're robust, comprehensible, and hard to blow up — not because
they're secret.

## Strategy A — `rsi2`: short-term mean reversion (the active one)

**Idea.** In an uptrend, sharp multi-day selloffs in broad indexes have
historically tended to snap back within days. Buy brief panic, sell the bounce.

**Instruments.** SPY and QQQ only. Broad ETFs can't gap −40% on earnings; a
single stock can.

**Entry — at tomorrow's open, when at today's close BOTH are true:**
1. RSI(2) < 10 — a very stretched short-term selloff. RSI(2) is a 2-day
   Wilder RSI; below 10 roughly means "down hard, two days in a row."
2. Close > 200-day SMA — the regime filter. Panic in an uptrend tends to mean-
   revert; panic in a downtrend (2008, 2022) tends to keep falling. This one
   condition is most of the risk control.

**Exit — at tomorrow's open, when at today's close ANY is true:**
1. Close > 5-day SMA — the bounce happened; take it.
2. RSI(2) > 65 — momentum snapped back hard; same conclusion.
3. Held 10 trading days — time stop. If the bounce hasn't come in two weeks,
   the thesis is wrong; stop waiting.

**No per-trade stop-loss — on purpose, and you should understand why.** In the
published research, tight stops make mean-reversion worse: the strategy buys
dips, and a stop systematically sells the very lows. Protection comes from
four other layers: the 200-day regime filter, the time stop, position sizing
(≤50% of equity per position), and the portfolio kill switches in `risk.py`.
The honest cost: individual trades can sit through drawdowns of several
percent. If that keeps you up at night, the right lever is smaller
MAX_POSITION_PCT — not a stop.

**Expected behavior (from the literature and long backtests — verify with
`python backtest.py` yourself):** trades a few times a month per symbol; in
the market maybe 15–25% of the time; win rate historically high (~65–75%) with
small average wins and occasional larger losses; returns lumpy — quiet months,
then clusters. Historically this class of rules produced mid-single-digit
annual returns on the index with lower exposure. On $5,000, a *good* year
might mean a few hundred dollars. That's the true scale.

**Known failure modes.** (1) The edge decays as markets get more efficient —
recent decades are weaker than the 1990s in most studies. (2) Regime-filter
whipsaw: price hovering around the 200-day SMA flips the filter on and off.
(3) A crash that starts above the 200-day SMA (Feb 2020) hands it a fast loss
before the filter shuts it off. The kill switch exists for exactly this.

## Strategy B — `trend`: month-end trend filter (the baseline)

**Rules.** On the last **calendar** trading day of each month (derived from the
bar index — not "whatever bar happens to be last in a truncated fetch"): if
close > 200-day SMA, hold the ETF from the next open; otherwise sit in cash.
Between month-ends, carry the previous decision unchanged. The live loop must
use the same month-end detection as the backtest (see CURSOR_PROMPTS.md A2).

**Why it's here.** It trades ~1–2 times a year, sidesteps the deepest bear
markets, and is nearly impossible to operate incorrectly. It's the benchmark
`rsi2` must justify itself against, and the fallback if you decide active mean
reversion isn't worth the effort. Historically: buy-and-hold-ish returns with
roughly half the max drawdown — paid for with whipsaw losses in choppy
sideways years.

## Portfolio rules (both strategies)

- Long only. No margin, no shorting, whole shares, never spend more than cash.
- Max 2 concurrent positions, each ≤ 50% of equity. If both SPY and QQQ signal
  and only one slot is free, the lower RSI(2) (more oversold) wins.
- Execution timing: signals on the close, orders queued after hours, filled at
  next open — identical in backtest and live.
- Position sizing: backtest uses the same `risk.size_shares` rules as live
  (MAX_POSITION_PCT, cash-only). Multi-symbol portfolios use
  `run_portfolio_backtest` (MAX_POSITIONS + lowest-RSI entry priority). Single-
  symbol `run_backtest` still sizes each entry at ≤ MAX_POSITION_PCT.

## Risk layer (see risk.py)

- Daily loss ≥ 2% of start-of-day equity → flatten everything, stand down for
  the day.
- Equity ≥ 10% below its peak → flatten, hard halt; requires `reset-halt`
  after a human reviews the journal.
- Same-day duplicate runs blocked.

## How to not fool yourself (read before changing any parameter)

1. **One change at a time**, and decide the evaluation *before* looking.
2. **Beware the parameter garden.** If you try 20 variants and pick the best
   backtest, you've mostly selected luck. Prefer parameters that are stable:
   entry at RSI 5/10/15 should all be decent, not one great and two terrible.
3. **Split your data.** Tune on 2010–2018, confirm on 2019–present. Prompt B4
   in CURSOR_PROMPTS.md builds this.
4. **Include the bad years.** Any test that skips 2020 and 2022 is fiction.
5. **Judge on drawdown and consistency, not CAGR.** You will actually have to
   sit through the drawdown; you only get the CAGR if you don't quit.
6. **Paper results trump backtests.** 60–90 days of live paper trading is the
   only test that includes real fills, real data quirks, and real you.

## Market data (hosted path)

Daily bars come from **Alpaca's market data API** (same account as the broker).
For historical queries with `end` more than 15 minutes ago, the consolidated
**SIP** feed is available on the free Basic plan — better than scraping Yahoo
Finance and reliable from cloud servers. Live hosted runs use this path after
Part B (CURSOR_PROMPTS.md). Local dev may still use yfinance until migration.
Backtest and live must call the same `fetch_daily()` so signals stay aligned.

## Parameters live in config.py

`RSI2`: entry_rsi=10, trend_sma=200, exit_sma=5, exit_rsi=65, max_hold_days=10.
`TREND`: trend_sma=200. Change them there, re-backtest, journal why.
