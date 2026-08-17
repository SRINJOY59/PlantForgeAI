"""Redis key names shared across services. Treat like the schema contracts:
renaming one is a breaking change for every service."""

DOC_HASH_PREFIX = "doc:"                 # doc:<sha256> set = already ingested
WRITE_BUFFER = "graphd:write_buffer"     # resolver RPUSHes resolved subgraphs
WRITE_DLQ = "graphd:write_dlq"           # unparseable buffer items land here
FLUSH_LOCK = "graphd:flush_lock"
GRAPH_VERSION = "graph:version"          # INCR on every committed batch
DELTA_STREAM = "graph:deltas"            # XADD GraphDelta after each commit
ALERT_STREAM = "alerts:critical"         # agents & watchers publish, UI/gateway tail
DRAFT_WORK_ORDERS_STREAM = "work_orders:drafts"
# <stream entry id> -> {decision, by, at}. Beside the stream, not in it: the
# draft is immutable (it is what the agent produced at one graph version), the
# planner's decision is a later fact about it.
WORK_ORDER_DECISIONS = "work_orders:decisions"
CURSOR_PREFIX = "cursor:"                # cursor:<name> = a consumer's position
ALERTED_SET = "agents:alerted"           # fingerprints of alerts already raised
ANSWER_CACHE = "answercache:entries"     # id -> cached (question, answer, deps)
ANSWER_CACHE_LRU = "answercache:lru"     # id -> ts, for eviction
# standards:revision:<standard> = the revision the watcher last saw published.
# Watch state, not plant knowledge: it came off the open web, so it stays out
# of the graph, where every fact is supposed to trace to a document we hold.
STANDARD_REVISION_PREFIX = "standards:revision:"
RATE_PREFIX = "ratelimit:"               # ratelimit:<bucket>:<who> fixed window
EXTRACTION_LOCK_PREFIX = "lock:extract:"  # lock:extract:<lane>:<content_hash>
EXTRACTION_CACHE_PREFIX = "cache:extract:"  # cache:extract:<lane>:<content_hash>
