"""Model calls with retry/backoff, GenAI tracing, and usage accounting (provider-agnostic)."""

from __future__ import annotations

import asyncio
import time

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.application.context import SYSTEM_PROMPT
from app.application.events import RunEventRecorder
from app.application.ports import TelemetryPort
from app.core.config import Settings
from app.domain.llm import LLMResponse, LLMTransientError
from app.domain.ports import LLMPort


class LLMGateway:
    """Decorates an ``LLMPort`` Strategy with the runtime's retry policy and accounting.

    One reason to change: how a model call is made robust and measured. The
    provider adapters know nothing about retries, budgets, or audit events.
    """

    def __init__(
        self,
        llm: LLMPort,
        settings: Settings,
        events: RunEventRecorder,
        tools: list[dict],
        telemetry: TelemetryPort,
    ) -> None:
        self.llm = llm
        self._settings = settings
        self._events = events
        self._tools = tools
        self._telemetry = telemetry

    async def complete(self, st: dict, messages: list[dict], context_stats: dict) -> LLMResponse:
        """Call the model (with retries), then charge the run's usage and emit ``llm.call``."""
        t0 = time.perf_counter()
        resp = await self._complete_with_retry(st, messages)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        self._account(st, resp, latency_ms, context_stats)
        return resp

    def _account(self, st: dict, resp: LLMResponse, latency_ms: int, context_stats: dict) -> None:
        s = self._settings
        cost = (resp.input_tokens * s.cost_in_per_mtok + resp.output_tokens * s.cost_out_per_mtok) / 1e6
        usage = st["usage"]
        usage["llm_calls"] += 1
        usage["input_tokens"] += resp.input_tokens
        usage["output_tokens"] += resp.output_tokens
        usage["cost_usd"] = round(usage["cost_usd"] + cost, 6)
        usage["llm_ms"] += latency_ms
        self._events.emit(
            st,
            "llm.call",
            {
                "model": resp.model,
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "latency_ms": latency_ms,
                "cost_usd": round(cost, 6),
                "context": context_stats,
                "tool_calls": len(resp.tool_calls),
            },
        )
        self._telemetry.llm_call(resp.model, resp.input_tokens, resp.output_tokens, cost, latency_ms / 1000.0)

    async def _complete_with_retry(self, st: dict, messages: list[dict]) -> LLMResponse:
        s = self._settings
        attempt = 0
        async for attempt_ctl in AsyncRetrying(
            stop=stop_after_attempt(s.llm_max_attempts),
            wait=wait_exponential_jitter(initial=s.llm_backoff_s, max=s.llm_max_backoff_s),
            retry=retry_if_exception_type(LLMTransientError),
            reraise=True,
        ):
            with attempt_ctl:
                attempt += 1
                try:
                    return await self._traced_call(st, messages)
                except LLMTransientError as e:
                    await self._before_retry(st, attempt, e)
                    raise
        raise AssertionError("unreachable: AsyncRetrying re-raises the last error")

    async def _traced_call(self, st: dict, messages: list[dict]) -> LLMResponse:
        attrs = {
            "gen_ai.request.model": getattr(self.llm, "model", ""),
            "gen_ai.provider.name": getattr(self.llm, "provider", ""),
            "run.id": st["run_id"],
            "gen_ai.operation.name": "chat",
        }
        with self._telemetry.span("chat", **attrs) as sp:
            resp = await self.llm.complete(SYSTEM_PROMPT, messages, self._tools, st)
            sp["gen_ai.usage.input_tokens"] = resp.input_tokens
            sp["gen_ai.usage.output_tokens"] = resp.output_tokens
            sp["gen_ai.response.model"] = resp.model
            self._events.emit(st, "gen_ai.span", {k: sp[k] for k in sp if k != "error.message"})
            return resp

    async def _before_retry(self, st: dict, attempt: int, e: LLMTransientError) -> None:
        """Publish ``llm.retry``; honour a provider ``Retry-After`` on top of tenacity's wait."""
        s = self._settings
        delay = s.llm_backoff_s * 2 ** max(attempt - 1, 0)
        if e.retry_after_s is not None:
            delay = e.retry_after_s
        elif "quota" in str(e).lower() or "rate limit" in str(e).lower():
            delay = delay * 10
        delay = min(max(delay, s.llm_backoff_s), s.llm_max_backoff_s)
        self._events.emit(st, "llm.retry", {"attempt": attempt, "error": str(e)[:200], "retry_in_s": delay})
        if e.retry_after_s is not None:
            await asyncio.sleep(min(e.retry_after_s, s.llm_max_backoff_s))
