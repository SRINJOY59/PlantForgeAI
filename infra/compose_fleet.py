"""The fleet, when a worker is a container rather than a subprocess.

QueueAutoscaler only ever asks for spec / count / scale_to / reap_drained, so
this answers those four against `docker compose` and the policy code upstream
does not change a line. Same abstraction that lets the tests run with no docker
at all.

Compose splits extraction by lane, so unlike WorkerFleet every stage here owns
exactly one queue.
"""

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from plantmind_core.telemetry import get_logger

from infra.autoscaler import ScalePolicy

log = get_logger("infra.compose_fleet")

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ComposeSpec:
    """A compose service and how far it may be scaled. Mirrors the surface of
    WorkerSpec, because the autoscaler reads nothing else off a spec."""

    name: str
    min_replicas: int = 1
    max_replicas: int = 1

    @property
    def scalable(self) -> bool:
        return self.max_replicas > self.min_replicas


class ComposeFleet:
    SPECS = [
        ComposeSpec("ingestion", max_replicas=3),
        ComposeSpec("extraction-wo", max_replicas=4),
        ComposeSpec("extraction-pnid", max_replicas=3),
        ComposeSpec("extraction-text", max_replicas=4),
        ComposeSpec("resolution", max_replicas=3),
        # pinned for the same reason it is pinned locally: one writer, so the
        # flush can batch without taking a lock
        ComposeSpec("graphd"),
        ComposeSpec("connectors"),
    ]

    # per_worker is sized against the -c in each service's compose command:
    # roughly two waves of what one container can hold at once.
    POLICIES = [
        ScalePolicy("extraction-wo", ("q_parse_wo",), per_worker=16),
        ScalePolicy("extraction-pnid", ("q_extract_pnid",), per_worker=8),
        ScalePolicy("extraction-text", ("q_extract_text",), per_worker=64),
        ScalePolicy("ingestion", ("q_classify",), per_worker=32),
        ScalePolicy("resolution", ("q_resolve",), per_worker=32),
    ]

    def __init__(self, compose_file=None, project="plantmind", runner=None,
                 background=True):
        self._file = str(compose_file or REPO / "docker-compose.yml")
        self._project = project
        self._run = runner or self._compose      # seam: tests inject a fake
        self._background = background
        self._inflight = set()
        self._lock = threading.Lock()

    def spec(self, name) -> ComposeSpec:
        for spec in self.SPECS:
            if spec.name == name:
                return spec
        raise KeyError(f"no compose service named {name!r}")

    def count(self, name) -> int:
        out = self._run(["ps", "-q", name])
        return len([line for line in out.splitlines() if line.strip()])

    def scale_to(self, name, target: int):
        """Ask compose for `target` containers, without waiting for it.

        Scaling down blocks until the container is gone, and a worker holding a
        long task can legitimately take the full stop_grace_period to finish
        it. Doing that on the caller's thread would stall every other stage
        behind one slow shutdown, so the command runs on its own thread and the
        next tick picks up wherever it got to. One scale per service at a time:
        docker is the source of truth for the count, and asking again while the
        last answer is still landing just queues up duplicate work.
        """
        with self._lock:
            if name in self._inflight:
                return
            self._inflight.add(name)

        if self._background:
            threading.Thread(target=self._scale_now, args=(name, target),
                             daemon=True, name=f"scale-{name}").start()
        else:
            self._scale_now(name, target)

    def _scale_now(self, name, target):
        try:
            # --no-recreate leaves existing containers alone, so scaling one
            # lane never restarts the rest of the stack. --no-build matters
            # more than it looks: this runs inside a container where the build
            # context does not exist, and compose would otherwise try to use it.
            self._run(["up", "-d", "--no-recreate", "--no-build",
                       "--scale", f"{name}={target}", name])
        except Exception as e:
            log.error("compose scale failed", service=name, target=target,
                      error=str(e))
        finally:
            with self._lock:
                self._inflight.discard(name)

    def reap_drained(self, grace=45):
        pass        # compose removes the container as part of scaling down

    def _compose(self, args) -> str:
        cmd = ["docker", "compose", "-f", self._file, "-p", self._project] + args
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(
                f"{' '.join(cmd)} -> exit {done.returncode}: "
                f"{done.stderr.strip()[:200]}")
        return done.stdout
