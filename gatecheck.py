"""
Promotion gate checker (Stage A). CLI accepts only a JSON results file path;
thresholds come from config.GATE_STAGE_A — never from the JSON.

Usage:
  python gatecheck.py results/gate_orb15.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import config


@dataclass
class Criterion:
    name: str
    passed: bool
    detail: str


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def evaluate_stage_a(data: dict, *, thresholds: dict | None = None) -> list[Criterion]:
    """Return PASS/FAIL per Stage A criterion."""
    t = thresholds or config.GATE_STAGE_A
    kind = data.get("kind", "intraday")
    min_trades = t["min_trades_swing"] if kind in ("swing", "overnight") else t["min_trades_intraday"]
    oos = data.get("oos") or {}
    stress = data.get("cost_stress") or {}
    stab = data.get("param_stability") or {}
    out: list[Criterion] = []

    years = float(data.get("data_years", 0))
    out.append(
        Criterion(
            "data_years",
            years >= t["min_years_data"],
            f"{years:.2f}y (need ≥{t['min_years_data']})",
        )
    )

    trades = int(oos.get("num_trades", 0))
    out.append(
        Criterion(
            "sample_size",
            trades >= min_trades,
            f"{trades} OOS trades (need ≥{min_trades} for {kind})",
        )
    )

    oos_net = float(oos.get("net_return_pct", -999))
    out.append(
        Criterion(
            "oos_net_return",
            oos_net > t["oos_min_net_return"],
            f"net {oos_net:.2f}% (need >{t['oos_min_net_return']}%)",
        )
    )

    pf = float(oos.get("profit_factor", 0))
    out.append(
        Criterion(
            "oos_profit_factor",
            pf >= t["oos_min_profit_factor"],
            f"PF {pf:.2f} (need ≥{t['oos_min_profit_factor']})",
        )
    )

    dd = float(oos.get("max_drawdown_pct", 999))
    out.append(
        Criterion(
            "oos_max_drawdown",
            dd <= t["oos_max_drawdown_pct"],
            f"MaxDD {dd:.1f}% (need ≤{t['oos_max_drawdown_pct']}%)",
        )
    )

    s2 = stress.get("2x") or stress.get("2.0") or {}
    s2_net = float(s2.get("net_return_pct", -999))
    out.append(
        Criterion(
            "cost_stress_2x",
            s2_net > t["oos_min_net_return"],
            f"2× cost net {s2_net:.2f}% (need >0%)",
        )
    )

    frac = float(stab.get("profitable_frac", 0))
    out.append(
        Criterion(
            "param_stability",
            frac >= t["param_stability_min_profitable_frac"],
            f"{frac:.0%} neighbors profitable (need ≥{t['param_stability_min_profitable_frac']:.0%})",
        )
    )

    halt_pct = float(data.get("halt_days_pct", 999))
    out.append(
        Criterion(
            "halt_compatibility",
            halt_pct <= t["max_daily_halt_days_pct"],
            f"{halt_pct:.1f}% halt days (need ≤{t['max_daily_halt_days_pct']}%)",
        )
    )

    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage A promotion gate checker")
    parser.add_argument("results_json", type=Path, help="Path to gate results JSON")
    args = parser.parse_args(argv)

    if not args.results_json.is_file():
        print(f"ERROR: file not found: {args.results_json}", file=sys.stderr)
        return 2

    data = _load(args.results_json)
    name = data.get("strategy", args.results_json.stem)
    criteria = evaluate_stage_a(data)
    all_pass = all(c.passed for c in criteria)

    print(f"Strategy: {name}")
    print(f"Kind: {data.get('kind', 'intraday')}")
    if data.get("data_note"):
        print(f"Data note: {data['data_note']}")
    print("")
    for c in criteria:
        mark = "PASS" if c.passed else "FAIL"
        print(f"  [{mark}] {c.name}: {c.detail}")

    s3 = (data.get("cost_stress") or {}).get("3x") or (data.get("cost_stress") or {}).get("3.0")
    if s3:
        print(f"\n  (info) 3× cost net: {float(s3.get('net_return_pct', float('nan'))):.2f}%")

    print("")
    print("OVERALL:", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
