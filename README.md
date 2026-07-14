# PlantMind — Industrial Knowledge Graph Platform

Microservice system that ingests heterogeneous plant documents (work orders,
P&IDs, SOPs/incident reports), builds a denoised knowledge graph, and serves
PathRAG-based retrieval with citations.

## Services

| Service      | Role                                                        | Talks to            |
|--------------|-------------------------------------------------------------|---------------------|
| `gateway`    | FastAPI edge: `/ingest`, `/ask` (SSE), `/alerts`, `/metrics` | retrieval (HTTP), Redis |
| `ingestion`  | Hash gate → classifier → routes to extraction queues         | Redis (Celery)      |
| `extraction` | 3 Celery queues: WO parser / P&ID VLM / text RAG-extractor   | Redis, MinIO, LLM   |
| `resolution` | Tiered entity resolution (rules → embeddings → LLM) + per-key Redis locks | Redis |
| `graphd`     | **Sole Neo4j writer** (batched UNWIND), denoise beat, delta events | Neo4j, Redis  |
| `retrieval`  | PathRAG: link → paths → flow-prune → assemble → answer → verify | Neo4j (read-only), LLM |
| `agents`     | Event-driven: failure-pattern watcher, compliance scanner    | Redis (delta stream)|

## Hard rules

1. **Writes to Neo4j go through `graphd` only.** Retrieval/agents use a read-only DB user.
2. Extractors emit `CandidateSubgraph` JSON — never DB writes.
3. Every edge carries provenance `(doc_id, page, span, extractor_version, confidence)`.
4. All async messaging over Redis: Celery queues for work, Streams for `GraphDelta` events.
5. LLM access only via `plantmind_core.llm` (tiered: cheap/mid/vision; retries; token budget).

## Data flow

```
upload → gateway → ingestion(hash+classify)
       → extraction.{workorder|pnid|text} → CandidateSubgraph
       → resolution (locks) → ResolvedSubgraph → write_buffer
       → graphd (batch UNWIND, bump graph_version, emit GraphDelta)
       → agents react / caches invalidate
query  → gateway → retrieval (cache → PathRAG → stream) → SSE to UI
```

## Run

```
cp .env.example .env   # fill API keys
docker compose up      # neo4j, redis, minio + all services
```

## Dev setup (local venv)

```
python -m venv .venv
.venv\Scripts\pip install -e libs\core[celery,dev] minio openpyxl fakeredis
echo <abs-path-to-repo>\services > .venv\Lib\site-packages\plantmind_services.pth
```

The .pth puts services/ on sys.path, so module smoke tests run from anywhere:
`python -m extraction.workorder.parser data\samples\work_orders.csv`
(.env is discovered by walking up from wherever you run.)

## Repo layout

- `libs/core` — shared pip package: schemas (pydantic contracts), LLM client, config, telemetry
- `services/<name>/` — the service's python package itself (imported as `<name>`,
  e.g. `graphd.writer`); container built from the shared
  `infra/docker/service.Dockerfile` with `SERVICE: <name>` build arg, deps in
  `infra/docker/requirements/<name>.txt`, command in docker-compose.yml
- `infra/neo4j/init.cypher` — constraints + indexes (run once)
- `eval/` — golden QA set + extraction benchmarks
- `data/samples/` — demo corpus
