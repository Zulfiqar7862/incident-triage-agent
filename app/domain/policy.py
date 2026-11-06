"""Write/read tool gates and risk labels — pure policy decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RiskLevel = Literal["high", "low"]


def risk_for_kind(kind: str) -> RiskLevel:
    """Map tool kind to operator-facing risk. Writes are always high."""
    return "high" if kind == "write" else "low"


@dataclass(frozen=True)
class WriteGateDecision:
    """Outcome of the confidence floor check before opening an approval gate."""

    allowed: bool
    confidence: float
    floor: float
    reason: str | None = None

    @property
    def blocked_message(self) -> str | None:
        if self.allowed:
            return None
        return (
            f"Blocked by policy: confidence {self.confidence:.2f} is below the "
            f"{self.floor:.2f} required to propose a production change. "
            "Gather more evidence, or use ask_operator if you are unsure."
        )


def evaluate_write_confidence(confidence: float, floor: float) -> WriteGateDecision:
    """Confidence-based routing: don't page a human for a low-confidence guess."""
    if confidence < floor:
        return WriteGateDecision(
            allowed=False,
            confidence=confidence,
            floor=floor,
            reason="below_min_write_confidence",
        )
    return WriteGateDecision(allowed=True, confidence=confidence, floor=floor)
