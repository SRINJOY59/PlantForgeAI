"""Populate the fault-mode library by running the simulator through its faults.

This is where the simulator stops being a live plant to watch and becomes a
knowledge generator. For each IDV it: resets the sim to nominal, lets a clean
baseline accumulate in the historian, injects the fault, lets the cascade
develop, then reads the window back out and distils it into a FaultSignature.
The signature is labelled with the IDV that caused it - the one thing the live
plant can never tell us - and written to Neo4j as a FaultMode next to the
equipment it touches and the SOP that answers it.

Run it once and the Library view has content; run it again and each FaultMode is
overwritten in place, so the library converges rather than accreting duplicates.
It talks to the sim only over its HTTP control API and to the plant only through
the historian, so it needs no simulator internals beyond the tag list.

usage:
    python -m tools.build_fault_library                 # curated core faults
    python -m tools.build_fault_library --all           # every IDV 1-21
    python -m tools.build_fault_library --idv 4,6,8      # a chosen few
    python -m tools.build_fault_library --dry-run        # extract, don't write
    python -m tools.build_fault_library --settle 90 --react 180
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo / "libs" / "core"))
sys.path.insert(0, str(_repo / "services"))

from plantmind_core.schemas import FaultMode           # noqa: E402
from plantmind_core.timeseries import HistorianReader   # noqa: E402
from diagnostics.signature import extract_signature     # noqa: E402
from simulation.tep.topology import (                   # noqa: E402
    ALL_TAGS, IDV_TABLE, TAG_BY_ID,
)

DEFAULT_SIM_URL = "http://localhost:8012"

# baseline lead-in and reaction windows, in real seconds. The sim runs at 1 Hz,
# so these are also roughly the sample counts each side of onset.
DEFAULT_SETTLE_S = 120
DEFAULT_REACT_S = 240

# the historian sink flushes on a short timer; wait past it before reading so the
# tail of the reaction window has actually landed in the database.
FLUSH_MARGIN_S = 6

# The faults with a clear, repeatable fingerprint - the ones worth seeding a
# demonstrable library from. IDV 16-20 are "unknown" in the TEP paper (weak,
# diffuse signatures); --all includes them for completeness.
CORE_IDVS = [1, 2, 4, 5, 6, 7, 8, 13, 14]

# Which seeded SOP answers each fault, where the domain link is defensible
# (Downs & Vogel 1993). Unmapped IDVs get no procedure edge - honest silence
# beats a fabricated link.
IDV_PROCEDURE = {
    1:  "sop:TEP-REACTOR-P-HIGH",   # A/C feed ratio step -> reactor pressure
    6:  "sop:TEP-REACTOR-P-HIGH",   # A feed loss -> pressure dynamics
    7:  "sop:TEP-REACTOR-P-HIGH",   # C header pressure loss
    4:  "sop:TEP-REACTOR-T-HIGH",   # reactor coolant inlet T step
    11: "sop:TEP-REACTOR-T-HIGH",   # reactor coolant inlet T random
    14: "sop:TEP-REACTOR-T-HIGH",   # reactor coolant valve stuck
    8:  "sop:TEP-PRODUCT-PURITY",   # feed composition variation -> purity
    13: "sop:TEP-PRODUCT-PURITY",   # kinetics drift -> purity
}

ALL_TAG_IDS = [t.tag_id for t in ALL_TAGS]


# --- HTTP to the sim control API -------------------------------------------
def _request(url: str, method: str, body: dict | None = None, timeout: float = 15.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class SimDriver:
    """The simulator seen through its HTTP control surface, nothing more."""

    def __init__(self, base_url: str):
        self._base = base_url.rstrip("/")

    def reset(self) -> None:
        _request(f"{self._base}/sim/reset", "POST", {})

    def inject(self, idv: int) -> str:
        r = _request(f"{self._base}/sim/idv", "POST", {"idv": idv, "active": True})
        return r.get("description", "")

    def clear(self, idv: int) -> None:
        _request(f"{self._base}/sim/idv", "POST", {"idv": idv, "active": False})

    def ping(self) -> bool:
        try:
            r = _request(f"{self._base}/health", "GET")
            return r.get("status") == "ok"
        except (urllib.error.URLError, OSError):
            return False


# --- signature -> FaultMode -------------------------------------------------
def _unit_areas(sig) -> list[str]:
    """The areas this fault touches, in the order they first moved - so the head
    of the cascade leads the list. Dedup keeps first appearance."""
    areas: list[str] = []
    for d in sig.deviations:                     # already sorted by first mover
        tag = TAG_BY_ID.get(d.tag_id)
        area = tag.unit_area if tag else None
        if area and area not in areas:
            areas.append(area)
    return areas


def _severity(sig) -> str:
    """Grade the episode by its strongest excursion, in baseline-std units. A
    tag 15 std off nominal is not a warning; a mild drift is not a crisis."""
    if not sig.deviations:
        return "info"
    peak = max(d.magnitude for d in sig.deviations)
    if peak >= 15:
        return "critical"
    if peak >= 6:
        return "warning"
    return "info"


def _build_fault_mode(idv: int, sig) -> FaultMode:
    sig.severity = _severity(sig)
    return FaultMode(
        id=f"faultmode:IDV-{idv}",
        cause_id=f"IDV-{idv}",
        cause_label=IDV_TABLE.get(idv, f"IDV-{idv}"),
        unit_areas=_unit_areas(sig),
        signature=sig,
        procedure_id=IDV_PROCEDURE.get(idv),
    )


def _print_summary(fm: FaultMode) -> None:
    sig = fm.signature
    proc = fm.procedure_id or "-"
    print(f"  {fm.cause_id:<7} {sig.severity:<8} "
          f"areas={','.join(fm.unit_areas) or '-'}  sop={proc}")
    for d in sig.deviations[:6]:
        print(f"       {d.first_mover_rank}. {d.tag_id:<20} {d.direction:<4} "
              f"z={d.magnitude:<7} +{d.onset_offset_s:.0f}s")
    extra = len(sig.deviations) - 6
    if extra > 0:
        print(f"       ... and {extra} more")


# --- the campaign ----------------------------------------------------------
def run_campaign(sim_url: str, idvs: list[int], settle_s: int, react_s: int,
                 dry_run: bool) -> int:
    reader = HistorianReader.from_settings()
    if reader is None:
        print("ERROR: historian is not configured (TIMESCALE_DSN unset). "
              "The library is built from what the historian recorded; without "
              "it there is nothing to read.", file=sys.stderr)
        return 2

    sim = SimDriver(sim_url)
    if not sim.ping():
        print(f"ERROR: no simulator at {sim_url}. Start tep-sim first, or pass "
              f"--sim-url.", file=sys.stderr)
        return 2

    store = None
    if not dry_run:
        from diagnostics.library import FaultLibraryStore
        store = FaultLibraryStore.from_settings()

    print(f"Building fault library from {len(idvs)} fault(s) via {sim_url}")
    print(f"  settle={settle_s}s  react={react_s}s  "
          f"{'DRY RUN (no writes)' if dry_run else 'writing to Neo4j'}\n")

    stored = 0
    try:
        for idv in idvs:
            label = IDV_TABLE.get(idv, f"IDV-{idv}")
            print(f"IDV-{idv}: {label}")

            # 1. clean slate, then let a nominal baseline accumulate
            sim.reset()
            _sleep("  settling", settle_s)

            # 2. mark onset in wall-clock (what the historian timestamps by) and fire
            onset = datetime.now(timezone.utc)
            sim.inject(idv)

            # 3. let the cascade develop, then wait for the tail to flush to the DB
            _sleep("  reacting", react_s)
            time.sleep(FLUSH_MARGIN_S)

            # 4. read the bracketing window and distil it
            samples = reader.around(ALL_TAG_IDS, onset,
                                    before_s=settle_s, after_s=react_s)
            if not samples:
                print("  no telemetry in window - is the historian sink running? "
                      "skipping.\n")
                sim.clear(idv)
                continue

            sig = extract_signature(
                samples, onset,
                source="sim", cause_id=f"IDV-{idv}", cause_label=label,
            )
            fm = _build_fault_mode(idv, sig)

            if not sig.deviations:
                print("  no tag left its baseline band - no signature to store.\n")
            else:
                _print_summary(fm)
                if store is not None:
                    store.store(fm)
                    stored += 1
                print()

            # 5. clear the fault before the next reset
            sim.clear(idv)

        # leave the plant at nominal
        sim.reset()
    finally:
        if store is not None:
            store.close()

    print(f"Done. {stored} fault mode(s) written." if not dry_run
          else "Done (dry run - nothing written).")
    return 0


def _sleep(label: str, seconds: int) -> None:
    """Sleep with a one-line countdown so a long campaign shows progress."""
    for remaining in range(seconds, 0, -1):
        print(f"\r{label}... {remaining:>4}s ", end="", flush=True)
        time.sleep(1)
    print(f"\r{label}... done   ")


def _parse_idvs(args) -> list[int]:
    if args.idv:
        try:
            return [int(x) for x in args.idv.split(",") if x.strip()]
        except ValueError:
            raise SystemExit(f"--idv must be comma-separated integers, got {args.idv!r}")
    return list(range(1, 22)) if args.all else CORE_IDVS


def main() -> int:
    p = argparse.ArgumentParser(description="Build the TEP fault-mode library.")
    p.add_argument("--sim-url", default=DEFAULT_SIM_URL,
                   help=f"simulator control API (default {DEFAULT_SIM_URL})")
    p.add_argument("--idv", help="comma-separated IDV numbers, e.g. 4,6,8")
    p.add_argument("--all", action="store_true", help="run every IDV 1-21")
    p.add_argument("--settle", type=int, default=DEFAULT_SETTLE_S,
                   help=f"baseline seconds before injection (default {DEFAULT_SETTLE_S})")
    p.add_argument("--react", type=int, default=DEFAULT_REACT_S,
                   help=f"reaction seconds after injection (default {DEFAULT_REACT_S})")
    p.add_argument("--dry-run", action="store_true",
                   help="extract and print signatures without writing to Neo4j")
    args = p.parse_args()

    return run_campaign(args.sim_url, _parse_idvs(args),
                        args.settle, args.react, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
