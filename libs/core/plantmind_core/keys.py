"""Redis key names shared across services. Treat like the schema contracts:
renaming one is a breaking change for every service."""

DOC_HASH_PREFIX = "doc:"                 # doc:<sha256> set = already ingested
WRITE_BUFFER = "graphd:write_buffer"     # resolver RPUSHes resolved subgraphs
WRITE_DLQ = "graphd:write_dlq"           # unparseable buffer items land here
FLUSH_LOCK = "graphd:flush_lock"
GRAPH_VERSION = "graph:version"          # INCR on every committed batch
DELTA_STREAM = "graph:deltas"            # XADD GraphDelta after each commit
ALERT_STREAM = "alerts:critical"         # agents & watchers publish, UI/gateway tail
DIAGNOSES_STREAM = "diagnoses:live"      # diagnostics publishes, Diagnose view tails
DIAGNOSES_INDEX = "diagnoses:index"      # prefix diagnoses:index:<id> -> Diagnosis json (TTL'd)
RCA_REQUESTS_STREAM = "rca:requests"     # UI asks for LLM RCA on one diagnosis; agents run it
DRAFT_WORK_ORDERS_STREAM = "work_orders:drafts"
# <stream entry id> -> {decision, by, at}. Beside the stream, not in it: the
# draft is immutable (it is what the agent produced at one graph version), the
# planner's decision is a later fact about it.
WORK_ORDER_DECISIONS = "work_orders:decisions"
# <stream entry id> -> the schedule an engineer proposed for that draft: the
# slot, the crew, and where the Slack authorisation of it has got to. Separate
# from the decision above because they answer different questions - "is this
# work justified" versus "is this crew going in at this hour" - and because a
# schedule can be re-proposed after a rejection while the draft never changes.
WORK_ORDER_SCHEDULES = "work_orders:schedules"
# <stream entry id> -> [assignment id, ...]. The engineer's side of a dispatch:
# who this order actually went to, so the console can say "3 workers notified"
# without walking every crew member's inbox.
WORK_ORDER_ASSIGNMENTS = "work_orders:assignments"
# crew:<engineer key> -> {worker id: worker json}. Who reports to this
# engineer. Held here rather than in the profiles table because the gateway is
# deliberately stateless towards Supabase - it verifies tokens, it does not
# query users - and a roster is coordination state like every other key here.
CREW_PREFIX = "crew:"
# assignments:<worker key> -> {assignment id: assignment json}. One worker's
# job list, in their own language. The worker key is their account email
# lowercased: it is the only identifier that survives both the roster (typed by
# an engineer) and the JWT (issued by Supabase).
ASSIGNMENTS_PREFIX = "assignments:"
# cache:brief:<draft id>:<lang> -> the translated worker brief. The draft is
# immutable, so a re-dispatch or a second worker on the same language must not
# spend a second LLM call to say the same thing.
DISPATCH_BRIEF_PREFIX = "cache:brief:"
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
