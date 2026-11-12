"""``TelemetryPort`` adapter: Prometheus counters plus OpenTelemetry GenAI spans."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

from app.infrastructure.observability import metrics, tracing


class PrometheusOtelTelemetry:
    """Adapter from the application's ``TelemetryPort`` to Prometheus and OTel."""

    def span(self, name: str, **attrs: Any) -> AbstractContextManager[dict[str, Any]]:
        return tracing.span(name, **attrs)

    def llm_call(self, model: str, input_tokens: int, output_tokens: int, cost_usd: float, latency_s: float) -> None:
        metrics.record_llm_call(model, input_tokens, output_tokens, cost_usd, latency_s)

    def tool_call(self, tool: str, is_error: bool) -> None:
        metrics.record_tool(tool, is_error)

    def approval(self, decision: str) -> None:
        metrics.record_approval(decision)

    def export(self, run_counts: dict[str, int], event_counts: dict[str, int]) -> tuple[bytes, str]:
        """Mirror Store totals into gauges, then render the Prometheus text format."""
        metrics.set_run_counts(run_counts)
        metrics.set_event_counts(event_counts)
        return metrics.render_metrics()
