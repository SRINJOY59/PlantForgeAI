from __future__ import annotations
import argparse
import asyncio
import logging
import math
import os
from collections import deque
import numpy as np
import redis

# Add project root to sys.path to allow imports of simulation package
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.base.runner import BaseSimulationRunner
from simulation.base.publisher import BaseTelemetryPublisher

# CSTR Topology & Models
from simulation.cstr.topology import VESSEL_MAP, VESSELS
from simulation.cstr.model import CstrTrain
from simulation.cstr.controller import CstrControllerBank

# Column Models
from simulation.column.model import ColumnModel
from simulation.column.controller import ColumnControllerBank

# TEP Model
from simulation.tep.runner import TepRunner

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("simulation-run")

# ──────────────────────────────────────────────────────────────────────────────
# CSTR Constants
# ──────────────────────────────────────────────────────────────────────────────
SIM_HZ = float(os.environ.get("SIM_HZ", "1.0"))
SIM_DT = 1.0 / SIM_HZ

# Ornstein-Uhlenbeck parameters
OU_THETA = 0.05
OU_SIGMA_Ca0 = 0.04
OU_SIGMA_T0 = 0.3

# Sensor noise
SIGMA_SENS_T = 2e-4
SIGMA_SENS_Ca = 3e-4

# Instrument quantization
QUANT_T = 0.1
QUANT_Ca = 0.001

# Stall detection
VARIANCE_CHECK_TICKS = 30
STALL_VAR_FLOOR_T = 0.005
T_HISTORY_LEN = 60

UNIT_MAP = {
    "T": "K",
    "Ca": "mol/L",
    "Tc": "K",
    "CoolantValve": "%",
}

def _apply_sensor_noise(value: float, sigma_rel: float, dt: float, quant: float) -> float:
    noise = sigma_rel * abs(value) * math.sqrt(dt) * np.random.normal()
    noisy = value + noise
    return round(noisy / quant) * quant

# ──────────────────────────────────────────────────────────────────────────────
# Column Constants
# ──────────────────────────────────────────────────────────────────────────────
OU_SIGMA_ZF = 0.008
OU_SIGMA_FLOW = 0.003
SIGMA_SENS_X = 5e-4

class CstrRunner(BaseSimulationRunner):
    """CSTR specific simulation loop runner."""
    def __init__(self, port: int):
        model = CstrTrain()
        bank = CstrControllerBank()
        publisher = BaseTelemetryPublisher()
        super().__init__(model, bank, publisher, dt=SIM_DT, port=port, title="cstr-sim")
        self._T_history = deque(maxlen=T_HISTORY_LEN)
        self._ou_state = {tag: [0.0, 0.0] for tag in VESSEL_MAP}

    def on_reset(self):
        self._T_history.clear()
        self._ou_state = {tag: [0.0, 0.0] for tag in VESSEL_MAP}

    def get_topology_status(self) -> dict:
        return {
            "vessel_states": {
                tag: {"Ca": v.Ca, "T": v.T, "Tc": v.Tc}
                for tag, v in self.model.vessels.items()
            }
        }

    def _step_ou(self, tag: str, dt: float) -> tuple[float, float]:
        xi = self._ou_state[tag]
        dW_Ca = np.random.normal(0.0, math.sqrt(dt))
        dW_T  = np.random.normal(0.0, math.sqrt(dt))
        xi[0] += -OU_THETA * xi[0] * dt + OU_SIGMA_Ca0 * dW_Ca
        xi[1] += -OU_THETA * xi[1] * dt + OU_SIGMA_T0  * dW_T
        self._ou_state[tag] = xi
        return xi[0], xi[1]

    def _check_stall(self):
        if len(self._T_history) < T_HISTORY_LEN // 2:
            return
        arr = np.array(self._T_history)
        var = float(np.var(arr))
        if var < STALL_VAR_FLOOR_T:
            log.warning(
                "SIMULATION_STALLED: CSTR-101.T variance=%.6f K² < floor %.6f K² over last %d ticks",
                var, STALL_VAR_FLOOR_T, len(self._T_history)
            )
            self._sim_health = "stalled"
        else:
            self._sim_health = "nominal"

    async def tick(self, dt: float) -> None:
        disturbances = {}
        for tag in VESSEL_MAP:
            dCa0, dT0 = self._step_ou(tag, dt)
            disturbances[tag] = (dCa0, dT0)

        true_state = self.model.get_state()
        control_inputs = self.bank.compute(true_state)
        new_states = self.model.step(dt, control_inputs, disturbances)

        if "CSTR-101" in new_states:
            self._T_history.append(new_states["CSTR-101"]["T"])
        if self._tick_count > 0 and self._tick_count % VARIANCE_CHECK_TICKS == 0:
            self._check_stall()

        # Apply sensor noise to true states
        noisy_state = {}
        for tag, state in new_states.items():
            T_noisy = _apply_sensor_noise(state["T"], SIGMA_SENS_T, dt, QUANT_T)
            Ca_noisy = _apply_sensor_noise(state["Ca"], SIGMA_SENS_Ca, dt, QUANT_Ca)
            Tc_noisy = _apply_sensor_noise(state["Tc"], SIGMA_SENS_T, dt, QUANT_T)
            noisy_state[tag] = {"Ca": Ca_noisy, "T": T_noisy, "Tc": Tc_noisy}

        readings = self.bank.published_readings(noisy_state, control_inputs)

        tags_to_publish = {}
        for vessel_tag, vals in readings.items():
            for measure, value in vals.items():
                tag_id = f"{vessel_tag}.{measure}"
                unit = UNIT_MAP.get(measure, "")
                tags_to_publish[tag_id] = (value, unit)

        if "CSTR-104" in readings:
            c104 = readings["CSTR-104"]
            tags_to_publish["CSTR-104.OUT.Ca"] = (c104["Ca"], "mol/L")
            tags_to_publish["CSTR-104.OUT.T"] = (c104["T"], "K")
            tags_to_publish["CSTR-104.OUT.Flow"] = (0.1, "m3/s")

        await asyncio.to_thread(self.publisher.publish_tags, tags_to_publish)


class ColumnRunner(BaseSimulationRunner):
    """Distillation Column specific simulation loop runner."""
    def __init__(self, port: int):
        model = ColumnModel()
        bank = ColumnControllerBank()
        publisher = BaseTelemetryPublisher()
        super().__init__(model, bank, publisher, dt=SIM_DT, port=port, title="column-sim")
        
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._redis = redis.from_url(url, decode_responses=True)
        self._ou_zF = 0.0
        self._ou_flow = 0.0

    def on_reset(self):
        self._ou_zF = 0.0
        self._ou_flow = 0.0

    def get_topology_status(self) -> dict:
        return {
            "vessel_states": {
                "COLUMN-1": {"x": self.model.x.tolist()}
            }
        }

    def _get_latest_cstr_feed(self) -> tuple[float, float]:
        Ca, T = 0.5, 340.0
        try:
            entries = self._redis.xrevrange("plant:telemetry", max="+", min="-", count=100)
            found_Ca = False
            found_T = False
            for entry_id, fields in entries:
                tag_id = fields.get("tag_id")
                if tag_id == "CSTR-104.OUT.Ca" and not found_Ca:
                    Ca = float(fields.get("value", "0.5"))
                    found_Ca = True
                elif tag_id == "CSTR-104.OUT.T" and not found_T:
                    T = float(fields.get("value", "340.0"))
                    found_T = True
                if found_Ca and found_T:
                    break
        except Exception:
            pass
        return Ca, T

    async def tick(self, dt: float) -> None:
        Ca_feed, T_feed = await asyncio.to_thread(self._get_latest_cstr_feed)

        # Convert feed concentration to mole fraction
        z_F_base = float(np.clip(Ca_feed / 4.0, 0.0, 1.0))
        F_base = 0.1

        # Apply OU disturbances on feed
        dW_zF = np.random.normal(0.0, math.sqrt(dt))
        dW_flow = np.random.normal(0.0, math.sqrt(dt))
        
        self._ou_zF += -OU_THETA * self._ou_zF * dt + OU_SIGMA_ZF * dW_zF
        self._ou_flow += -OU_THETA * self._ou_flow * dt + OU_SIGMA_FLOW * dW_flow

        z_F_noisy = float(np.clip(z_F_base + self._ou_zF, 0.0, 1.0))
        feed_flow_noisy = float(max(0.01, F_base + self._ou_flow))

        true_state = self.model.get_state()
        control_inputs = self.bank.compute(true_state)
        
        disturbances = {"z_F": z_F_noisy, "feed_flow": feed_flow_noisy}
        new_states = self.model.step(dt, control_inputs, disturbances)

        # Apply sensor noise to compositions
        noisy_x = []
        for x_val in new_states["x"]:
            noise = SIGMA_SENS_X * abs(x_val) * math.sqrt(dt) * np.random.normal()
            noisy_x.append(float(np.clip(x_val + noise, 0.0, 1.0)))

        noisy_state = {"x": noisy_x, "T": new_states["T"]}
        readings = self.bank.published_readings(noisy_state, control_inputs)

        tags_to_publish = {}
        for stage_idx, (x, t) in enumerate(zip(readings["x"], readings["T"])):
            stage_str = f"TRAY-{stage_idx:02d}"
            tags_to_publish[f"COLUMN-1.{stage_str}.x"] = (x, "mol_frac")
            tags_to_publish[f"COLUMN-1.{stage_str}.T"] = (t, "K")

        tags_to_publish["COLUMN-1.DISTILLATE.x"] = (readings["x"][0], "mol_frac")
        tags_to_publish["COLUMN-1.BOTTOMS.x"] = (readings["x"][11], "mol_frac")
        tags_to_publish["COLUMN-1.REFLUX.R"] = (readings["L_R"], "m3/s")
        tags_to_publish["COLUMN-1.REBOILER.Duty"] = (readings["V"], "m3/s")
        tags_to_publish["COLUMN-1.FLOODING"] = (readings["flooding_index"], "index")

        await asyncio.to_thread(self.publisher.publish_tags, tags_to_publish)


def main():
    parser = argparse.ArgumentParser(description="Unified Simulation runner.")
    parser.add_argument("--type", type=str, required=True,
                        choices=["cstr", "column", "tep"],
                        help="Simulation type: cstr, column, or tep")
    args = parser.parse_args()

    if args.type == "tep":
        port = int(os.environ.get("SIM_PORT", "8012"))
        log.info("Starting Tennessee Eastman Process simulation runner on port %d...", port)
        runner = TepRunner(port=port)
    elif args.type == "cstr":
        port = int(os.environ.get("SIM_PORT", "8010"))
        log.info("Starting CSTR simulation runner on port %d...", port)
        runner = CstrRunner(port=port)
    else:
        port = int(os.environ.get("SIM_PORT", "8011"))
        log.info("Starting Distillation Column simulation runner on port %d...", port)
        runner = ColumnRunner(port=port)

    runner.run()

if __name__ == "__main__":
    main()
