"""Structured logging with trace ids + token accounting.
Kept dependency-free (stdlib logging) so every service can import it."""

import json
import logging
import sys
import time
from collections import defaultdict
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "trace": trace_id_var.get(),
            "msg": record.getMessage(),
        }
        extra = getattr(record, "kv", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, default=str)


class _KVLogger:
    """logger.info("msg", key=value, ...) style on top of stdlib."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _log(self, level: int, msg: str, **kv) -> None:
        self._logger.log(level, msg, extra={"kv": kv} if kv else None)

    def debug(self, msg: str, **kv) -> None:   self._log(logging.DEBUG, msg, **kv)
    def info(self, msg: str, **kv) -> None:    self._log(logging.INFO, msg, **kv)
    def warning(self, msg: str, **kv) -> None: self._log(logging.WARNING, msg, **kv)
    def error(self, msg: str, **kv) -> None:   self._log(logging.ERROR, msg, **kv)


_configured = False


def get_logger(name: str) -> _KVLogger:
    global _configured
    if not _configured:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(logging.INFO)
        _configured = True
    return _KVLogger(logging.getLogger(name))


class TokenMeter:
    """In-process token counters, dumpable to /metrics."""

    def __init__(self) -> None:
        self._counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"prompt": 0, "completion": 0, "calls": 0}
        )

    def record(self, model: str, prompt: int, completion: int) -> None:
        c = self._counts[model]
        c["prompt"] += prompt
        c["completion"] += completion
        c["calls"] += 1

    def snapshot(self) -> dict:
        return {m: dict(c) for m, c in self._counts.items()}
