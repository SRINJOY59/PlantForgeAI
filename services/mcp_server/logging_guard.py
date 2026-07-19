"""Keep stdout clean for the MCP protocol.

MCP-over-stdio owns stdout: the client parses every byte on it as JSON-RPC
framing, so a single stray log line kills the connection. PlantMind's telemetry
logs structured JSON to stdout - correct for a Docker service, fatal here. This
reroutes every handler to stderr, and wraps get_logger so loggers created after
the sweep are rerouted too.

Must run BEFORE any plantmind_core import that calls get_logger at module
level - which is why __init__.py stays empty and __main__ calls this first.
"""

import logging
import sys


def reroute_to_stderr() -> None:
    def sweep() -> None:
        loggers = [logging.getLogger()] + [
            logging.getLogger(name)
            for name in logging.Logger.manager.loggerDict]
        for lg in loggers:
            for handler in getattr(lg, "handlers", []):
                if isinstance(handler, logging.StreamHandler) \
                        and getattr(handler, "stream", None) is sys.stdout:
                    handler.stream = sys.stderr

    from plantmind_core import telemetry
    original = telemetry.get_logger

    def rerouted(name: str):
        logger = original(name)
        sweep()
        return logger

    telemetry.get_logger = rerouted
    sweep()
