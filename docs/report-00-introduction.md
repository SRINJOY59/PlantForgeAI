# 0. Why the engineering is the contribution

A retrieval technique that works in a notebook and a system a plant can rely on
are separated by everything that is not the technique.

The novel parts of PlantForge are real: a knowledge graph assembled from the
documents a plant already owns, agents that investigate a failure the moment it
lands rather than when someone asks, and an evidence discipline that separates
facts harvested from the graph from prose written by a model. But every one of
those ideas is one bad engineering decision away from being unusable. A graph
whose indexes do not match its queries grows slower with every document it
learns. An agent that publishes an alert but loses it on restart teaches
operators to distrust the feed. A pipeline that pushes twenty-megabyte scans
through its message broker dies at exactly the load that proves the product
works. None of those are research failures. All of them are fatal.

That asymmetry shaped how this was built. The interesting question was rarely
"can the model do it" — it usually could — but "what happens on the hundredth
document, the fiftieth simultaneous user, the third restart, and the first
malformed file." Those questions have engineering answers, and the answers are
what turned a set of techniques into something that survives contact with a real
plant: seven specialised worker pools instead of one, a deliberately serialised
writer protecting a version guarantee, an idempotency gate that makes duplicate
uploads free, a coordination layer designed so that losing it costs throughput
and never facts, and a concurrency model derived from load measurements rather
than from convention.

The three sections that follow are that story, in the order the system
experiences it. **How a file becomes a fact** — the ingestion pipeline, its
worker topology and how it scales itself under backlog. **How seven strangers
agree** — the coordination layer that lets independent services cooperate without
calling each other. **And then fifty people ask at once** — the read path, where
every decision is judged by whether one user can degrade another's experience.

Each records not just what was built, but the measurement that forced it. Where a
ceiling remains, it is named rather than omitted — a system whose limits are
known is engineered; one whose limits are undiscovered is merely untested.
