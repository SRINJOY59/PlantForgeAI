// Run once against a fresh database. Constraints double as race-condition
// backstops: a duplicate create fails loudly instead of corrupting the graph.

// every node carries :Entity plus its type label; all writes and lookups
// key on Entity.id, which keeps cross-label MATCHes on the id index
CREATE CONSTRAINT entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT equipment_tag IF NOT EXISTS
FOR (e:Equipment) REQUIRE e.tag IS UNIQUE;

CREATE CONSTRAINT instrument_tag IF NOT EXISTS
FOR (i:Instrument) REQUIRE i.tag IS UNIQUE;

CREATE CONSTRAINT doc_hash IF NOT EXISTS
FOR (d:Document) REQUIRE d.content_hash IS UNIQUE;

CREATE CONSTRAINT workorder_id IF NOT EXISTS
FOR (w:WorkOrder) REQUIRE w.wo_id IS UNIQUE;

CREATE INDEX doc_number IF NOT EXISTS
FOR (d:Document) ON (d.doc_number);

CREATE INDEX chunk_superseded IF NOT EXISTS
FOR (c:Chunk) ON (c.superseded);

// Vector index for chunk embeddings (tune dimension to embedding model)
CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
}};

// Read-only user for retrieval + agents (writes only via graphd)
CREATE USER retrieval_ro IF NOT EXISTS SET PASSWORD 'CHANGE_ME' CHANGE NOT REQUIRED;
GRANT ROLE reader TO retrieval_ro;
