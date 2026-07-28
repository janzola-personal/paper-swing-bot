"""Synthetic gate results — each fails exactly one Stage A criterion."""

import json
from pathlib import Path

import pytest

from gatecheck import evaluate_stage_a


def _base() -> dict:
    return {
        "strategy": "fixture",
        "kind": "intraday",
        "data_years": 6.0,
        "oos": {
            "num_trades": 400,
            "net_return_pct": 5.0,
            "profit_factor": 1.5,
            "max_drawdown_pct": 10.0,
        },
        "cost_stress": {"2x": {"net_return_pct": 2.0}, "3x": {"net_return_pct": -1.0}},
        "param_stability": {"profitable_frac": 0.6},
        "halt_days_pct": 3.0,
    }


@pytest.mark.parametrize(
    "field_path,mutator",
    [
        ("data_years", lambda d: d.update({"data_years": 3.0})),
        ("sample_size", lambda d: d["oos"].update({"num_trades": 50})),
        ("oos_net_return", lambda d: d["oos"].update({"net_return_pct": -1.0})),
        ("oos_profit_factor", lambda d: d["oos"].update({"profit_factor": 1.0})),
        ("oos_max_drawdown", lambda d: d["oos"].update({"max_drawdown_pct": 20.0})),
        ("cost_stress_2x", lambda d: d["cost_stress"]["2x"].update({"net_return_pct": -0.5})),
        ("param_stability", lambda d: d["param_stability"].update({"profitable_frac": 0.3})),
        ("halt_compatibility", lambda d: d.update({"halt_days_pct": 8.0})),
    ],
)
def test_stage_a_fail_exactly_one(field_path, mutator):
    data = _base()
    mutator(data)
    criteria = evaluate_stage_a(data)
    failed = [c for c in criteria if not c.passed]
    assert len(failed) == 1, [(c.name, c.passed) for c in criteria]
    assert failed[0].name == field_path or (
        field_path == "sample_size" and failed[0].name == "sample_size"
    )


def test_stage_a_all_pass():
    criteria = evaluate_stage_a(_base())
    assert all(c.passed for c in criteria)


def test_gatecheck_cli(tmp_path: Path):
    p = tmp_path / "ok.json"
    p.write_text(json.dumps(_base()))
    from gatecheck import main

    assert main([str(p)]) == 0
