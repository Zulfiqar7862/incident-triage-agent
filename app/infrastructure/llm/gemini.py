"""Gemini (Google Generative Language API) adapter and wire-format converters."""

from __future__ import annotations

import uuid

import httpx

from app.domain.llm import LLMError, LLMResponse, ToolCall
from app.infrastructure.llm.http import make_client, post_json

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
        self._client = make_client(timeout, transport)

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
        data = await post_json(self._client, GEMINI_URL.format(model=self.model), self._headers, payload)
        return from_gemini(data, self.model)

    async def aclose(self) -> None:
        """Close the pooled HTTP client."""
        await self._client.aclose()
