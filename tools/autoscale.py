"""Follow queue depth and scale the compose worker services to match.

Runs as its own container (see docker-compose.yml), talking to the docker
daemon through the mounted socket. Also runnable on the host:

    python -m tools.autoscale
"""

import signal
import threading

from plantmind_core.bus import RedisBus
from plantmind_core.telemetry import get_logger

from infra import ComposeFleet, QueueAutoscaler

log = get_logger("tools.autoscale")


def main():
    fleet = ComposeFleet()
    autoscaler = QueueAutoscaler(fleet, RedisBus.from_settings(),
                                 policies=ComposeFleet.POLICIES)

    log.info("autoscaler starting",
             services={p.service: fleet.spec(p.service).max_replicas
                       for p in ComposeFleet.POLICIES})

    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())

    autoscaler.start(interval=5.0)
    stopped.wait()

    log.info("autoscaler stopping")
    autoscaler.stop()


if __name__ == "__main__":
    main()
