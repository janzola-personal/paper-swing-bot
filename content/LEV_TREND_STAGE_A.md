# Leveraged trend Stage A

Research run: Faber month-end trend on QLD (2×) and TQQQ (3×).
Initial cash (research sizing): $20,000. Daily-loss halt modeled at 2%.
Intended sizing: single position, 100% of allocation.

| symbol | full CAGR % | full MaxDD % | OOS net % | OOS trades | 2× cost % | halt days % | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QLD | 12.84 | -31.1 | 77.2 | 3 | 76.8 | 5.33 | FAIL |
| TQQQ | 16.06 | -45.0 | 89.3 | 3 | 88.9 | 9.34 | FAIL |

## Failures (both)

- **sample_size:** monthly trend produces ~1–2 trades/year — far below the 100 OOS-trade swing gate.
- **oos_max_drawdown:** leveraged products exceed the 15% Stage A MaxDD cap (QLD 18.9%, TQQQ 32.7%).
- **halt_compatibility:** at full sizing, daily-loss halt trips on >5% of days (QLD 5.3%, TQQQ 9.3%).

## Selection

QLD is closer to the gate (lower MaxDD / halt rate). Engine config uses **QLD**,
`BOT_SUBMIT_LEV_TREND=false`, shadow default **true**. Infrastructure ships;
paper submit stays off until a future Stage A pass (or an owner-approved gate
threshold change typed explicitly in chat).

Signal semantics unchanged: month-end decision on close → fill next open.
