"""Operator control flags and per-run gate locks shared by the run service and the graph."""

from __future__ import annotations

import threading

CONTROL_STATUS = {
    "cancel": ("cancelled", "Cancelled by operator"),
    "pause": ("paused", "Paused by operator at a step boundary"),
}
"""Control action -> (status, reason) applied at the next step boundary."""


class RunControls:
    """Pending ``pause`` / ``cancel`` requests, consumed once at the next step boundary."""

    def __init__(self) -> None:
        self._flags: dict[str, str] = {}

    def request(self, run_id: str, action: str) -> None:
        """Ask the run to stop at its next step boundary."""
        if action not in CONTROL_STATUS:
            raise ValueError(f"Unknown control action '{action}'")
        self._flags[run_id] = action

    def take(self, run_id: str) -> str | None:
        """Pop the pending action, if any."""
        return self._flags.pop(run_id, None)


class GateLocks:
    """One lock per run so approve / reject / double-clicks claim a gate exactly once.

    ``threading.Lock`` (not ``asyncio.Lock``) because the HTTP layer may call the
    service from worker threads (sync routes, TestClient); the critical section
    never awaits.
    """

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._mu = threading.Lock()

    def for_run(self, run_id: str) -> threading.Lock:
        with self._mu:
            lock = self._locks.get(run_id)
            if lock is None:
                lock = self._locks[run_id] = threading.Lock()
            return lock
