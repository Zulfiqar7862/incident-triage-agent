"""Optional Langfuse integration. No-op unless LANGFUSE_PUBLIC_KEY + SECRET are set."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("observability.langfuse")
_client: Any = None


def configure_langfuse(public_key: str, secret_key: str, host: str) -> None:
    global _client
    if not public_key or not secret_key:
        _client = None
        return
    try:
        from langfuse import Langfuse

        _client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        log.info("langfuse enabled host=%s", host)
    except Exception as e:  # noqa: BLE001
        log.warning("langfuse init failed: %s", e)
        _client = None


def trace_generation(**kwargs: Any) -> None:
    if _client is None:
        return
    try:
        _client.generation(**kwargs)
    except Exception as e:  # noqa: BLE001
        log.debug("langfuse generation failed: %s", e)


def shutdown_langfuse() -> None:
    global _client
    if _client is not None:
        try:
            _client.flush()
        except Exception:  # noqa: BLE001
            pass
        _client = None
