"""Intraday engine CLI guards."""

import subprocess
import sys


def test_unattended_refused_without_flag(monkeypatch):
    monkeypatch.delenv("INTRADAY_SUPERVISED_OK", raising=False)
    proc = subprocess.run(
        [sys.executable, "-m", "intraday.engine", "--unattended"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "Refusing --unattended" in proc.stderr + proc.stdout
