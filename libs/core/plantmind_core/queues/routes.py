"""Task routing between services. A Route pairs a task name with the queue
it runs on, so a task can't be sent to the wrong pool by accident. Services
call routes by name through the broker — no cross-service imports."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    task: str
    queue: str

    def send(self, app, *args, **kwargs):
        """Enqueue this task on its own queue via any celery app."""
        return app.send_task(self.task, args=args, kwargs=kwargs, queue=self.queue)


class Routes:
    classify = Route("ingestion.tasks.classify", "q_classify")
    parse_workorder = Route("extraction.tasks.parse_workorder", "q_parse_wo")
    extract_pnid = Route("extraction.tasks.extract_pnid", "q_extract_pnid")
    extract_text = Route("extraction.tasks.extract_text", "q_extract_text")
    extract_manual = Route("extraction.tasks.extract_manual", "q_extract_text")
    extract_email = Route("extraction.tasks.extract_email", "q_extract_text")
    extract_image = Route("extraction.tasks.extract_image", "q_extract_pnid")
    resolve = Route("resolution.tasks.resolve", "q_resolve")
    flush = Route("graphd.writer.flush_write_buffer", "q_write")
    denoise = Route("graphd.denoise.run", "q_write")

    @classmethod
    def all(cls) -> list[Route]:
        return [v for v in vars(cls).values() if isinstance(v, Route)]
