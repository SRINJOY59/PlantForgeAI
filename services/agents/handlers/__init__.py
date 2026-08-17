"""Agent alarm and event handlers.

Each module handles one class of incoming event. The AgentsRuntime in
consumer.py delegates to these handlers so the main loop stays lean.
"""
from agents.handlers.delta import DeltaHandler
from agents.handlers.tep_alarm import TepAlarmHandler
from agents.handlers.process_limit import ProcessLimitHandler

__all__ = ["DeltaHandler", "TepAlarmHandler", "ProcessLimitHandler"]
