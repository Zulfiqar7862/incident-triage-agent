"""Budget policy: which run ceilings have crossed the alert ratio (pure)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetCrossing:
    budget: str
    used: float
    limit: float


def budget_crossings(
    st: dict, *, ratio: float, default_cost_cap: float, already_alerted: set[str]
) -> list[BudgetCrossing]:
    """Return newly crossed budgets (steps, tokens, cost) in a fixed order."""
    checks: list[tuple[str, float, float]] = [
        ("steps", st["step"], st["max_steps"]),
        ("tokens", st["usage"]["input_tokens"] + st["usage"]["output_tokens"], st["max_run_tokens"]),
    ]
    cost_cap = st.get("max_run_cost_usd", default_cost_cap)
    if cost_cap > 0:
        checks.append(("cost_usd", st["usage"]["cost_usd"], cost_cap))
    return [
        BudgetCrossing(name, used, limit)
        for name, used, limit in checks
        if limit > 0 and name not in already_alerted and used >= limit * ratio
    ]
