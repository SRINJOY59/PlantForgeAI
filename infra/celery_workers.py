"""Local celery worker processes, one per pipeline stage - the dev-machine
equivalent of the worker containers in docker-compose.yml.

A stage runs one or more interchangeable replicas. QueueAutoscaler moves that
count between a spec's min and max; leaving them equal pins the stage.
"""

import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOGS = REPO / "logs"


@dataclass(frozen=True)
class WorkerSpec:
    """One pipeline stage. start() brings up min_replicas of it."""

    name: str
    module: str
    queues: str
    pool: str
    concurrency: int
    beat: bool = False
    min_replicas: int = 1
    max_replicas: int = 1

    @property
    def scalable(self) -> bool:
        return self.max_replicas > self.min_replicas


@dataclass
class Replica:
    """A running worker process. `node` is its celery node name, which is how
    we address it for a warm shutdown."""

    label: str
    node: str
    proc: subprocess.Popen
    log: object
    draining_since: float = 0.0


class WorkerFleet:
    # prefork is broken on windows, hence threads/solo pools
    SPECS = [
        WorkerSpec("ingestion", "ingestion.tasks", "q_classify",
                   "threads", 4, max_replicas=3),
        WorkerSpec("extraction", "extraction.tasks",
                   "q_parse_wo,q_extract_pnid,q_extract_text",
                   "threads", 8, max_replicas=4),
        WorkerSpec("resolution", "resolution.tasks", "q_resolve",
                   "threads", 4, max_replicas=3),
        # graphd stays at exactly one. A second writer would race on the
        # buffer and cost us the lock-free batched UNWIND, so min == max
        # and the autoscaler skips it.
        WorkerSpec("graphd", "graphd.tasks", "q_write", "solo", 1, beat=True),
        WorkerSpec("connectors", "connectors.tasks", "q_connectors",
                   "threads", 2, beat=True),
    ]

    def __init__(self):
        self._replicas = {spec.name: [] for spec in self.SPECS}
        self._counter = {spec.name: 0 for spec in self.SPECS}
        self._beats = []
        self._draining = []
        self._app = None

    # -- lifecycle -----------------------------------------------------------
    def start(self, settle_seconds=8):
        LOGS.mkdir(exist_ok=True)
        for spec in self.SPECS:
            for _ in range(spec.min_replicas):
                self.scale_up(spec.name)
            if spec.beat:
                self._start_beat(spec)
        time.sleep(settle_seconds)   # let them connect before anyone submits

    def stop(self):
        everything = ([r for rs in self._replicas.values() for r in rs]
                      + self._draining + self._beats)
        for replica in everything:
            replica.proc.terminate()
            replica.log.close()
        if everything:
            print(f"workers stopped ({len(everything)}) - logs in logs/")
        self._replicas = {spec.name: [] for spec in self.SPECS}
        self._beats, self._draining = [], []

    # -- scaling -------------------------------------------------------------
    def spec(self, name) -> WorkerSpec:
        for spec in self.SPECS:
            if spec.name == name:
                return spec
        raise KeyError(f"no worker spec named {name!r}")

    def count(self, name) -> int:
        """Live replicas. Draining ones are on their way out, so they do not
        count as capacity."""
        return len(self._replicas[name])

    def nodes(self, name) -> list:
        return [r.node for r in self._replicas[name]]

    def scale_to(self, name, target: int):
        """Bring a stage to `target` replicas. The autoscaler asks in these
        terms so a fleet backed by containers can do it in one call instead of
        one per replica."""
        while self.count(name) < target:
            self.scale_up(name)
        while self.count(name) > target:
            self.scale_down(name)

    def scale_up(self, name) -> str:
        spec = self.spec(name)
        self._counter[name] += 1
        label = f"{name}-{self._counter[name]}"
        node = f"{label}@{socket.gethostname()}"
        replica = self._spawn(
            label, node,
            [sys.executable, "-m", "celery", "-A", spec.module, "worker",
             "-Q", spec.queues, "-P", spec.pool, "-c", str(spec.concurrency),
             "-n", node, "--loglevel", "info"])
        self._replicas[name].append(replica)
        return node

    def scale_down(self, name):
        """Warm-shut the newest replica: it finishes what it is holding and
        acks before exiting. Terminating instead would leave those tasks
        unacked, and the redis broker does not redeliver an unacked task until
        visibility_timeout - an hour by default. Returns the node name, or
        None if the stage has nobody left to stop."""
        if not self._replicas[name]:
            return None
        replica = self._replicas[name].pop()
        self._control().broadcast("shutdown", destination=[replica.node])
        replica.draining_since = time.monotonic()
        self._draining.append(replica)
        return replica.node

    def reap_drained(self, grace=45):
        """Close out replicas that have finished draining. Called every
        autoscaler tick so scale_down never has to block on the shutdown."""
        still_going = []
        for replica in self._draining:
            if replica.proc.poll() is not None:
                replica.log.close()
            elif time.monotonic() - replica.draining_since > grace:
                replica.proc.terminate()          # would not go quietly
                replica.log.close()
            else:
                still_going.append(replica)
        self._draining = still_going

    # -- plumbing ------------------------------------------------------------
    def _start_beat(self, spec):
        # celery's embedded beat (-B) refuses to run on windows, so the
        # scheduler gets its own process. Its schedule file is per-service:
        # two beats sharing one shelve corrupt each other's state.
        self._beats.append(self._spawn(
            f"{spec.name}-beat", "",
            [sys.executable, "-m", "celery", "-A", spec.module, "beat",
             "-s", str(LOGS / f"beat-schedule-{spec.name}"),
             "--loglevel", "info"]))

    def _spawn(self, label, node, cmd) -> Replica:
        logfile = open(LOGS / f"{label}.log", "a", encoding="utf-8")
        logfile.write(f"\n===== run {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        logfile.flush()
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=logfile,
                                stderr=subprocess.STDOUT)
        print(f"worker: {label} up (pid {proc.pid})")
        return Replica(label=label, node=node, proc=proc, log=logfile)

    def _control(self):
        # any app pointed at the same broker can send control commands; this
        # one exists only to talk, never to run tasks
        if self._app is None:
            from celery import Celery

            from plantmind_core.config import get_settings
            self._app = Celery(broker=get_settings().redis_url)
        return self._app.control
