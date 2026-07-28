# Promotion gates (FROZEN — 2026-07-28)

Edit thresholds only **before** testing a strategy, never after seeing results.
`gatecheck.py` reads numeric defaults from `config.GATE_STAGE_A` /
`config.GATE_STAGE_B`; this file is the human contract.

## Stages

| Stage | Meaning |
|-------|---------|
| BENCH | Research / backtest only |
| BACKTEST-PASS | Stage A (all criteria) |
| PAPER | Hosted paper submit, Stage B |
| LIVE-ELIGIBLE | Stage B cleared — still not a live flip |

## Stage A — Backtest pass (all required)

- **Data:** ≥5 years minute history including 2020 and 2022 when the feed allows;
  otherwise maximum available with gap stated in the report.
- **Sample size:** ≥300 trades (intraday) / ≥100 (swing/overnight).
- **Out-of-sample:** parameters frozen on first 60% of data; pass/fail on final 40%.
- **After-cost OOS:** net return > 0, profit factor ≥ 1.2, max drawdown ≤ 15%.
- **Cost stress:** still net-positive OOS at **2×** baseline costs (record 3× too).
  Baseline intraday: 5 bps slippage/side + half spread; market orders.
- **Parameter stability:** perturb each key parameter ±33%; majority profitable OOS.
- **Halt compatibility:** ≤5% of backtest days would trip the 2% daily-loss halt.

## Stage B — Paper pass

- ≥60 trading days **and** ≥40 completed paper trades (`dry_run=false`).
- Zero manual overrides of entries, exits, or halts.
- Paper net directionally consistent with backtest OOS (not just “up”).
- Fill-quality audit: if measured slippage > model, re-run Stage A with measured costs.

## Demotion

- Hard halt → BENCH pending review.
- Rolling 30-trade net loss worse than backtest worst comparable stretch → demote.

See [PHASE2_INTRADAY.md](PHASE2_INTRADAY.md) §1 for rationale.
