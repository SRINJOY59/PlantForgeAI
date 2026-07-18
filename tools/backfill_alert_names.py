"""Give the alerts already on the stream readable, openable citations.

Alerts raised before citations carried a filename show a content hash and can't
be opened. Rather than re-run compliance sweeps or re-investigate failures - the
expensive path - this reads every alert back off the stream, resolves each
citation's filename from the graph, and rewrites the stream in place. Cheap, and
it covers every kind at once: compliance, failure patterns, standards.

From here on the consumer names citations at emit time, so this is a one-shot
migration for the backlog, not something that needs to run again.

    python -m tools.backfill_alert_names
"""

from plantmind_core import keys
from plantmind_core.bus import RedisBus
from plantmind_core.schemas import Alert

from agents.reader import AgentReader


def main():
    bus = RedisBus.from_settings()
    reader = AgentReader.from_settings()

    entries = bus._r.xrange(keys.ALERT_STREAM)
    if not entries:
        print("no alerts on the stream")
        return

    alerts, named = [], 0
    for _, fields in entries:
        alert = Alert.model_validate_json(fields["payload"])
        before = [c.filename for c in alert.citations]
        reader.name_citations(alert.citations)
        if [c.filename for c in alert.citations] != before:
            named += 1
        alerts.append(alert)

    # rewrite the stream in order: the entry ids change, but the UI replays from
    # the start, so a named alert simply replaces its hash-only self
    bus._r.delete(keys.ALERT_STREAM)
    for alert in alerts:
        bus.publish_alert(alert.model_dump_json())

    print(f"rewrote {len(alerts)} alerts; {named} gained a citation name")


if __name__ == "__main__":
    main()
