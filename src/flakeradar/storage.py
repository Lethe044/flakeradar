"""SQLite-backed storage for test run history.

The schema is intentionally small: a `runs` table (one row per pytest
invocation or stress iteration) and a `results` table (one row per test
outcome within a run). Everything else - flakiness scoring, clustering,
reporting - is computed on read, so the storage layer stays simple and the
scoring logic can evolve without a migration.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    git_sha TEXT,
    git_branch TEXT,
    source TEXT NOT NULL DEFAULT 'pytest'
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    nodeid TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration REAL NOT NULL DEFAULT 0,
    longrepr TEXT,
    file TEXT,
    line INTEGER,
    recorded_at REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_results_nodeid ON results (nodeid);
CREATE INDEX IF NOT EXISTS idx_results_run_id ON results (run_id);
"""


@dataclass
class TestResult:
    nodeid: str
    outcome: str  # "passed" | "failed" | "skipped" | "error"
    duration: float = 0.0
    longrepr: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None


@dataclass
class HistoryEntry:
    run_id: str
    started_at: float
    git_sha: Optional[str]
    outcome: str
    duration: float
    longrepr: Optional[str]


class Storage:
    """Thin wrapper around a SQLite database file."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- writes ---------------------------------------------------------

    def start_run(
        self,
        run_id: str,
        git_sha: Optional[str] = None,
        git_branch: Optional[str] = None,
        source: str = "pytest",
        started_at: Optional[float] = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO runs (run_id, started_at, git_sha, git_branch, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, started_at or time.time(), git_sha, git_branch, source),
            )

    def record_results(self, run_id: str, results: List[TestResult]) -> None:
        if not results:
            return
        now = time.time()
        rows = [
            (
                run_id,
                r.nodeid,
                r.outcome,
                r.duration,
                (r.longrepr or "")[:4000] or None,
                r.file,
                r.line,
                now,
            )
            for r in results
        ]
        with self._conn:
            self._conn.executemany(
                "INSERT INTO results "
                "(run_id, nodeid, outcome, duration, longrepr, file, line, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    def prune_runs(self, keep_last_n: int) -> int:
        """Delete all but the most recent `keep_last_n` runs. Returns rows removed."""
        run_ids = [
            row["run_id"]
            for row in self._conn.execute(
                "SELECT run_id FROM runs ORDER BY started_at DESC"
            ).fetchall()
        ]
        to_remove = run_ids[keep_last_n:]
        if not to_remove:
            return 0
        with self._conn:
            placeholders = ",".join("?" for _ in to_remove)
            self._conn.execute(
                f"DELETE FROM results WHERE run_id IN ({placeholders})", to_remove
            )
            self._conn.execute(
                f"DELETE FROM runs WHERE run_id IN ({placeholders})", to_remove
            )
        return len(to_remove)

    # -- reads ------------------------------------------------------------

    def all_nodeids(self) -> List[str]:
        rows = self._conn.execute("SELECT DISTINCT nodeid FROM results").fetchall()
        return [r["nodeid"] for r in rows]

    def history_for(self, nodeid: str, limit: Optional[int] = None) -> List[HistoryEntry]:
        query = (
            "SELECT r.run_id, r.started_at, r.git_sha, res.outcome, res.duration, res.longrepr "
            "FROM results res JOIN runs r ON res.run_id = r.run_id "
            "WHERE res.nodeid = ? ORDER BY r.started_at ASC"
        )
        rows = self._conn.execute(query, (nodeid,)).fetchall()
        entries = [
            HistoryEntry(
                run_id=row["run_id"],
                started_at=row["started_at"],
                git_sha=row["git_sha"],
                outcome=row["outcome"],
                duration=row["duration"],
                longrepr=row["longrepr"],
            )
            for row in rows
        ]
        if limit:
            entries = entries[-limit:]
        return entries

    def run_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()
        return int(row["c"])

    def iter_all_history(self) -> Iterator[tuple]:
        """Yield (nodeid, [HistoryEntry, ...]) for every known test."""
        for nodeid in self.all_nodeids():
            yield nodeid, self.history_for(nodeid)


@contextmanager
def open_storage(db_path: Path) -> Iterator[Storage]:
    store = Storage(db_path)
    try:
        yield store
    finally:
        store.close()
