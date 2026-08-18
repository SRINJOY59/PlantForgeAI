"""Read side of the historian.

The thin wrapper the query callers hold - the trend charts, and the diagnostics
service that reads the window around a fault. It lives in core, next to the
TimeseriesDB it wraps, precisely because more than one service reads history: the
historian owns the write loop, but "what can be asked of the past" is shared, and
a reader that sat inside the historian service would force every other reader to
depend on that whole service to ask a question.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from plantmind_core.telemetry import get_logger
from plantmind_core.timeseries.client import TimeseriesDB

log = get_logger("timeseries.reader")


class HistorianReader:
    def __init__(self, db: TimeseriesDB):
        self._db = db

    @classmethod
    def from_settings(cls) -> "HistorianReader | None":
        db = TimeseriesDB.from_settings()
        return cls(db) if db is not None else None

    def window(self, tag_ids: list[str], start: datetime, end: datetime):
        """Raw samples for tags in [start, end], oldest first."""
        return self._db.window(tag_ids, start, end)

    def recent(self, tag_ids: list[str], minutes: int = 10):
        """The last `minutes` of history for a set of tags - the default shape
        a chart or a just-tripped-alarm investigation asks for."""
        end = datetime.now(timezone.utc)
        return self._db.window(tag_ids, end - timedelta(minutes=minutes), end)

    def around(self, tag_ids: list[str], moment: datetime,
               before_s: int = 600, after_s: int = 120):
        """The window bracketing an event - lead-in before, reaction after.
        This is the read the fault-signature extractor is built on."""
        start = moment - timedelta(seconds=before_s)
        end = moment + timedelta(seconds=after_s)
        return self._db.window(tag_ids, start, end)

    def latest(self, tag_ids: list[str]):
        return self._db.latest(tag_ids)

    def known_tags(self, since_minutes: int = 1440) -> list[str]:
        """The plant's tag universe as the historian has actually seen it - what
        a live diagnosis reads across without hard-coding a topology."""
        return self._db.distinct_tags(since_minutes)
