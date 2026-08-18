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

    def reset(self, hold_output: float = 0.0):
        """Reset the loop, optionally holding a nominal output.

        Bumpless when hold_output is given. A plain zero-reset drops the
        integral to 0, so on the first tick after a reset — with the process
        sitting at setpoint, i.e. error ~ 0 — the loop outputs ~0 and slams its
        valve shut. In TEP that collapsed every controlled flow (separator
        outlet, compressor recycle, stripper inlet, purge, D-feed) the instant
        the sim was reset, tripping a burst of low-flow alarms across the
        reactor, separator and compressor until the integrators wound back up.

        At steady state output = Ki * integral (the Kp and Kd terms vanish at
        zero error), so seeding integral = hold_output / Ki makes the loop
        resume holding hold_output instead of zero.
        """
        self._integral = hold_output / self.Ki if self.Ki else 0.0
        self._prev_error = 0.0
