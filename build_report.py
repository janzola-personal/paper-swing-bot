"""
Build results/REPORT.md after a full backtest pass.

Does NOT change config strategy defaults. Reads Alpaca daily bars via
data.fetch_daily (same path as live). Outputs CSV equity curves, PNGs, and
an honest markdown report with OOS split + RSI2 stability grid.

Usage:
  python build_report.py
"""

from __future__ import annotations

import os
import shutil
from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd

import config
from backtest import buy_and_hold, run_backtest, run_portfolio_backtest
from data import fetch_daily
from strategy import STRATEGIES, rsi2_positions, strategy_params, trend_positions

ET = ZoneInfo("America/New_York")
OOS_SPLIT = date(2019, 1, 1)  # STRATEGY.md: tune pre-2019, confirm 2019+
GRID_ENTRY = [5.0, 10.0, 15.0]
GRID_EXIT_RSI = [55.0, 65.0, 75.0]
# Next.js serves public/ at site root — PNGs for /research markdown on Vercel.
PUBLIC_EQUITY_DIR = os.path.join("public", "research", "equity")
WEB_EQUITY_PREFIX = "/research/equity"
CONTENT_REPORT = os.path.join("content", "REPORT.md")


def _stat_row(stats: dict) -> dict:
    keys = [
        "final_equity",
        "total_return_pct",
        "cagr_pct",
        "max_drawdown_pct",
        "sharpe",
        "exposure_pct",
        "num_trades",
        "win_rate_pct",
        "avg_trade_pct",
    ]
    return {k: stats.get(k) for k in keys}


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or v != v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}" if abs(v) < 1000 else f"{v:,.2f}"
    return str(v)


def _slice_frame(df: pd.DataFrame, start: date | None, end: date | None) -> pd.DataFrame:
    out = df
    if start is not None:
        out = out[out.index.date >= start]
    if end is not None:
        out = out[out.index.date < end]
    return out


def _plot_equity(curves: dict[str, pd.Series], path: str, title: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for label, series in curves.items():
        if series is None or len(series) == 0:
            continue
        # Normalize to 100 for comparison
        norm = 100.0 * series / float(series.iloc[0])
        ax.plot(norm.index, norm.values, label=label, linewidth=1.2)
    ax.set_title(title)
    ax.set_ylabel("Growth of $100")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    os.makedirs(PUBLIC_EQUITY_DIR, exist_ok=True)
    years = config.BACKTEST_YEARS
    cash0 = config.BACKTEST_INITIAL_CASH
    slip = config.SLIPPAGE_BPS
    generated = datetime.now(ET).strftime("%Y-%m-%d %H:%M %Z")

    frames: dict[str, pd.DataFrame] = {}
    for sym in config.SYMBOLS:
        frames[sym] = fetch_daily(sym, years=years)
        print(f"fetched {sym}: {frames[sym].index[0].date()} → {frames[sym].index[-1].date()} ({len(frames[sym])} bars)")

    # ---- Full-sample single-symbol + B&H ---------------------------------
    full_stats: dict[str, dict] = {}
    equity_for_plot: dict[str, dict[str, pd.Series]] = {s: {} for s in config.SYMBOLS}

    for sym, df in frames.items():
        for name, fn in STRATEGIES.items():
            params = strategy_params(name)
            pos = fn(df, params)
            st = run_backtest(df, pos, cash0, slip)
            full_stats[f"{sym}/{name}"] = st
            st["equity_curve"].to_csv(os.path.join(config.RESULTS_DIR, f"equity_{sym}_{name}.csv"))
            equity_for_plot[sym][name] = st["equity_curve"]
            print(f"  {sym}/{name}: CAGR={st.get('cagr_pct')} MaxDD={st.get('max_drawdown_pct')} Sharpe={st.get('sharpe')}")
        bh = buy_and_hold(df, cash0, slip)
        full_stats[f"{sym}/buy_hold"] = bh
        bh["equity_curve"].to_csv(os.path.join(config.RESULTS_DIR, f"equity_{sym}_buy_hold.csv"))
        equity_for_plot[sym]["buy_hold"] = bh["equity_curve"]

    # Portfolio (live-matching sizing) for each strategy
    for name, fn in STRATEGIES.items():
        params = strategy_params(name)
        positions = {s: fn(frames[s], strategy_params(name)) for s in config.SYMBOLS}
        pst = run_portfolio_backtest(frames, positions, cash0, slip)
        full_stats[f"PORTFOLIO/{name}"] = pst
        if "equity_curve" in pst:
            pst["equity_curve"].to_csv(
                os.path.join(config.RESULTS_DIR, f"equity_PORTFOLIO_{name}.csv")
            )
        print(f"  PORTFOLIO/{name}: CAGR={pst.get('cagr_pct')} MaxDD={pst.get('max_drawdown_pct')}")

    # PNGs
    png_paths = []
    for sym in config.SYMBOLS:
        path = os.path.join(config.RESULTS_DIR, f"equity_{sym}.png")
        _plot_equity(
            {
                "rsi2": equity_for_plot[sym].get("rsi2"),
                "rsi2_tight": equity_for_plot[sym].get("rsi2_tight"),
                "trend": equity_for_plot[sym].get("trend"),
                "buy & hold": equity_for_plot[sym].get("buy_hold"),
            },
            path,
            f"{sym} equity (normalized) — sizing = risk.size_shares",
        )
        png_paths.append(path)

    port_curves = {}
    for name in STRATEGIES:
        key = f"PORTFOLIO/{name}"
        if key in full_stats and "equity_curve" in full_stats[key]:
            port_curves[name] = full_stats[key]["equity_curve"]
    if port_curves:
        path = os.path.join(config.RESULTS_DIR, "equity_PORTFOLIO.png")
        _plot_equity(port_curves, path, "Portfolio SPY+QQQ (live sizing rules)")
        png_paths.append(path)

    # ---- OOS split (IS < 2019-01-01, OOS >= 2019-01-01) ------------------
    oos_rows = []
    for sym, df in frames.items():
        is_df = _slice_frame(df, None, OOS_SPLIT)
        oos_df = _slice_frame(df, OOS_SPLIT, None)
        # Need SMA warm-up inside each window — use full history for indicators
        # but only score equity on the window (standard: compute signals on full
        # series, evaluate trades whose exit falls in window). Simpler honest
        # approach used here: run backtest on the sliced frame only (warm-up
        # NaNs reduce early signals — reported as limitation).
        for label, window in (("IS(<2019)", is_df), ("OOS(≥2019)", oos_df)):
            if len(window) < 220:
                oos_rows.append([sym, "rsi2", label, "insufficient bars", "—", "—", "—", "—"])
                continue
            for name, fn in STRATEGIES.items():
                params = strategy_params(name)
                st = run_backtest(window, fn(window, params), cash0, slip)
                oos_rows.append(
                    [
                        sym,
                        name,
                        label,
                        _fmt(st.get("cagr_pct")),
                        _fmt(st.get("max_drawdown_pct")),
                        _fmt(st.get("sharpe")),
                        _fmt(st.get("num_trades")),
                        f"{window.index[0].date()}→{window.index[-1].date()}",
                    ]
                )
            bh = buy_and_hold(window, cash0, slip)
            oos_rows.append(
                [
                    sym,
                    "buy_hold",
                    label,
                    _fmt(bh.get("cagr_pct")),
                    _fmt(bh.get("max_drawdown_pct")),
                    _fmt(bh.get("sharpe")),
                    _fmt(bh.get("num_trades")),
                    f"{window.index[0].date()}→{window.index[-1].date()}",
                ]
            )

    # ---- RSI2 stability grid (entry_rsi × exit_rsi) on SPY full sample ---
    grid_rows = []
    spy = frames[config.BENCHMARK]
    for entry in GRID_ENTRY:
        for exit_rsi in GRID_EXIT_RSI:
            params = deepcopy(config.RSI2)
            params["entry_rsi"] = entry
            params["exit_rsi"] = exit_rsi
            pos = rsi2_positions(spy, params)
            st = run_backtest(spy, pos, cash0, slip)
            mark = " ← default" if entry == config.RSI2["entry_rsi"] and exit_rsi == config.RSI2["exit_rsi"] else ""
            grid_rows.append(
                [
                    _fmt(entry),
                    _fmt(exit_rsi),
                    _fmt(st.get("cagr_pct")),
                    _fmt(st.get("max_drawdown_pct")),
                    _fmt(st.get("sharpe")),
                    _fmt(st.get("num_trades")),
                    mark.strip(),
                ]
            )

    # ---- Write REPORT.md -------------------------------------------------
    data_start = min(df.index[0].date() for df in frames.values())
    data_end = max(df.index[-1].date() for df in frames.values())

    summary_rows = []
    for key, st in full_stats.items():
        if "error" in st:
            continue
        summary_rows.append(
            [
                key,
                _fmt(st.get("cagr_pct")),
                _fmt(st.get("max_drawdown_pct")),
                _fmt(st.get("sharpe")),
                _fmt(st.get("total_return_pct")),
                _fmt(st.get("num_trades")),
                _fmt(st.get("win_rate_pct")),
                _fmt(st.get("exposure_pct")),
                _fmt(st.get("final_equity")),
            ]
        )

    md: list[str] = []
    md.append("# Backtest report")
    md.append("")
    md.append(f"Generated: **{generated}**")
    md.append("")
    md.append("## Setup (defaults unchanged)")
    md.append("")
    md.append(f"- Initial cash: `${cash0:,.0f}`")
    md.append(f"- Slippage: `{slip} bps` per side; commissions $0")
    md.append(f"- Sizing: `risk.size_shares` — max `{config.MAX_POSITION_PCT:.0%}` of equity, cash-only")
    md.append(f"- Universe: `{', '.join(config.SYMBOLS)}`; active live strategy in config: `{config.ACTIVE_STRATEGY}`")
    md.append(f"- Data: Alpaca SIP daily via `fetch_daily` (`adjustment=all`), ~{years}y")
    md.append(f"- Sample: **{data_start} → {data_end}**")
    md.append(f"- RSI2 defaults: `{config.RSI2}`")
    md.append(f"- RSI2_TIGHT (lab): `{config.RSI2_TIGHT}`")
    md.append(f"- TREND defaults: `{config.TREND}`")
    md.append("- Execution: signal on bar *t* close → fill at bar *t+1* open (no look-ahead)")
    md.append("")
    md.append("## Full-sample stats")
    md.append("")
    md.append(
        _markdown_table(
            [
                "run",
                "CAGR %",
                "Max DD %",
                "Sharpe",
                "Total ret %",
                "Trades",
                "Win %",
                "Exposure %",
                "Final $",
            ],
            summary_rows,
        )
    )
    md.append("")
    md.append("## Equity curves")
    md.append("")
    for p in png_paths:
        name = os.path.basename(p)
        web = f"{WEB_EQUITY_PREFIX}/{name}"
        md.append(f"![{name}]({web})")
        md.append("")
    md.append("Normalized to 100 at the first equity point of each series.")
    md.append("")
    md.append("## Out-of-sample split")
    md.append("")
    md.append(
        f"Per STRATEGY.md: in-sample **before {OOS_SPLIT.isoformat()}**, "
        f"out-of-sample **on/after {OOS_SPLIT.isoformat()}**. "
        "Each window is backtested on its own slice (SMA warm-up consumes early bars inside the window — see limitations)."
    )
    md.append("")
    md.append(
        _markdown_table(
            ["symbol", "strategy", "window", "CAGR %", "Max DD %", "Sharpe", "Trades", "span"],
            oos_rows,
        )
    )
    md.append("")
    md.append("## RSI2 stability grid (SPY, full sample)")
    md.append("")
    md.append(
        "Vary `entry_rsi` ∈ {5,10,15} and `exit_rsi` ∈ {55,65,75}. "
        "**Do not pick the best cell for live trading** — that is classic overfitting. "
        "Prefer a neighborhood where nearby cells are also acceptable (STRATEGY.md)."
    )
    md.append("")
    md.append(
        _markdown_table(
            ["entry_rsi", "exit_rsi", "CAGR %", "Max DD %", "Sharpe", "Trades", "note"],
            grid_rows,
        )
    )
    md.append("")
    md.append("## Lab variant: rsi2_tight (E1 — not live)")
    md.append("")
    md.append(
        f"`rsi2_tight` uses `{config.RSI2_TIGHT}` — stricter entry (RSI<5) and "
        f"shorter hold (5 days). **Do not switch `ACTIVE_STRATEGY`** unless OOS "
        "CAGR and Max DD clearly beat default rsi2 *and* buy-and-hold on a cost-adjusted "
        "basis; tighter entry usually means fewer trades and higher parameter risk."
    )
    md.append("")
    tight_keys = [k for k in full_stats if k.endswith("/rsi2_tight") or k == "PORTFOLIO/rsi2_tight"]
    base_keys = [k for k in full_stats if k.endswith("/rsi2") or k == "PORTFOLIO/rsi2"]
    if tight_keys and base_keys:
        def _pick(keys, field):
            for k in keys:
                if field in full_stats[k]:
                    return full_stats[k][field]
            return None
        md.append(
            f"- Portfolio rsi2 OOS proxy: CAGR {_fmt(_pick(base_keys, 'cagr_pct'))}%, "
            f"Max DD {_fmt(_pick(base_keys, 'max_drawdown_pct'))}%"
        )
        md.append(
            f"- Portfolio rsi2_tight: CAGR {_fmt(_pick(tight_keys, 'cagr_pct'))}%, "
            f"Max DD {_fmt(_pick(tight_keys, 'max_drawdown_pct'))}%"
        )
        md.append("- **Recommendation:** keep `ACTIVE_STRATEGY='rsi2'` unless tight wins on DD-adjusted terms after costs.")
    md.append("")
    md.append("## Limitations (read before believing any number)")
    md.append("")
    md.append("1. **Past ≠ future.** Published mean-reversion edges decay; ETFs change.")
    md.append("2. **Parameter garden.** The grid will show a best cell — that is mostly selection bias if you promote it.")
    md.append("3. **Slippage model is flat (5 bps).** Real open fills, gaps, and stress days differ.")
    md.append("4. **No borrow, no corporate-action drama beyond Alpaca `adjustment=all`.**")
    md.append("5. **OOS warm-up:** slicing the series resets SMA/RSI history at the cut — OOS CAGR is slightly disadvantaged vs a continuous book.")
    md.append("6. **Survivorship:** SPY/QQQ are survivors; the test does not include delisted junk.")
    md.append("7. **Risk halts (daily loss / drawdown) are not simulated in this backtest** — live paper can halt when the sim would not.")
    md.append("8. **Paper fills still beat this report.** 60–90 days of submitted paper is the real exam.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Metric definitions")
    md.append("")
    md.append(
        "- **CAGR (compound annual growth rate):** "
        "`(final_equity / initial_cash) ^ (1 / years) - 1`, with `years = n_bars / 252`. "
        "Smooths path dependency into one number — easy to worship, easy to quit before you earn it."
    )
    md.append(
        "- **Max drawdown (Max DD):** largest peak-to-trough decline of the equity curve, "
        "`min(equity / equity.cummax() - 1)`. The pain you must sit through."
    )
    md.append(
        "- **Sharpe:** annualized daily-return mean / daily-return std × √252 "
        "(risk-free rate treated as 0). Sensitive to quiet flat periods and to how returns are sampled."
    )
    md.append("")
    md.append(
        "*Report generated by `build_report.py`. Strategy defaults were not modified.*"
    )

    report_md = "\n".join(md) + "\n"
    report_path = os.path.join(config.RESULTS_DIR, "REPORT.md")
    with open(report_path, "w") as f:
        f.write(report_md)
    with open(CONTENT_REPORT, "w") as f:
        f.write(report_md)
    print(f"\nWrote {report_path}")
    print(f"Wrote {CONTENT_REPORT}")
    for p in png_paths:
        dest = os.path.join(PUBLIC_EQUITY_DIR, os.path.basename(p))
        shutil.copy2(p, dest)
        print(f"Wrote {p}")
        print(f"  → {dest}")


if __name__ == "__main__":
    main()
