"""Opening human gates: validate a write or question and build the pending decision."""

from __future__ import annotations

import time
from collections.abc import Callable

from app.application.events import RunEventRecorder
from app.application.ports import PendingPresenter, ToolOutcome
from app.application.tools import ToolArgsError, ToolSpec
from app.domain.errors import ToolError
from app.domain.llm import ToolCall
from app.domain.policy import evaluate_write_confidence

ServiceResolver = Callable[[str], object]
"""Raises ``ToolError`` for an unknown service name (``ClusterPort.validate_service``)."""


class WriteGate:
    """Policy check in front of every production change and operator question.

    Returns either the pending decision to park the run on, or a ``ToolOutcome``
    error the model sees (bad args, unknown service, confidence below the floor).
    """

    def __init__(
        self,
        *,
        min_write_confidence: float,
        events: RunEventRecorder,
        present_pending: PendingPresenter = dict,
    ) -> None:
        self._floor = min_write_confidence
        self._events = events
        self._present = present_pending

    def open(
        self, st: dict, call: ToolCall, spec: ToolSpec, step: int, resolve_service: ServiceResolver
    ) -> dict | ToolOutcome:
        """Return the enriched pending dict, or an error outcome when policy blocks it."""
        try:
            args = spec.parse(call.args).model_dump()
        except ToolArgsError as e:
            return (f"Invalid arguments for {call.name}: {e}", True, {})

        if "service" in args:
            try:
                resolve_service(args["service"])
            except ToolError as e:
                self._events.emit(
                    st,
                    "policy.blocked",
                    {"id": call.id, "tool": call.name, "reason": "unknown_service", "service": args.get("service")},
                )
                return (str(e), True, {})

        if spec.kind == "write":
            return self._approval(st, call, args, step)
        return self._present(
            {
                "kind": "input",
                "tool_call_id": call.id,
                "tool": call.name,
                "args": args,
                "question": args["question"],
                "step": step,
                "requested_at": time.time(),
            }
        )

    def _approval(self, st: dict, call: ToolCall, args: dict, step: int) -> dict | ToolOutcome:
        decision = evaluate_write_confidence(float(args["confidence"]), self._floor)
        if not decision.allowed:
            self._events.emit(
                st,
                "policy.blocked",
                {"id": call.id, "tool": call.name, "confidence": decision.confidence, "min_confidence": decision.floor},
            )
            return (decision.blocked_message or "Blocked by policy", True, {})
        return self._present(
            {
                "kind": "approval",
                "tool_call_id": call.id,
                "tool": call.name,
                "args": args,
                "step": step,
                "requested_at": time.time(),
                "executing": False,
            }
        )
