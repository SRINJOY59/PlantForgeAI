"""Reset must restore steady state, not collapse the plant.

The bug these pin: reset_pids() zeroed the loop integrators, so on the first
tick after a reset — process at setpoint, error ~ 0 — every regulatory loop
output fell to ~0 and slammed its valve shut. The controlled flows collapsed
and the watcher fired a burst of low-flow alarms across the reactor, separator
and compressor on every single reset.
"""

from simulation.base.pid import PIDController
from simulation.tep.constants import NOMINAL_VALVES
from simulation.tep.controller import TepControllerBank


def test_plain_reset_collapses_output_at_setpoint():
    """The old behaviour, kept as the thing the bumpless path must beat."""
    pid = PIDController(setpoint=75.0, Kp=1.0, Ki=0.1)
    pid.reset()
    assert pid.compute(75.0) == 0.0          # error 0, integral 0 -> valve shut


def test_bumpless_reset_holds_the_nominal_output():
    pid = PIDController(setpoint=75.0, Kp=1.0, Ki=0.1)
    pid.reset(hold_output=63.053)
    # at setpoint the loop resumes holding its nominal valve, not zero
    assert round(pid.compute(75.0), 3) == 63.053
    assert round(pid.compute(75.0), 3) == 63.053


def test_zero_ki_reset_does_not_divide_by_zero():
    pid = PIDController(setpoint=1.0, Kp=1.0, Ki=0.0)
    pid.reset(hold_output=50.0)              # no integral to hold it; must not raise
    assert pid._integral == 0.0


def test_reset_pids_restores_every_valve_to_nominal():
    bank = TepControllerBank()
    # drive the valves somewhere else, as a run would
    for tag in bank._mv:
        bank._mv[tag] = 0.0

    bank.reset_pids()

    assert bank.mv == NOMINAL_VALVES


def test_first_tick_after_reset_keeps_controlled_flows_open():
    """The end-to-end guarantee: a reset followed by one control step at
    nominal must not drive any controlled valve toward zero."""
    bank = TepControllerBank()
    bank.reset_pids()

    nominal_state = {
        "REACTOR.T": 122.9, "REACTOR.P": 2705.0, "REACTOR.Level": 75.0,
        "SEPARATOR.P": 2633.7, "SEPARATOR.Level": 50.0, "STRIPPER.Level": 50.0,
    }
    bank.step(nominal_state, dt=1.0)

    for loop, valve in TepControllerBank._LOOP_VALVE.items():
        held = bank.mv[valve]
        assert held > 1.0, f"{valve} collapsed to {held} after reset"
        # and it is holding its nominal, not some arbitrary non-zero value
        assert abs(held - NOMINAL_VALVES[valve]) < 5.0


def test_cold_start_is_also_bumpless():
    """A freshly constructed bank — no reset called — must already hold its
    valves open. The cold-start path hits the same zero-integral trap, so it
    routes through the same preload."""
    bank = TepControllerBank()
    nominal_state = {
        "REACTOR.T": 122.9, "REACTOR.P": 2705.0, "REACTOR.Level": 75.0,
        "SEPARATOR.P": 2633.7, "SEPARATOR.Level": 50.0, "STRIPPER.Level": 50.0,
    }
    bank.step(nominal_state, dt=1.0)
    for valve in TepControllerBank._LOOP_VALVE.values():
        assert bank.mv[valve] > 1.0, f"{valve} collapsed on cold start"
