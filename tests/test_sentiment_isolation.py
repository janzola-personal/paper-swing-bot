"""AST guard: sentiment_log must not import trading stack."""

import ast
from pathlib import Path


FORBIDDEN = {"strategy", "risk", "broker", "engine"}


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_sentiment_log_no_trading_imports():
    path = Path("research/sentiment_log.py")
    bad = _imports_in(path) & FORBIDDEN
    assert not bad, f"forbidden imports: {bad}"


def test_engine_does_not_import_sentiment():
    path = Path("engine.py")
    assert "sentiment" not in path.read_text()
