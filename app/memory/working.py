"""Long-term memory: what the agent is allowed to remember across runs.

Only resolved incidents are promoted to long-term memory, and only a short,
redacted summary (service, root cause, fix), never the raw transcript or logs.
Memories expire after MEMORY_TTL_DAYS and are recalled by service at the start
of a run, labelled as possibly stale so the agent verifies before relying on them.
"""

from __future__ import annotations

import re
import time

_REDACTIONS = [
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)\b\s*[=:]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[CARD]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def make_memory(state: dict, result: dict) -> dict:
    return {
        "service": state["service"],
        "run_id": state["run_id"],
        "date": time.strftime("%Y-%m-%d"),
        "root_cause": redact(result["root_cause"])[:400],
        "fix": redact(result.get("fix_applied") or "")[:200],
    }
