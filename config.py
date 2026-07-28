"""
Central configuration. Every tunable number lives here.

RULE: If you change a strategy parameter, re-run the backtest BEFORE the next
live (paper) session. Never tune parameters based on a handful of live trades.
"""

# ---------------------------------------------------------------------------
# SAFETY MASTER SWITCH
# ---------------------------------------------------------------------------
# This project is paper-trading only. main.py refuses to start if this is not
# True, and broker.py connects with paper=True unconditionally.
# Going live one day is a deliberate, manual, multi-step decision (see README
# "Go-live checklist") -- not a config flip.
PAPER_TRADING = True

# ---------------------------------------------------------------------------
# UNIVERSE
# ---------------------------------------------------------------------------
# Liquid, broad ETFs only. Single stocks add idiosyncratic risk (earnings
# gaps, halts) that this simple system does not handle.
SYMBOLS = ["SPY", "QQQ"]
BENCHMARK = "SPY"

# Which strategy generates signals for live/paper trading: "rsi2" or "trend"
ACTIVE_STRATEGY = "rsi2"

# ---------------------------------------------------------------------------
# STRATEGY PARAMETERS (see STRATEGY.md for what these mean and why)
# ---------------------------------------------------------------------------
RSI2 = {
    "rsi_period": 2,
    "entry_rsi": 10.0,      # buy signal: RSI(2) closes below this...
    "trend_sma": 200,       # ...while close is above the 200-day SMA
    "exit_sma": 5,          # sell signal: close crosses above the 5-day SMA
    "exit_rsi": 65.0,       # or RSI(2) closes above this
    "max_hold_days": 10,    # time stop: exit after this many bars regardless
}

# Lab variant (E1): stricter entry + shorter hold — NOT active live strategy.
RSI2_TIGHT = {
    "rsi_period": 2,
    "entry_rsi": 5.0,
    "trend_sma": 200,
    "exit_sma": 5,
    "exit_rsi": 65.0,
    "max_hold_days": 5,
}

TREND = {
    "trend_sma": 200,       # month-end close above 200-day SMA -> hold, else cash
}

# ---------------------------------------------------------------------------
# RISK LIMITS (enforced in risk.py -- treat these as load-bearing walls)
# ---------------------------------------------------------------------------
MAX_POSITIONS = 2            # max simultaneous positions
MAX_POSITION_PCT = 0.50      # max fraction of equity in any one position
MAX_DAILY_LOSS_PCT = 0.02    # lose >2% of equity in a day -> flatten + halt for the day
MAX_DRAWDOWN_HALT_PCT = 0.10 # equity 10% below its peak -> flatten + halt until manual reset
ALLOW_SHORTING = False       # long-only. Do not change without a tested strategy.
ALLOW_MARGIN = False         # cash account behavior: never buy more than cash on hand

# ---------------------------------------------------------------------------
# DATA FRESHNESS (hosted run abort)
# ---------------------------------------------------------------------------
# If the latest daily bar is older than this many *calendar* days vs the
# trading day, skip the run (journal + ERROR notify). Covers long weekends
# (Fri→Mon = 3) with margin for holidays / API glitches — not for tuning edge.
MAX_BAR_STALE_DAYS = 5

# ---------------------------------------------------------------------------
# BACKTEST ASSUMPTIONS
# ---------------------------------------------------------------------------
BACKTEST_INITIAL_CASH = 5_000.0
BACKTEST_YEARS = 15
SLIPPAGE_BPS = 5             # 0.05% per side; commissions assumed $0 (Alpaca)

# ---------------------------------------------------------------------------
# PROMOTION GATE (Phase 2 — frozen in gates.md; gatecheck.py reads these)
# ---------------------------------------------------------------------------
GATE_STAGE_A = {
    "min_years_data": 5,
    "min_trades_intraday": 300,
    "min_trades_swing": 100,
    "oos_train_frac": 0.60,
    "oos_min_net_return": 0.0,
    "oos_min_profit_factor": 1.2,
    "oos_max_drawdown_pct": 15.0,
    "cost_stress_multipliers": [2.0, 3.0],
    "param_perturb_pct": 0.33,
    "param_stability_min_profitable_frac": 0.5,
    "max_daily_halt_days_pct": 5.0,
    "intraday_slippage_bps": 5,
    "intraday_half_spread_bps": 2,
}

GATE_STAGE_B = {
    "min_trading_days": 60,
    "min_trades": 40,
    "max_manual_overrides": 0,
}

# ---------------------------------------------------------------------------
# FILES
# ---------------------------------------------------------------------------
STATE_FILE = "state.json"     # peak equity, halt flag, last run date
JOURNAL_FILE = "journal.csv"  # every decision the bot makes, with reasons
RESULTS_DIR = "results"       # backtest outputs
