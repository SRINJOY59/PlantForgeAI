from unittest.mock import MagicMock

import pytest

from plantmind_core.celeryapp import WorkerApp
from plantmind_core.queues import Route, Routes


def test_worker_app_applies_delivery_guarantees():
    conf = WorkerApp("testsvc").app.conf

    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_serializer == "json"
    assert conf.accept_content == ["json"]
    assert conf.task_ignore_result is True
    assert conf.task_time_limit > conf.task_soft_time_limit


def test_task_decorator_registers_under_route_name():
    worker = WorkerApp("testsvc")

    @worker.task(Routes.flush)
    def my_flush():
        return "ok"

    assert Routes.flush.task in worker.app.tasks


def test_schedule_puts_task_on_its_own_queue():
    worker = WorkerApp("testsvc")

    worker.schedule(Routes.flush, every_seconds=2.0)
    worker.schedule(Routes.denoise, every_seconds=3600)

    beat = worker.app.conf.beat_schedule
    assert beat[Routes.flush.task]["schedule"] == 2.0
    assert beat[Routes.flush.task]["options"]["queue"] == "q_write"
    assert Routes.denoise.task in beat  # second schedule didn't overwrite the first


def test_every_route_has_task_and_queue():
    routes = Routes.all()
    assert len(routes) >= 6
    for route in routes:
        assert "." in route.task      # fully qualified: service.module.name
        assert route.queue.startswith("q_")


def test_route_send_targets_its_own_queue():
    app = MagicMock()

    Routes.parse_workorder.send(app, "doc-123", priority=1)

    app.send_task.assert_called_once_with(
        "extraction.tasks.parse_workorder",
        args=("doc-123",),
        kwargs={"priority": 1},
        queue="q_parse_wo",
    )


def test_worker_send_delegates_through_route():
    worker = WorkerApp("testsvc")
    worker.app = MagicMock()

    worker.send(Routes.resolve, "payload")

    worker.app.send_task.assert_called_once()
    _, called_kwargs = worker.app.send_task.call_args
    assert called_kwargs["queue"] == "q_resolve"


def test_routes_are_immutable():
    with pytest.raises(Exception):
        Routes.flush.queue = "q_other"
