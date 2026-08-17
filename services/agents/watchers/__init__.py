"""Watchers package: threshold monitors and deterministic failure detection.
"""

from agents.watchers.failure import FailureWatcher, Trigger, family_of

__all__ = [
    "FailureWatcher",
    "Trigger",
    "family_of",
]
