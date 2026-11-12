"""Run event recording: the one place that appends audit events and status changes."""

from __future__ import annotations

import json
import logging

from app.domain.labels import status_words
from app.domain.ports import EventLog, RunRepository

log = logging.getLogger("agent")


class RunEventRecorder:
    """Appends hash-chained events and persists status transitions (Observer source).

    Every event lands in the append-only ``EventLog``; the SSE endpoint and the UI
    observe that log. Nothing else publishes run events.
    """

    def __init__(self, events: EventLog, runs: RunRepository) -> None:
        self._events = events
        self._runs = runs

    def emit(self, st: dict, type_: str, payload: dict) -> None:
        """Append ``type_`` with the current step number to the run's event log."""
        payload = {"step": st["step"], **payload}
        self._events.append_event(st["run_id"], type_, payload)
        log.info(json.dumps({"run": st["run_id"], "event": type_, "step": st["step"]}))

    def set_status(self, st: dict, status: str, reason: str | None = None) -> None:
        """Persist a status transition, then publish ``run.status``."""
        st["status"], st["status_reason"] = status, reason
        self._runs.save(st)
        self.emit(st, "run.status", {"status": status, "status_label": status_words(status), "reason": reason})
