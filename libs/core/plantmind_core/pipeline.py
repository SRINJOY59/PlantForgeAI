"""The one entry point into the pipeline: stage bytes and enqueue a classify
note. Gateway uploads, the submit CLI, and connectors all funnel through
here so 'how a document enters' is defined once."""

import uuid

from plantmind_core.queues import Flow


def stage_and_enqueue(store, sender, filename: str, data: bytes,
                      source="upload") -> str:
    staging_key = f"staging/{uuid.uuid4().hex}/{filename}"
    store.put(staging_key, data)
    sender(Flow.ingest, {"staging_key": staging_key, "filename": filename,
                         "source": source})
    return staging_key
