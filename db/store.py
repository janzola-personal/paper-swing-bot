"""
Store backends for bot persistence.

- MemoryStore / SQLiteStore: tests
- FileStore: optional local state.json + journal.csv + runs.json
- PostgresStore: production (DATABASE_URL → Supabase)

No secrets are stored in tables; credentials stay in the environment.
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


@dataclass
class ClaimResult:
    acquired: bool
    status: str  # "claimed" | "skipped_duplicate"
    run_id: int | None = None


class Store(Protocol):
    def load_state(self) -> BotState: ...
    def save_state(self, state: BotState) -> None: ...
    def claim_run(self, trading_day: date, strategy: str, mode: str) -> ClaimResult: ...
    def complete_run(
        self, trading_day: date, strategy: str, status: str
    ) -> None: ...
    def get_run(
        self, trading_day: date, strategy: str
    ) -> dict[str, Any] | None: ...
    def list_runs(self, strategy: str) -> list[dict[str, Any]]: ...
    def list_journal(self, limit: int = 5000) -> list[dict[str, Any]]: ...
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
        self.state = BotState()
        self.runs: dict[tuple[str, str], dict[str, Any]] = {}
        self.journal: list[dict[str, Any]] = []
        self.equity: list[dict[str, Any]] = []
        self._run_seq = 0

    def load_state(self) -> BotState:
        return BotState(**asdict(self.state))

    def save_state(self, state: BotState) -> None:
        self.state = BotState(**asdict(state))

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

    def list_journal(self, limit: int = 5000) -> list[dict[str, Any]]:
        return list(self.journal[-limit:])

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
    """state.json + journal.csv + runs.json under the working directory."""

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

    def load_state(self) -> BotState:
        from dataclasses import fields

        if not os.path.exists(self.state_path):
            return BotState()
        with open(self.state_path) as f:
            raw = json.load(f)
        known = {fld.name for fld in fields(BotState)}
        return BotState(**{k: v for k, v in raw.items() if k in known})

    def save_state(self, state: BotState) -> None:
        with open(self.state_path, "w") as f:
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

    def list_journal(self, limit: int = 5000) -> list[dict[str, Any]]:
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
    ) -> None:
        import journal as journal_mod

        # Keep CSV schema; trading_day/actor live in reason prefix if needed.
        note = reason
        if actor:
            note = f"[actor={actor}] {reason}"
        if trading_day is not None:
            note = f"[day={trading_day.isoformat()}] {note}"
        # Temporarily point journal module at our path
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
    id integer PRIMARY KEY CHECK (id = 1),
    peak_equity real NOT NULL DEFAULT 0,
    day_start_equity real NOT NULL DEFAULT 0,
    day_start_trading_day text,
    halted integer NOT NULL DEFAULT 0,
    halted_reason text NOT NULL DEFAULT '',
    day_halted_trading_day text,
    paused integer NOT NULL DEFAULT 0,
    last_run_date text,
    watchdog_norun_sent_day text,
    updated_at text NOT NULL
);
INSERT OR IGNORE INTO bot_state (id, updated_at) VALUES (1, datetime('now'));

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


class SQLiteStore:
    def __init__(self, path: str = ":memory:") -> None:
        # check_same_thread=False for pytest flexibility; single-threaded engine use
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SQLITE_SCHEMA)
        self._conn.commit()

    def load_state(self) -> BotState:
        row = self._conn.execute("SELECT * FROM bot_state WHERE id = 1").fetchone()
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
        )

    def save_state(self, state: BotState) -> None:
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
              updated_at = datetime('now')
            WHERE id = 1
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

    def list_journal(self, limit: int = 5000) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM journal ORDER BY id DESC LIMIT ?",
            (limit,),
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
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO journal (
              trading_day, timestamp_utc, symbol, action, qty, ref_price,
              reason, equity, cash, dry_run, actor
            ) VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    def load_state(self) -> BotState:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bot_state WHERE id = 1")
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
        )

    def save_state(self, state: BotState) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE bot_state SET
                      peak_equity = %s,
                      day_start_equity = %s,
                      day_start_trading_day = %s,
                      halted = %s,
                      halted_reason = %s,
                      day_halted_trading_day = %s,
                      paused = %s,
                      last_run_date = %s,
                      watchdog_norun_sent_day = %s,
                      updated_at = now()
                    WHERE id = 1
                    """,
                    (
                        state.peak_equity,
                        state.day_start_equity,
                        state.day_start_date or None,
                        state.halted,
                        state.halted_reason,
                        state.day_halted_date or None,
                        state.paused,
                        state.last_run_date or None,
                        state.watchdog_norun_sent_day or None,
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

    def list_journal(self, limit: int = 5000) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, trading_day, timestamp_utc, symbol, action, qty,
                           ref_price, reason, equity, cash, dry_run, actor
                    FROM journal
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (limit,),
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
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO journal (
                      trading_day, symbol, action, qty, ref_price,
                      reason, equity, cash, dry_run, actor
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
