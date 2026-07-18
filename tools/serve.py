"""Run the whole backend for local dev in one command: infra containers +
pipeline workers + the agents consumer + the retrieval and gateway APIs.
Ctrl+C stops everything.

    python -m tools.serve

Then point the UI at the gateway (default http://localhost:8000).
"""

import subprocess
import sys
import time
from pathlib import Path

from plantmind_core.bus import RedisBus
from plantmind_core.config import get_settings

from infra import Infrastructure, QueueAutoscaler, WorkerFleet

REPO = Path(__file__).resolve().parents[1]
LOGS = REPO / "logs"

# long-running processes that aren't celery workers
SERVERS = [
    ("agents", [sys.executable, "-m", "agents.consumer"]),
    ("retrieval", [sys.executable, "-m", "uvicorn", "retrieval.main:app",
                   "--host", "0.0.0.0", "--port", "8001"]),
    ("gateway", [sys.executable, "-m", "uvicorn", "gateway.main:app",
                 "--host", "0.0.0.0", "--port", "8000"]),
    ("interview", [sys.executable, "-m", "uvicorn", "interview.main:app",
                   "--host", "0.0.0.0", "--port", "8002"]),
]


def main():
    infra = Infrastructure(get_settings())
    fleet = WorkerFleet()
    servers = []

    infra.up()
    infra.apply_schema()
    fleet.start()

    autoscaler = QueueAutoscaler(fleet, RedisBus.from_settings())
    autoscaler.start(interval=5.0)

    LOGS.mkdir(exist_ok=True)
    for name, cmd in SERVERS:
        logfile = open(LOGS / f"{name}.log", "a", encoding="utf-8")
        logfile.write(f"\n===== run {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        logfile.flush()
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=logfile,
                                stderr=subprocess.STDOUT)
        servers.append((name, proc, logfile))
        print(f"server: {name} up (pid {proc.pid})")

    print("\nbackend running:")
    print("  gateway   http://localhost:8000   (point the UI here)")
    print("  retrieval http://localhost:8001")
    print("  interview http://localhost:8002   (knowledge-capture voice interview)")
    print("  neo4j     http://localhost:7474   minio http://localhost:9001")
    print("autoscaler on: extraction/ingestion/resolution follow queue depth")
    print("logs in logs/ — ctrl+c to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        autoscaler.stop()          # before the fleet, so it can't respawn
        for name, proc, logfile in servers:
            proc.terminate()
            logfile.close()
        fleet.stop()
        print("stopped.")


if __name__ == "__main__":
    main()
