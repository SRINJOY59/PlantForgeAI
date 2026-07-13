"""Redis key names shared across services. Treat like the schema contracts:
renaming one is a breaking change for every service."""

DOC_HASH_PREFIX = "doc:"                 # doc:<sha256> set = already ingested
WRITE_BUFFER = "graphd:write_buffer"     # resolver RPUSHes resolved subgraphs
WRITE_DLQ = "graphd:write_dlq"           # unparseable buffer items land here
FLUSH_LOCK = "graphd:flush_lock"
GRAPH_VERSION = "graph:version"          # INCR on every committed batch
DELTA_STREAM = "graph:deltas"            # XADD GraphDelta after each commit
