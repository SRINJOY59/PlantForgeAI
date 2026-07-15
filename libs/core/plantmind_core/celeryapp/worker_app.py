"""Celery wrapper shared by all worker services, so the delivery policy
lives in one place and tasks are always registered/scheduled through their
Route (right name, right queue)."""

from celery import Celery

from plantmind_core.config import get_settings
from plantmind_core.queues import Route


class WorkerApp:
    def __init__(self, service: str):
        s = get_settings()
        self.service = service
        self.app = Celery(service, broker=s.redis_url)
        self.app.conf.update(
            # json only — pickle over the wire is an RCE waiting to happen
            task_serializer="json",
            accept_content=["json"],
            # fire-and-forget pipeline: outcomes flow through redis streams
            # and the graph itself; celery results would just burn memory
            task_ignore_result=True,

            # at-least-once delivery: ack after the task runs, re-deliver if
            # the worker dies mid-task. Safe because every handler is
            # idempotent (content hashes, MERGE writes, prov_hash keys).
            task_acks_late=True,
            task_reject_on_worker_lost=True,

            # take one message at a time — a 30s VLM extraction shouldn't
            # hoard quick parses in its prefetch buffer
            worker_prefetch_multiplier=1,

            # a hung LLM/DB call gets a soft warning at 9 min, hard kill at
            # 10, then the task re-queues instead of jamming the pool
            task_soft_time_limit=540,
            task_time_limit=600,

            broker_connection_retry_on_startup=True,
            timezone="UTC",
        )

    def task(self, route: Route):
        """Decorator: register a function under the route's task name."""
        return self.app.task(name=route.task)

    def schedule(self, route: Route, every_seconds: float):
        """Run the route's task periodically, on its own queue."""
        beat = dict(self.app.conf.beat_schedule or {})
        beat[route.task] = {
            "task": route.task,
            "schedule": every_seconds,
            "options": {"queue": route.queue},
        }
        self.app.conf.beat_schedule = beat

    def send(self, route: Route, *args, **kwargs):
        """Hand work to another service through the broker."""
        return route.send(self.app, *args, **kwargs)
