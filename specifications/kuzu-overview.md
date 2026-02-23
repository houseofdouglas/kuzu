# Kuzu — Conceptual Overview

## What Kuzu Is

Kuzu is an **embedded, serverless property graph database**. There is no separate server process — you link it into your application as a library. It stores data in a **labeled property graph**: nodes carry labels and properties, directed edges carry a type and properties. The query language is **Cypher** (the same language used by Neo4j), extended with Kuzu-specific features for analytical workloads.

The storage is **columnar and disk-based**, oriented around read-heavy analytical queries rather than high-throughput OLTP. Write transactions are serialized (one writer at a time), but multiple readers run concurrently. It is fully ACID compliant via a Write-Ahead Log.

---

## Data Model Essentials

**Nodes** are created from typed tables. Every node table has a primary key:
```cypher
CREATE NODE TABLE Feature(id STRING, name STRING, description STRING, status STRING, PRIMARY KEY(id))
CREATE NODE TABLE Component(id STRING, name STRING, PRIMARY KEY(id))
```

**Edges** are typed relationships between node tables:
```cypher
CREATE REL TABLE DependsOn(FROM Feature TO Feature, strength STRING)
CREATE REL TABLE Implements(FROM Feature TO Component)
CREATE REL TABLE Breaks(FROM Feature TO Feature, reason STRING)
```

Both nodes and edges can carry **rich property types**: scalar values, but also `STRUCT` (named fields), `LIST` (variable-length arrays), `MAP` (key-value), and `UNION` (tagged variants). A specification's metadata can be stored as a flat struct property rather than forcing everything into primitive columns.

---

## Schema Lifecycle

The schema is **declared upfront** but can evolve without recreation:
```cypher
ALTER TABLE Feature ADD acceptance_criteria STRING[] DEFAULT [];
ALTER TABLE Feature DROP deprecated_field;
```

You can add or remove properties from existing tables. You cannot change a property's type in-place, and there is no automatic schema inference — structure must be declared explicitly.

---

## Querying

Cypher queries compose naturally for impact analysis and traversal:

```cypher
-- What features would be affected if we change feature X?
MATCH (x:Feature {id: 'auth-login'})-[:DependsOn*1..5]->(affected:Feature)
RETURN affected.id, affected.name;

-- Find all transitive dependents
MATCH path = (f:Feature)-[:DependsOn*]->(target:Feature {id: 'auth-token'})
RETURN nodes(path), length(path);

-- What would break if we remove a feature?
MATCH (f:Feature {id: 'auth-login'})<-[:Breaks]-(breaker:Feature)
RETURN breaker;
```

Variable-length paths (`*1..n`) are first-class — finding all transitive dependencies in a spec graph is a single query.

---

## Python API

```python
import kuzu

db = kuzu.Database("./spec.db")
conn = kuzu.Connection(db)

# Define schema
conn.execute("CREATE NODE TABLE Feature(id STRING, name STRING, description STRING, PRIMARY KEY(id))")

# Insert data
conn.execute("CREATE (:Feature {id: 'auth', name: 'Authentication', description: 'User login flow'})")

# Parameterized query (safe for LLM-generated queries)
result = conn.execute(
    "MATCH (f:Feature {id: $id}) RETURN f",
    parameters={"id": "auth"}
)

# Retrieve results as dicts or dataframes
for row in result.get_all():
    print(row)

df = result.get_as_df()         # Pandas DataFrame
pl_df = result.get_as_pl()      # Polars DataFrame
arrow = result.get_as_arrow()   # PyArrow Table
```

Results include `NODE` objects with `.properties` dict access, making it straightforward to serialize graph data back to an LLM context.

---

## Fit Assessment for LLM-Managed Spec Storage

| Requirement | Kuzu Support | Notes |
|---|---|---|
| Nodes for features/components | ✅ | Typed node tables with rich properties |
| Edges for relationships | ✅ | Typed rel tables with directional CSR storage |
| Transitive dependency traversal | ✅ | Variable-length Cypher paths, shortest path |
| Schema evolution (add features) | ✅ | `ALTER TABLE ADD/DROP` |
| Atomic spec updates | ✅ | Full ACID transactions |
| Python API for LLM integration | ✅ | First-class; returns pandas/arrow/dicts |
| Full-text search on descriptions | ✅ | Via `fts` extension (installable) |
| Semi-structured property bags | ✅ | `STRUCT`, `MAP`, `LIST` types |
| Versioning / history tracking | ⚠️ | No built-in; requires manual node versioning |
| Single writer at a time | ⚠️ | Fine for a spec system; blocks concurrent LLM agents |
| Schema inference | ❌ | Schema must be declared explicitly |

**Verdict: Kuzu is well-suited for this use case.** The combination of typed graph storage, Cypher path queries for impact analysis, ACID transactions for reliable spec updates, and a clean Python API aligns directly with the requirement. The main implementation concern is **versioning** — spec history must be modeled explicitly (e.g., `SpecSnapshot` nodes with timestamped state) if rollback capability is needed.

---

## Extensions Worth Loading

| Extension | Purpose |
|---|---|
| `fts` | Full-text search over description and acceptance criteria text fields |
| `json` | Parse/generate JSON if LLM output is JSON-formatted |
| `vector` | Store and search embedding vectors (e.g., `FLOAT[1536]`) for semantic spec search |
| `algo` | Community detection, centrality, PageRank on spec dependency graph |

The `vector` extension is particularly relevant: embedding each feature's description enables LLM prompts like "find features similar to this new requirement" before deciding whether to create vs. merge.

---

## Recommended Configuration

```python
db = kuzu.Database(
    database_path="./spec.db",
    buffer_pool_size=512 * 1024 * 1024,  # 512MB if spec fits in memory
    max_num_threads=4,                    # parallelism for read queries
    enable_compression=True,
    read_only=False,
    auto_checkpoint=True,
    checkpoint_threshold=16 * 1024 * 1024,  # 16MB WAL before checkpoint
    enable_checksums=True,                   # detect WAL corruption
)
```

For **read-only LLM querying** separate from the write connection, open a second `Database` instance with `read_only=True` pointing to the same path. Multiple read-only instances are allowed simultaneously.
