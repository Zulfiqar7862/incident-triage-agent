"""Structured logging via structlog (JSON) or plain text for local dev."""
from __future__ import annotations

import logging
import re
import sys

import structlog

_REDACT = re.compile(r"(api[_-]?key|authorization|token|secret|password)\s*[:=]\s*\S+", re.I)


def _redact_string(s: str) -> str:
    return _REDACT.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=***", s)


def _redact_processor(logger, method_name, event_dict):  # noqa: ANN001
    for k, v in list(event_dict.items()):
        if isinstance(v, str):
            event_dict[k] = _redact_string(v)
    return event_dict


def configure_logging(fmt: str = "text", level: str = "INFO") -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=lvl, force=True)

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_processor,
        structlog.processors.StackInfoRenderer(),
    ]
    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(lvl),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Keep stdlib loggers (uvicorn, agent) visible
    for name in ("agent", "api", "uvicorn", "uvicorn.error"):
        logging.getLogger(name).setLevel(lvl)
