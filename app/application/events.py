"""Run event recording: one place that appends audit events and status changes."""

from __future__ import annotations

import json
import logging

from app.domain.labels import status_words
from app.domain.ports import RunStorePort

log = logging.getLogger("agent")


class RunEventRecorder:
    """Appends hash-chained events and persists status transitions (Observer source).

    Every event lands in the Store's append-only log; the SSE endpoint and the
    UI observe that log. Nothing else publishes run events.
    """

    def __init__(self, store: RunStorePort):
        self._store = store

    def emit(self, st: dict, type_: str, payload: dict) -> None:
        payload = {"step": st["step"], **payload}
        self._store.append_event(st["run_id"], type_, payload)
        log.info(json.dumps({"run": st["run_id"], "event": type_, "step": st["step"]}))

    def set_status(self, st: dict, status: str, reason: str | None = None) -> None:
        st["status"], st["status_reason"] = status, reason
        self._store.save(st)
        self.emit(st, "run.status", {"status": status, "status_label": status_words(status), "reason": reason})
