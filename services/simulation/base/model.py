from __future__ import annotations

class BaseProcessModel:
    """Base interface for dynamic plant models.
    
    A process model represents the underlying differential equations (ODEs)
    and true state variables of the physical system (e.g. vessels, trays).
    """
    def step(self, dt: float, control_inputs: dict, disturbances: dict | None = None) -> dict:
        """Advance the physics model by dt seconds using control inputs and disturbances.
        
        Returns:
            dict containing the updated true state values of the system.
        """
        raise NotImplementedError("Subclasses must implement step()")

    def reset(self) -> None:
        """Reset the physical system state back to its initial conditions."""
        raise NotImplementedError("Subclasses must implement reset()")

    def get_state(self) -> dict:
        """Return the current true physical state values."""
        raise NotImplementedError("Subclasses must implement get_state()")
