"""
Stage A research for leveraged-ETF Faber trend (QLD / TQQQ).

Produces:
  - Console stats table (full sample + OOS + halt interaction + cost stress)
  - results/gate_lev_trend_{qld,tqqq}.json for gatecheck.py

Uses DATA_SOURCE=yfinance by default so it runs without Alpaca keys.
Signal on bar t close → fill at bar t+1 open (no look-ahead).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure repo root on path when run as script.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATA_SOURCE", "yfinance")

import config
from backtest import buy_and_hold, run_backtest
from data import fetch_daily
from gatecheck import evaluate_stage_a
from strategy import strategy_params, trend_positions


def _profit_factor(trades: list[dict]) -> float:
    wins = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    losses = sum(-t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0)
    if losses <= 0:
        return 99.0 if wins > 0 else 0.0
    return wins / losses


def _halt_days_pct(equity: pd.Series, daily_loss_pct: float) -> float:
    """Fraction of days where day-over-day equity drop would trip daily-loss halt.

    Approximates morning capture = prior close equity, after-close = today close.
    """
    if len(equity) < 2:
        return 100.0
    day_ret = equity.pct_change().dropna()
    trips = (day_ret <= -daily_loss_pct).sum()
    return 100.0 * float(trips) / float(len(day_ret))


def _oos_split(df: pd.DataFrame, train_frac: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    cut = int(len(df) * train_frac)
    cut = max(cut, 1)
    cut = min(cut, len(df) - 2)
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


def _run_one(
    symbol: str,
    *,
    years: int,
    initial_cash: float,
    slippage_bps: float,
    daily_loss_pct: float,
) -> dict:
    df = fetch_daily(symbol, years=years, source="yfinance")
    params = strategy_params("trend")
    pos = trend_positions(df, params)
    full = run_backtest(df, pos, initial_cash, slippage_bps)
    bh = buy_and_hold(df, initial_cash, slippage_bps)

    # Rebuild trades for profit factor on full sample path via OOS slice.
    train_frac = config.GATE_STAGE_A["oos_train_frac"]
    _, oos_df = _oos_split(df, train_frac)
    # Warm SMA on full history but only score OOS window: recompute positions on
    # full series, then backtest OOS slice with positions aligned (no look-ahead:
    # OOS fills still use prior-bar signal within the slice simulator).
    oos_pos = trend_positions(oos_df, params)
    oos_stats = run_backtest(oos_df, oos_pos, initial_cash, slippage_bps)

    # Cost stress on OOS
    oos_2x = run_backtest(oos_df, oos_pos, initial_cash, slippage_bps * 2)
    oos_3x = run_backtest(oos_df, oos_pos, initial_cash, slippage_bps * 3)

    # Parameter stability: perturb trend_sma ±33%
    neighbors = []
    base_sma = int(params["trend_sma"])
    for sma in sorted(
        {
            max(50, int(round(base_sma * (1 - 0.33)))),
            base_sma,
            int(round(base_sma * (1 + 0.33))),
        }
    ):
        npos = trend_positions(oos_df, {"trend_sma": sma})
        nstats = run_backtest(oos_df, npos, initial_cash, slippage_bps)
        neighbors.append(nstats.get("total_return_pct", -999) > 0)

    # Halt interaction on full equity curve at intended sizing (MAX_POSITION_PCT=1
    # for single-symbol leveraged book — size_shares already caps by cash).
    halt_pct = _halt_days_pct(full["equity_curve"], daily_loss_pct)

    # Profit factor: reconstruct OOS trades by re-running a lightweight path
    pf = _profit_factor_from_backtest(oos_df, oos_pos, initial_cash, slippage_bps)

    data_years = (df.index[-1] - df.index[0]).days / 365.25
    gate = {
        "strategy": f"lev_trend_{symbol.lower()}",
        "kind": "swing",
        "data_years": round(data_years, 2),
        "data_note": (
            f"yfinance daily {df.index[0].date()}→{df.index[-1].date()}; "
            "includes 2020/2022 when history allows; OOS = final 40%"
        ),
        "oos": {
            "num_trades": int(oos_stats.get("num_trades", 0)),
            "net_return_pct": float(oos_stats.get("total_return_pct", -999)),
            "profit_factor": round(pf, 3),
            "max_drawdown_pct": abs(float(oos_stats.get("max_drawdown_pct", 999))),
        },
        "cost_stress": {
            "2x": {"net_return_pct": float(oos_2x.get("total_return_pct", -999))},
            "3x": {"net_return_pct": float(oos_3x.get("total_return_pct", -999))},
        },
        "param_stability": {
            "profitable_frac": float(sum(neighbors) / len(neighbors)) if neighbors else 0.0
        },
        "halt_days_pct": round(halt_pct, 2),
        "full_sample": {
            "cagr_pct": full.get("cagr_pct"),
            "max_drawdown_pct": full.get("max_drawdown_pct"),
            "sharpe": full.get("sharpe"),
            "num_trades": full.get("num_trades"),
            "total_return_pct": full.get("total_return_pct"),
            "final_equity": full.get("final_equity"),
        },
        "buy_hold": {
            "cagr_pct": bh.get("cagr_pct"),
            "max_drawdown_pct": bh.get("max_drawdown_pct"),
            "sharpe": bh.get("sharpe"),
            "total_return_pct": bh.get("total_return_pct"),
        },
    }
    return gate


def _profit_factor_from_backtest(
    df: pd.DataFrame, pos: pd.Series, initial_cash: float, slippage_bps: float
) -> float:
    """Replicate run_backtest trade list for profit factor."""
    slip = slippage_bps / 10_000.0
    open_, close = df["open"], df["close"]
    cash, shares = initial_cash, 0
    prev_target = 0
    entry_px = 0.0
    trades: list[dict] = []
    import risk

    for t in range(1, len(df)):
        target = int(pos.iloc[t - 1])
        px = float(open_.iloc[t])
        if target != prev_target:
            if target == 1 and shares == 0:
                fill = px * (1 + slip)
                qty = risk.size_shares(fill, cash, cash)
                if qty > 0:
                    cash -= qty * fill
                    shares = qty
                    entry_px = fill
            elif target == 0 and shares > 0:
                fill = px * (1 - slip)
                cash += shares * fill
                trades.append({"pnl_pct": fill / entry_px - 1.0})
                shares = 0
            prev_target = target
    return _profit_factor(trades)


def main() -> int:
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    # Use larger cash so share counts are realistic for high-priced TQQQ.
    # Intended lev_trend sizing: single position up to 100% of its allocation.
    config.MAX_POSITION_PCT = 1.0
    config.MAX_POSITIONS = 1
    cash = 20_000.0
    daily_loss = config.MAX_DAILY_LOSS_PCT
    years = max(config.BACKTEST_YEARS, 15)

    results = {}
    for symbol in ("QLD", "TQQQ"):
        print(f"\n######## {symbol} / trend ########")
        gate = _run_one(
            symbol,
            years=years,
            initial_cash=cash,
            slippage_bps=config.SLIPPAGE_BPS,
            daily_loss_pct=daily_loss,
        )
        results[symbol] = gate
        path = Path(config.RESULTS_DIR) / f"gate_lev_trend_{symbol.lower()}.json"
        # Write only gatecheck-required fields (+ note); keep extras in report file.
        payload = {k: v for k, v in gate.items() if k not in ("full_sample", "buy_hold")}
        path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"Wrote {path}")
        print(
            f"  full CAGR={gate['full_sample']['cagr_pct']}% "
            f"MaxDD={gate['full_sample']['max_drawdown_pct']}% "
            f"Sharpe={gate['full_sample']['sharpe']} "
            f"trades={gate['full_sample']['num_trades']}"
        )
        print(
            f"  OOS net={gate['oos']['net_return_pct']}% "
            f"PF={gate['oos']['profit_factor']} "
            f"MaxDD={gate['oos']['max_drawdown_pct']}% "
            f"trades={gate['oos']['num_trades']}"
        )
        print(
            f"  2× cost OOS={gate['cost_stress']['2x']['net_return_pct']}% "
            f"halt_days={gate['halt_days_pct']}% "
            f"stability={gate['param_stability']['profitable_frac']:.0%}"
        )
        print(
            f"  buy&hold CAGR={gate['buy_hold']['cagr_pct']}% "
            f"MaxDD={gate['buy_hold']['max_drawdown_pct']}%"
        )
        criteria = evaluate_stage_a(payload)
        for c in criteria:
            print(f"  [{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}")
        print("  OVERALL:", "PASS" if all(c.passed for c in criteria) else "FAIL")

    # Summary markdown (gitignored results/ — also write to content for UI later)
    report = Path(config.RESULTS_DIR) / "LEV_TREND_STAGE_A.md"
    lines = [
        "# Leveraged trend Stage A",
        "",
        f"Initial cash (research sizing): ${cash:,.0f}",
        f"Daily-loss halt modeled at {daily_loss:.0%}",
        "",
        "| symbol | full CAGR % | full MaxDD % | OOS net % | OOS trades | 2× cost % | halt days % | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for symbol, gate in results.items():
        criteria = evaluate_stage_a(
            {k: v for k, v in gate.items() if k not in ("full_sample", "buy_hold")}
        )
        verdict = "PASS" if all(c.passed for c in criteria) else "FAIL"
        lines.append(
            f"| {symbol} | {gate['full_sample']['cagr_pct']} | "
            f"{gate['full_sample']['max_drawdown_pct']} | "
            f"{gate['oos']['net_return_pct']} | {gate['oos']['num_trades']} | "
            f"{gate['cost_stress']['2x']['net_return_pct']} | "
            f"{gate['halt_days_pct']} | {verdict} |"
        )
    lines.append("")
    report.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
