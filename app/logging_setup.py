"""Logging: human-readable text locally, one JSON object per line in production."""
from __future__ import annotations

import json
import logging
import re
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
        }
        msg = record.getMessage()
        try:
            parsed = json.loads(msg)  # runtime events are already JSON
            entry.update(parsed if isinstance(parsed, dict) else {"msg": msg})
        except ValueError:
            entry["msg"] = msg
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class RedactTokens(logging.Filter):
    """The SSE stream takes the API token as a query parameter; keep it out of access logs."""

    _pattern = re.compile(r"([?&]token=)[^&\s\"]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(self._pattern.sub(r"\1[REDACTED]", a) if isinstance(a, str) else a for a in record.args)
        record.msg = self._pattern.sub(r"\1[REDACTED]", str(record.msg))
        return True


def configure_logging(fmt: str = "text", level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    handler.addFilter(RedactTokens())
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
