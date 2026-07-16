"""Watches a folder (a shared drive, a SharePoint-synced directory, an
export dump) and pulls files modified since the last sync. The workhorse
connector - most plants can point one at a network share on day one."""

from pathlib import Path

from connectors.base import Connector, SyncItem


class FolderConnector(Connector):
    def __init__(self, id: str, path: str, recursive=True):
        super().__init__(id)
        self._root = Path(path)
        self._recursive = recursive

    def fetch(self, since: str):
        floor = float(since) if since and since != "0" else 0.0
        walk = self._root.rglob("*") if self._recursive else self._root.glob("*")
        files = [p for p in walk if p.is_file() and not p.name.startswith(".")]
        # ascending mtime so the runner's last marker is the newest seen
        for path in sorted(files, key=lambda p: p.stat().st_mtime):
            mtime = path.stat().st_mtime
            if mtime <= floor:
                continue
            yield SyncItem(filename=path.name, data=path.read_bytes(),
                           marker=f"{mtime:.6f}")
