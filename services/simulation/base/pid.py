from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class PIDController:
    """Incremental PID controller with anti-windup clamping.
    
    Compatible with both reverse-acting and direct-acting configurations
    depending on the sign of inputs / error calculation.
    """
    setpoint: float
    Kp: float = 1.0
    Ki: float = 0.0
    Kd: float = 0.0
    output_min: float = 0.0
    output_max: float = 100.0
    dt: float = 1.0

    _integral: float = field(default=0.0, init=False, repr=False)
    _prev_error: float = field(default=0.0, init=False, repr=False)

    def compute(self, measurement: float) -> float:
        error = self.setpoint - measurement

        self._integral += error * self.dt
        derivative = (error - self._prev_error) / self.dt
        self._prev_error = error

        output = self.Kp * error + self.Ki * self._integral + self.Kd * derivative

        # clamp + anti-windup: if output saturates, back off the integral
        if output > self.output_max:
            self._integral -= (output - self.output_max) / self.Ki if self.Ki else 0
            output = self.output_max
        elif output < self.output_min:
            self._integral -= (output - self.output_min) / self.Ki if self.Ki else 0
            output = self.output_min
        return output

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0
