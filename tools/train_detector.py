"""Train the multivariate PCA anomaly detector model from nominal plant data.

Reads a nominal window from the historian (or gathers baseline telemetry from Redis plant:telemetry),
fits the PCA subspace model, calculates Hotelling's T² and SPE control limits,
and saves the calibrated model to data/pca_detector.json.

Usage:
    python -m tools.train_detector
    python -m tools.train_detector --duration 30
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo / "libs" / "core"))
sys.path.insert(0, str(_repo / "services"))

import redis
from diagnostics.detector import DetectorStore, train_pca_model
from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger
from plantmind_core.timeseries import HistorianReader
from simulation.tep.topology import ALL_TAGS

log = get_logger("tools.train_detector")


def collect_redis_baseline(redis_url: str, duration_s: int = 30) -> dict[str, list[float]]:
    """Poll live plant:telemetry stream for nominal samples."""
    r = redis.Redis.from_url(redis_url, decode_responses=True)
    tag_ids = [t.tag_id for t in ALL_TAGS]
    series: dict[str, list[float]] = {t: [] for t in tag_ids}

    start = time.time()
    last_id = "0"
    print(f"Sampling nominal baseline from Redis plant:telemetry for {duration_s}s...")
    while time.time() - start < duration_s:
        resp = r.xread({"plant:telemetry": last_id}, count=200, block=1000)
        if resp:
            for _, entries in resp:
                for entry_id, fields in entries:
                    last_id = entry_id
                    tag = fields.get("tag_id")
                    if tag in series:
                        try:
                            series[tag].append(float(fields.get("value")))
                        except (ValueError, TypeError):
                            pass
        sample_count = max((len(v) for v in series.values()), default=0)
        print(f"\rCollected {sample_count} samples across {len(series)} tags...", end="", flush=True)
    print()
    return {k: v for k, v in series.items() if len(v) >= 10}


def train_from_historian(reader: HistorianReader, lookback_hours: int = 1) -> dict[str, list[float]]:
    """Read nominal historical data from the time-series historian."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=lookback_hours)
    tags = reader.known_tags() or [t.tag_id for t in ALL_TAGS]

    raw_rows = reader.window(tags, start, end)
    series: dict[str, list[float]] = {t: [] for t in tags}
    for row in raw_rows:
        if row.value is not None and row.tag_id in series:
            series[row.tag_id].append(row.value)
    return {k: v for k, v in series.items() if len(v) >= 30}


def main() -> int:
    p = argparse.ArgumentParser(description="Train the PCA Anomaly Detector for TEP.")
    p.add_argument("--duration", type=int, default=30, help="Baseline sampling duration in seconds")
    p.add_argument("--lookback-hours", type=int, default=1, help="Historian lookback hours")
    p.add_argument("--variance-target", type=float, default=0.85, help="Variance target for PCA")
    p.add_argument("--key", default="models/pca_detector.json", help="MinIO object key")
    args = p.parse_args()

    s = get_settings()
    data: dict[str, list[float]] = {}
    reader = HistorianReader.from_settings()

    if reader is not None:
        try:
            print("Attempting to load nominal data from historian...")
            data = train_from_historian(reader, args.lookback_hours)
            if data:
                print(f"Loaded {max(len(v) for v in data.values())} historical samples.")
        except Exception as e:
            print(f"Historian read fallback ({e})...")

    if not data or max((len(v) for v in data.values()), default=0) < 30:
        data = collect_redis_baseline(s.redis_url, duration_s=args.duration)

    if not data or max((len(v) for v in data.values()), default=0) < 10:
        print("ERROR: Could not collect sufficient data to train PCA detector.")
        return 1

    sample_size = max(len(v) for v in data.values())
    print(f"Training PCA model on {len(data)} tags ({sample_size} samples)...")
    model = train_pca_model(data, variance_target=args.variance_target)

    store = DetectorStore(key=args.key)
    store.save(model)

    print(f"[OK] PCA Model successfully calibrated and persisted to MinIO ({args.key})")
    print(f"  Retained components: {model.k_components} ({round(model.variance_explained * 100, 1)}% variance)")
    print(f"  Hotelling's T² Limit (99%): {round(model.t2_limit, 2)}")
    print(f"  SPE/Q Limit (99%): {round(model.spe_limit, 2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
