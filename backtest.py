"""
Daily-bar backtester. Deliberately simple and transparent so you can read every
assumption.

Execution model (matches the live loop):
  - Signal computed on bar t's CLOSE.
  - Trade executed at bar t+1's OPEN, +/- slippage.
  - Long-only, whole shares, cash-limited, no margin.
  - Position sizing uses risk.size_shares (MAX_POSITION_PCT + cash), same as live.

Usage:
  python backtest.py                          # all config.SYMBOLS, both strategies
  python backtest.py --symbols SPY --strategy rsi2
"""

import argparse
import os

import numpy as np
import pandas as pd

import config
import risk
from data import fetch_daily
from strategy import STRATEGIES


def run_backtest(df: pd.DataFrame, pos: pd.Series, initial_cash: float,
                 slippage_bps: float) -> dict:
    """Single-symbol backtest with live-matching position sizing."""
    slip = slippage_bps / 10_000.0
    open_, close = df["open"], df["close"]

    cash, shares = initial_cash, 0
    prev_target = 0
    entry_px = 0.0
    equity_rows, trades = [], []

    for t in range(1, len(df)):
        target = int(pos.iloc[t - 1])          # decided on yesterday's close
        px = float(open_.iloc[t])              # executed at today's open
        if target != prev_target:
            if target == 1 and shares == 0:
                fill = px * (1 + slip)
                # Mark equity before the buy; size_shares matches main.py / live.
                equity = cash
                qty = risk.size_shares(fill, equity, cash)
                if qty > 0:
                    cash -= qty * fill
                    shares = qty
                    entry_px = fill
            elif target == 0 and shares > 0:
                fill = px * (1 - slip)
                cash += shares * fill
                trades.append({"exit_date": df.index[t], "pnl_pct": fill / entry_px - 1.0})
                shares = 0
            prev_target = target
        equity_rows.append((df.index[t], cash + shares * float(close.iloc[t])))

    equity = pd.Series(dict(equity_rows), name="equity")
    return _stats(equity, pos, trades, initial_cash)


def run_portfolio_backtest(
    frames: dict[str, pd.DataFrame],
    positions: dict[str, pd.Series],
    initial_cash: float,
    slippage_bps: float,
) -> dict:
    """Multi-symbol backtest mirroring main.py (MAX_POSITIONS + size_shares).

    frames/positions keyed by symbol; dates aligned on intersection of indexes.
    Signal on bar t-1 close → fill at bar t open; no look-ahead.
    """
    slip = slippage_bps / 10_000.0
    symbols = list(frames.keys())
    common = frames[symbols[0]].index
    for sym in symbols[1:]:
        common = common.intersection(frames[sym].index)
    common = common.sort_values()
    if len(common) < 2:
        return {"error": "not enough overlapping data"}

    cash = initial_cash
    held: dict[str, int] = {s: 0 for s in symbols}
    entry_px: dict[str, float] = {}
    trades: list = []
    equity_rows = []

    for i in range(1, len(common)):
        day = common[i]
        prev = common[i - 1]
        # Mark-to-market equity at today's open (pre-trade).
        equity = cash
        for s in symbols:
            if held[s] > 0:
                equity += held[s] * float(frames[s].loc[day, "open"])

        # Desired book from yesterday's close signals.
        wants: list[tuple[str, int, float]] = []
        for s in symbols:
            want = int(positions[s].loc[prev])
            from data import rsi as _rsi
            r = float(_rsi(frames[s].loc[:prev, "close"], 2).iloc[-1])
            if np.isnan(r):
                r = 100.0
            wants.append((s, want, r))

        # Sells first.
        for s, want, _ in wants:
            if want == 0 and held[s] > 0:
                px = float(frames[s].loc[day, "open"]) * (1 - slip)
                cash += held[s] * px
                trades.append({"symbol": s, "exit_date": day, "pnl_pct": px / entry_px[s] - 1.0})
                held[s] = 0

        equity = cash + sum(
            held[s] * float(frames[s].loc[day, "open"]) for s in symbols if held[s] > 0
        )

        entries = [(s, w, r) for s, w, r in wants if w == 1 and held[s] == 0]
        entries.sort(key=lambda x: x[2])
        room = max(config.MAX_POSITIONS - sum(1 for s in symbols if held[s] > 0), 0)
        for s, _w, _r in entries[:room]:
            px = float(frames[s].loc[day, "open"]) * (1 + slip)
            qty = risk.size_shares(px, equity, cash)
            if qty <= 0:
                continue
            cash -= qty * px
            held[s] = qty
            entry_px[s] = px
            equity = cash + sum(
                held[x] * float(frames[x].loc[day, "open"]) for x in symbols if held[x] > 0
            )

        mtm = cash + sum(
            held[s] * float(frames[s].loc[day, "close"]) for s in symbols if held[s] > 0
        )
        equity_rows.append((day, mtm))

    eq = pd.Series(dict(equity_rows), name="equity")
    pos_mean = float(np.mean([positions[s].reindex(common).fillna(0).mean() for s in symbols]))
    return _stats(eq, pd.Series(pos_mean, index=common), trades, initial_cash)


def initial_cash_cap(cash: float, equity: float | None = None) -> float:
    """Budget for one new position: min(cash, MAX_POSITION_PCT * equity)."""
    eq = cash if equity is None else equity
    return min(cash, eq * config.MAX_POSITION_PCT)


def _stats(equity: pd.Series, pos: pd.Series, trades: list, initial: float) -> dict:
    if len(equity) < 2:
        return {"error": "not enough data"}
    total = equity.iloc[-1] / initial - 1.0
    years = len(equity) / 252.0
    cagr = (equity.iloc[-1] / initial) ** (1 / years) - 1.0 if years > 0 else np.nan
    dd = equity / equity.cummax() - 1.0
    daily_ret = equity.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else np.nan
    wins = [t for t in trades if t["pnl_pct"] > 0]
    return {
        "final_equity": round(float(equity.iloc[-1]), 2),
        "total_return_pct": round(100 * total, 1),
        "cagr_pct": round(100 * cagr, 2),
        "max_drawdown_pct": round(100 * float(dd.min()), 1),
        "sharpe": round(float(sharpe), 2),
        "exposure_pct": round(100 * float(pos.mean()), 1),
        "num_trades": len(trades),
        "win_rate_pct": round(100 * len(wins) / len(trades), 1) if trades else np.nan,
        "avg_trade_pct": round(100 * float(np.mean([t["pnl_pct"] for t in trades])), 2) if trades else np.nan,
        "equity_curve": equity,
    }


def buy_and_hold(df: pd.DataFrame, initial_cash: float, slippage_bps: float) -> dict:
    pos = pd.Series(1, index=df.index)
    return run_backtest(df, pos, initial_cash, slippage_bps)


def print_report(title: str, stats: dict) -> None:
    keys = ["final_equity", "total_return_pct", "cagr_pct", "max_drawdown_pct",
            "sharpe", "exposure_pct", "num_trades", "win_rate_pct", "avg_trade_pct"]
    print(f"\n=== {title} ===")
    for k in keys:
        if k in stats and stats[k] == stats[k]:  # skip NaN
            print(f"  {k:18s} {stats[k]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=config.SYMBOLS)
    parser.add_argument("--strategy", choices=[*STRATEGIES, "both"], default="both")
    parser.add_argument("--years", type=int, default=config.BACKTEST_YEARS)
    args = parser.parse_args()

    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    names = list(STRATEGIES) if args.strategy == "both" else [args.strategy]

    for symbol in args.symbols:
        df = fetch_daily(symbol, years=args.years)
        span = f"{df.index[0].date()} -> {df.index[-1].date()}"
        print(f"\n############ {symbol}  ({span}, {len(df)} bars) ############")
        for name in names:
            pos = STRATEGIES[name](df)
            stats = run_backtest(df, pos, config.BACKTEST_INITIAL_CASH, config.SLIPPAGE_BPS)
            print_report(f"{symbol} / {name}", stats)
            stats["equity_curve"].to_csv(
                os.path.join(config.RESULTS_DIR, f"equity_{symbol}_{name}.csv")
            )
        bh = buy_and_hold(df, config.BACKTEST_INITIAL_CASH, config.SLIPPAGE_BPS)
        print_report(f"{symbol} / buy & hold", bh)

    print(
        "\nRead these numbers with suspicion: past performance, survivorship of "
        "published strategies, and parameter choices all flatter backtests. "
        "See STRATEGY.md -> 'How to not fool yourself'."
    )


if __name__ == "__main__":
    main()
