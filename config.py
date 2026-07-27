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
# BACKTEST ASSUMPTIONS
# ---------------------------------------------------------------------------
BACKTEST_INITIAL_CASH = 5_000.0
BACKTEST_YEARS = 15
SLIPPAGE_BPS = 5             # 0.05% per side; commissions assumed $0 (Alpaca)

# ---------------------------------------------------------------------------
# FILES
# ---------------------------------------------------------------------------
STATE_FILE = "state.json"     # peak equity, halt flag, last run date
JOURNAL_FILE = "journal.csv"  # every decision the bot makes, with reasons
RESULTS_DIR = "results"       # backtest outputs
