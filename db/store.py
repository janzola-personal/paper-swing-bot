"""
Store backends for bot persistence.

- MemoryStore / SQLiteStore: tests
- FileStore: optional local state.json + journal.csv + runs.json
- PostgresStore: production (DATABASE_URL → Supabase)

No secrets are stored in tables; credentials stay in the environment.

bot_state and journal are keyed by strategy (multi-engine). Default strategy
is "rsi2" for backward-compatible call sites.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from risk import BotState

DEFAULT_STRATEGY = "rsi2"


@dataclass
class ClaimResult:
    acquired: bool
    status: str  # "claimed" | "skipped_duplicate"
    run_id: int | None = None


class Store(Protocol):
    def load_state(self, strategy: str = DEFAULT_STRATEGY) -> BotState: ...
    def save_state(
        self, state: BotState, strategy: str = DEFAULT_STRATEGY
    ) -> None: ...
    def claim_run(self, trading_day: date, strategy: str, mode: str) -> ClaimResult: ...
    def complete_run(
        self, trading_day: date, strategy: str, status: str
    ) -> None: ...
    def get_run(
        self, trading_day: date, strategy: str
    ) -> dict[str, Any] | None: ...
    def list_runs(self, strategy: str) -> list[dict[str, Any]]: ...
    def list_journal(
        self, limit: int = 5000, strategy: str | None = None
    ) -> list[dict[str, Any]]: ...
    def append_journal(
        self,
        *,
        trading_day: date | None,
        symbol: str,
        action: str,
        qty: int,
        ref_price: float,
        reason: str,
        equity: float,
        cash: float,
        dry_run: bool,
        actor: str | None = None,
        strategy: str | None = None,
    ) -> None: ...
    def snapshot_equity(
        self,
        trading_day: date,
        strategy: str,
        equity: float,
        cash: float,
        positions: dict[str, int],
    ) -> None: ...


# ---------------------------------------------------------------------------
# Memory (unit tests)
# ---------------------------------------------------------------------------


class MemoryStore:
    def __init__(self) -> None:
        self.states: dict[str, BotState] = {}
        self.runs: dict[tuple[str, str], dict[str, Any]] = {}
        self.journal: list[dict[str, Any]] = []
        self.equity: list[dict[str, Any]] = []
        self._run_seq = 0

    def load_state(self, strategy: str = DEFAULT_STRATEGY) -> BotState:
        st = self.states.get(strategy)
        if st is None:
            return BotState()
        return BotState(**asdict(st))

    def save_state(self, state: BotState, strategy: str = DEFAULT_STRATEGY) -> None:
        self.states[strategy] = BotState(**asdict(state))

    def claim_run(self, trading_day: date, strategy: str, mode: str) -> ClaimResult:
        key = (trading_day.isoformat(), strategy)
        if key in self.runs:
            # Reclaim stuck mid-write claims so a dual scheduler / retry can finish.
            if self.runs[key].get("status") == "claimed":
                self.runs[key]["mode"] = mode
                self.runs[key]["started_at"] = datetime.now(timezone.utc).isoformat()
                self.runs[key]["completed_at"] = None
                return ClaimResult(True, "reclaimed", self.runs[key].get("id"))
            return ClaimResult(False, "skipped_duplicate", self.runs[key].get("id"))
        self._run_seq += 1
        self.runs[key] = {
            "id": self._run_seq,
            "status": "claimed",
            "mode": mode,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        return ClaimResult(True, "claimed", self._run_seq)

    def complete_run(self, trading_day: date, strategy: str, status: str) -> None:
        key = (trading_day.isoformat(), strategy)
        if key in self.runs:
            self.runs[key]["status"] = status
            self.runs[key]["completed_at"] = datetime.now(timezone.utc).isoformat()

    def get_run(self, trading_day: date, strategy: str) -> dict[str, Any] | None:
        return self.runs.get((trading_day.isoformat(), strategy))

    def list_runs(self, strategy: str) -> list[dict[str, Any]]:
        out = []
        for (day, strat), row in self.runs.items():
            if strat != strategy:
                continue
            out.append({**row, "trading_day": day, "strategy": strat})
        return out

    def list_journal(
        self, limit: int = 5000, strategy: str | None = None
    ) -> list[dict[str, Any]]:
        rows = self.journal
        if strategy is not None:
            rows = [r for r in rows if r.get("strategy") == strategy]
        return list(rows[-limit:])

    def append_journal(
        self,
        *,
        trading_day: date | None,
        symbol: str,
        action: str,
        qty: int,
        ref_price: float,
        reason: str,
        equity: float,
        cash: float,
        dry_run: bool,
        actor: str | None = None,
        strategy: str | None = None,
    ) -> None:
        self.journal.append(
            {
                "trading_day": trading_day.isoformat() if trading_day else None,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "symbol": symbol,
                "action": action,
                "qty": qty,
                "ref_price": ref_price,
                "reason": reason,
                "equity": equity,
                "cash": cash,
                "dry_run": dry_run,
                "actor": actor,
                "strategy": strategy,
            }
        )

    def snapshot_equity(
        self,
        trading_day: date,
        strategy: str,
        equity: float,
        cash: float,
        positions: dict[str, int],
    ) -> None:
        self.equity.append(
            {
                "trading_day": trading_day.isoformat(),
                "strategy": strategy,
                "equity": equity,
                "cash": cash,
                "positions": dict(positions),
            }
        )


# ---------------------------------------------------------------------------
# File (optional local)
# ---------------------------------------------------------------------------


class FileStore:
    """state.json + journal.csv + runs.json under the working directory.

    Multi-engine: state keyed under results/state_<strategy>.json when strategy
    is not the default; journal strategy is prefixed into the reason field.
    """

    def __init__(
        self,
        state_path: str | None = None,
        journal_path: str | None = None,
        runs_path: str | Path = "runs.json",
    ) -> None:
        import config

        self.state_path = state_path or config.STATE_FILE
        self.journal_path = journal_path or config.JOURNAL_FILE
        self.runs_path = Path(runs_path)

    def _state_path_for(self, strategy: str) -> str:
        if strategy == DEFAULT_STRATEGY:
            return self.state_path
        base = Path(self.state_path)
        return str(base.with_name(f"{base.stem}_{strategy}{base.suffix}"))

    def load_state(self, strategy: str = DEFAULT_STRATEGY) -> BotState:
        from dataclasses import fields

        path = self._state_path_for(strategy)
        if not os.path.exists(path):
            return BotState()
        with open(path) as f:
            raw = json.load(f)
        known = {fld.name for fld in fields(BotState)}
        return BotState(**{k: v for k, v in raw.items() if k in known})

    def save_state(self, state: BotState, strategy: str = DEFAULT_STRATEGY) -> None:
        path = self._state_path_for(strategy)
        with open(path, "w") as f:
            json.dump(asdict(state), f, indent=2)

    def _load_runs(self) -> dict[str, Any]:
        if not self.runs_path.exists():
            return {}
        return json.loads(self.runs_path.read_text())

    def _save_runs(self, data: dict[str, Any]) -> None:
        self.runs_path.write_text(json.dumps(data, indent=2))

    def claim_run(self, trading_day: date, strategy: str, mode: str) -> ClaimResult:
        data = self._load_runs()
        key = f"{trading_day.isoformat()}|{strategy}"
        if key in data:
            if data[key].get("status") == "claimed":
                data[key]["mode"] = mode
                data[key]["started_at"] = datetime.now(timezone.utc).isoformat()
                data[key]["completed_at"] = None
                self._save_runs(data)
                return ClaimResult(True, "reclaimed", data[key].get("id"))
            return ClaimResult(False, "skipped_duplicate", data[key].get("id"))
        run_id = int(data.get("_seq", 0)) + 1
        data["_seq"] = run_id
        data[key] = {
            "id": run_id,
            "status": "claimed",
            "mode": mode,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_runs(data)
        return ClaimResult(True, "claimed", run_id)

    def complete_run(self, trading_day: date, strategy: str, status: str) -> None:
        data = self._load_runs()
        key = f"{trading_day.isoformat()}|{strategy}"
        if key in data:
            data[key]["status"] = status
            data[key]["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save_runs(data)

    def get_run(self, trading_day: date, strategy: str) -> dict[str, Any] | None:
        data = self._load_runs()
        return data.get(f"{trading_day.isoformat()}|{strategy}")

    def list_runs(self, strategy: str) -> list[dict[str, Any]]:
        data = self._load_runs()
        out = []
        for key, row in data.items():
            if key == "_seq" or not isinstance(row, dict):
                continue
            if "|" not in key:
                continue
            day, strat = key.split("|", 1)
            if strat != strategy:
                continue
            out.append({**row, "trading_day": day, "strategy": strat})
        return out

    def list_journal(
        self, limit: int = 5000, strategy: str | None = None
    ) -> list[dict[str, Any]]:
        # File journal is CSV; Stage B UI uses Postgres. Empty is fine locally.
        return []

    def append_journal(
        self,
        *,
        trading_day: date | None,
        symbol: str,
        action: str,
        qty: int,
        ref_price: float,
        reason: str,
        equity: float,
        cash: float,
        dry_run: bool,
        actor: str | None = None,
        strategy: str | None = None,
    ) -> None:
        import journal as journal_mod

        note = reason
        if strategy:
            note = f"[strategy={strategy}] {note}"
        if actor:
            note = f"[actor={actor}] {note}"
        if trading_day is not None:
            note = f"[day={trading_day.isoformat()}] {note}"
        import config

        prev = config.JOURNAL_FILE
        config.JOURNAL_FILE = self.journal_path
        try:
            journal_mod.log(symbol, action, qty, ref_price, note, equity, cash, dry_run)
        finally:
            config.JOURNAL_FILE = prev

    def snapshot_equity(
        self,
        trading_day: date,
        strategy: str,
        equity: float,
        cash: float,
        positions: dict[str, int],
    ) -> None:
        path = Path("equity_snapshots.jsonl")
        row = {
            "trading_day": trading_day.isoformat(),
            "strategy": strategy,
            "equity": equity,
            "cash": cash,
            "positions": positions,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with path.open("a") as f:
            f.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# SQLite (tests — same logical schema as Postgres)
# ---------------------------------------------------------------------------

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS bot_state (
    id integer PRIMARY KEY AUTOINCREMENT,
    strategy text NOT NULL UNIQUE,
    peak_equity real NOT NULL DEFAULT 0,
    day_start_equity real NOT NULL DEFAULT 0,
    day_start_trading_day text,
    halted integer NOT NULL DEFAULT 0,
    halted_reason text NOT NULL DEFAULT '',
    day_halted_trading_day text,
    paused integer NOT NULL DEFAULT 0,
    last_run_date text,
    watchdog_norun_sent_day text,
    virtual_cash real NOT NULL DEFAULT 0,
    updated_at text NOT NULL
);
INSERT OR IGNORE INTO bot_state (strategy, updated_at) VALUES ('rsi2', datetime('now'));

CREATE TABLE IF NOT EXISTS runs (
    id integer PRIMARY KEY AUTOINCREMENT,
    trading_day text NOT NULL,
    strategy text NOT NULL,
    started_at text NOT NULL,
    completed_at text,
    status text NOT NULL,
    mode text NOT NULL,
    UNIQUE (trading_day, strategy)
);

CREATE TABLE IF NOT EXISTS journal (
    id integer PRIMARY KEY AUTOINCREMENT,
    trading_day text,
    timestamp_utc text NOT NULL,
    symbol text NOT NULL,
    action text NOT NULL,
    qty integer NOT NULL DEFAULT 0,
    ref_price real,
    reason text,
    equity real,
    cash real,
    dry_run integer NOT NULL DEFAULT 1,
    actor text,
    strategy text,
    run_id integer
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id integer PRIMARY KEY AUTOINCREMENT,
    trading_day text NOT NULL,
    strategy text NOT NULL,
    equity real NOT NULL,
    cash real NOT NULL,
    positions_json text NOT NULL DEFAULT '{}',
    created_at text NOT NULL,
    UNIQUE (trading_day, strategy)
);
"""


def _row_to_bot_state(row: sqlite3.Row | None) -> BotState:
    if row is None:
        return BotState()
    keys = row.keys()
    return BotState(
        peak_equity=float(row["peak_equity"] or 0),
        day_start_equity=float(row["day_start_equity"] or 0),
        day_start_date=row["day_start_trading_day"] or "",
        halted=bool(row["halted"]),
        halted_reason=row["halted_reason"] or "",
        day_halted_date=row["day_halted_trading_day"] or "",
        paused=bool(row["paused"]),
        last_run_date=row["last_run_date"] or "",
        watchdog_norun_sent_day=(
            row["watchdog_norun_sent_day"] or ""
            if "watchdog_norun_sent_day" in keys
            else ""
        ),
        virtual_cash=float(row["virtual_cash"] or 0) if "virtual_cash" in keys else 0.0,
    )


class SQLiteStore:
    def __init__(self, path: str = ":memory:") -> None:
        # check_same_thread=False for pytest flexibility; single-threaded engine use
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SQLITE_SCHEMA)
        self._conn.commit()

    def load_state(self, strategy: str = DEFAULT_STRATEGY) -> BotState:
        row = self._conn.execute(
            "SELECT * FROM bot_state WHERE strategy = ?", (strategy,)
        ).fetchone()
        return _row_to_bot_state(row)

    def save_state(self, state: BotState, strategy: str = DEFAULT_STRATEGY) -> None:
        existing = self._conn.execute(
            "SELECT id FROM bot_state WHERE strategy = ?", (strategy,)
        ).fetchone()
        if existing is None:
            self._conn.execute(
                """
                INSERT INTO bot_state (
                  strategy, peak_equity, day_start_equity, day_start_trading_day,
                  halted, halted_reason, day_halted_trading_day, paused,
                  last_run_date, watchdog_norun_sent_day, virtual_cash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    strategy,
                    state.peak_equity,
                    state.day_start_equity,
                    state.day_start_date or None,
                    int(state.halted),
                    state.halted_reason,
                    state.day_halted_date or None,
                    int(state.paused),
                    state.last_run_date or None,
                    state.watchdog_norun_sent_day or None,
                    state.virtual_cash,
                ),
            )
        else:
            self._conn.execute(
                """
                UPDATE bot_state SET
                  peak_equity = ?,
                  day_start_equity = ?,
                  day_start_trading_day = ?,
                  halted = ?,
                  halted_reason = ?,
                  day_halted_trading_day = ?,
                  paused = ?,
                  last_run_date = ?,
                  watchdog_norun_sent_day = ?,
                  virtual_cash = ?,
                  updated_at = datetime('now')
                WHERE strategy = ?
                """,
                (
                    state.peak_equity,
                    state.day_start_equity,
                    state.day_start_date or None,
                    int(state.halted),
                    state.halted_reason,
                    state.day_halted_date or None,
                    int(state.paused),
                    state.last_run_date or None,
                    state.watchdog_norun_sent_day or None,
                    state.virtual_cash,
                    strategy,
                ),
            )
        self._conn.commit()

    def claim_run(self, trading_day: date, strategy: str, mode: str) -> ClaimResult:
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO runs (trading_day, strategy, started_at, status, mode)
            VALUES (?, ?, datetime('now'), 'claimed', ?)
            """,
            (trading_day.isoformat(), strategy, mode),
        )
        self._conn.commit()
        if cur.rowcount == 1:
            rid = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return ClaimResult(True, "claimed", int(rid))
        row = self._conn.execute(
            "SELECT id, status FROM runs WHERE trading_day = ? AND strategy = ?",
            (trading_day.isoformat(), strategy),
        ).fetchone()
        if row and row["status"] == "claimed":
            self._conn.execute(
                """
                UPDATE runs SET mode = ?, started_at = datetime('now'),
                  completed_at = NULL, status = 'claimed'
                WHERE trading_day = ? AND strategy = ? AND status = 'claimed'
                """,
                (mode, trading_day.isoformat(), strategy),
            )
            self._conn.commit()
            return ClaimResult(True, "reclaimed", int(row["id"]))
        return ClaimResult(False, "skipped_duplicate", int(row["id"]) if row else None)

    def complete_run(self, trading_day: date, strategy: str, status: str) -> None:
        self._conn.execute(
            """
            UPDATE runs SET status = ?, completed_at = datetime('now')
            WHERE trading_day = ? AND strategy = ?
            """,
            (status, trading_day.isoformat(), strategy),
        )
        self._conn.commit()

    def get_run(self, trading_day: date, strategy: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE trading_day = ? AND strategy = ?",
            (trading_day.isoformat(), strategy),
        ).fetchone()
        if row is None:
            return None
        return {k: row[k] for k in row.keys()}

    def list_runs(self, strategy: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE strategy = ? ORDER BY trading_day",
            (strategy,),
        ).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]

    def list_journal(
        self, limit: int = 5000, strategy: str | None = None
    ) -> list[dict[str, Any]]:
        if strategy is None:
            rows = self._conn.execute(
                "SELECT * FROM journal ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM journal WHERE strategy = ? ORDER BY id DESC LIMIT ?",
                (strategy, limit),
            ).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]

    def append_journal(
        self,
        *,
        trading_day: date | None,
        symbol: str,
        action: str,
        qty: int,
        ref_price: float,
        reason: str,
        equity: float,
        cash: float,
        dry_run: bool,
        actor: str | None = None,
        strategy: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO journal (
              trading_day, timestamp_utc, symbol, action, qty, ref_price,
              reason, equity, cash, dry_run, actor, strategy
            ) VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trading_day.isoformat() if trading_day else None,
                symbol,
                action,
                qty,
                ref_price,
                reason,
                equity,
                cash,
                int(dry_run),
                actor,
                strategy,
            ),
        )
        self._conn.commit()

    def snapshot_equity(
        self,
        trading_day: date,
        strategy: str,
        equity: float,
        cash: float,
        positions: dict[str, int],
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO equity_snapshots (
              trading_day, strategy, equity, cash, positions_json, created_at
            ) VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(trading_day, strategy) DO UPDATE SET
              equity = excluded.equity,
              cash = excluded.cash,
              positions_json = excluded.positions_json,
              created_at = excluded.created_at
            """,
            (
                trading_day.isoformat(),
                strategy,
                equity,
                cash,
                json.dumps(positions),
            ),
        )
        self._conn.commit()


# ---------------------------------------------------------------------------
# Postgres (production)
# ---------------------------------------------------------------------------


class PostgresStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.environ.get("DATABASE_URL") or ""
        if not self.database_url:
            raise ValueError("DATABASE_URL required for PostgresStore")

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url)

    def load_state(self, strategy: str = DEFAULT_STRATEGY) -> BotState:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM bot_state WHERE strategy = %s", (strategy,)
                )
                row = cur.fetchone()
                if row is None:
                    return BotState()
                cols = [d.name for d in cur.description]
                data = dict(zip(cols, row))
        return BotState(
            peak_equity=float(data.get("peak_equity") or 0),
            day_start_equity=float(data.get("day_start_equity") or 0),
            day_start_date=(
                data["day_start_trading_day"].isoformat()
                if data.get("day_start_trading_day")
                else ""
            ),
            halted=bool(data.get("halted")),
            halted_reason=data.get("halted_reason") or "",
            day_halted_date=(
                data["day_halted_trading_day"].isoformat()
                if data.get("day_halted_trading_day")
                else ""
            ),
            paused=bool(data.get("paused")),
            last_run_date=(
                data["last_run_date"].isoformat() if data.get("last_run_date") else ""
            ),
            watchdog_norun_sent_day=(
                data["watchdog_norun_sent_day"].isoformat()
                if data.get("watchdog_norun_sent_day")
                else ""
            ),
            virtual_cash=float(data.get("virtual_cash") or 0),
        )

    def save_state(self, state: BotState, strategy: str = DEFAULT_STRATEGY) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO bot_state (
                      strategy, peak_equity, day_start_equity, day_start_trading_day,
                      halted, halted_reason, day_halted_trading_day, paused,
                      last_run_date, watchdog_norun_sent_day, virtual_cash, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()
                    )
                    ON CONFLICT (strategy) DO UPDATE SET
                      peak_equity = EXCLUDED.peak_equity,
                      day_start_equity = EXCLUDED.day_start_equity,
                      day_start_trading_day = EXCLUDED.day_start_trading_day,
                      halted = EXCLUDED.halted,
                      halted_reason = EXCLUDED.halted_reason,
                      day_halted_trading_day = EXCLUDED.day_halted_trading_day,
                      paused = EXCLUDED.paused,
                      last_run_date = EXCLUDED.last_run_date,
                      watchdog_norun_sent_day = EXCLUDED.watchdog_norun_sent_day,
                      virtual_cash = EXCLUDED.virtual_cash,
                      updated_at = now()
                    """,
                    (
                        strategy,
                        state.peak_equity,
                        state.day_start_equity,
                        state.day_start_date or None,
                        state.halted,
                        state.halted_reason,
                        state.day_halted_date or None,
                        state.paused,
                        state.last_run_date or None,
                        state.watchdog_norun_sent_day or None,
                        state.virtual_cash,
                    ),
                )
            conn.commit()

    def claim_run(self, trading_day: date, strategy: str, mode: str) -> ClaimResult:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO runs (trading_day, strategy, status, mode)
                    VALUES (%s, %s, 'claimed', %s)
                    ON CONFLICT (trading_day, strategy) DO NOTHING
                    RETURNING id
                    """,
                    (trading_day, strategy, mode),
                )
                row = cur.fetchone()
                if row:
                    conn.commit()
                    return ClaimResult(True, "claimed", int(row[0]))
                cur.execute(
                    """
                    SELECT id, status FROM runs
                    WHERE trading_day = %s AND strategy = %s
                    """,
                    (trading_day, strategy),
                )
                existing = cur.fetchone()
                if existing and existing[1] == "claimed":
                    cur.execute(
                        """
                        UPDATE runs SET mode = %s, started_at = now(),
                          completed_at = NULL, status = 'claimed'
                        WHERE trading_day = %s AND strategy = %s
                          AND status = 'claimed'
                        RETURNING id
                        """,
                        (mode, trading_day, strategy),
                    )
                    reclaimed = cur.fetchone()
                    conn.commit()
                    rid = int(reclaimed[0]) if reclaimed else int(existing[0])
                    return ClaimResult(True, "reclaimed", rid)
            conn.commit()
        return ClaimResult(
            False, "skipped_duplicate", int(existing[0]) if existing else None
        )

    def complete_run(self, trading_day: date, strategy: str, status: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE runs SET status = %s, completed_at = now()
                    WHERE trading_day = %s AND strategy = %s
                    """,
                    (status, trading_day, strategy),
                )
            conn.commit()

    def get_run(self, trading_day: date, strategy: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, trading_day, strategy, started_at, completed_at,
                           status, mode
                    FROM runs
                    WHERE trading_day = %s AND strategy = %s
                    """,
                    (trading_day, strategy),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d.name for d in cur.description]
                data = dict(zip(cols, row))
        if data.get("trading_day") is not None:
            data["trading_day"] = data["trading_day"].isoformat()
        return data

    def list_runs(self, strategy: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, trading_day, strategy, started_at, completed_at,
                           status, mode
                    FROM runs
                    WHERE strategy = %s
                    ORDER BY trading_day
                    """,
                    (strategy,),
                )
                rows = cur.fetchall()
                cols = [d.name for d in cur.description]
        out = []
        for row in rows:
            data = dict(zip(cols, row))
            if data.get("trading_day") is not None:
                data["trading_day"] = data["trading_day"].isoformat()
            out.append(data)
        return out

    def list_journal(
        self, limit: int = 5000, strategy: str | None = None
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if strategy is None:
                    cur.execute(
                        """
                        SELECT id, trading_day, timestamp_utc, symbol, action, qty,
                               ref_price, reason, equity, cash, dry_run, actor, strategy
                        FROM journal
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, trading_day, timestamp_utc, symbol, action, qty,
                               ref_price, reason, equity, cash, dry_run, actor, strategy
                        FROM journal
                        WHERE strategy = %s
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                        (strategy, limit),
                    )
                rows = cur.fetchall()
                cols = [d.name for d in cur.description]
        out = []
        for row in rows:
            data = dict(zip(cols, row))
            if data.get("trading_day") is not None:
                data["trading_day"] = data["trading_day"].isoformat()
            out.append(data)
        return out

    def append_journal(
        self,
        *,
        trading_day: date | None,
        symbol: str,
        action: str,
        qty: int,
        ref_price: float,
        reason: str,
        equity: float,
        cash: float,
        dry_run: bool,
        actor: str | None = None,
        strategy: str | None = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO journal (
                      trading_day, symbol, action, qty, ref_price,
                      reason, equity, cash, dry_run, actor, strategy
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        trading_day,
                        symbol,
                        action,
                        qty,
                        ref_price,
                        reason,
                        equity,
                        cash,
                        dry_run,
                        actor,
                        strategy,
                    ),
                )
            conn.commit()

    def snapshot_equity(
        self,
        trading_day: date,
        strategy: str,
        equity: float,
        cash: float,
        positions: dict[str, int],
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO equity_snapshots (
                      trading_day, strategy, equity, cash, positions_json
                    ) VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (trading_day, strategy) DO UPDATE SET
                      equity = EXCLUDED.equity,
                      cash = EXCLUDED.cash,
                      positions_json = EXCLUDED.positions_json,
                      created_at = now()
                    """,
                    (trading_day, strategy, equity, cash, json.dumps(positions)),
                )
            conn.commit()


def default_store() -> Store:
    """Postgres when DATABASE_URL / STATE_BACKEND=postgres; else FileStore."""
    backend = (os.environ.get("STATE_BACKEND") or "auto").lower()
    url = os.environ.get("DATABASE_URL") or ""
    if backend == "postgres" or (backend == "auto" and url):
        return PostgresStore(url)
    if backend == "memory":
        return MemoryStore()
    return FileStore()
