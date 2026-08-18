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
            for key, value in extra.items():
                # the envelope wins: a field the caller happens to call "level"
                # or "msg" must not overwrite the record's real severity or
                # message, or a line reads {"level": "HH"} and every log filter
                # looking for WARNING silently stops matching it
                payload[f"kv_{key}" if key in payload else key] = value
        return json.dumps(payload, default=str)


class _KVLogger:
    """logger.info("msg", key=value, ...) style on top of stdlib."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    # level and msg are positional-only, so a caller may log a field called
    # "level" or "msg". Without the '/' they collide with these parameters and
    # the logging call raises TypeError - inside whatever handler was logging,
    # which is the last place anyone looks for a crash. An alarm handler
    # logging level="HH" died on that line for every alarm it was given, and
    # the only trace was its caller reporting "failed to process alert".
    def _log(self, level: int, msg: str, /, **kv) -> None:
        self._logger.log(level, msg, extra={"kv": kv} if kv else None)

    def debug(self, msg: str, /, **kv) -> None:   self._log(logging.DEBUG, msg, **kv)
    def info(self, msg: str, /, **kv) -> None:    self._log(logging.INFO, msg, **kv)
    def warning(self, msg: str, /, **kv) -> None: self._log(logging.WARNING, msg, **kv)
    def error(self, msg: str, /, **kv) -> None:   self._log(logging.ERROR, msg, **kv)


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
