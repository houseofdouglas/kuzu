# Spec Management System Architecture

## Context

The Vahmos project already operates a multi-agent team:
`Kate (PM) → UX Designer → Engineering Director → Dev agents → QA/E2E`

Each agent produces artifacts: feature specs, design specs, technical specs, acceptance criteria. The spec management system routes these artifacts through a Kuzu graph, making relationships queryable and changes validatable for impact before they are committed.

The spec graph adds a **consistency enforcement layer** between agent outputs.

---

## Recommended Architecture: Agent + MCP Server

### Why This Fits

The existing agents already delegate to each other via Claude's `Task` tool. Adding a `spec-manager` agent to that delegation chain requires no new infrastructure — just another `.md` file in `agents/`. MCP is the right protocol because it lets Claude agents call Python functions directly with typed parameters, without shell escaping or prompt formatting concerns.

### Component Overview

```
spec_manager/          # Python package — the database access layer
spec/                  # Source of truth — structured JSON/Cypher files in git
spec.db                # .gitignore — derived artifact, rebuilt from spec/ on load
agents/spec-manager.md # Claude agent — the single writer to the spec graph
.git/hooks/pre-commit  # Cycle detection on every commit
.github/workflows/     # 3-way merge validation on every PR
```

### Agent Delegation Flow

```
Kate proposes feature
    └─► spec-manager agent
            ├─ MCP: check_conflicts(feature)
            ├─ MCP: detect_cycles()
            ├─ MCP: write_node(Feature, {...})
            └─ returns: node_id, affected_nodes[], warnings[]

UX Designer produces design spec
    └─► spec-manager agent
            ├─ MCP: write_node(DesignSpec, {...})
            └─ MCP: write_edge(DesignedBy, design_id, feature_id)

Engineering Director produces tech spec
    └─► spec-manager agent
            ├─ MCP: write_node(TechSpec, {...})
            └─ MCP: write_edge(Specifies, tech_id, feature_id)
```

The `spec-manager` agent is the **single writer** to the graph. All other agents propose; spec-manager validates and commits.

---

## What to Build

### 1. `spec_manager/` Python Package

```
spec_manager/
├── __init__.py
├── db.py           # Kuzu connection, schema init, rebuild from spec/
├── nodes.py        # Node CRUD with type validation
├── edges.py        # Edge CRUD with cycle detection guard
├── diff.py         # 3-way changeset computation
├── merge.py        # Conflict classification and resolution interface
├── export.py       # Serialize graph → spec/ JSON files
└── mcp_server.py   # FastMCP server exposing tools to Claude agents
```

**Core MCP tools exposed**:

| Tool | Parameters | Returns |
|---|---|---|
| `read_spec_node` | `id: str` | Node properties + immediate neighbors |
| `write_spec_node` | `table: str, properties: dict` | New node ID, affected nodes |
| `write_spec_edge` | `table: str, from_id: str, to_id: str, props: dict` | Edge confirmation, cycle warning |
| `query_spec` | `cypher: str` | Query results as list of dicts |
| `detect_cycles` | — | List of circular dependency chains |
| `get_affected_by` | `node_id: str, depth: int` | Transitive dependents |
| `export_to_files` | — | Writes current state to `spec/` |

### 2. `spec/` Directory in Git

```
spec/
├── schema.cypher           # DDL: CREATE NODE TABLE, CREATE REL TABLE
├── nodes/
│   ├── features.json       # Feature nodes as JSON array
│   ├── components.json
│   ├── design-specs.json
│   └── tech-specs.json
└── edges/
    ├── depends-on.json
    ├── implements.json
    ├── designed-by.json
    └── specifies.json
```

`spec.db` is `.gitignore`d. Rebuild from `spec/`:

```python
def rebuild_spec_db(spec_dir: str, db_path: str):
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)
    schema = pathlib.Path(spec_dir, "schema.cypher").read_text()
    for stmt in schema.split(";"):
        if stmt.strip():
            conn.execute(stmt)
    for node_file in pathlib.Path(spec_dir, "nodes").glob("*.json"):
        for node in json.loads(node_file.read_text()):
            table = node_file.stem.title().replace("-", "")
            props = ", ".join(f"{k}: ${k}" for k in node)
            conn.execute(f"CREATE (:{table} {{{props}}})", node)
    for edge_file in pathlib.Path(spec_dir, "edges").glob("*.json"):
        for edge in json.loads(edge_file.read_text()):
            conn.execute(
                f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) "
                f"CREATE (a)-[:{edge['table']}]->(b)",
                edge
            )
```

### 3. `agents/spec-manager.md` — New Claude Agent

```yaml
---
name: spec-manager
description: >
  Use this agent when any agent needs to read from or write to the specification
  graph, validate a proposed spec change, check for dependency conflicts, run
  impact analysis, or resolve a merge conflict between a feature branch spec
  and the main trunk spec. This agent is the single writer to the spec graph.
  All other agents must route spec mutations through this agent.
model: sonnet
color: purple
---

You are the Spec Manager for the Vahmos project. You maintain the canonical
software specification as a property graph in Kuzu. You are the sole authority
on what enters the spec graph — all other agents propose, you decide and commit.

Your responsibilities:
1. Validate proposed spec changes against existing nodes and edges
2. Detect dependency cycles before committing new edges
3. Run impact analysis: "if we change X, what else is affected?"
4. Resolve merge conflicts between a feature branch spec and main trunk
5. Maintain the single-writer constraint — never allow concurrent writes

When another agent asks you to add a feature, you:
1. Check if a similar feature already exists (semantic deduplication)
2. Check if proposed DependsOn edges would create a cycle
3. Check what existing nodes would be affected by this addition
4. Commit the change and export to spec/ files
5. Return: the new node ID, list of affected nodes, any warnings

When resolving a merge conflict, you receive:
- The node state on branch
- The node state on main
- The graph neighborhood of the conflicting node
- The branch description of what changed and why
You produce a merged state or escalate to human review if the conflict
requires a product decision beyond your authority.
```

### 4. Git Enforcement

**Pre-commit hook** (`.git/hooks/pre-commit`):
```bash
#!/bin/sh
python -m spec_manager detect-cycles
python -m spec_manager validate-export   # spec/ files match spec.db state
```

**CI action** (`.github/workflows/spec-merge-check.yml`):
- On PR open: load three spec states into three in-memory Kuzu instances
- Compute `branch_delta` and `main_delta`
- Classify conflicts
- Post structured conflict report as PR comment
- Block merge if unresolved conflicts remain

---

## The Merge Pipeline End-to-End

```
Developer opens feature branch
    └─► spec.db copied from main at branch-point (common ancestor)

Developer + Claude agents work
    └─► All spec writes route through spec-manager agent
    └─► spec/ files updated on each write (MCP: export_to_files)
    └─► pre-commit: cycle detection on every commit

Developer opens PR (branch → main)
    └─► CI loads three states into three in-memory Kuzu DBs:
              ancestor = spec/ files at branch-point commit
              branch   = spec/ files at branch HEAD
              main     = spec/ files at main HEAD
    └─► CI computes branch_delta and main_delta as changesets
    └─► CI classifies each changed node/edge:

        Branch did        | Main did                   | Classification
        ──────────────────┼────────────────────────────┼───────────────────────
        Add node X        | Nothing                    | Auto-merge
        Modify node X     | Nothing                    | Auto-merge
        Modify node X     | Modify X (same value)      | Auto-merge (identical)
        Modify node X     | Modify X (different value) | CONFLICT: structural
        Add edge X→Y      | Delete node Y              | CONFLICT: topological
        Delete node X     | Modify node X              | CONFLICT: delete/modify
        Add node X        | Add node X (diff props)    | CONFLICT: collision

    └─► CI invokes spec-manager agent with conflict context for LLM resolution
    └─► spec-manager produces: resolved changeset OR escalation to human
    └─► Human approves → merged spec/ files committed to main
    └─► main spec.db rebuilt from merged spec/ files
    └─► next PR in queue unblocked (sequential merge enforced)
```

---

## Kuzu's Role Inside the Merge Tool

Graph-aware conflict detection catches things a property-level JSON diff misses:

```python
# Topological conflict: branch adds an edge to a node deleted on main
conn_main.execute(
    "MATCH (b:Feature)-[:DependsOn]->(f:Feature {id: $id}) RETURN b.id",
    {"id": deleted_node_id}
)
# Any result = a dangling dependency would be created by this merge

# Cycle introduced by combining two non-cyclic changesets
conn_merged.execute(
    "MATCH (f:Feature)-[:DependsOn* ACYCLIC 1..20]->(f) RETURN f.id"
)
# Any result = the merge creates a cycle that neither branch had alone
```

---

## Why Not a Process Control Service?

A workflow engine (Temporal, Prefect, Dagster) is the right answer for **unpredictable high concurrency** — many developers writing simultaneously and needing coordination across distributed workers. For Vahmos at current scale:

- The agent team is invoked synchronously, not running as parallel daemons
- Git already provides branching and sequencing primitives
- The merge queue constraint is enforced by CI (PR checks), not a runtime service

The process control logic lives in the spec-manager agent's reasoning and in the CI pipeline. Introduce a workflow engine when team size or change frequency makes the agent+CI model break down — not before.

---

## Comparison of Options

| Approach | Fits existing agent pattern | LLM-aware conflict resolution | Infrastructure to operate | Recommended |
|---|---|---|---|---|
| Agent + MCP Server | ✅ | ✅ | Python package only | **Yes** |
| Python CLI + Git hooks | ✅ | ⚠️ partial | None | Simpler fallback |
| Workflow engine | ❌ separate system | ✅ | Significant | No, premature |
