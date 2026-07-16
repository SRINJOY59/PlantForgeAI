"""The autoscaler decides how much of the fleet exists, so the tests that
matter are the ones about restraint: it must not flap, and it must never grow
graphd."""

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from infra.autoscaler import QueueAutoscaler, ScalePolicy
from infra.celery_workers import WorkerFleet, WorkerSpec
from infra.compose_fleet import ComposeFleet

EXTRACTION = WorkerSpec("extraction", "extraction.tasks", "q_parse_wo",
                        "threads", 8, min_replicas=1, max_replicas=4)
PINNED = WorkerSpec("graphd", "graphd.tasks", "q_write", "solo", 1)

POLICY = ScalePolicy("extraction", ("q_parse_wo",), per_worker=16)


class FakeFleet:
    def __init__(self, specs):
        self._specs = {s.name: s for s in specs}
        self.counts = {s.name: s.min_replicas for s in specs}
        self.events = []
        self.reaped = 0

    def spec(self, name):
        return self._specs[name]

    def count(self, name):
        return self.counts[name]

    def scale_to(self, name, target):
        direction = "up" if target > self.counts[name] else "down"
        self.events.append((direction, name, target))
        self.counts[name] = target

    def reap_drained(self, grace=45):
        self.reaped += 1


class FakeBus:
    def __init__(self, **depths):
        self._depths = depths

    def depths(self):
        return dict(self._depths)

    def set(self, **depths):
        self._depths = depths


def scaler(depths, specs=(EXTRACTION,), policies=(POLICY,), quiet_ticks=3):
    fleet = FakeFleet(list(specs))
    bus = FakeBus(**depths)
    return fleet, bus, QueueAutoscaler(fleet, bus, policies=list(policies),
                                       quiet_ticks=quiet_ticks)


# -- policy arithmetic --------------------------------------------------------
def test_backlog_sums_every_queue_the_stage_consumes():
    policy = ScalePolicy("extraction",
                         ("q_parse_wo", "q_extract_pnid", "q_extract_text"),
                         per_worker=16)
    assert policy.backlog({"q_parse_wo": 5, "q_extract_pnid": 6,
                           "q_extract_text": 5}) == 16


def test_a_queue_redis_has_never_seen_counts_as_zero():
    assert POLICY.backlog({}) == 0


def test_desired_rounds_up_so_a_partial_batch_still_gets_a_worker():
    assert POLICY.desired({"q_parse_wo": 17}, 1, 4) == 2


def test_desired_never_drops_below_the_minimum():
    assert POLICY.desired({"q_parse_wo": 0}, 1, 4) == 1


def test_desired_clamps_to_the_maximum():
    assert POLICY.desired({"q_parse_wo": 10_000}, 1, 4) == 4


# -- scaling up ---------------------------------------------------------------
def test_idle_fleet_never_moves():
    fleet, _, auto = scaler({"q_parse_wo": 0})
    for _ in range(10):
        auto.tick()
    assert fleet.counts["extraction"] == 1
    assert fleet.events == []


def test_a_burst_gets_all_its_capacity_in_one_tick():
    fleet, _, auto = scaler({"q_parse_wo": 50})     # ceil(50/16) = 4
    auto.tick()
    assert fleet.counts["extraction"] == 4
    # one scale_to, not three scale_ups: a container fleet turns each of these
    # into a docker call, so asking once matters
    assert fleet.events == [("up", "extraction", 4)]


def test_scale_up_stops_at_max_however_deep_the_queue():
    fleet, _, auto = scaler({"q_parse_wo": 10_000})
    auto.tick()
    assert fleet.counts["extraction"] == 4


# -- scaling down -------------------------------------------------------------
def test_scale_down_waits_for_consecutive_quiet_ticks():
    fleet, bus, auto = scaler({"q_parse_wo": 50})
    auto.tick()
    assert fleet.counts["extraction"] == 4

    bus.set(q_parse_wo=0)
    auto.tick()
    auto.tick()
    assert fleet.counts["extraction"] == 4, "must not tear down on a lull"
    auto.tick()
    assert fleet.counts["extraction"] == 3


def test_scale_down_gives_up_one_replica_at_a_time():
    fleet, bus, auto = scaler({"q_parse_wo": 50})
    auto.tick()
    bus.set(q_parse_wo=0)
    for _ in range(3):
        auto.tick()
    assert fleet.counts["extraction"] == 3
    for _ in range(3):
        auto.tick()
    assert fleet.counts["extraction"] == 2


def test_work_arriving_resets_the_quiet_counter():
    fleet, bus, auto = scaler({"q_parse_wo": 50})
    auto.tick()

    bus.set(q_parse_wo=0)
    auto.tick()
    auto.tick()                    # two quiet ticks banked

    bus.set(q_parse_wo=50)         # still busy - forget them
    auto.tick()
    assert fleet.counts["extraction"] == 4

    bus.set(q_parse_wo=0)
    auto.tick()
    auto.tick()
    assert fleet.counts["extraction"] == 4, "counter should have restarted"
    auto.tick()
    assert fleet.counts["extraction"] == 3


def test_scale_down_never_goes_below_the_minimum():
    fleet, bus, auto = scaler({"q_parse_wo": 0})
    for _ in range(30):
        auto.tick()
    assert fleet.counts["extraction"] == 1


# -- the single-writer invariant ---------------------------------------------
def test_a_pinned_spec_is_not_scalable():
    assert PINNED.scalable is False
    assert EXTRACTION.scalable is True


def test_a_pinned_stage_is_left_alone_even_with_a_huge_backlog():
    fleet, _, auto = scaler({"q_write": 5_000}, specs=(PINNED,),
                            policies=(ScalePolicy("graphd", ("q_write",),
                                                  per_worker=1),))
    auto.tick()
    assert fleet.counts["graphd"] == 1
    assert fleet.events == []


def test_default_policies_do_not_mention_graphd():
    # belt and braces: graphd is pinned by its spec *and* absent from the
    # policy list. Losing either one would still leave one writer.
    assert "graphd" not in [p.service for p in QueueAutoscaler.POLICIES]


def test_the_real_graphd_spec_is_pinned_to_exactly_one():
    spec = WorkerFleet().spec("graphd")
    assert spec.min_replicas == spec.max_replicas == 1
    assert not spec.scalable


def test_every_default_policy_names_a_real_scalable_stage():
    fleet = WorkerFleet()
    for policy in QueueAutoscaler.POLICIES:
        spec = fleet.spec(policy.service)      # raises if the name is wrong
        assert spec.scalable, f"{policy.service} is pinned but has a policy"


# -- housekeeping -------------------------------------------------------------
def test_every_tick_reaps_drained_replicas():
    fleet, _, auto = scaler({"q_parse_wo": 0})
    auto.tick()
    auto.tick()
    assert fleet.reaped == 2


def test_snapshot_reports_the_live_count_per_stage():
    fleet, _, auto = scaler({"q_parse_wo": 50})
    auto.tick()
    assert auto.snapshot() == {"extraction": 4}


# -- the same autoscaler, driving containers ---------------------------------
class FakeCompose:
    """Stands in for the `docker compose` CLI."""

    def __init__(self, counts=None):
        self.counts = counts or {}
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "ps":
            name = args[2]
            return "\n".join(f"container{i}" for i in
                             range(self.counts.get(name, 0)))
        if args[0] == "up":
            scale = next(a for a in args if "=" in a and not a.startswith("-"))
            name, target = scale.split("=")
            self.counts[name] = int(target)
        return ""


def fleet_for(cli):
    # background=False keeps the scale on this thread so tests can assert on it
    return ComposeFleet(runner=cli, background=False)


def test_compose_fleet_counts_containers_from_ps():
    cli = FakeCompose({"extraction-text": 3})
    assert fleet_for(cli).count("extraction-text") == 3
    assert cli.calls == [["ps", "-q", "extraction-text"]]


def test_compose_fleet_reports_zero_when_a_service_has_no_containers():
    assert fleet_for(FakeCompose({})).count("extraction-text") == 0


def test_compose_fleet_scales_in_a_single_command():
    cli = FakeCompose({"extraction-text": 1})
    fleet_for(cli).scale_to("extraction-text", 4)
    assert cli.calls[-1] == ["up", "-d", "--no-recreate", "--no-build",
                             "--scale", "extraction-text=4", "extraction-text"]
    assert cli.counts["extraction-text"] == 4


def test_compose_fleet_never_builds():
    # it runs inside a container where the build context does not exist
    cli = FakeCompose({"extraction-text": 1})
    fleet_for(cli).scale_to("extraction-text", 2)
    assert "--no-build" in cli.calls[-1]


def test_a_scale_still_running_is_not_issued_again():
    # scaling down waits out stop_grace_period, so ticks keep arriving while
    # the last command is in flight. They must not stack up.
    released = threading.Event()
    started = threading.Event()
    calls = []

    def slow(args):
        calls.append(args)
        if args[0] == "up":
            started.set()
            released.wait(5)
        return ""

    fleet = ComposeFleet(runner=slow)          # background=True: real threads
    fleet.scale_to("extraction-text", 4)
    assert started.wait(5), "first scale never started"

    fleet.scale_to("extraction-text", 4)       # tick again, still in flight
    fleet.scale_to("extraction-text", 4)
    assert len([c for c in calls if c[0] == "up"]) == 1

    released.set()
    time.sleep(0.2)
    fleet.scale_to("extraction-text", 3)       # in-flight cleared, this runs
    time.sleep(0.2)
    assert len([c for c in calls if c[0] == "up"]) == 2


def test_a_scale_that_blows_up_does_not_wedge_the_service():
    # the finally: if a failed scale left the service marked in-flight, it
    # would never scale again
    def broken(args):
        if args[0] == "up":
            raise RuntimeError("daemon unreachable")
        return ""

    fleet = ComposeFleet(runner=broken, background=False)
    fleet.scale_to("extraction-text", 4)       # swallowed and logged
    assert "extraction-text" not in fleet._inflight


def test_scaling_one_service_does_not_block_another():
    released = threading.Event()
    started = threading.Event()
    calls = []

    def slow(args):
        calls.append(args)
        if args[0] == "up" and "extraction-text=2" in args:
            started.set()
            released.wait(5)
        return ""

    fleet = ComposeFleet(runner=slow)
    fleet.scale_to("extraction-text", 2)
    assert started.wait(5)
    fleet.scale_to("ingestion", 3)             # different service, must proceed
    time.sleep(0.2)
    released.set()
    assert any("ingestion=3" in c for c in calls if c[0] == "up")


def test_compose_fleet_pins_graphd():
    fleet = fleet_for(FakeCompose())
    assert not fleet.spec("graphd").scalable
    assert fleet.spec("extraction-text").scalable


def test_compose_policies_only_name_scalable_services():
    fleet = fleet_for(FakeCompose())
    for policy in ComposeFleet.POLICIES:
        assert fleet.spec(policy.service).scalable


def test_compose_policies_do_not_mention_graphd():
    assert "graphd" not in [p.service for p in ComposeFleet.POLICIES]


def test_compose_policy_queues_match_the_compose_commands():
    # each compose service consumes exactly one queue; a policy watching the
    # wrong one would scale on a backlog its containers cannot touch
    expected = {
        "extraction-wo": ("q_parse_wo",),
        "extraction-pnid": ("q_extract_pnid",),
        "extraction-text": ("q_extract_text",),
        "ingestion": ("q_classify",),
        "resolution": ("q_resolve",),
    }
    assert {p.service: p.queues for p in ComposeFleet.POLICIES} == expected


def test_the_autoscaler_drives_a_compose_fleet_unchanged():
    cli = FakeCompose({"extraction-text": 1})
    fleet = fleet_for(cli)
    bus = FakeBus(q_extract_text=200)          # ceil(200/64) = 4
    auto = QueueAutoscaler(fleet, bus, policies=ComposeFleet.POLICIES)

    auto.tick()
    assert cli.counts["extraction-text"] == 4

    bus.set(q_extract_text=0)
    auto.tick()
    auto.tick()
    assert cli.counts["extraction-text"] == 4, "must not flap"
    auto.tick()
    assert cli.counts["extraction-text"] == 3


def test_a_failing_ps_surfaces_the_stderr():
    # count() is read-only and on the tick thread, so unlike a scale it is
    # allowed to raise - the autoscaler's loop catches and logs it
    def broken(args):
        raise RuntimeError("docker compose -> exit 1: no such service")

    with pytest.raises(RuntimeError, match="no such service"):
        fleet_for(broken).count("extraction-text")
