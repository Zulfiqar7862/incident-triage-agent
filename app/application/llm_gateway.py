"""LLM calls with retry/backoff and GenAI tracing, independent of the provider."""

from __future__ import annotations

import asyncio

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.application.events import RunEventRecorder
from app.config import Settings
from app.context import SYSTEM_PROMPT
from app.domain.llm import LLMResponse, LLMTransientError
from app.domain.ports import LLMPort
from app.observability.tracing import span as otel_span


class LLMGateway:
    """Wraps an ``LLMPort`` Strategy with the runtime's retry policy."""

    def __init__(self, llm: LLMPort, settings: Settings, events: RunEventRecorder, tools: list[dict]):
        self.llm = llm
        self._settings = settings
        self._events = events
        self._tools = tools

    async def complete(self, st: dict, messages: list[dict]) -> LLMResponse:
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
                    with otel_span(
                        "chat",
                        **{
                            "gen_ai.request.model": getattr(self.llm, "model", ""),
                            "gen_ai.provider.name": getattr(self.llm, "provider", ""),
                            "run.id": st["run_id"],
                            "gen_ai.operation.name": "chat",
                        },
                    ) as sp:
                        resp = await self.llm.complete(SYSTEM_PROMPT, messages, self._tools, st)
                        sp["gen_ai.usage.input_tokens"] = resp.input_tokens
                        sp["gen_ai.usage.output_tokens"] = resp.output_tokens
                        sp["gen_ai.response.model"] = resp.model
                        self._events.emit(st, "gen_ai.span", {k: sp[k] for k in sp if k != "error.message"})
                        return resp
                except LLMTransientError as e:
                    delay = s.llm_backoff_s * 2 ** max(attempt - 1, 0)
                    if e.retry_after_s is not None:
                        delay = e.retry_after_s
                    elif "quota" in str(e).lower() or "rate limit" in str(e).lower():
                        delay = delay * 10
                    delay = min(max(delay, s.llm_backoff_s), s.llm_max_backoff_s)
                    self._events.emit(st, "llm.retry", {"attempt": attempt, "error": str(e)[:200], "retry_in_s": delay})
                    if e.retry_after_s is not None:
                        await asyncio.sleep(min(e.retry_after_s, s.llm_max_backoff_s))
                    raise
        raise AssertionError("unreachable: AsyncRetrying re-raises the last error")
