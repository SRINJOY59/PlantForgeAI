"""Builds the configured connectors from connectors.json. Adding a source
type is registering one class here."""

import importlib
import json
from pathlib import Path

from plantmind_core.telemetry import get_logger

log = get_logger("connectors.registry")

# type -> "module:class". Imported on demand rather than up front, because
# several connectors carry a vendor SDK that the deployment may not have: the
# Google Drive client needs google-auth, and importing it eagerly here meant a
# worker without that wheel could not build a *folder* connector either. One
# absent optional dependency took the whole registry down, and the traceback
# named google.auth rather than anything the operator had configured.
TYPES = {
    "folder": "connectors.folder:FolderConnector",
    "bucket": "connectors.bucket:BucketConnector",
    "sharepoint": "connectors.sharepoint:SharePointConnector",
    "upkeep": "connectors.upkeep:UpKeepConnector",
    "outlook": "connectors.outlook:OutlookConnector",
    "gdrive": "connectors.gdrive:GoogleDriveConnector",
}


def connector_class(kind: str):
    """-> the class for `kind`, or None if it is unknown or unavailable.

    Unknown and unavailable are logged differently on purpose: a typo in
    connectors.json and a missing SDK need different things done about them.
    """
    target = TYPES.get(kind)
    if not target:
        log.warning("unknown connector type", type=kind,
                    known=sorted(TYPES))
        return None

    module_name, class_name = target.split(":")
    try:
        return getattr(importlib.import_module(module_name), class_name)
    except ImportError as e:
        log.error("connector type unavailable - install its dependency",
                  type=kind, module=module_name, error=str(e))
    except AttributeError as e:
        log.error("connector class missing", type=kind, target=target,
                  error=str(e))
    return None


def load_connectors(config_path: str) -> list:
    path = Path(config_path)
    if not path.exists():
        log.warning("no connectors config", path=str(path))
        return []
    connectors = []
    for entry in json.loads(path.read_text()):
        entry = {k: v for k, v in entry.items() if not k.startswith("_")}
        factory = connector_class(entry.pop("type", ""))
        if not factory:
            continue
        try:
            connectors.append(factory(**entry))
        except Exception as e:
            # one misconfigured source must not stop the others syncing
            log.error("could not build connector", id=entry.get("id"),
                      error_type=type(e).__name__, error=str(e))
    return connectors
