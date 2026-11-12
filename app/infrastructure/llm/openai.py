"""OpenAI Chat Completions adapter and wire-format converter."""

from __future__ import annotations

import json

import httpx

from app.domain.llm import LLMResponse, ToolCall
from app.infrastructure.llm.http import make_client, post_json


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
        self._client = make_client(timeout, transport)

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
        data = await post_json(self._client, "https://api.openai.com/v1/chat/completions", self._headers, payload)
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

    async def aclose(self) -> None:
        """Close the pooled HTTP client."""
        await self._client.aclose()
