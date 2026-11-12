"""Budget policy (pure): alert-ratio crossings and exhausted ceilings."""

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


def exhausted_budget(st: dict, *, default_cost_cap: float, hard_stop: bool) -> str | None:
    """Return the operator-facing reason when a run ceiling is used up, else ``None``.

    Checked at every step boundary, in a fixed order: steps, tokens, cost.
    """
    if st["step"] >= st["max_steps"]:
        return f"Step budget of {st['max_steps']} used up without finishing. " + (
            "Run cancelled." if hard_stop else "Review the trace, send guidance, and resume to grant 10 more steps."
        )
    if st["usage"]["input_tokens"] + st["usage"]["output_tokens"] >= st["max_run_tokens"]:
        return "Token budget for this run is used up." + (
            " Run cancelled." if hard_stop else " Resume to grant 50% more."
        )
    cost_cap = st.get("max_run_cost_usd", default_cost_cap)
    if default_cost_cap > 0 and st["usage"]["cost_usd"] >= cost_cap:
        return f"Cost budget of ${cost_cap:.2f} for this run is used up." + (
            " Run cancelled." if hard_stop else " Resume to raise it 50%."
        )
    return None
