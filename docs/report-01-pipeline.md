# 1. From a file to a fact

Someone drags a 20 MB scanned inspection report into the browser. What follows is
how that file becomes something the plant can be asked about — six Celery worker
pools, one deliberately serialised writer, and a set of decisions each forced by
the problem the previous one created.

```
   ┌────────┐   bytes    ┌──────────────────────────────────────────────┐
   │ upload │───────────►│ MinIO   staging area      temporary          │
   └───┬────┘            │              ↓ promoted on classification    │
       │  broker message │         permanent store, keyed by content    │
       │  = a storage    └───────────────┬──────────────────────────────┘
       │    address only                 │ every worker fetches
       ▼                                 │ bytes by address
  ╔═══════════════════════╗ ◄────────────┤
  ║ ingestion             ║  content fingerprint claimed atomically;    │
  ║ q_classify      -c 4  ║  a repeat upload dies here, before          │
  ║ identify + promote    ║  any model is billed                        │
  ╚═══════════╤═══════════╝                                             │
              │ routed by document kind                                 │
  ┌───────────┼─────────────────┬──────────────────┐                    │
  ▼           ▼                 ▼                  ▼                    │
┌──────────┐┌──────────────┐┌────────────────┐┌──────────────┐          │
│extraction││ extraction   ││  extraction    ││ emails,      │          │
│   -wo    ││   -pnid      ││    -text       ││ manuals,     │          │
│q_parse_wo││q_extract_pnid││ q_extract_text ││ corrections  │          │
│   -c 8   ││    -c 4      ││    -c 32       ││  → text lane │          │
│determin- ││ vision model ││  LLM, hot lane ││ images       │          │
│istic     ││ + images     ││                ││  → pnid lane │          │
└─────┬────┘└──────┬───────┘└───────┬────────┘└──────┬───────┘          │
      └────────────┴────────────────┴────────────────┘                  │
                   │  candidate nodes + edges + provenance per claim    │
                   ▼                                                    │
  ╔═══════════════════════╗                                             │
  ║ resolution            ║  surface form ⇒ stable entity id            │
  ║ q_resolve       -c 4  ║  "P-101A" / "Pump 101A" / "P101-A"          │
  ╚═══════════╤═══════════╝                                             │
              │ pushed onto a list — work leaves Celery here            │
              ▼                                                         │
   ══════ write buffer (Redis list) ══════                              │
              │ drained on the beat every 2 s, ≤500 subgraphs           │
              ▼                                                         │
  ╔═══════════════════════╗ ◄── CONCURRENCY 1, PERMANENTLY              │
  ║ graphd    -c 1 -B     ║     flush on a 2 s beat                     │
  ║ q_write               ║     graph denoising hourly, same queue      │
  ╚═══════════╤═══════════╝                                             │
              ▼                                                         │
    ┌──────────────────┐  publishes {version, nodes touched, edge       │
    │ Neo4j            │   types, source docs} ──► agents investigate   │
    └────────┬─────────┘                                                │
             └── a citation reopens the stored original, years later ───┘

   also on the beat: connectors   q_connectors -c 2 -B
                     external source sync, every 300 s
```

## The broker settings that make six pools survivable

All six pools share one configuration, and five of its choices are load-bearing
rather than default:

**Acknowledge after the work finishes, not when it is picked up** — and treat a
lost worker as a rejection. A worker killed mid-extraction returns its document
to the queue rather than losing it. This buys at-least-once delivery, which is
only safe because every handler is idempotent by construction: the content-hash
gate stops repeats at the door, graph writes merge rather than append, and edges
carry a provenance hash. A re-run converges instead of duplicating.

**Take one message at a time.** By default a Celery worker greedily buffers
messages. With a 30-second vision extraction sharing a pool, that means one
worker hoarding quick parses it will not reach for half a minute while another
sits idle. Prefetching a single message costs a negligible round-trip and keeps
the queue genuinely shared.

**Warn at nine minutes, kill at ten.** A hung model or database call raises a
catchable signal first, then is terminated, so the task re-queues rather than
occupying a slot forever. The container shutdown grace period is set to match
that ten-minute ceiling: a worker force-killed mid-task leaves its message
unacknowledged, and the broker will not redeliver until a visibility timeout an
hour later. Mismatching those two punches an hour-long hole in the pipeline after
every deploy.

**Discard task results.** This is a fire-and-forget pipeline — outcomes arrive as
graph commits and event-stream entries, so retaining results would consume memory
to record something nobody reads.

**Accept JSON only.** Pickle over a message broker is remote code execution
waiting for a misconfigured port.

Every task also inherits behaviour that intercepts *final* failure — after
retries are exhausted — and publishes a system alert naming the task and its id,
so a document that dies in the pipeline surfaces instead of vanishing silently.

## Why the shape is what it is

**The broker carries an address, never the payload.** The bytes go to object
storage under a temporary staging key, and the message holds only that key.
Queues are memory-resident and sized for millions of small messages; 20 MB
payloads turn the broker into a file server and exhaust it at exactly the load
worth surviving. An address keeps every message a few hundred bytes and lets
several workers read one object without copies existing.

**Classification is where a file earns identity.** The first pool fetches the
bytes, hashes the contents, and claims that fingerprint with an atomic
set-if-absent. Two tabs submitting the same file in the same second yield exactly
one winner; the loser stops before any billed call. The object is then promoted
from staging to a permanent home keyed by its own content hash. Nothing is ever
deleted — which is what lets a citation reopen the exact page years later, and is
the difference between an assistant and a plausible guesser.

**Then the lanes diverge, because the economics differ by orders of magnitude.**
The table lane runs 8-wide on deterministic parsing. The drawing lane runs 4-wide
because each item is a vision call costing seconds and real money — standalone
images route here too, sharing the vision-shaped budget rather than the text one.
The text lane runs 32-wide as the hot path, and absorbs manuals, emails and
engineer corrections, since a correction is just a short document whose
provenance records a human rather than a vendor. Routing lives in one declared
topology; no service contains routing logic of its own.

**And here the pipeline stops being parallel on purpose.** Resolution pushes
finished subgraphs onto a list, and the writer — pinned to a single worker, never
to be raised — drains up to 500 of them every two seconds on its own beat. Each
drain is one batch, one transaction, one atomic increment of the graph version
that is stamped on every downstream answer, assessment and work order. Two
writers would interleave batches and make that stamp a fiction; throughput here
is bought by enlarging the batch, never by adding workers. A failed batch is
bisected until the offending subgraph is isolated and parked for inspection, so
one malformed drawing cannot block everything queued behind it. Hourly graph
denoising runs on the same single-worker queue, which guarantees it can never
race the writer.

**Under load the pipeline breathes.** A supervisor polls queue depths every five
seconds and computes, per stage, the backlog divided by how much one worker is
expected to absorb, clamped between a floor and a ceiling. Backlog is the signal
rather than CPU, because these stages wait on model APIs — processor usage reads
as idle while thousands of documents queue. That absorption figure is where each
lane's economics are declared: the drawing lane scales out at 8 queued items per
worker because each is expensive, while the text lane tolerates 64 before adding
one. Scaling up jumps straight to the computed target, since a backlog is a
person waiting; scaling down requires several consecutive quiet polls and then
removes a single worker, because flapping around a threshold costs more
throughput than an idle container costs money. The writer carries no scaling
policy at all — elastic everywhere it can be, rigid exactly where correctness
forbids it.

**The last act is a broadcast.** The commit appends to the change stream, and
agents waiting on that stream wake to investigate. The file that arrived as bytes
is now facts, and those facts have just started a conversation.
