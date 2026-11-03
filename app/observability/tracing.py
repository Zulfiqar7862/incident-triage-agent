"""OpenTelemetry tracing with GenAI semantic conventions. OTLP export is optional."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

log = logging.getLogger("observability.tracing")

_tracer = None
_provider = None


def configure_tracing(otlp_endpoint: str = "") -> None:
    global _tracer, _provider
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except Exception as e:  # noqa: BLE001
        log.warning("otel sdk unavailable: %s", e)
        return

    resource = Resource.create({"service.name": "incident-triage-agent"})
    provider = TracerProvider(resource=resource)
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint.rstrip("/") + "/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
            log.info("otel OTLP exporter → %s", otlp_endpoint)
        except Exception as e:  # noqa: BLE001
            log.warning("otel OTLP exporter failed: %s — spans stay local", e)
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    _provider = provider
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("incident-triage-agent")


def shutdown_tracing() -> None:
    global _provider, _tracer
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:  # noqa: BLE001
            pass
    _provider = None
    _tracer = None


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[dict]:
    """Yield a mutable attr dict; records an OTel span when the SDK is configured."""
    bag: dict[str, Any] = dict(attrs)
    if _tracer is None:
        yield bag
        return
    from opentelemetry.trace import Status, StatusCode

    with _tracer.start_as_current_span(name) as sp:
        for k, v in list(bag.items()):
            if v is not None:
                sp.set_attribute(k, v)
        try:
            yield bag
            for k, v in bag.items():
                if v is not None:
                    try:
                        sp.set_attribute(k, v)
                    except Exception:  # noqa: BLE001
                        pass
            if bag.get("error.message"):
                sp.set_status(Status(StatusCode.ERROR, str(bag["error.message"])))
        except Exception as e:
            sp.set_status(Status(StatusCode.ERROR, str(e)))
            sp.record_exception(e)
            raise
