"""Provider-neutral LLM value types shared by the agent loop and every adapter.

Adapters in ``app.llm`` convert these to and from each provider's wire format;
the application layer only ever sees these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    raw: dict | None = None  # provider data to replay on the next request


class LLMError(Exception):
    """Non-retryable (bad request, auth, safety block)."""


class LLMTransientError(Exception):
    """Rate limit, overload, timeout: the runtime retries with backoff."""

    def __init__(self, message: str, retry_after_s: float | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s
