"""Shared HTTP plumbing for the provider adapters (plain httpx, mockable transport).

The runtime keeps history in one neutral format:
  {"role": "user", "content": str}
  {"role": "assistant", "text": str, "tool_calls": [{"id", "name", "args"}], "raw": {...}?}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str, "is_error": bool}
and each adapter converts it to its provider's wire format. "raw" holds provider
data that must be sent back verbatim (Gemini thought signatures).
"""

from __future__ import annotations

import httpx

from app.domain.llm import LLMError, LLMTransientError

RETRYABLE_STATUS = (408, 409, 429, 500, 502, 503, 504, 529)


def make_client(timeout: float, transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0), transport=transport)


def retry_after_seconds(response: httpx.Response) -> float | None:
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


async def post_json(client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> dict:
    try:
        r = await client.post(url, headers=headers, json=payload)
    except httpx.TransportError as e:  # includes timeouts
        raise LLMTransientError(f"network error: {e!r}") from e
    if r.status_code in RETRYABLE_STATUS:
        raise LLMTransientError(f"HTTP {r.status_code}: {r.text[:300]}", retry_after_seconds(r))
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:800]}")
    try:
        return r.json()
    except ValueError as e:
        raise LLMTransientError(f"invalid JSON from provider: {r.text[:200]}") from e
