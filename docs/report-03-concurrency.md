# 3. Serving many users concurrently

Ingestion is permitted to take minutes. The read path is not: an engineer types a
question and waits, and the requirement is that their wait stays short while
fifty colleagues do the same. This section specifies the mechanisms that make
that hold, and the measurements that confirm each one.

The governing constraint is single-sentence: **no request may make another
request wait.** Everything below follows from it.

## Execution model

Each API service runs an asynchronous event loop — one thread accepting many
concurrent requests and switching between them whenever one pauses on external
I/O. Around that sit two additional layers of parallelism:

```
   ┌── API service ─────────────────────────────────────────────┐
   │                                                            │
   │  process 1                      process 2                  │
   │  ┌──────────────────┐           ┌──────────────────┐       │
   │  │ EVENT LOOP       │           │ EVENT LOOP       │       │  2 processes
   │  │ 1 thread, N      │           │ 1 thread, N      │       │  = 2 interpreter
   │  │ concurrent reqs  │           │ concurrent reqs  │       │    locks
   │  └────────┬─────────┘           └────────┬─────────┘       │
   │           │ offload blocking work        │                 │
   │           ▼                              ▼                 │
   │  ┌──────────────────┐           ┌──────────────────┐       │
   │  │ THREAD POOL      │           │ THREAD POOL      │       │  ≈ min(32,
   │  │ short waits only │           │                  │       │    cpu+4)
   │  └────────┬─────────┘           └────────┬─────────┘       │
   └───────────┼──────────────────────────────┼─────────────────┘
               ▼                              ▼
      ┌────────────────────┐        ┌────────────────────┐
      │ Neo4j driver pool  │        │ Redis, object store│
      │ 50 connections     │        │                    │
      │ 30 s acquisition   │        │                    │
      │ timeout            │        │                    │
      └────────────────────┘        └────────────────────┘
```

Two worker processes per service, because a single Python process holds one
interpreter lock and the response path does real CPU work — JSON serialisation,
a cosine scan over cached embeddings. Two processes give two locks. Within each,
the event loop handles concurrency and the thread pool handles blocking.

## Mechanism 1 — offloading blocking calls, selectively

The graph driver is synchronous: asked for data it holds its thread until the
answer returns. Called directly from the event loop it would freeze every other
request in that process, including users mid-way through a streamed answer that
never touches the graph.

Every blocking call on a request path is therefore executed on the thread pool:
graph reads, the cosine scan over the answer cache, object-storage fetches, the
graph-version read. The loop is returned to other requests immediately.

**The offload is deliberately not universal, and this is the specification's most
important detail.** The thread pool holds roughly `min(32, cpu + 4)` threads.
Offloading a call that returns in milliseconds borrows a thread and gives it
straight back. Offloading a call that *waits* — the live alert stream parks for
up to 15 seconds per connection — occupies one thread for the entire wait, and
the 33rd concurrent viewer then queues behind two colleagues' idle sockets.

So long-lived waits use a genuinely asynchronous client instead, one that
registers the socket with the operating system's readiness mechanism and holds no
thread at all, resuming only when data arrives. The rule the system implements:

> **Offload waits that finish promptly. Use an async client for waits that
> linger.** Applying either universally reintroduces the other failure.

Measured on the alert stream at 100 concurrent viewers: thread-pool offload
served 88 and failed 12, median 30.5 s. The async client served 100 of 100, zero
failures, median 15.5 s.

## Mechanism 2 — bounded waits and matched timeouts

Blocking stream reads park for a bounded 15 seconds rather than indefinitely, so
a connection always returns to the loop on a known schedule and can be cancelled
cleanly. The client socket timeout is set above it at 20 seconds. Inverting that
ordering makes a healthy system report connection failures on a timer.

Graph connections come from a pool of 50 with a 30-second acquisition timeout, so
a burst queues briefly rather than opening unbounded connections, and a
pathological backlog surfaces as a timeout rather than exhausting the database.

## Mechanism 3 — indexing so requests hold resources briefly

A request that holds a pooled connection longer than necessary reduces the
concurrency the pool can support, so query cost is a concurrency concern, not
only a latency one.

Every node carries a generic entity label plus a specific type label, with a
uniqueness guarantee on the machine id. The read path, however, anchors almost
every query on the *human* label — the tag an engineer says aloud, like "P-101A".
That property carried no index. A second gap compounded it: the query planner
selects an index using only the label written into the query pattern, and cannot
know at planning time that every pump is also a generic entity, so lookups naming
the specific type could not use the index built on the generic one.

The worst case multiplied. Fetching an asset's failure history performs a
secondary document lookup *for each failure row returned* — unindexed, one
request became a full scan of the document library, repeated per failure.
Profiling the same query on the same data:

| | plan | database work |
|---|---|---|
| unindexed | label scan ×2 | **728 units** |
| range indexes added | index seek ×2 | **129 units** |

The ratio is not the point. The scan returned 252 rows, which is exactly 6
failures × 42 documents; at 20,000 documents that term reaches ~120,000 while the
indexed seek stays at 18. This is a change in growth, not in speed — unindexed,
every document ingested would have made every equipment lookup permanently
slower.

## Mechanism 4 — removing work entirely, and capping what remains

Questions are checked against a semantic answer cache before reaching a language
model, so a repeated question costs a vector comparison instead of a generation.
The cache is bounded by last-touch ordering, so it evicts oldest-first rather
than growing without limit.

Expensive endpoints carry per-user rate limits implemented as a counter whose
expiry is set on first use — self-cleaning, no sweep job. This is admission
control rather than optimisation: it caps what any single user can do to everyone
else's latency.

## Validated behaviour

At 50 concurrent users, **200 of 200 requests succeeded on every endpoint** — no
timeouts, no dropped streams. Throughput settled at 85–105 requests/second on
lightweight endpoints and 55–77 on presigned document URLs. The failure mode
under saturation is *queueing*, not *erroring*, which is the property that
matters for a control-room tool: slow is survivable, unavailable is not.

The same run identified the remaining ceiling, which is documented rather than
omitted: the graph visualisation endpoint saturates at ~8 requests/second, taking
840 ms per call, because it serialises up to 400 nodes with full property maps on
every request without caching. The graph version counter makes this directly
fixable — that view changes only when the graph does.
