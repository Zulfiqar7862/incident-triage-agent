"""Provider-neutral LLM interface.

The runtime keeps history in one neutral format:
  {"role": "user", "content": str}
  {"role": "assistant", "text": str, "tool_calls": [{"id", "name", "args"}], "raw": {...}?}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str, "is_error": bool}
and each adapter converts it to its provider's wire format. "raw" holds provider
data that must be sent back verbatim (Gemini thought signatures).

Plain httpx keeps the dependency surface small and every request easy to read.
Every adapter accepts an httpx transport so tests can run against a mocked API.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field

import httpx

from app.config import ConfigError, Settings


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


RETRYABLE_STATUS = (408, 409, 429, 500, 502, 503, 504, 529)


def _client(timeout: float, transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0), transport=transport)


class LLMTransientError(Exception):
    """Rate limit, overload, timeout: the runtime retries with backoff."""

    def __init__(self, message: str, retry_after_s: float | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Prefer Retry-After, then Gemini's retryDelay in the error body."""
    ra = response.headers.get("retry-after")
    if ra:
        try:
            return max(0.0, float(ra))
        except ValueError:
            pass
    try:
        details = (response.json().get("error") or {}).get("details") or []
    except ValueError:
        details = []
    for d in details:
        delay = d.get("retryDelay") if isinstance(d, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return max(0.0, float(delay[:-1]))
            except ValueError:
                pass
    # No Retry-After / retryDelay: let the runtime decide. It lengthens backoff when
    # the error text mentions quota, without forcing a 30s sleep that breaks unit tests.
    return None


async def _post(client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> dict:
    try:
        r = await client.post(url, headers=headers, json=payload)
    except httpx.TransportError as e:  # includes timeouts
        raise LLMTransientError(f"network error: {e!r}") from e
    if r.status_code in RETRYABLE_STATUS:
        raise LLMTransientError(f"HTTP {r.status_code}: {r.text[:300]}", _retry_after_seconds(r))
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:800]}")
    try:
        return r.json()
    except ValueError as e:
        raise LLMTransientError(f"invalid JSON from provider: {r.text[:200]}") from e


# ---- Gemini (Google AI / Generative Language API) ------------------------------------------
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Documented placeholder for function calls Gemini did not generate itself (e.g. history
# written by another provider). Real signatures from Gemini are always replayed verbatim.
GEMINI_DUMMY_SIGNATURE = "skip_thought_signature_validator"
GEMINI_BLOCKED = {"SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"}


def to_gemini(messages: list[dict]) -> list[dict]:
    contents: list[dict] = []
    gemini_ids: set[str] = set()  # call ids Gemini itself issued (echoed back in functionResponse)

    def push(role: str, parts: list[dict]) -> None:
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": list(parts)})

    for m in messages:
        if m["role"] == "user":
            push("user", [{"text": m["content"]}])
        elif m["role"] == "assistant":
            raw = m.get("raw") or {}
            if raw.get("provider") == "gemini" and raw.get("parts"):
                parts = raw["parts"]  # verbatim, including thoughtSignature fields
                gemini_ids |= {p["functionCall"]["id"] for p in parts if p.get("functionCall", {}).get("id")}
            else:
                parts = [{"text": m["text"]}] if m.get("text") else []
                for i, c in enumerate(m.get("tool_calls", [])):
                    part: dict = {"functionCall": {"name": c["name"], "args": c["args"]}}
                    if i == 0:
                        part["thoughtSignature"] = GEMINI_DUMMY_SIGNATURE
                    parts.append(part)
                parts = parts or [{"text": "(no output)"}]
            push("model", parts)
        elif m["role"] == "tool":
            response = {"error": m["content"]} if m.get("is_error") else {"result": m["content"]}
            fr = {"name": m["name"], "response": response}
            if m["tool_call_id"] in gemini_ids:
                fr["id"] = m["tool_call_id"]
            push("user", [{"functionResponse": fr}])
    # Function responses go before any text in the same user turn.
    for c in contents:
        if c["role"] == "user":
            c["parts"].sort(key=lambda p: 0 if "functionResponse" in p else 1)
    return contents


def from_gemini(data: dict, model: str) -> LLMResponse:
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "unknown")
        raise LLMError(f"Gemini returned no candidates (prompt blocked: {reason})")
    cand = candidates[0]
    parts = (cand.get("content") or {}).get("parts") or []
    finish = cand.get("finishReason", "")
    text = "\n".join(p["text"] for p in parts if "text" in p and not p.get("thought")).strip()
    calls = []
    for p in parts:
        fc = p.get("functionCall")
        if fc:
            calls.append(ToolCall(fc.get("id") or f"gemcall_{uuid.uuid4().hex[:12]}", fc["name"], fc.get("args") or {}))
    if finish in GEMINI_BLOCKED and not calls and not text:
        raise LLMError(f"Gemini stopped the response (finishReason={finish})")
    if finish == "MALFORMED_FUNCTION_CALL" and not calls:
        # The runtime nudges the model to try again when a turn has no tool calls.
        text = (
            text + "\n" if text else ""
        ) + "(The previous function call was malformed; please retry it with valid JSON arguments.)"
    usage = data.get("usageMetadata") or {}
    out_tokens = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
    raw = {"provider": "gemini", "parts": [p for p in parts if not p.get("thought")]} if parts else None
    return LLMResponse(text, calls, usage.get("promptTokenCount", 0), out_tokens, data.get("modelVersion", model), raw)


class GeminiLLM:
    provider = "gemini"

    def __init__(
        self,
        model: str,
        api_key: str,
        timeout: float,
        max_output_tokens: int = 8192,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.model = model
        self.max_output_tokens = max_output_tokens
        self._headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        self._client = _client(timeout, transport)

    async def complete(
        self, system: str, messages: list[dict], tools: list[dict], state: dict | None = None
    ) -> LLMResponse:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": to_gemini(messages),
            "tools": [
                {
                    "functionDeclarations": [
                        {"name": t["name"], "description": t["description"], "parametersJsonSchema": t["input_schema"]}
                        for t in tools
                    ]
                }
            ],
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            "generationConfig": {"maxOutputTokens": self.max_output_tokens},
        }
        data = await _post(self._client, GEMINI_URL.format(model=self.model), self._headers, payload)
        return from_gemini(data, self.model)


# ---- Anthropic ---------------------------------------------------------------------------------
def to_anthropic(messages: list[dict]) -> list[dict]:
    out: list[dict] = []

    def push(role: str, blocks: list[dict]) -> None:
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": blocks})

    for m in messages:
        if m["role"] == "user":
            push("user", [{"type": "text", "text": m["content"]}])
        elif m["role"] == "assistant":
            blocks = [{"type": "text", "text": m["text"]}] if m.get("text") else []
            blocks += [
                {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]}
                for c in m.get("tool_calls", [])
            ]
            push("assistant", blocks or [{"type": "text", "text": "(no output)"}])
        elif m["role"] == "tool":
            push(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": m["tool_call_id"],
                        "content": m["content"],
                        "is_error": bool(m.get("is_error")),
                    }
                ],
            )
    for msg in out:  # tool_result blocks must come before text in a user turn
        if msg["role"] == "user":
            msg["content"].sort(key=lambda b: 0 if b["type"] == "tool_result" else 1)
    return out


class AnthropicLLM:
    provider = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str,
        timeout: float,
        max_output_tokens: int = 8192,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.model = model
        self.max_output_tokens = max_output_tokens
        self._headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        self._client = _client(timeout, transport)

    async def complete(
        self, system: str, messages: list[dict], tools: list[dict], state: dict | None = None
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "system": system,
            "messages": to_anthropic(messages),
            "tools": [
                {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in tools
            ],
        }
        data = await _post(self._client, "https://api.anthropic.com/v1/messages", self._headers, payload)
        blocks = data.get("content", [])
        text = "\n".join(b["text"] for b in blocks if b.get("type") == "text").strip()
        calls = [ToolCall(b["id"], b["name"], b.get("input") or {}) for b in blocks if b.get("type") == "tool_use"]
        usage = data.get("usage", {})
        return LLMResponse(
            text, calls, usage.get("input_tokens", 0), usage.get("output_tokens", 0), data.get("model", self.model)
        )


# ---- OpenAI ------------------------------------------------------------------------------------
def to_openai(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            msg = {"role": "assistant", "content": m.get("text") or None}
            if m.get("tool_calls"):
                msg["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": json.dumps(c["args"])},
                    }
                    for c in m["tool_calls"]
                ]
            out.append(msg)
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
    return out


class OpenAILLM:
    provider = "openai"

    def __init__(
        self,
        model: str,
        api_key: str,
        timeout: float,
        max_output_tokens: int = 8192,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.model = model
        self.max_output_tokens = max_output_tokens
        self._headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
        self._client = _client(timeout, transport)

    async def complete(
        self, system: str, messages: list[dict], tools: list[dict], state: dict | None = None
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "messages": [{"role": "system", "content": system}] + to_openai(messages),
            "tools": [
                {
                    "type": "function",
                    "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
                }
                for t in tools
            ],
        }
        data = await _post(self._client, "https://api.openai.com/v1/chat/completions", self._headers, payload)
        msg = data["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            raw = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {"_unparseable_arguments": raw}  # validation fails; the agent sees the error and retries
            calls.append(ToolCall(tc["id"], tc["function"]["name"], args))
        usage = data.get("usage", {})
        return LLMResponse(
            (msg.get("content") or "").strip(),
            calls,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            data.get("model", self.model),
        )


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

    @property
    def _client(self):
        return self._active._client

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
                import logging

                logging.getLogger("llm").warning(
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


# ---- factory -----------------------------------------------------------------------------------
def _gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def resolve_provider(settings: Settings) -> str:
    provider = settings.llm_provider
    if provider == "auto":
        if _gemini_key():
            provider = "gemini"
        elif os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        else:
            provider = "scripted"
    if provider == "scripted" and settings.require_llm:
        raise ConfigError(
            "REQUIRE_LLM is true but no model is configured. Set GEMINI_API_KEY (or another provider's key)."
        )
    return provider


def make_llm(settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
    provider = resolve_provider(settings)
    if provider == "gemini":
        key = _gemini_key()
        if not key:
            raise ConfigError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
        primary = GeminiLLM(
            settings.gemini_model, key, settings.llm_timeout_s, settings.llm_max_output_tokens, transport
        )
        fb_name = (settings.gemini_fallback_model or "").strip()
        if fb_name and fb_name != settings.gemini_model:
            fallback = GeminiLLM(fb_name, key, settings.llm_timeout_s, settings.llm_max_output_tokens, transport)
            return GeminiWithFallback(primary, fallback)
        return primary
    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ConfigError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
        return AnthropicLLM(
            settings.anthropic_model,
            os.environ["ANTHROPIC_API_KEY"],
            settings.llm_timeout_s,
            settings.llm_max_output_tokens,
            transport,
        )
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise ConfigError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
        return OpenAILLM(
            settings.openai_model,
            os.environ["OPENAI_API_KEY"],
            settings.llm_timeout_s,
            settings.llm_max_output_tokens,
            transport,
        )
    from app.scripted import ScriptedPolicy

    return ScriptedPolicy(delay_s=settings.scripted_delay_s)
