"""Diagnose the plant at a moment: the deterministic pipeline, in one place.

extract and match are pure functions; this is the thin orchestration that reads
the historian window around an onset, distils it, and scores it against the
library - the single definition of "what does the plant look like it's doing
right now, and what known fault is that." The online loop calls it when an alarm
fires; a UI button would call it for a moment an operator points at; a test
calls it with a fake reader. There is still no LLM here - the result is a live
signature and a ranked list of candidates, evidence for a human or for the
narration step, never an asserted verdict.

The library is snapshotted at construction and refreshed on demand rather than
re-read per call: a diagnosis fires on a live alarm and must be cheap, while the
library only changes when a campaign runs. A long-lived loop calls reload() when
it learns the graph moved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from plantmind_core.schemas import DiagnosisMatch, FaultMode, FaultSignature
from plantmind_core.telemetry import get_logger

from diagnostics.signature import extract_signature
from diagnostics.matcher import match_signature

log = get_logger("diagnostics.diagnose")

# how far each side of the onset to read. Lead-in gives every tag its baseline;
# the reaction is what gets scored. Matches the historian reader's own defaults.
DEFAULT_BEFORE_S = 600
DEFAULT_AFTER_S = 120


@dataclass
class DiagnosisResult:
    """A live signature and the known faults it resembles, most likely first."""
    onset: datetime
    signature: FaultSignature
    matches: list[DiagnosisMatch] = field(default_factory=list)

    @property
    def top(self) -> DiagnosisMatch | None:
        return self.matches[0] if self.matches else None


class Diagnostician:
    def __init__(self, reader, library: list[FaultMode], tag_ids: list[str],
                 *, store=None):
        self._reader = reader
        self._library = library
        self._tag_ids = tag_ids
        self._store = store              # kept only so reload() can re-read

    @classmethod
    def from_settings(cls, tag_ids: list[str] | None = None) -> "Diagnostician | None":
        """Wire a reader and load the library, or None when the historian is
        unconfigured - the same disabled signal the sink and reader use, so a
        deployment without a historian degrades instead of crash-looping.

        With no tag_ids, the tag universe is discovered from what the historian
        has recorded, so diagnostics needs no compile-time knowledge of the
        plant's topology."""
        from plantmind_core.timeseries import HistorianReader
        from diagnostics.library import FaultLibraryStore

        reader = HistorianReader.from_settings()
        if reader is None:
            log.warning("historian unconfigured; diagnostician disabled")
            return None
        if tag_ids is None:
            tag_ids = reader.known_tags()
        store = FaultLibraryStore.from_settings()
        library = store.all()
        log.info("diagnostician ready", fault_modes=len(library),
                 tags=len(tag_ids))
        return cls(reader, library, tag_ids, store=store)

    def reload(self) -> None:
        """Re-read the library - call after a campaign has added fault modes."""
        if self._store is not None:
            self._library = self._store.all()
            log.info("fault library reloaded", fault_modes=len(self._library))

    def refresh_tags(self) -> None:
        """Re-discover the tag universe from the historian. New tags (a unit
        brought online) become part of the next diagnosis; an empty result is
        ignored so a transient blank read never narrows the window to nothing."""
        tags = self._reader.known_tags()
        if tags:
            self._tag_ids = tags

    @property
    def library_size(self) -> int:
        return len(self._library)

    def diagnose_at(
        self,
        onset: datetime,
        *,
        before_s: int = DEFAULT_BEFORE_S,
        after_s: int = DEFAULT_AFTER_S,
        severity: str = "warning",
        top_k: int = 5,
    ) -> DiagnosisResult | None:
        """Diagnose the episode bracketing `onset`. Returns None when the window
        is empty (nothing recorded - never a false 'all clear'), and a result
        with no matches when the plant moved but nothing in the library fits."""
        samples = self._reader.around(self._tag_ids, onset,
                                      before_s=before_s, after_s=after_s)
        if not samples:
            log.info("no telemetry around onset; cannot diagnose",
                     onset=onset.isoformat())
            return None

        signature = extract_signature(samples, onset, source="plant",
                                      severity=severity)
        matches = match_signature(signature, self._library, top_k=top_k)
        log.info("diagnosis complete", onset=onset.isoformat(),
                 deviations=len(signature.deviations),
                 candidates=len(matches),
                 top=matches[0].cause_id if matches else None)
        return DiagnosisResult(onset=onset, signature=signature, matches=matches)
