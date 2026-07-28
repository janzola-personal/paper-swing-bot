# Backtest report

Generated: **2026-07-27 20:44 EDT**

## Setup (defaults unchanged)

- Initial cash: `$5,000`
- Slippage: `5 bps` per side; commissions $0
- Sizing: `risk.size_shares` — max `50%` of equity, cash-only
- Universe: `SPY, QQQ`; active live strategy in config: `rsi2`
- Data: Alpaca SIP daily via `fetch_daily` (`adjustment=all`), ~15y
- Sample: **2016-01-04 → 2026-07-27**
- RSI2 defaults: `{'rsi_period': 2, 'entry_rsi': 10.0, 'trend_sma': 200, 'exit_sma': 5, 'exit_rsi': 65.0, 'max_hold_days': 10}`
- TREND defaults: `{'trend_sma': 200}`
- Execution: signal on bar *t* close → fill at bar *t+1* open (no look-ahead)

## Full-sample stats

| run | CAGR % | Max DD % | Sharpe | Total ret % | Trades | Win % | Exposure % | Final $ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SPY/rsi2 | 0.92 | -7.80 | 0.34 | 10.10 | 84 | 65.50 | 10.60 | 5,503.60 |
| SPY/trend | 4.01 | -13.60 | 0.67 | 51.40 | 10 | 60.00 | 76.30 | 7,567.97 |
| SPY/buy_hold | 9.45 | -21.10 | 0.86 | 158.90 | 0 | — | 100.00 | 12,946.04 |
| QQQ/rsi2 | 1.34 | -5.30 | 0.39 | 15.10 | 82 | 70.70 | 11.00 | 5,754.40 |
| QQQ/trend | 8.48 | -16.10 | 0.90 | 135.80 | 5 | 100.00 | 76.50 | 11,788.37 |
| QQQ/buy_hold | 13.47 | -27.50 | 0.88 | 278.50 | 0 | — | 100.00 | 18,926.94 |
| PORTFOLIO/rsi2 | 2.29 | -12.70 | 0.41 | 26.90 | 166 | 68.10 | 10.80 | 6,343.73 |
| PORTFOLIO/trend | 11.92 | -20.60 | 0.89 | 227.50 | 15 | 73.30 | 76.40 | 16,376.65 |

## Lab variant: rsi2_tight (E1 — not live)

`rsi2_tight` uses stricter entry (`entry_rsi=5`) and shorter hold (`max_hold_days=5`).
Re-run `python build_report.py` to populate SPY/QQQ/PORTFOLIO rows for `rsi2_tight`.
**Recommendation:** keep `ACTIVE_STRATEGY='rsi2'` unless tight clearly wins on
drawdown-adjusted OOS terms after costs.

## Equity curves

![equity_SPY.png](equity_SPY.png)

![equity_QQQ.png](equity_QQQ.png)

![equity_PORTFOLIO.png](equity_PORTFOLIO.png)

Normalized to 100 at the first equity point of each series.

## Out-of-sample split

Per STRATEGY.md: in-sample **before 2019-01-01**, out-of-sample **on/after 2019-01-01**. Each window is backtested on its own slice (SMA warm-up consumes early bars inside the window — see limitations).

| symbol | strategy | window | CAGR % | Max DD % | Sharpe | Trades | span |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | rsi2 | IS(<2019) | -1.11 | -6.00 | -0.41 | 17 | 2016-01-04→2018-12-31 |
| SPY | trend | IS(<2019) | 3.08 | -11.30 | 0.60 | 1 | 2016-01-04→2018-12-31 |
| SPY | buy_hold | IS(<2019) | 4.67 | -11.30 | 0.70 | 0 | 2016-01-04→2018-12-31 |
| SPY | rsi2 | OOS(≥2019) | 1.66 | -4.00 | 0.65 | 60 | 2019-01-02→2026-07-27 |
| SPY | trend | OOS(≥2019) | 4.13 | -14.00 | 0.70 | 7 | 2019-01-02→2026-07-27 |
| SPY | buy_hold | OOS(≥2019) | 10.60 | -19.30 | 0.94 | 0 | 2019-01-02→2026-07-27 |
| QQQ | rsi2 | IS(<2019) | 0.58 | -4.10 | 0.18 | 20 | 2016-01-04→2018-12-31 |
| QQQ | trend | IS(<2019) | 7.14 | -7.50 | 1.00 | 1 | 2016-01-04→2018-12-31 |
| QQQ | buy_hold | IS(<2019) | 6.76 | -14.20 | 0.74 | 0 | 2016-01-04→2018-12-31 |
| QQQ | rsi2 | OOS(≥2019) | 1.76 | -4.00 | 0.54 | 56 | 2019-01-02→2026-07-27 |
| QQQ | trend | OOS(≥2019) | 8.12 | -15.40 | 0.83 | 4 | 2019-01-02→2026-07-27 |
| QQQ | buy_hold | OOS(≥2019) | 14.77 | -25.40 | 0.95 | 0 | 2019-01-02→2026-07-27 |

## RSI2 stability grid (SPY, full sample)

Vary `entry_rsi` ∈ {5,10,15} and `exit_rsi` ∈ {55,65,75}. **Do not pick the best cell for live trading** — that is classic overfitting. Prefer a neighborhood where nearby cells are also acceptable (STRATEGY.md).

| entry_rsi | exit_rsi | CAGR % | Max DD % | Sharpe | Trades | note |
| --- | --- | --- | --- | --- | --- | --- |
| 5.00 | 55.00 | 0.89 | -4.40 | 0.42 | 47 |  |
| 5.00 | 65.00 | 0.93 | -5.00 | 0.42 | 47 |  |
| 5.00 | 75.00 | 0.93 | -5.00 | 0.42 | 47 |  |
| 10.00 | 55.00 | 0.94 | -7.40 | 0.37 | 85 |  |
| 10.00 | 65.00 | 0.92 | -7.80 | 0.34 | 84 | ← default |
| 10.00 | 75.00 | 0.92 | -7.80 | 0.34 | 84 |  |
| 15.00 | 55.00 | 1.68 | -4.50 | 0.56 | 121 |  |
| 15.00 | 65.00 | 1.93 | -3.80 | 0.62 | 120 |  |
| 15.00 | 75.00 | 1.93 | -3.80 | 0.62 | 120 |  |

## Limitations (read before believing any number)

1. **Past ≠ future.** Published mean-reversion edges decay; ETFs change.
2. **Parameter garden.** The grid will show a best cell — that is mostly selection bias if you promote it.
3. **Slippage model is flat (5 bps).** Real open fills, gaps, and stress days differ.
4. **No borrow, no corporate-action drama beyond Alpaca `adjustment=all`.**
5. **OOS warm-up:** slicing the series resets SMA/RSI history at the cut — OOS CAGR is slightly disadvantaged vs a continuous book.
6. **Survivorship:** SPY/QQQ are survivors; the test does not include delisted junk.
7. **Risk halts (daily loss / drawdown) are not simulated in this backtest** — live paper can halt when the sim would not.
8. **Paper fills still beat this report.** 60–90 days of submitted paper is the real exam.

---

## Metric definitions

- **CAGR (compound annual growth rate):** `(final_equity / initial_cash) ^ (1 / years) - 1`, with `years = n_bars / 252`. Smooths path dependency into one number — easy to worship, easy to quit before you earn it.
- **Max drawdown (Max DD):** largest peak-to-trough decline of the equity curve, `min(equity / equity.cummax() - 1)`. The pain you must sit through.
- **Sharpe:** annualized daily-return mean / daily-return std × √252 (risk-free rate treated as 0). Sensitive to quiet flat periods and to how returns are sampled.

*Report generated by `build_report.py`. Strategy defaults were not modified.*
