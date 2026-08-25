"""Edge logic that isn't HTTP plumbing: accept an upload into the pipeline,
fetch an original document for a citation click, gather metrics. The
FastAPI layer (main.py) owns request/response and proxying to retrieval."""

import json
import time
import uuid
from datetime import date
from pathlib import Path

from plantmind_core import corrections, keys
from plantmind_core.bus import RedisBus
from plantmind_core.notify import SlackNotifier
from plantmind_core.pipeline import stage_and_enqueue
from plantmind_core.storage import ObjectStore
from plantmind_core.telemetry import get_logger

log = get_logger("gateway.service")

# The monitored-tag list the field asset picker falls back to when the sim has
# not populated sim:limits in redis. Same source and precedence the TEP watcher
# uses: the mounted container path first, then the repo path for local dev.
_ENVELOPE_PATHS = [
    Path("/srv/config/tep_envelopes.json"),
    Path(__file__).resolve().parents[2] / "config" / "tep_envelopes.json",
]

# How far back the field asset-context scan reads the alarm / diagnosis streams.
# One fault episode is a handful of stream entries; a few hundred is generous
# without turning a phone tap into a full-stream replay.
_FIELD_SCAN = 400
# An alarm older than this (seconds) is history, not the live state a worker
# standing at the asset needs. The streams carry no explicit clear event, so
# recency is how we decide an alarm is still worth surfacing.
_ALARM_ACTIVE_WINDOW_S = 1800


class GatewayService:
    def __init__(self, store: ObjectStore, bus: RedisBus, sender):
        self._store = store
        self._bus = bus
        self._send = sender

    @classmethod
    def from_settings(cls) -> "GatewayService":
        from plantmind_core.celeryapp import WorkerApp
        return cls(ObjectStore.from_settings(), RedisBus.from_settings(),
                   WorkerApp("gateway").send)

    def ingest(self, filename: str, data: bytes, source="upload") -> dict:
        """Stage the bytes and drop a classify note - the synchronous half of
        an async pipeline: we acknowledge 'accepted', not 'processed'."""
        stage_and_enqueue(self._store, self._send, filename, data, source)
        log.info("accepted upload", filename=filename, size=len(data))
        return {"status": "accepted", "filename": filename}

    def correct(self, question: str, answer: str, correction: str,
                author: str, cited_docs: list) -> dict:
        """An engineer says we got something wrong.

        It takes the ordinary ingest road, because that is all a correction
        is: a short document, written by a person instead of a vendor, that
        the plant did not have before. Same staging, same classify note, same
        extraction and resolution behind it - the lane it lands in is what
        marks its provenance HUMAN.
        """
        record = corrections.Correction(
            question=question, answer=answer, correction=correction,
            author=author, date=date.today().isoformat(),
            cited_docs=cited_docs)
        name = corrections.filename(uuid.uuid4().hex[:12])
        stage_and_enqueue(self._store, self._send, name,
                          corrections.render(record), source="correction")
        log.info("accepted correction", author=author, filename=name,
                 corrects=cited_docs)
        return {"status": "accepted", "filename": name}

    def document(self, doc_id: str):
        """(filename, bytes) for a citation's source, or None."""
        return self._store.find_document(doc_id)

    def document_url(self, doc_id: str) -> str | None:
        """A presigned MinIO URL the browser can fetch directly.

        No hostname rewriting here. This used to swap minio:9000 for
        localhost:9000 *after* signing, which invalidated the signature: SigV4
        covers the Host header, so MinIO recomputed against the host the
        browser actually sent, disagreed, and returned SignatureDoesNotMatch.
        The URL is now signed for MINIO_PUBLIC_ENDPOINT up front.
        """
        return self._store.presigned_url(doc_id)

    def document_name(self, doc_id: str) -> str | None:
        """The readable filename behind a doc_id, taken off the object key."""
        return self._store.document_filename(doc_id)

    def metrics(self) -> dict:
        return {"graph_version": self._bus.graph_version(),
                "queues": self._bus.depths()}

    def read_alerts(self, after: str, block_ms: int):
        return self._bus.read_alerts(after, block_ms=block_ms)

    async def read_alerts_async(self, after: str, block_ms: int):
        return await self._bus.read_alerts_async(after, block_ms=block_ms)

    async def read_draft_work_orders_async(self, after: str, block_ms: int):
        return await self._bus.read_draft_work_orders_async(after, block_ms=block_ms)

    def work_order_decisions(self) -> dict:
        return self._bus.work_order_decisions()

    def decide_work_order(self, draft_id: str, decision: str, who: str):
        self._bus.set_work_order_decision(draft_id, decision, who)
        log.info("work order decision", draft=draft_id, decision=decision,
                 by=who)

    def schedule_work_order(self, draft_id: str, schedule: dict,
                            draft: dict) -> dict:
        """An engineer proposes a time slot and crew for a work order.

        Saves the schedule to Redis and sends the Slack approval request.
        The draft does not move until Slack answers.
        """
        schedule["draft_id"] = draft_id
        schedule["status"] = "pending_approval"
        self._bus.set_work_order_schedule(draft_id, schedule)

        try:
            notifier = SlackNotifier.from_settings()
            notifier.post_work_order_approval(draft, schedule)
        except Exception as e:
            log.warning("slack approval request failed", error=str(e)[:200])

        log.info("work order scheduled", draft=draft_id,
                 requested_by=schedule.get("requested_by"))
        return schedule

    async def handle_schedule_decision(self, draft_id: str, decision: str,
                                       who: str, channel: str) -> dict | None:
        """Slack answered. Record it, and on approval dispatch to the crew.

        Convenience wrapper that does both steps synchronously — used by any
        caller that CAN wait (e.g. internal API, tests). The Slack routes use
        record_schedule_decision + dispatch_approved_order separately so they
        can respond within Slack's 3-second window.

        Returns the updated record, or None when this draft was never
        scheduled or has already been decided.
        """
        record = self.record_schedule_decision(draft_id, decision, who, channel)
        if record is None:
            return None
        if decision != "approved":
            return record

        try:
            recipients = await self.dispatch_approved_order(draft_id, record)
            record["dispatched_to"] = recipients
        except Exception as e:
            log.warning("dispatch failed after approval", draft=draft_id,
                        error=str(e)[:200])
            record["dispatch_error"] = str(e)[:200]
        return record

    def record_schedule_decision(self, draft_id: str, decision: str,
                                 who: str, channel: str) -> dict | None:
        """Record a Slack approval/rejection — synchronous, milliseconds.

        This is the fast half of the old handle_schedule_decision. It does a
        single Redis write and returns the updated record. No LLM calls, no
        HTTP to the agents service, no translation — those belong in
        dispatch_approved_order, which the caller can run whenever it likes.

        Returns the updated record, or None when this draft was never
        scheduled or has already been decided (idempotent double-tap).
        """
        record = self._bus.claim_schedule_decision(
            draft_id, decision, who, channel)
        if record is None:
            return None

        log.info("schedule decision", draft=draft_id, decision=decision,
                 by=who, via=channel)
        return record

    async def dispatch_approved_order(self, draft_id: str,
                                      record: dict) -> list:
        """Send an approved work order to the crew — async, 30-90 seconds.

        This is the slow half: read the draft back, call the agents service
        for LLM-generated briefs + translations, then assign each crew member
        their copy in Redis. Called either inline (handle_schedule_decision)
        or as a background task (Slack routes).

        Returns the list of recipients. Raises on failure so the caller can
        decide how to surface it (inline error vs. Slack follow-up message).
        """
        draft = self.draft_by_id(draft_id)
        if draft is None:
            log.warning("approved a draft we cannot read back; nothing "
                        "dispatched", draft=draft_id)
            record["dispatch_error"] = "draft could not be read back"
            self._bus.set_work_order_schedule(draft_id, record)
            raise ValueError("draft could not be read back")

        from gateway.dispatch import dispatch_to_crew
        recipients = await dispatch_to_crew(self._bus, draft, record,
                                            self._agents_http())
        record["dispatched_at"] = time.time()
        record["dispatched_to"] = recipients
        record.pop("dispatch_error", None)
        self._bus.set_work_order_schedule(draft_id, record)
        return recipients

    @staticmethod
    def _agents_http():
        """The agents client, fetched at call time rather than held.

        deps.wire() runs in the lifespan hook, after this service is built, so
        an attribute captured in __init__ would be None forever."""
        from gateway.deps import get_agents_http
        return get_agents_http()

    async def redispatch(self, draft_id: str) -> list:
        """Send an already-approved order to the crew again.

        The retry path for a failed dispatch, and for a crew member added
        after the fact. Delegates to dispatch_approved_order."""
        record = self._bus.work_order_schedule(draft_id)
        if record is None or record.get("status") != "approved":
            raise ValueError("work order is not approved")
        return await self.dispatch_approved_order(draft_id, record)

    def draft_by_id(self, draft_id: str) -> dict | None:
        """Read one draft back off the stream by its entry id.

        XRANGE with the same id as start and end, which is how you address a
        single stream entry - the drafts stream is capped but never rewritten,
        so an id that came out of it addresses the same draft forever.

        The field is 'payload' because that is what publish_draft_work_order
        writes; the bus client is built with decode_responses=True, so what
        comes back is already str.
        """
        if not draft_id:
            return None
        try:
            entries = self._bus._r.xrange(keys.DRAFT_WORK_ORDERS_STREAM,
                                          draft_id, draft_id)
        except Exception as e:
            log.warning("could not read draft", draft=draft_id, error=str(e))
            return None
        if not entries:
            return None
        _entry_id, fields = entries[0]
        raw = (fields or {}).get("payload")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            log.warning("draft payload is not json", draft=draft_id)
            return None

    def work_order_schedules(self) -> dict:
        return self._bus.work_order_schedules()

    def work_order_schedule(self, draft_id: str) -> dict | None:
        return self._bus.work_order_schedule(draft_id)

    def crew(self, engineer_key: str) -> list:
        return self._bus.crew(engineer_key)

    def add_crew_member(self, engineer_key: str, worker: dict) -> None:
        self._bus.set_crew_member(engineer_key, worker)

    def remove_crew_member(self, engineer_key: str, worker_id: str) -> int:
        return self._bus.remove_crew_member(engineer_key, worker_id)

    # --- a worker's own job list ------------------------------------------

    def assignments_for(self, worker_key: str) -> list:
        return self._bus.assignments_for(worker_key)

    def update_assignment(self, worker_key: str, assignment_id: str,
                          status: str, note: str = "") -> dict | None:
        """Move one job forward and stamp when it happened.

        Timestamps are only ever written once. A worker tapping "done" twice
        must not rewrite when the work finished, and a job that goes done ->
        in_progress (a mis-tap, or a second device catching up) must not erase
        the completion time that a planner may already have acted on.
        """
        patch = {"status": status}
        if note:
            patch["worker_note"] = note
        existing = self._bus.assignment(worker_key, assignment_id) or {}
        stamp = {"acknowledged": "acknowledged_at", "in_progress": "started_at",
                 "done": "completed_at"}.get(status)
        if stamp and not existing.get(stamp):
            patch[stamp] = time.time()
        updated = self._bus.update_assignment(worker_key, assignment_id, patch)
        if updated is not None:
            log.info("assignment update", assignment=assignment_id,
                     worker=worker_key, status=status)
        return updated

    def rate_check(self, bucket: str, limit: int, window_s: int):
        return self._bus.rate_check(bucket, limit, window_s)

    # ---------------------------------------------------------- field copilot
    # The asset universe a field worker can scope to, and the live analytic
    # state of one asset. Live *numeric* trend is not here on purpose: the UI
    # already tails plant:telemetry over the WebSocket, so the value/trend is a
    # frontend concern. What the backend adds is the state a phone can't derive
    # on its own - which alarms are standing, and what the diagnostics runtime
    # last concluded about this asset.

    def list_assets(self) -> list[dict]:
        """Monitorable assets, derived from the envelope set.

        The envelopes (keyed by tag_id, e.g. 'REACTOR.P') are the authoritative
        list of tags the plant watches, the same source the TEP watcher alarms
        on. Prefers the live Redis copy (sim:limits); when the simulator has not
        published that yet - which is the common case - it falls back to the
        envelope file on disk, exactly as the watcher does, so the picker is
        populated instead of empty. Grouped by unit (the tag prefix) at the UI.
        Never raises: an empty picker is a better failure than a 500.
        """
        envelopes: dict = {}
        try:
            raw = self._bus._r.hgetall("sim:limits")
            for tag_id, env_str in (raw or {}).items():
                try:
                    envelopes[tag_id] = json.loads(env_str)
                except (ValueError, TypeError):
                    envelopes[tag_id] = {}
        except Exception as e:
            log.warning("field: could not read sim:limits", error=str(e))

        if not envelopes:
            envelopes = self._load_envelope_file()

        assets = []
        for tag_id, env in envelopes.items():
            env = env if isinstance(env, dict) else {}
            unit = tag_id.split(".")[0] if "." in tag_id else tag_id
            assets.append({
                "tag": tag_id,
                "unit": unit,
                "setpoint": env.get("setpoint"),
                "units": env.get("units") or env.get("unit_of_measure"),
            })
        assets.sort(key=lambda a: (a["unit"], a["tag"]))
        return assets

    @staticmethod
    def _load_envelope_file() -> dict:
        """{tag_id -> envelope} from the TEP envelope file, or {} if unreadable.

        Keys starting with '_' are metadata (comments, schema notes), not tags,
        so they are dropped - the same filter the watcher applies."""
        for path in _ENVELOPE_PATHS:
            try:
                if path.exists():
                    with open(path) as f:
                        return {k: v for k, v in json.load(f).items()
                                if not k.startswith("_")}
            except Exception as e:
                log.warning("field: envelope file unreadable", path=str(path),
                            error=str(e))
        log.warning("field: no envelope file found; asset picker will be empty")
        return {}

    def asset_context(self, tag: str) -> dict:
        """Live analytic state for one asset: standing alarms + last diagnosis.

        Assembled from the same streams the console reads, filtered to this tag.
        Everything is best-effort: a stream that can't be read costs that one
        section, never the whole context, because a field worker asking a
        question should still get an answer if the diagnosis lookup hiccups.
        """
        import time
        now = time.time()

        active_alarms = []
        try:
            for _id, payload_str in self._bus.read_alerts("0", block_ms=0)[-_FIELD_SCAN:]:
                p = self._parse(payload_str)
                if not p or p.get("kind") != "process_limit":
                    continue
                if p.get("tag_id") != tag:
                    continue
                ts = p.get("timestamp")
                try:
                    fresh = ts is None or (now - float(ts)) <= _ALARM_ACTIVE_WINDOW_S
                except (TypeError, ValueError):
                    fresh = True
                if not fresh:
                    continue
                active_alarms.append({
                    "level": p.get("level"),
                    "value": p.get("value"),
                    "limit": p.get("limit"),
                    "setpoint": p.get("setpoint"),
                    "severity": p.get("severity"),
                    "timestamp": ts,
                    "message": p.get("message"),
                })
        except Exception as e:
            log.warning("field: alarm scan failed", tag=tag, error=str(e))

        # keep only the newest alarm per level (H can escalate to HH; a worker
        # wants the current picture, not every crossing that got us here)
        by_level = {}
        for a in active_alarms:
            by_level[a["level"]] = a
        active_alarms = list(by_level.values())

        latest_diagnosis = None
        try:
            for _id, diag_str in self._bus.read_diagnoses("0", block_ms=0)[-_FIELD_SCAN:]:
                d = self._parse(diag_str)
                if not d or d.get("trigger_tag") != tag:
                    continue
                latest_diagnosis = d          # streams are ordered; last wins
        except Exception as e:
            log.warning("field: diagnosis scan failed", tag=tag, error=str(e))

        candidates = []
        if latest_diagnosis:
            for m in (latest_diagnosis.get("matches") or [])[:3]:
                candidates.append({
                    "cause_id": m.get("cause_id"),
                    "label": m.get("label") or m.get("cause_id"),
                    "score": m.get("score"),
                })

        return {
            "tag": tag,
            "unit": tag.split(".")[0] if "." in tag else tag,
            "active_alarms": active_alarms,
            "diagnosis": None if not latest_diagnosis else {
                "id": latest_diagnosis.get("id"),
                "onset": latest_diagnosis.get("onset"),
                "trigger_level": latest_diagnosis.get("trigger_level"),
                "candidates": candidates,
            },
        }

    @staticmethod
    def _parse(payload_str):
        try:
            return json.loads(payload_str) if payload_str else None
        except (ValueError, TypeError):
            return None
