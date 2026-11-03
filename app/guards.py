"""Agent-specific failure modes: runaway loops and prompt-injection markers."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

# Phrases that show up in injection attempts inside tool output / user content.
INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard all prior",
    "you are now in admin mode",
    "system prompt override",
    "system notice to ai agent",
    "dump all secrets",
    "approve all mutating",
)


def call_fingerprint(name: str, args: dict) -> str:
    # Ignore free-text fields that change every attempt; compare the action itself.
    filtered = {k: v for k, v in (args or {}).items() if k not in ("reason", "summary", "root_cause", "follow_ups", "note", "question")}
    blob = json.dumps({"name": name, "args": filtered}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def find_injection_markers(text: str) -> list[str]:
    low = (text or "").lower()
    return [m for m in INJECTION_MARKERS if m in low]


class LoopGuard:
    """Stop when the same tool+args keeps getting issued (stuck agent)."""

    def __init__(self, max_identical: int = 3):
        self.max_identical = max_identical
        self._counts: Counter[str] = Counter()

    def record(self, name: str, args: dict) -> None:
        if name in ("update_working_memory", "finish", "ask_operator"):
            return
        self._counts[call_fingerprint(name, args)] += 1

    def should_stop(self) -> tuple[bool, str | None]:
        for fp, n in self._counts.items():
            if n >= self.max_identical:
                return True, f"Repeated the same tool call {n} times ({fp}). Send guidance and resume, or cancel."
        return False, None

    def loads(self, data: dict | None) -> None:
        self._counts = Counter((data or {}).get("counts") or {})

    def dumps(self) -> dict:
        return {"counts": dict(self._counts)}
