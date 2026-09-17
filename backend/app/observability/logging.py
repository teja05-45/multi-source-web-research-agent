"""Structured (JSON) logging configuration with request-ID correlation.

Every log record can carry a `request_id` (propagated via a contextvar so
nested async calls don't need to pass it explicitly) plus arbitrary
structured `extra` fields. Secrets (API keys, credentials) are never logged;
`_SENSITIVE_KEYS` provides a belt-and-suspenders redaction filter in case a
field name accidentally matches.
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from typing import Any

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_SENSITIVE_KEYS = {"api_key", "apikey", "authorization", "secret", "token", "password", "credential"}


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> str:
    return _request_id_ctx.get()


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("***REDACTED***" if k.lower() in _SENSITIVE_KEYS else _redact(v))
            for k, v in value.items()
        }
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", get_request_id()),
        }
        # Anything passed via `extra=` ends up as a normal attribute on the
        # record; pull out the non-standard ones.
        standard_keys = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())
        extras = {
            k: v for k, v in record.__dict__.items() if k not in standard_keys and k != "request_id"
        }
        if extras:
            payload["data"] = _redact(extras)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger("research_agent")
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.propagate = False
