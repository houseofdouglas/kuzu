# Kuzu — Technical Deep Dive

## Storage Architecture

Kuzu stores data in a **columnar format on disk**, organized into node groups and column chunks. This is fundamentally different from row-oriented databases.

```
Database file
└── Node Table: Feature
    ├── Column: id (STRING, primary key)
    │   └── Node groups → Column chunks → Compressed segments
    ├── Column: name (STRING)
    └── Column: description (STRING)

Relationship Table: DependsOn
└── CSR (Compressed Sparse Row) adjacency list
    ├── Forward direction: source → list of targets
    └── Backward direction: target → list of sources (if storage_direction=BOTH)
```

**Compression** is applied per-column: integer bitpacking, ALP (Accelerated Logical Predicates) for floats, null bitmaps. The `enableCompression=True` default is sensible to keep.

**Buffer Manager** keeps hot pages in memory (configurable pool size). For a spec database that fits in memory, set `buffer_pool_size` equal to the expected database size for best performance.

**Relationship storage direction** defaults to `BOTH`, meaning CSR lists are stored in both directions. For spec graphs where you query both `DependsOn` (forward) and "what depends on this?" (backward), this is correct — but doubles the storage for rel tables.

---

## Transaction Internals

Each transaction gets a unique 64-bit ID and a start timestamp. Kuzu uses **timestamp-based MVCC**:

- When a write transaction commits, it gets a commit timestamp
- Concurrent read transactions see only data committed before their start timestamp — no dirty reads
- Write transactions are **serialized at commit time** (one at a time), not at start time
- The WAL records every modification; `CHECKPOINT` merges WAL into the persistent columnar store

For an LLM spec system: if two LLM agents try to write concurrently, the second will wait for the first to commit. This is generally acceptable for a spec management workflow.

**WAL record types** relevant to durability:
- `COMMIT_RECORD` — marks transaction committed
- `CREATE/DROP/ALTER` catalog records — schema changes are WAL-logged
- `TABLE_INSERTION_RECORD`, `NODE_DELETION_RECORD`, `REL_UPDATE_RECORD` — data changes

On crash recovery, Kuzu replays the WAL from the last checkpoint. The `throw_on_wal_replay_failure=True` default means a corrupted WAL surfaces as an error rather than silent data loss.

---

## Type System for Spec Storage

```
Primitives:  INT64, DOUBLE, BOOL, STRING, UUID, DATE, TIMESTAMP
Nested:
  LIST(T)               -- ordered, variable-length: STRING[], Feature[]
  ARRAY(T, n)           -- fixed-length: FLOAT[1536] (for embedding vectors)
  STRUCT(f1 T1, ...)    -- named fields, heterogeneous types
  MAP(K, V)             -- key-value, all keys same type
  UNION(v1 T1, v2 T2)   -- tagged variant (discriminated union)
```

For spec nodes, `STRUCT` is particularly useful for embedding structured metadata:
```cypher
CREATE NODE TABLE Feature(
  id STRING,
  metadata STRUCT(owner STRING, priority INT64, tags STRING[], created DATE),
  acceptance_criteria STRUCT(given STRING[], when_ STRING[], then_ STRING[]),
  PRIMARY KEY(id)
)
```

`STRUCT` fields are accessed with dot notation in Cypher: `f.metadata.owner`. Nested lists within structs work: `f.acceptance_criteria.given[0]`.

**Important limitation**: There is no native `JSON` type in the core schema. The `json` extension adds JSON functions (`json_extract`, `json_object`, etc.) for handling JSON strings, but they are stored as `STRING` and parsed at query time — not indexed as structured data. For spec storage, using typed `STRUCT` properties is strongly preferable to storing JSON strings.

---

## Cypher Capabilities Relevant to Spec Diffing

**Full clause support**:
- Reading: `MATCH`, `OPTIONAL MATCH`, `UNWIND`, `CALL`, `LOAD FROM`
- Writing: `CREATE`, `MERGE` (with `ON CREATE SET` / `ON MATCH SET`), `SET`, `DELETE` (with `DETACH DELETE`)
- Projection: `RETURN`, `WITH`, `ORDER BY`, `SKIP`, `LIMIT`, `DISTINCT`

**MERGE is critical for LLM-generated spec updates** — it creates a node/edge if it doesn't exist or matches if it does, in one atomic operation:
```cypher
-- Safe idempotent upsert from LLM output
MERGE (f:Feature {id: 'new-feature'})
ON CREATE SET f.name = 'New Feature', f.description = $desc, f.status = 'draft'
ON MATCH SET f.description = $desc, f.updated_at = date()
```

**Inline subquery counting**:
```cypher
MATCH (f:Feature)
RETURN f.name,
       COUNT { MATCH (f)-[:DependsOn]->(dep:Feature) } AS dependency_count,
       COUNT { MATCH (f)<-[:DependsOn]-(rev:Feature) } AS reverse_dependency_count
ORDER BY dependency_count DESC;
```

**Path semantics for impact analysis**:
```cypher
-- TRAIL: no repeated edges (safe for spec graphs with cycles)
MATCH (f:Feature {id: $start})-[e:DependsOn* TRAIL 1..10]->(affected)
RETURN affected.id, length(e) AS depth

-- Shortest path between two features
MATCH (a:Feature {id: $a})-[e* SHORTEST 1..20]->(b:Feature {id: $b})
RETURN nodes(e), length(e)
```

**`EXPLAIN` and `PROFILE`** are available for query plan inspection, useful when optimizing LLM-generated queries:
```cypher
EXPLAIN MATCH (f:Feature)-[:DependsOn*1..5]->(dep) RETURN dep;
```

---

## Query Execution Pipeline

A query goes through these stages (relevant for debugging LLM-generated Cypher):

1. **Parser** (ANTLR4 grammar) → parse tree. Syntax errors surface here with line/column positions.
2. **Binder** → validates table/property names against the catalog, resolves types. Semantic errors surface here ("table `Featur` does not exist").
3. **Planner** → builds a logical plan, enumerates join orders, applies cost-based optimization.
4. **Processor** → executes vectorized physical operators (hash joins, recursive extend, aggregations) in parallel across available threads.
5. **Result** → materialized into `FactorizedTable` then returned to caller.

The binder validates against the **live catalog**, so tables created and immediately queried in the same connection are visible without any refresh.

---

## Schema Evolution Mechanics

When you execute `ALTER TABLE Feature ADD tags STRING[] DEFAULT []`:

1. A new `AlterTableEntry` is created in the catalog
2. The change is WAL-logged as a catalog modification
3. Existing rows see the `DEFAULT` value for the new column — no table rewrite occurs
4. At the next `CHECKPOINT`, the catalog change is persisted

**What you can do**:
- Add a property: `ALTER TABLE Feature ADD tags STRING[] DEFAULT []`
- Drop a property: `ALTER TABLE Feature DROP deprecated_field`
- `DROP IF EXISTS` variant to avoid errors
- Rename a table or property
- Add/drop FROM-TO connections in relationship groups

**What you cannot do** (current codebase):
- Change a property's type in-place
- Rename the primary key column
- Add a non-nullable property without a default value

---

## Implementing Spec Versioning

Kuzu has no built-in versioning. The recommended pattern is explicit snapshot nodes:

```cypher
// Version snapshot schema
CREATE NODE TABLE SpecSnapshot(
  version_id STRING,
  created_at TIMESTAMP,
  description STRING,
  PRIMARY KEY(version_id)
)
CREATE REL TABLE SnapshotOf(
  FROM SpecSnapshot TO Feature,
  state STRUCT(name STRING, description STRING, status STRING)
)

// Capture state before modification
MATCH (f:Feature)
WITH collect(f) AS features
CREATE (snap:SpecSnapshot {
  version_id: $version_id,
  created_at: timestamp(),
  description: $change_desc
})
WITH snap, features
UNWIND features AS f
CREATE (snap)-[:SnapshotOf {state: {name: f.name, description: f.description, status: f.status}}]->(f)

// Diff two versions
MATCH (v1:SpecSnapshot {version_id: $v1})-[s1:SnapshotOf]->(f:Feature)
MATCH (v2:SpecSnapshot {version_id: $v2})-[s2:SnapshotOf]->(f)
WHERE s1.state <> s2.state
RETURN f.id, s1.state AS before, s2.state AS after
```

An alternative is a **bitemporal property approach**: add `valid_from`/`valid_to` timestamps on all spec nodes and query with:
```cypher
WHERE f.valid_from <= $ts AND (f.valid_to IS NULL OR f.valid_to > $ts)
```

The snapshot approach is more graph-idiomatic and enables diff queries directly in Cypher. The bitemporal approach requires less storage but makes graph traversal queries more complex.

---

## Key Source Locations

| Concern | Path |
|---|---|
| Public C++ API | [src/include/main/](../src/include/main/) |
| Type system | [src/include/common/types/types.h](../src/include/common/types/types.h) |
| Clause types (Cypher support) | [src/include/common/enums/clause_type.h](../src/include/common/enums/clause_type.h) |
| Transaction model | [src/include/transaction/transaction.h](../src/include/transaction/transaction.h) |
| WAL records | [src/include/storage/wal/](../src/include/storage/wal/) |
| Catalog entries | [src/include/catalog/](../src/include/catalog/) |
| Storage columnar format | [src/include/storage/](../src/include/storage/) |
| Python API | [tools/python_api/src_py/](../tools/python_api/src_py/) |
| Python API tests | [tools/python_api/test/](../tools/python_api/test/) |
| ANTLR4 Cypher grammar | [src/antlr4/Cypher.g4](../src/antlr4/Cypher.g4) |
| Extensions | [extension/](../extension/) |
