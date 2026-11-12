"""SQLite persistence for runs/events/inbox/memories.

Schema is defined in app.db.models and versioned via Alembic
(app/db/migrations). This Store remains the sync facade the Runtime and
UI use; the async SQLAlchemy engine is available for workers/jobs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.application.exceptions import ConcurrencyConflict

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    checkpoint_version INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ts REAL NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL DEFAULT '',
    event_hash TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, seq);
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ts REAL NOT NULL,
    text TEXT NOT NULL,
    acked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    run_id TEXT,
    created_at REAL NOT NULL,
    content TEXT NOT NULL
);
"""


class CheckpointConflict(ConcurrencyConflict):
    """Optimistic concurrency failure: another writer advanced checkpoint_version."""


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            # Additive migration for DBs created before hash chaining.
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(events)").fetchall()}
            if "prev_hash" not in cols:
                self._conn.execute("ALTER TABLE events ADD COLUMN prev_hash TEXT NOT NULL DEFAULT ''")
            if "event_hash" not in cols:
                self._conn.execute("ALTER TABLE events ADD COLUMN event_hash TEXT NOT NULL DEFAULT ''")

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _rows(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ---- runs / checkpoints -------------------------------------------------
    def create_run(self, state: dict) -> None:
        now = time.time()
        state["checkpoint_version"] = 1
        self._exec(
            "INSERT INTO runs (id, scenario_id, title, status, created_at, updated_at, checkpoint_version, state)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (state["run_id"], state["scenario_id"], state["title"], state["status"], now, now, 1, json.dumps(state)),
        )

    def save(self, state: dict, *, cas: bool = True) -> None:
        """Write a checkpoint. The latest checkpoint is the run's source of truth.

        When ``cas`` is True (default), the UPDATE is conditioned on the
        in-memory ``checkpoint_version`` matching the row. One automatic retry
        rebases onto the latest DB version (covers same-process races between the
        drive task unwinding and an approve/reject). A second failure raises
        ``CheckpointConflict``.
        """
        attempts = 2 if cas else 1
        last_err: Exception | None = None
        for _ in range(attempts):
            expected = int(state.get("checkpoint_version") or 0)
            new_ver = expected + 1
            to_write = dict(state)
            to_write["checkpoint_version"] = new_ver
            payload = json.dumps(to_write)
            now = time.time()
            with self._lock:
                if cas:
                    cur = self._conn.execute(
                        "UPDATE runs SET status=?, updated_at=?, checkpoint_version=?, state=? "
                        "WHERE id=? AND checkpoint_version=?",
                        (to_write["status"], now, new_ver, payload, to_write["run_id"], expected),
                    )
                    if cur.rowcount == 1:
                        state["checkpoint_version"] = new_ver
                        return
                    row = self._conn.execute(
                        "SELECT checkpoint_version FROM runs WHERE id=?", (to_write["run_id"],)
                    ).fetchone()
                    have = int(row["checkpoint_version"]) if row else None
                    last_err = CheckpointConflict(
                        f"checkpoint CAS failed for {to_write['run_id']}: expected v{expected}, have v{have}"
                    )
                    if have is not None:
                        state["checkpoint_version"] = have  # rebase for retry
                    continue
                self._conn.execute(
                    "UPDATE runs SET status=?, updated_at=?, checkpoint_version=?, state=? WHERE id=?",
                    (to_write["status"], now, new_ver, payload, to_write["run_id"]),
                )
                state["checkpoint_version"] = new_ver
                return
        assert last_err is not None
        raise last_err

    def load(self, run_id: str) -> dict | None:
        rows = self._rows("SELECT state FROM runs WHERE id=?", (run_id,))
        return json.loads(rows[0]["state"]) if rows else None

    def list_runs(self, limit: int = 50) -> list[dict]:
        rows = self._rows(
            "SELECT id, scenario_id, title, status, created_at, updated_at FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def runs_with_status(self, statuses: list[str]) -> list[dict]:
        marks = ",".join("?" * len(statuses))
        rows = self._rows(f"SELECT state FROM runs WHERE status IN ({marks})", tuple(statuses))
        return [json.loads(r["state"]) for r in rows]

    # ---- event log ------------------------------------------------------------
    @staticmethod
    def _event_hash(prev_hash: str, run_id: str, ts: float, type_: str, payload_json: str) -> str:
        blob = f"{prev_hash}|{run_id}|{ts:.6f}|{type_}|{payload_json}"
        return hashlib.sha256(blob.encode()).hexdigest()

    def append_event(self, run_id: str, type_: str, payload: dict[str, Any]) -> dict:
        """Append-only event write. No update/delete API exists for the events table.

        Each row carries ``prev_hash`` + ``event_hash`` (SHA-256 chain per run).
        This detects silent edits to the local DB; it is not a WORM/external
        audit store and does not protect against someone with filesystem access
        rewriting the whole file.
        """
        ts = time.time()
        payload_json = json.dumps(payload, default=str, sort_keys=True)
        with self._lock:
            row = self._conn.execute(
                "SELECT event_hash FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            prev_hash = row["event_hash"] if row and row["event_hash"] else ""
            event_hash = self._event_hash(prev_hash, run_id, ts, type_, payload_json)
            cur = self._conn.execute(
                "INSERT INTO events (run_id, ts, type, payload, prev_hash, event_hash) VALUES (?,?,?,?,?,?)",
                (run_id, ts, type_, payload_json, prev_hash, event_hash),
            )
            seq = cur.lastrowid
        return {
            "seq": seq,
            "run_id": run_id,
            "ts": ts,
            "type": type_,
            "payload": payload,
            "prev_hash": prev_hash,
            "event_hash": event_hash,
        }

    def events_since(self, run_id: str, after: int = 0, limit: int = 500) -> list[dict]:
        rows = self._rows(
            "SELECT seq, run_id, ts, type, payload, prev_hash, event_hash "
            "FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
            (run_id, after, limit),
        )
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(r["payload"])
            out.append(d)
        return out

    def verify_event_chain(self, run_id: str) -> dict[str, Any]:
        """Recompute the hash chain for a run. Returns ok / first bad seq."""
        rows = self._rows(
            "SELECT seq, run_id, ts, type, payload, prev_hash, event_hash FROM events WHERE run_id=? ORDER BY seq",
            (run_id,),
        )
        prev = ""
        for r in rows:
            payload_json = r["payload"]  # already stored JSON text
            # Re-canonicalize: payload was stored with sort_keys=True
            expected_prev = prev
            if (r["prev_hash"] or "") != expected_prev:
                return {"ok": False, "seq": r["seq"], "reason": "prev_hash mismatch"}
            expected = self._event_hash(expected_prev, r["run_id"], float(r["ts"]), r["type"], payload_json)
            if (r["event_hash"] or "") != expected:
                return {"ok": False, "seq": r["seq"], "reason": "event_hash mismatch"}
            prev = r["event_hash"] or ""
        return {"ok": True, "events": len(rows)}

    # ---- operator inbox (acked only after the step that consumed it is checkpointed)
    def push_inbox(self, run_id: str, text: str) -> None:
        self._exec("INSERT INTO inbox (run_id, ts, text) VALUES (?,?,?)", (run_id, time.time(), text))

    def peek_inbox(self, run_id: str) -> list[dict]:
        rows = self._rows("SELECT id, ts, text FROM inbox WHERE run_id=? AND acked=0 ORDER BY id", (run_id,))
        return [dict(r) for r in rows]

    def ack_inbox(self, ids: list[int]) -> None:
        if ids:
            marks = ",".join("?" * len(ids))
            self._exec(f"UPDATE inbox SET acked=1 WHERE id IN ({marks})", tuple(ids))

    # ---- long-term memory ----------------------------------------------------
    def add_memory(self, service: str, run_id: str, content: dict) -> None:
        self._exec(
            "INSERT INTO memories (service, run_id, created_at, content) VALUES (?,?,?,?)",
            (service, run_id, time.time(), json.dumps(content)),
        )

    def recall(self, services: list[str], ttl_days: int, limit: int = 3) -> list[dict]:
        if not services:
            return []
        now = time.time()
        marks = ",".join("?" * len(services))
        rows = self._rows(
            f"SELECT content, created_at FROM memories WHERE service IN ({marks}) AND created_at >= ?"
            " ORDER BY created_at DESC LIMIT ?",
            (*services, now - ttl_days * 86400, limit),
        )
        return [{**json.loads(r["content"]), "age_days": round((now - r["created_at"]) / 86400, 1)} for r in rows]

    # ---- operations ------------------------------------------------------------
    def ping(self) -> bool:
        return self._rows("SELECT 1")[0][0] == 1

    def status_counts(self) -> dict[str, int]:
        return {r["status"]: r["n"] for r in self._rows("SELECT status, COUNT(*) AS n FROM runs GROUP BY status")}

    def event_counts(self) -> dict[str, int]:
        return {r["type"]: r["n"] for r in self._rows("SELECT type, COUNT(*) AS n FROM events GROUP BY type")}
