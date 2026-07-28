# Phase 2 promotion report

Generated: **2026-07-27 22:52 EDT**

Feed: Alpaca SIP when available. Intraday rows may use fixtures in CI.
Reject is success — the gate exists to kill thin edges before paper.

| Strategy | Verdict | Trades (OOS) | 2× cost net % | Notes |
|----------|---------|--------------|---------------|-------|
| overnight | REJECT — failed: cost_stress_2x | 120 | -0.5 | fixture (fetch failed: Missing ALPACA_API_KEY_ID / ALPACA_AP |
| orb15 | REJECT — failed: data_years, sample_size, cost_stress_2x, param_stability | 45 | -1.0 | Minute SIP history limited in CI — run locally with data/min |
| vwap_z | REJECT — failed: data_years, sample_size, cost_stress_2x, param_stability | 45 | -1.0 | Minute SIP history limited in CI — run locally with data/min |

## Recommendations

- **overnight:** expect cost-stress failure; useful to calibrate slippage model.
- **orb15 / vwap_z:** download minute SIP cache locally, re-run backtests, then gatecheck.
- Do not enable intraday `--submit` until Stage A passes on honest minute history.
- Swing `ACTIVE_STRATEGY` remains `rsi2`; rsi2_tight is lab-only (see content/REPORT.md).


(Full report in results/ — gitignored.)
