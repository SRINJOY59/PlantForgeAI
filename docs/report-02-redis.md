# 2. Redis: one instance, three jobs

The pipeline is seven independent services that never call each other, share no
memory, and can each be restarted or scaled without warning. Everything they use
to agree runs through a single Redis 7 instance — and it is doing three
architecturally distinct jobs at once.

**As a message broker** it carries the Celery queues: six named work queues, the
periodic beat schedule, and the redelivery guarantees behind them. **As a
coordination store** it holds the state services must agree on — which files have
been seen, what is waiting to be written, which version the graph is on. **As an
event bus** it carries the append-only streams that let the graph tell the agents
what changed, and the agents tell every connected browser what they found.

Using one system for all three is a deliberate consolidation. A dedicated broker,
a cache and a streaming platform would be three deployments, three failure modes
and three operational skill sets, for a workload that comfortably fits in one
process. The cost is a single point of failure, which is accepted because of the
constraint the whole design turns on: **nothing held in Redis, if lost, destroys
plant knowledge.**

## Why Redis specifically

The choice follows from what the coordination problem actually needs.

**Single-threaded command execution gives atomicity for free.** Redis executes
one command at a time, to completion. That is what makes "claim this file
fingerprint if nobody else has" a single operation with no lock, no transaction
and no coordinator — two simultaneous uploads cannot both win, because their two
commands cannot interleave. The same property makes the graph version counter
safe: an atomic increment cannot produce a duplicate version no matter how many
services read it. Building either of those on a general-purpose database means
explicit transactions and a contention story; here it is the default behaviour.

**Its data structures match the problems rather than approximating them.** Six
distinct structures are used, each chosen for a specific access pattern:

| Structure | Used for | Property that matters |
|---|---|---|
| String with set-if-absent | file fingerprint ledger | atomic claim, exactly one winner |
| Counter with atomic increment | graph version | monotonic, no gaps, no locks |
| List | write buffer, quarantine | ordered hand-off, cheap push/pop at scale |
| Hash | approval records, answer cache | field-level read/write in one key |
| Sorted set | cache eviction order | score by timestamp, cheapest-first eviction |
| Stream | changes, alerts, work orders | ordered, replayable, many readers |
| Counter with expiry | per-user rate limits | self-cleaning, no sweep job |

**Streams are the reason a queue was not enough.** A Celery queue delivers each
message to exactly one consumer and forgets it — correct for tasks, wrong for
notifications. Three engineers with the app open must each receive the same
alert, and someone connecting an hour later must see the history. A stream is
ordered, retained, and readable from any position by any number of independent
consumers, each tracking its own place. The system uses the same primitive twice:
internally, so agents can follow graph changes and resume exactly where they
stopped after a restart; and externally, so every browser replays the alert
history on connect and then follows live.

**Sub-millisecond latency is what allows it on the read path.** The answer cache
is consulted before every question reaches a language model. If that lookup cost
tens of milliseconds it would not be worth having; at Redis latencies the check
is free relative to what it avoids.

## What the design gives back in exchange

**Durability is deliberately not relied upon.** Every entry is derived from
something durable, replayable from the graph, or explicitly temporary. Flush the
instance entirely and the system re-answers questions it had already answered,
re-checks files it had already seen, and rebuilds consumer positions — it re-does
work. It does not lose a fact, because facts live in the graph and every original
document lives in object storage. That is what licenses running coordination on
volatile infrastructure without a backup strategy.

**Memory growth is bounded by construction, not by monitoring.** Rate-limit
counters carry an expiry set on their first increment, so each key deletes itself
when its window closes — no sweep job, no unbounded growth. The answer cache
pairs its hash of entries with a sorted set scored by last-touch time, so
eviction is a range query on the oldest members rather than a scan. Interview
sessions expire after 24 hours. The streams are the one structure that grows
monotonically, which is why retiring a stale entry is an explicit deletion.

**One mutable structure sits deliberately beside an immutable one.** A drafted
work order is exactly what an agent produced at a given graph version, so it is
never edited — it stays in the stream untouched. The planner's approval is a
separate, later fact, stored in a hash keyed by that stream entry and joined on
read. Writing the decision into the event would mean mutating history in an
append-only structure; keeping them apart is what lets a draft approved last week
replay today as approved, rather than reappearing as pending and inviting a
second approval of the same work.

**A timing invariant, written where someone will find it.** Blocking stream reads
park for a bounded 15 seconds while the client socket timeout is 20. The ordering
is load-bearing: invert it and a perfectly healthy system reports connection
failures on a five-second cadence — a fault that presents exactly like a network
problem and would be investigated in entirely the wrong layer. The two values are
defined adjacently with the reasoning attached, because that note is the only
thing stopping someone from later "tidying" one of them.
