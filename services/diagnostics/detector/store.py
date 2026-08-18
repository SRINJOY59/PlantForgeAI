"""Persistence for the trained PCA anomaly detector model using MinIO ObjectStore."""

from __future__ import annotations

import json
from pathlib import Path

from diagnostics.detector.model import PCAModel
from plantmind_core.storage import ObjectStore
from plantmind_core.telemetry import get_logger

log = get_logger("diagnostics.detector.store")

MINIO_MODEL_KEY = "models/pca_detector.json"
LOCAL_FALLBACK_PATH = Path("data/pca_detector.json")


class DetectorStore:
    """Save and load calibrated PCA anomaly models via MinIO ObjectStore."""

    def __init__(self, key: str = MINIO_MODEL_KEY, local_fallback: Path | str = LOCAL_FALLBACK_PATH):
        self._key = key
        self._local_path = Path(local_fallback)
        self._store: ObjectStore | None = None
        try:
            self._store = ObjectStore.from_settings()
        except Exception as e:
            log.warning("minio not available; using local detector store", error=str(e)[:120])

    def save(self, model: PCAModel) -> None:
        """Persist PCAModel to MinIO (and local fallback)."""
        payload_bytes = json.dumps(model.to_dict(), indent=2).encode("utf-8")

        # 1. Save to MinIO
        if self._store is not None:
            try:
                self._store.put(self._key, payload_bytes, content_type="application/json")
                log.info("pca detector model saved to minio", key=self._key,
                         tags=len(model.tags), k=model.k_components)
            except Exception as e:
                log.warning("failed to save pca model to minio; writing local file", error=str(e)[:120])

        # 2. Local fallback
        try:
            self._local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._local_path, "wb") as f:
                f.write(payload_bytes)
        except Exception:
            pass

    def load(self) -> PCAModel | None:
        """Load PCAModel from MinIO, or fallback to local file."""
        # 1. Try MinIO
        if self._store is not None:
            try:
                if self._store.exists(self._key):
                    data_bytes = self._store.get(self._key)
                    data = json.loads(data_bytes.decode("utf-8"))
                    log.info("loaded pca detector model from minio", key=self._key)
                    return PCAModel.from_dict(data)
            except Exception as e:
                log.warning("failed to read pca model from minio, trying local fallback", error=str(e)[:120])

        # 2. Try local fallback
        if self._local_path.exists():
            try:
                with open(self._local_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return PCAModel.from_dict(data)
            except Exception as e:
                log.warning("failed to load pca detector model from local file", path=str(self._local_path),
                            error=str(e)[:120])

        return None
