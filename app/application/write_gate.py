"""Build pending approval / input payloads and apply write-confidence policy."""

from __future__ import annotations

import time
from typing import Any

from app.domain.policy import evaluate_write_confidence
from app.llm import ToolCall
from app.tools import TOOLS, ToolArgsError, ToolSpec, enrich_pending


def build_gate_or_block(
    st: dict,
    call: ToolCall,
    spec: ToolSpec,
    step: int,
    *,
    min_write_confidence: float,
    resolve_service: Any,
    emit: Any,
) -> dict | tuple[str, bool, dict]:
    """Return enriched pending dict, or (error_content, is_error, meta) tuple.

    ``resolve_service(service_name)`` raises ToolError for unknown services.
    ``emit(st, type, payload)`` records policy blocks.
    """
    from app.mock_env import ToolError

    try:
        args = spec.parse(call.args).model_dump()
    except ToolArgsError as e:
        return (f"Invalid arguments for {call.name}: {e}", True, {})

    if "service" in args:
        try:
            resolve_service(args["service"])
        except ToolError as e:
            emit(
                st,
                "policy.blocked",
                {
                    "id": call.id,
                    "tool": call.name,
                    "reason": "unknown_service",
                    "service": args.get("service"),
                },
            )
            return (str(e), True, {})

    if spec.kind == "write":
        decision = evaluate_write_confidence(float(args["confidence"]), min_write_confidence)
        if not decision.allowed:
            emit(
                st,
                "policy.blocked",
                {
                    "id": call.id,
                    "tool": call.name,
                    "confidence": decision.confidence,
                    "min_confidence": decision.floor,
                },
            )
            return (decision.blocked_message or "Blocked by policy", True, {})
        pending = {
            "kind": "approval",
            "tool_call_id": call.id,
            "tool": call.name,
            "args": args,
            "step": step,
            "requested_at": time.time(),
            "executing": False,
        }
        return enrich_pending(pending)

    pending = {
        "kind": "input",
        "tool_call_id": call.id,
        "tool": call.name,
        "args": args,
        "question": args["question"],
        "step": step,
        "requested_at": time.time(),
    }
    return enrich_pending(pending)


def tool_spec(name: str) -> ToolSpec:
    return TOOLS[name]
