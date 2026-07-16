"""A connector is a data source that yields documents into the pipeline on
a schedule. Each yields SyncItems in ascending marker order; the runner
remembers the last marker so the next sync only picks up what's new. The
hash gate downstream makes re-yielding an unchanged file harmless anyway."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SyncItem:
    filename: str
    data: bytes
    marker: str          # sortable cursor token (mtime, last-modified, etag...)


class Connector(ABC):
    def __init__(self, id: str):
        self.id = id

    @abstractmethod
    def fetch(self, since: str):
        """Yield SyncItems newer than `since` (a prior marker, or '0'),
        in ascending marker order."""
        raise NotImplementedError
