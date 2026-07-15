// Enterprise-only statements, applied on top of init.cypher when the
// target is Neo4j Enterprise (e.g. a plant deployment). Dev containers run
// Community, which has no role-based access control.

// Read-only user for retrieval + agents (writes only via graphd)
CREATE USER retrieval_ro IF NOT EXISTS SET PASSWORD 'CHANGE_ME' CHANGE NOT REQUIRED;
GRANT ROLE reader TO retrieval_ro;
