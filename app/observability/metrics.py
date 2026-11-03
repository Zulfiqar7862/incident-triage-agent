"""Prometheus metrics for runs, tokens, cost, latency, and approvals."""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

LLM_CALLS = Counter("agent_llm_calls_total", "LLM calls", ["model"])
LLM_TOKENS = Counter("agent_llm_tokens_total", "Tokens", ["model", "direction"])
LLM_COST = Counter("agent_llm_cost_usd_total", "Estimated LLM cost (USD)")
LLM_LATENCY = Histogram("agent_llm_latency_seconds", "LLM latency", ["model"])
APPROVALS = Counter("agent_approvals_total", "Human gate decisions", ["decision"])
RUN_STATES = Gauge("agent_runs", "Runs by status", ["status"])
TOOL_CALLS = Counter("agent_tool_calls_total", "Tool invocations", ["tool", "error"])
EVENTS = Counter("agent_events_total", "Store event log by type", ["type"])


def record_llm_call(model: str, input_tokens: int, output_tokens: int, cost: float, latency_s: float) -> None:
    LLM_CALLS.labels(model=model or "unknown").inc()
    LLM_TOKENS.labels(model=model or "unknown", direction="input").inc(input_tokens)
    LLM_TOKENS.labels(model=model or "unknown", direction="output").inc(output_tokens)
    LLM_COST.inc(cost)
    LLM_LATENCY.labels(model=model or "unknown").observe(latency_s)


def record_approval(decision: str) -> None:
    APPROVALS.labels(decision=decision).inc()


def record_tool(tool: str, is_error: bool) -> None:
    TOOL_CALLS.labels(tool=tool or "unknown", error=str(bool(is_error)).lower()).inc()


def set_run_counts(counts: dict[str, int]) -> None:
    for status, n in counts.items():
        RUN_STATES.labels(status=status).set(n)


def set_event_counts(counts: dict[str, int]) -> None:
    # Counters can only increase; set via _value for scrape mirroring of Store.
    for type_, n in counts.items():
        EVENTS.labels(type=type_)._value.set(n)  # noqa: SLF001 — mirror Store totals


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
