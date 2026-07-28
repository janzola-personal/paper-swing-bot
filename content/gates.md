# Promotion gates (FROZEN — 2026-07-28)

Canonical thresholds live in repo-root [`gates.md`](../gates.md) and
`config.GATE_STAGE_A` / `config.GATE_STAGE_B`. Run research results through
[`gatecheck.py`](../gatecheck.py) (CLI only — pass a JSON results path).

## Stage A — Backtest (all required)

| Criterion | Intraday | Swing/overnight |
|-----------|----------|-----------------|
| Data years | ≥5 (note gaps) | ≥5 daily |
| Min trades | 300 | 100 |
| OOS split | last 40% | last 40% |
| OOS net return | > 0 | > 0 |
| OOS profit factor | ≥ 1.2 | ≥ 1.2 |
| OOS max drawdown | ≤ 15% | ≤ 15% |
| Cost stress 2× | net > 0 | net > 0 |
| Param stability | ≥50% neighbors profitable | same |
| Halt days | ≤ 5% of days | ≤ 5% |

## Stage B — Paper

- 60 trading days, 40 completed trades, 0 manual overrides.
- Paper vs backtest OOS consistency + fill-quality audit.

Dashboard `/gate` reads `gate_results` when populated (future).
