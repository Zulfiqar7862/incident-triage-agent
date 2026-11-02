"""Provider-neutral LLM interface.

The runtime keeps history in one neutral format:
  {"role": "user", "content": str}
  {"role": "assistant", "text": str, "tool_calls": [{"id", "name", "args"}]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str, "is_error": bool}
and each adapter converts it to its provider's wire format. Plain httpx keeps the
dependency surface small and the requests easy to read.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import httpx

from .config import Settings


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


class LLMTransientError(Exception):
    """Rate limit, overload, timeout: the runtime retries with backoff."""


class LLMError(Exception):
    """Non-retryable (bad request, auth)."""


async def _post(client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> dict:
    try:
        r = await client.post(url, headers=headers, json=payload)
    except httpx.TransportError as e:  # includes timeouts
        raise LLMTransientError(f"network error: {e!r}") from e
    if r.status_code in (408, 409, 429, 500, 502, 503, 504, 529):
        raise LLMTransientError(f"HTTP {r.status_code}: {r.text[:300]}")
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:500]}")
    return r.json()


# ---- Anthropic ------------------------------------------------------------------------
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
            blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]} for c in m.get("tool_calls", [])]
            push("assistant", blocks or [{"type": "text", "text": "(no output)"}])
        elif m["role"] == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"], "is_error": bool(m.get("is_error"))}])
    # The API wants tool_result blocks before any text in a user turn.
    for msg in out:
        if msg["role"] == "user":
            msg["content"].sort(key=lambda b: 0 if b["type"] == "tool_result" else 1)
    return out


class AnthropicLLM:
    provider = "anthropic"

    def __init__(self, model: str, api_key: str, timeout: float):
        self.model = model
        self._headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        self._client = httpx.AsyncClient(timeout=timeout)

    async def complete(self, system: str, messages: list[dict], tools: list[dict], state: dict | None = None) -> LLMResponse:
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "system": system,
            "messages": to_anthropic(messages),
            "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in tools],
        }
        data = await _post(self._client, "https://api.anthropic.com/v1/messages", self._headers, payload)
        blocks = data.get("content", [])
        text = "\n".join(b["text"] for b in blocks if b.get("type") == "text").strip()
        calls = [ToolCall(b["id"], b["name"], b.get("input") or {}) for b in blocks if b.get("type") == "tool_use"]
        usage = data.get("usage", {})
        return LLMResponse(text, calls, usage.get("input_tokens", 0), usage.get("output_tokens", 0), data.get("model", self.model))


# ---- OpenAI -----------------------------------------------------------------------------
def to_openai(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            msg = {"role": "assistant", "content": m.get("text") or None}
            if m.get("tool_calls"):
                msg["tool_calls"] = [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                    for c in m["tool_calls"]
                ]
            out.append(msg)
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
    return out


class OpenAILLM:
    provider = "openai"

    def __init__(self, model: str, api_key: str, timeout: float):
        self.model = model
        self._headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
        self._client = httpx.AsyncClient(timeout=timeout)

    async def complete(self, system: str, messages: list[dict], tools: list[dict], state: dict | None = None) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + to_openai(messages),
            "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools],
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
        return LLMResponse((msg.get("content") or "").strip(), calls, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), data.get("model", self.model))


def make_llm(settings: Settings):
    provider = settings.llm_provider
    if provider == "auto":
        provider = "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "openai" if os.getenv("OPENAI_API_KEY") else "scripted"
    if provider == "anthropic":
        return AnthropicLLM(settings.anthropic_model, os.environ["ANTHROPIC_API_KEY"], settings.llm_timeout_s)
    if provider == "openai":
        return OpenAILLM(settings.openai_model, os.environ["OPENAI_API_KEY"], settings.llm_timeout_s)
    from .scripted import ScriptedPolicy

    return ScriptedPolicy(delay_s=settings.scripted_delay_s)
