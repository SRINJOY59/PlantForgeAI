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

// ---------------------------------------------------------------------------
// Read-path indexes.
//
// The writer stores every node as {id, surface_form, ...extracted props}
// (graphd/batching.py), and the agent read path anchors almost every MATCH on
// surface_form - the human-readable tag, e.g. 'P-101A'. Without these, each of
// those lookups is a NodeByLabelScan: read every node of that label and compare
// the property. These make them index seeks.
//
// Range indexes, deliberately not uniqueness constraints: surface_form is not
// guaranteed unique (resolution maps it onto id, which is the real key), so a
// constraint here would start rejecting legitimate writes.
CREATE INDEX equipment_surface_form IF NOT EXISTS
FOR (e:Equipment) ON (e.surface_form);

CREATE INDEX failuremode_surface_form IF NOT EXISTS
FOR (f:FailureMode) ON (f.surface_form);

CREATE INDEX document_surface_form IF NOT EXISTS
FOR (d:Document) ON (d.surface_form);

CREATE INDEX workorder_surface_form IF NOT EXISTS
FOR (w:WorkOrder) ON (w.surface_form);

// entity_id above indexes :Entity(id). The planner chooses an index by the
// label written in the pattern, and it does not know at plan time that an
// Equipment is also an Entity - so a MATCH (e:Equipment {id: $id}) cannot use
// it. These cover the id lookups that name a type label instead of :Entity.
CREATE INDEX equipment_id IF NOT EXISTS
FOR (e:Equipment) ON (e.id);

CREATE INDEX document_id IF NOT EXISTS
FOR (d:Document) ON (d.id);

// Vector index for chunk embeddings. Dimensions MUST match what the
// embedding model actually emits (text-embedding-3-small -> 1536); keep in
// sync with EMBEDDING_DIM in .env
CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};

// Access control lives in enterprise.cypher - role grants need Neo4j
// Enterprise; the community container used for dev has no roles.
