"""Builds the configured connectors from connectors.json. Adding a source
type is registering one class here."""

import json
from pathlib import Path

from plantmind_core.telemetry import get_logger

from connectors.bucket import BucketConnector
from connectors.folder import FolderConnector
from connectors.sharepoint import SharePointConnector
from connectors.upkeep import UpKeepConnector
from connectors.outlook import OutlookConnector
from connectors.gdrive import GoogleDriveConnector

log = get_logger("connectors.registry")

TYPES = {
    "folder": FolderConnector,
    "bucket": BucketConnector,
    "sharepoint": SharePointConnector,
    "upkeep": UpKeepConnector,
    "outlook": OutlookConnector,
    "gdrive": GoogleDriveConnector,
}


def load_connectors(config_path: str) -> list:
    path = Path(config_path)
    if not path.exists():
        log.warning("no connectors config", path=str(path))
        return []
    connectors = []
    for entry in json.loads(path.read_text()):
        kind = entry.pop("type")
        factory = TYPES.get(kind)
        if not factory:
            log.warning("unknown connector type", type=kind)
            continue
        connectors.append(factory(**entry))
    return connectors
