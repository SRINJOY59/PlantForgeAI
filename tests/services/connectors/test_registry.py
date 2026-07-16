import json

from connectors.folder import FolderConnector
from connectors.registry import load_connectors


def test_builds_folder_connector_from_config(tmp_path):
    cfg = tmp_path / "connectors.json"
    cfg.write_text(json.dumps([
        {"type": "folder", "id": "inbox", "path": "data/inbox"}]))

    connectors = load_connectors(str(cfg))

    assert len(connectors) == 1
    assert isinstance(connectors[0], FolderConnector)
    assert connectors[0].id == "inbox"


def test_missing_config_returns_empty(tmp_path):
    assert load_connectors(str(tmp_path / "nope.json")) == []


def test_unknown_type_skipped(tmp_path):
    cfg = tmp_path / "connectors.json"
    cfg.write_text(json.dumps([
        {"type": "folder", "id": "ok", "path": "x"},
        {"type": "quantum-teleporter", "id": "bad"}]))

    connectors = load_connectors(str(cfg))
    assert [c.id for c in connectors] == ["ok"]
