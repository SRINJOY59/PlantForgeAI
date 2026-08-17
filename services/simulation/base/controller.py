from __future__ import annotations
from typing import Optional

class BaseControllerBank:
    """Base interface for controller bank management.
    
    A controller bank groups PIDs for a specific topology and manages
    fault injection offsets (valve clamps, sensor bias, gain degradation).
    """
    def compute(self, true_state: dict) -> dict:
        """Compute control valve outputs based on the true physical state.
        
        Returns:
            dict containing valve output commands (e.g. valve percentages).
        """
        raise NotImplementedError("Subclasses must implement compute()")

    def published_readings(self, true_state: dict, valve_outputs: dict) -> dict:
        """Apply sensor bias offsets for display/telemetry layers only.
        
        The PID loops should never use these biased outputs; they must run
        on the true physical values.
        """
        raise NotImplementedError("Subclasses must implement published_readings()")

    def saturate_valve(self, tag: str, pct: float):
        """Clamp valve at pct. None clears the clamp."""
        raise NotImplementedError()

    def bias_sensor(self, tag: str, offset: float):
        """Add offset to published sensor values only."""
        raise NotImplementedError()

    def degrade_pid(self, tag: str, factor: float):
        """Multiply PID outputs by factor (0 < factor <= 1)."""
        raise NotImplementedError()

    def clear_faults(self, tag: str | None = None):
        """Clear faults on tag, or all if tag is None."""
        raise NotImplementedError()

    def reset_pids(self):
        """Reset internal integrals and errors for all PID controllers."""
        raise NotImplementedError()

    def active_faults(self) -> dict:
        """Return dict of non-default fault states (e.g. for /sim/status)."""
        raise NotImplementedError()
