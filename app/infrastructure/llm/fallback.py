"""Decorator over two Gemini models: switch to the fallback on quota exhaustion."""

from __future__ import annotations

import logging

from app.domain.llm import LLMResponse, LLMTransientError
from app.infrastructure.llm.gemini import GeminiLLM

log = logging.getLogger("llm")


class GeminiWithFallback:
    """Primary Gemini model with automatic fallback on 429/quota exhaustion.

    Free-tier flash often returns 429; flash-lite usually still works. On a
    retryable 429 (or quota-flavoured transient error) we switch models for the
    rest of the process lifetime and emit a clear log line. Non-quota transient
    errors still bubble so the runtime can back off.
    """

    provider = "gemini"

    def __init__(self, primary: GeminiLLM, fallback: GeminiLLM | None):
        self._primary = primary
        self._fallback = fallback
        self._active = primary
        self._switched = False

    @property
    def model(self) -> str:
        return self._active.model

    async def aclose(self) -> None:
        """Close both models' HTTP clients."""
        await self._primary.aclose()
        if self._fallback is not None:
            await self._fallback.aclose()

    async def complete(
        self, system: str, messages: list[dict], tools: list[dict], state: dict | None = None
    ) -> LLMResponse:
        try:
            return await self._active.complete(system, messages, tools, state)
        except LLMTransientError as e:
            if (
                self._fallback is not None
                and not self._switched
                and self._active is self._primary
                and self._is_quota(e)
            ):
                log.warning(
                    "gemini primary model %s hit quota/429; falling back to %s",
                    self._primary.model,
                    self._fallback.model,
                )
                self._active = self._fallback
                self._switched = True
                return await self._active.complete(system, messages, tools, state)
            raise

    @staticmethod
    def _is_quota(e: LLMTransientError) -> bool:
        msg = str(e).lower()
        return "429" in msg or "quota" in msg or "rate limit" in msg or "resource_exhausted" in msg
