"""Anthropic Messages API adapter and wire-format converter."""

from __future__ import annotations

import httpx

from app.domain.llm import LLMResponse, ToolCall
from app.infrastructure.llm.http import make_client, post_json


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
        self._client = make_client(timeout, transport)

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
        data = await post_json(self._client, "https://api.anthropic.com/v1/messages", self._headers, payload)
        blocks = data.get("content", [])
        text = "\n".join(b["text"] for b in blocks if b.get("type") == "text").strip()
        calls = [ToolCall(b["id"], b["name"], b.get("input") or {}) for b in blocks if b.get("type") == "tool_use"]
        usage = data.get("usage", {})
        return LLMResponse(
            text, calls, usage.get("input_tokens", 0), usage.get("output_tokens", 0), data.get("model", self.model)
        )

    async def aclose(self) -> None:
        """Close the pooled HTTP client."""
        await self._client.aclose()
