"""The structured logger's field handling.

Both cases here come from one incident: an alarm handler logging level="HH"
raised TypeError from inside the logging call, on every alarm it was given, and
the only sign of it was its caller reporting "failed to process alert".
"""

import json
import logging

from plantmind_core.telemetry import _JsonFormatter, get_logger


def test_reserved_field_names_do_not_raise():
    get_logger("t").warning("TEP alarm fired", level="HH", msg="x", tag_id="R.T")


def test_caller_fields_cannot_shadow_the_log_envelope():
    record = logging.LogRecord("t", logging.WARNING, __file__, 1,
                               "TEP alarm fired", None, None)
    record.kv = {"level": "HH", "tag_id": "REACTOR.T"}
    payload = json.loads(_JsonFormatter().format(record))

    assert payload["level"] == "WARNING"      # severity, not the alarm level
    assert payload["kv_level"] == "HH"        # and the caller's field survives
    assert payload["tag_id"] == "REACTOR.T"


def test_ordinary_fields_are_passed_through():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "alarm", None, None)
    record.kv = {"tag_id": "REACTOR.T", "value": 150.0}
    payload = json.loads(_JsonFormatter().format(record))

    assert payload["msg"] == "alarm"
    assert payload["tag_id"] == "REACTOR.T" and payload["value"] == 150.0
