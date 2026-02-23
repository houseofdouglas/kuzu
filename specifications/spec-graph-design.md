# Spec Graph Design Decisions

## Question 1: Cyclic Graph or DAG?

**The spec graph will contain both, depending on relationship type.** The schema must reflect this distinction explicitly.

### DAG-Intended Relationships

Cycles in these are design defects, not expected data:

| Relationship | Direction | Cycle meaning |
|---|---|---|
| `DependsOn` / `Requires` | Feature → Feature | Circular dependency — logically broken |
| `Implements` | Feature → Component | Infinite implementation regress |
| `DerivedFrom` / `Extends` | Feature → Feature | Circular inheritance |

### Naturally Cyclic / Symmetric Relationships

Cycles here are valid or expected:

| Relationship | Why cyclic is OK |
|---|---|
| `Conflicts` | If A conflicts with B, B conflicts with A — undirected by nature |
| `RelatedTo` | Symmetric |
| `Tests` / `Validates` | Integration tests may mutually validate |
| `CompetesWith`, `Supersedes` | Domain-specific, often bidirectional |

### Design Principle

**Do not enforce DAG constraints at the database level.** Instead:
1. Store cycles — do not reject writes that create them
2. Detect cycles after spec mutations using a dedicated query
3. Surface cycle detection results for human or LLM review

```cypher
-- Run after every DependsOn write
-- Returns nodes that can reach themselves
MATCH (f:Feature)-[:DependsOn* ACYCLIC 1..20]->(f)
RETURN f.id AS circular_dependency_detected
```

The `ACYCLIC` path semantic prevents infinite traversal — it terminates when a node would be revisited, making this query safe even on graphs with cycles.

### Recommended Schema Split

```cypher
-- DAG-intended: directional, cycle = defect, enforce via post-write query
CREATE REL TABLE DependsOn(FROM Feature TO Feature, strength STRING)
CREATE REL TABLE Implements(FROM Feature TO Component)
CREATE REL TABLE DerivedFrom(FROM Feature TO Feature)

-- Symmetric/cyclic: undirected intent, create both directions on write
CREATE REL TABLE Conflicts(FROM Feature TO Feature, reason STRING)
CREATE REL TABLE RelatedTo(FROM Feature TO Feature)
```

For `Conflicts` and `RelatedTo`, write both directions on every insert:
```cypher
MATCH (a:Feature {id: $a}), (b:Feature {id: $b})
MERGE (a)-[:Conflicts {reason: $reason}]->(b)
MERGE (b)-[:Conflicts {reason: $reason}]->(a)
```

---

## Question 2: Multi-Developer Branch Divergence and Sequential Merge

### Core Architectural Decision

**Git is the source of truth for the spec. Kuzu is the runtime query engine.**

The spec lives in git as structured, diffable files. `spec.db` is a derived artifact — rebuilt from those files on load, not versioned itself.

```
git repo
├── spec/
│   ├── schema.cypher          # DDL: CREATE NODE TABLE, CREATE REL TABLE
│   ├── nodes/
│   │   ├── features.json      # All Feature nodes as JSON array
│   │   └── components.json    # All Component nodes as JSON array
│   └── edges/
│       ├── depends-on.json    # All DependsOn edges
│       └── implements.json
└── spec.db                    # .gitignore — derived from spec/, rebuilt on load
```

This gives git's full branching, history, blame, and conflict markers for free. LLMs work natively with text-based diffs on JSON/Cypher files.

### The Branch Lifecycle

```
main (canonical spec)
│
├──── branch-point snapshot (common ancestor)
│     │
│     └── dev-branch: developer + AI agent edits spec/
│
│     (main may receive other merges while branch is open)
│
└──── 3-way merge evaluation → merged commit → rebuild spec.db
```

### Three-Phase Merge Process

#### Phase 1 — Generate the Delta Triple

Load three states into three separate in-memory Kuzu instances:

1. **Ancestor** — spec at the branch-point commit (from git history)
2. **Branch-current** — spec at HEAD of the dev branch
3. **Main-current** — spec at HEAD of main at merge time

Compute two deltas:
- `branch_delta` = diff(ancestor, branch-current) — what the developer changed
- `main_delta` = diff(ancestor, main-current) — what landed on main since branch-off

Each delta is a structured changeset:
```json
{
  "added_nodes":    [{"table": "Feature", "id": "...", "properties": {}}],
  "modified_nodes": [{"table": "Feature", "id": "...", "before": {}, "after": {}}],
  "deleted_nodes":  [{"table": "Feature", "id": "..."}],
  "added_edges":    [{"table": "DependsOn", "from": "...", "to": "...", "properties": {}}],
  "deleted_edges":  [{"table": "DependsOn", "from": "...", "to": "..."}]
}
```

#### Phase 2 — Classify Conflicts

Compare `branch_delta` against `main_delta` by node/edge identity:

| Branch did | Main did | Classification |
|---|---|---|
| Add node X | Nothing | Auto-merge: add X to main |
| Modify node X | Nothing | Auto-merge: apply branch modification |
| Nothing | Modify node X | Auto-merge: already on main, no action needed |
| Modify node X | Modify node X (same property, same value) | Auto-merge: identical change |
| Modify node X | Modify node X (different values) | **Conflict: structural** |
| Add edge X→Y | Delete node Y | **Conflict: topological** |
| Delete node X | Modify node X | **Conflict: delete/modify** |
| Add node X | Add node X (different properties) | **Conflict: identity collision** |

#### Phase 3 — LLM-Assisted Conflict Resolution

For each conflict, provide the LLM with:
- Node state on branch
- Node state on main
- The graph neighborhood of the conflicting node (what depends on it, what it depends on)
- The branch commit message / change description as context

The LLM produces either:
1. A merged node state (when intent is compatible)
2. A conflict report flagging a human decision

The resolved changeset is applied to main's spec files in a single commit. `spec.db` is rebuilt from the merged spec files.

### Why Sequential Merging

Sequential merging (one branch at a time, updating main before the next merge) is required because:

- A topological conflict that is obvious in a 3-way merge becomes ambiguous in a 4-way merge
- The sequencing constraint must be enforced at the process level: a branch cannot be queued for merge until all previously opened merge requests against main are resolved
- This mirrors how database migration tools (Flyway, Alembic) work — migrations are sequentially numbered, never applied in parallel

### Kuzu's Role Inside the Merge Tool

Even though Kuzu is not the branching mechanism, it provides **graph-aware conflict detection** that text diffing cannot:

```python
# Load all three spec states into in-memory Kuzu instances for graph queries
# Use Cypher to find topological conflicts that property diffs miss

# Example: find all nodes that depended on a node being deleted on the branch
conn_main.execute(
    "MATCH (b:Feature)-[:DependsOn]->(f:Feature {id: $id}) RETURN b.id",
    {"id": deleted_node_id}
)
# If this returns rows, the deletion creates a dangling dependency on main
```

Graph queries surface conflicts that naive property-by-property JSON diffs miss:
- A new `DependsOn` edge on the branch targeting a node deleted on main
- A cycle introduced by combining two sets of non-cyclic changes
- Transitively affected nodes whose direct properties were not touched

### Rebuild Spec DB from Files

```python
import kuzu, json, pathlib

def rebuild_spec_db(spec_dir: str, db_path: str):
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)

    # Apply DDL
    schema = pathlib.Path(spec_dir, "schema.cypher").read_text()
    for statement in schema.split(";"):
        if statement.strip():
            conn.execute(statement)

    # Load nodes
    for node_file in pathlib.Path(spec_dir, "nodes").glob("*.json"):
        nodes = json.loads(node_file.read_text())
        for node in nodes:
            table = node_file.stem.replace("-", "_").title()
            props = ", ".join(f"{k}: ${k}" for k in node)
            conn.execute(f"CREATE (:{table} {{{props}}})", node)

    # Load edges
    for edge_file in pathlib.Path(spec_dir, "edges").glob("*.json"):
        edges = json.loads(edge_file.read_text())
        for edge in edges:
            # Edge JSON format: {"from_id": "...", "to_id": "...", "table": "DependsOn", ...}
            conn.execute(
                f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) "
                f"CREATE (a)-[:{edge['table']}]->(b)",
                edge
            )
```

### Summary

| Concern | Solution |
|---|---|
| Source of truth | Structured files in git (`spec/` directory) |
| Runtime queries | `spec.db` rebuilt from spec files on load |
| Branching | Native git branches |
| Merge sequencing | One branch at a time; queue enforced at process level |
| Conflict detection | 3-way diff: ancestor × branch-current × main-current |
| Structural conflicts | Property-level diff on matching node IDs |
| Topological conflicts | Kuzu graph queries across all three in-memory instances |
| Conflict resolution | LLM provided with conflicting states + graph neighborhood |
| Cycle detection | Post-write Cypher query with `ACYCLIC` path semantic |
