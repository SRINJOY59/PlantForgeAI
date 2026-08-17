from __future__ import annotations
from dataclasses import dataclass

@dataclass
class VesselSpec:
    """Static configuration for one vessel in the demo train."""
    tag: str
    type: str = "CSTR"           # Neo4j label prop
    unit: str = "DemoTrain1"
    Ca0: float = 4.0             # feed concentration [mol/L]  (URP: 4.0 mol/L)
    T0: float  = 340.0           # feed temperature [K]        (URP: 350 K → we use 340 K, slightly cooler feed)
    tau: float = 10.0            # residence time [s]          (URP: 10 s, V=0.1m³, q=0.01m³/s scaled)
    Ca_init: float = 2.0         # start at mid-conversion, not near zero
    T_init: float  = 335.0       # 8–10 K below setpoint so the PID has visible work to do
    Tc_init: float = 300.0       # coolant starts colder than steady-state to add initial dynamics

VESSELS: list[VesselSpec] = [
    VesselSpec(tag="CSTR-101",  Ca0=4.0, T0=340.0, tau=10.0,
               Ca_init=2.0, T_init=335.0, Tc_init=300.0),
    VesselSpec(tag="CSTR-102A", Ca0=4.0, T0=340.0, tau=10.0,
               Ca_init=2.0, T_init=334.0, Tc_init=300.0),
    VesselSpec(tag="CSTR-102B", Ca0=4.0, T0=340.0, tau=10.0,
               Ca_init=2.0, T_init=334.0, Tc_init=300.0),
    VesselSpec(tag="CSTR-104",  Ca0=4.0, T0=340.0, tau=12.0,
               Ca_init=1.5, T_init=333.0, Tc_init=300.0),
]

VESSEL_MAP: dict[str, VesselSpec] = {v.tag: v for v in VESSELS}

CONNECTED_TO: list[tuple[str, str]] = [
    ("FEED",     "CSTR-101"),
    ("CSTR-101", "CSTR-102A"),
    ("CSTR-101", "CSTR-102B"),
    ("CSTR-102A", "CSTR-104"),
    ("CSTR-102B", "CSTR-104"),
]

SHARES_HEADER: list[tuple[str, str]] = [
    ("CSTR-102A", "CSTR-102B"),
]

def feed_temperature_for(tag: str, states: dict[str, dict]) -> float | None:
    """Return the upstream vessel outlet temperature [K] for series coupling."""
    if tag in ("CSTR-102A", "CSTR-102B"):
        return states.get("CSTR-101", {}).get("T")
    if tag == "CSTR-104":
        t_a = states.get("CSTR-102A", {}).get("T")
        t_b = states.get("CSTR-102B", {}).get("T")
        if t_a is not None and t_b is not None:
            return 0.5 * (t_a + t_b)
    return None
