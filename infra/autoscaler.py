"""Match the number of worker processes to the depth of the queues they
consume.

Celery ships --autoscale, but it resizes the thread pool inside a single
process, and on celery 5.6 neither the thread nor the prefork TaskPool exposes
the grow/shrink its autoscaler calls. So we scale workers instead, which is the
axis that actually matters: it is the same signal and the same policy KEDA
applies in kubernetes, where the unit is a pod.

A "worker" here is whatever the fleet says it is. QueueAutoscaler only asks for
spec / count / scale_to / reap_drained, so WorkerFleet answers with local
subprocesses and ComposeFleet answers with containers, and the policy below
does not know or care which.

Tearing a worker down mid-job is survivable - tasks are idempotent and
acks_late redelivers - but both fleets still ask for a warm shutdown, because
the redis broker will not redeliver an unacked task until visibility_timeout,
an hour by default.
"""

import math
import threading
from dataclasses import dataclass

from plantmind_core.telemetry import get_logger

log = get_logger("infra.autoscaler")


@dataclass(frozen=True)
class ScalePolicy:
    """How much backlog justifies one more worker for a stage. per_worker is
    the queue depth a single replica is expected to absorb - lower it to make
    the stage scale out sooner."""

    service: str
    queues: tuple
    per_worker: int

    def backlog(self, depths: dict) -> int:
        return sum(depths.get(q, 0) for q in self.queues)

    def desired(self, depths: dict, minimum: int, maximum: int) -> int:
        want = math.ceil(self.backlog(depths) / self.per_worker)
        return max(minimum, min(maximum, want))


class QueueAutoscaler:
    """Polls queue depth and walks the fleet toward it.

    Up on the first busy tick, down only after several quiet ones. A burst
    should get capacity immediately; a lull between two batches should not
    tear down workers we are about to want back.
    """

    POLICIES = [
        ScalePolicy("extraction",
                    ("q_parse_wo", "q_extract_pnid", "q_extract_text"),
                    per_worker=16),
        ScalePolicy("ingestion", ("q_classify",), per_worker=32),
        ScalePolicy("resolution", ("q_resolve",), per_worker=32),
        # graphd is absent on purpose: single writer, see WorkerFleet.SPECS
    ]

    def __init__(self, fleet, bus, policies=None, quiet_ticks=3):
        self._fleet = fleet
        self._bus = bus
        self._policies = self.POLICIES if policies is None else policies
        self._quiet_ticks = quiet_ticks
        self._quiet = {}
        self._stop = threading.Event()
        self._thread = None

    def tick(self):
        self._fleet.reap_drained()
        depths = self._bus.depths()
        for policy in self._policies:
            self._apply(policy, depths)

    def _apply(self, policy, depths):
        spec = self._fleet.spec(policy.service)
        if not spec.scalable:
            return

        current = self._fleet.count(policy.service)
        desired = policy.desired(depths, spec.min_replicas, spec.max_replicas)

        if desired > current:
            self._quiet[policy.service] = 0
            self._fleet.scale_to(policy.service, desired)
            log.info("scaled up", service=policy.service, replicas=desired,
                     backlog=policy.backlog(depths))
        elif desired < current:
            quiet = self._quiet.get(policy.service, 0) + 1
            self._quiet[policy.service] = quiet
            if quiet >= self._quiet_ticks:
                self._quiet[policy.service] = 0
                self._fleet.scale_to(policy.service, current - 1)  # one at a time
                log.info("scaled down", service=policy.service,
                         replicas=current - 1, backlog=policy.backlog(depths))
        else:
            self._quiet[policy.service] = 0

    def snapshot(self) -> dict:
        """What the fleet looks like right now, for /metrics or a demo."""
        return {p.service: self._fleet.count(p.service) for p in self._policies}

    # -- background loop -----------------------------------------------------
    def start(self, interval=5.0):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(interval,),
                                        daemon=True, name="autoscaler")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self, interval):
        while not self._stop.wait(interval):
            try:
                self.tick()
            except Exception as e:
                # a transient redis blip should cost one tick, not the loop
                log.error("autoscale tick failed", error=str(e))
