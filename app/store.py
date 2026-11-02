"""SQLite persistence: run checkpoints, the append-only event log the UI streams,
an operator inbox, and long-term memory. Every agent step is checkpointed here,
which is what lets a run survive a process restart."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

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
    payload TEXT NOT NULL
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

    def save(self, state: dict) -> None:
        """Write a checkpoint. The latest checkpoint is the run's source of truth."""
        state["checkpoint_version"] = state.get("checkpoint_version", 0) + 1
        self._exec(
            "UPDATE runs SET status=?, updated_at=?, checkpoint_version=?, state=? WHERE id=?",
            (state["status"], time.time(), state["checkpoint_version"], json.dumps(state), state["run_id"]),
        )

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
    def append_event(self, run_id: str, type_: str, payload: dict[str, Any]) -> dict:
        ts = time.time()
        cur = self._exec(
            "INSERT INTO events (run_id, ts, type, payload) VALUES (?,?,?,?)",
            (run_id, ts, type_, json.dumps(payload, default=str)),
        )
        return {"seq": cur.lastrowid, "run_id": run_id, "ts": ts, "type": type_, "payload": payload}

    def events_since(self, run_id: str, after: int = 0, limit: int = 500) -> list[dict]:
        rows = self._rows(
            "SELECT seq, run_id, ts, type, payload FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
            (run_id, after, limit),
        )
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

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
        return [
            {**json.loads(r["content"]), "age_days": round((now - r["created_at"]) / 86400, 1)}
            for r in rows
        ]
