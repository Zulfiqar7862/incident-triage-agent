"""OpenTelemetry GenAI-style spans without requiring the OTel SDK.

Spans are always attached to the run event log (gen_ai.span). When
OTLP_ENDPOINT is set, they are also POSTed as an OTLP/HTTP JSON ExportTraceServiceRequest.
The exporter is off by default so local demos stay dependency-free.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import httpx

log = logging.getLogger("otel")

_enabled = False
_endpoint = ""
_service_name = "incident-agent"
_lock = threading.Lock()
_pending: list[dict] = []


def configure_tracing(endpoint: str = "", service_name: str = "incident-agent") -> None:
    global _enabled, _endpoint, _service_name
    _endpoint = (endpoint or os.getenv("OTLP_ENDPOINT") or "").rstrip("/")
    _service_name = service_name or "incident-agent"
    _enabled = bool(_endpoint)
    if _enabled:
        log.info("OTLP exporter enabled -> %s", _endpoint)


def shutdown_tracing() -> None:
    _flush()


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
    """Yield a mutable span dict. Caller may set usage / status fields before exit."""
    s: dict[str, Any] = {
        "trace_id": uuid.uuid4().hex,
        "span_id": uuid.uuid4().hex[:16],
        "name": name,
        "gen_ai.operation.name": name,
        "gen_ai.system": attrs.pop("gen_ai.system", "incident-agent"),
        "start_time_unix_nano": time.time_ns(),
        **attrs,
    }
    t0 = time.perf_counter()
    try:
        yield s
        s.setdefault("status", "ok")
    except Exception as e:  # noqa: BLE001
        s["status"] = "error"
        s["error.type"] = type(e).__name__
        s["error.message"] = str(e)[:300]
        raise
    finally:
        s["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        s["end_time_unix_nano"] = time.time_ns()
        if _enabled:
            with _lock:
                _pending.append(dict(s))
            if len(_pending) >= 4:
                _flush()


def _flush() -> None:
    if not _enabled:
        return
    with _lock:
        batch = list(_pending)
        _pending.clear()
    if not batch:
        return
    # Minimal OTLP/HTTP JSON body (trace partial success is fine for a demo).
    resource_spans = [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": _service_name}},
        ]},
        "scopeSpans": [{
            "scope": {"name": "incident-agent", "version": "1.0.0"},
            "spans": [_to_otlp(s) for s in batch],
        }],
    }]
    try:
        httpx.post(
            f"{_endpoint}/v1/traces",
            json={"resourceSpans": resource_spans},
            timeout=2.0,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("OTLP export failed: %s", e)


def _to_otlp(s: dict) -> dict:
    attrs = []
    for k, v in s.items():
        if k in ("trace_id", "span_id", "name", "start_time_unix_nano", "end_time_unix_nano", "latency_ms", "status"):
            continue
        attrs.append(_attr(k, v))
    attrs.append(_attr("latency_ms", s.get("latency_ms")))
    status_code = 2 if s.get("status") == "error" else 1
    return {
        "traceId": s["trace_id"],
        "spanId": s["span_id"],
        "name": s["name"],
        "kind": 1,
        "startTimeUnixNano": str(s["start_time_unix_nano"]),
        "endTimeUnixNano": str(s["end_time_unix_nano"]),
        "attributes": attrs,
        "status": {"code": status_code},
    }


def _attr(key: str, value: Any) -> dict:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)[:500]}}
