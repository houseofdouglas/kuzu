"""
Edge CRUD for the spec graph, with cycle detection for DAG-intended relationships.

DAG relations (DependsOn, Implements, DerivedFrom) are checked for cycles before
any edge is written. Non-DAG relations (Conflicts, RelatedTo, Satisfies) are
written without cycle checks.
"""

from __future__ import annotations

from typing import Any

from .db import SpecDB, _prefix_params

# ── Schema knowledge ──────────────────────────────────────────────────────────

DAG_RELATIONS = {"DependsOn", "Implements", "DerivedFrom"}

ALL_RELATIONS = {
    "DependsOn", "Implements", "DerivedFrom",
    "Conflicts", "RelatedTo", "Satisfies",
}

# Maximum path depth for cycle detection and impact queries
MAX_DEPTH = 50


def _check_cycle(db: SpecDB, table: str, from_id: str, to_id: str) -> bool:
    """
    Return True if adding the edge from_id→to_id in `table` would create a cycle.

    Pre-check: if `to_id` can already reach `from_id`, adding from_id→to_id closes a cycle.
    Uses Kuzu's ACYCLIC path semantics (no repeated nodes).
    """
    rows = db.query(
        f"MATCH (src {{id: $p_from}})-[:{table}* ACYCLIC 1..{MAX_DEPTH}]->(dst {{id: $p_to}}) "
        "RETURN src.id AS src",
        {"p_from": to_id, "p_to": from_id},
    )
    return len(rows) > 0


# ── Write ─────────────────────────────────────────────────────────────────────

def write_edge(
    db: SpecDB,
    table: str,
    from_id: str,
    to_id: str,
    props: dict[str, Any] | None = None,
) -> dict:
    """
    Write an edge, with cycle detection for DAG relation types.

    Raises:
        ValueError — unknown table, missing nodes, or cycle detected
    """
    if table not in ALL_RELATIONS:
        raise ValueError(f"Unknown relation table: {table!r}. Valid: {sorted(ALL_RELATIONS)}")

    # Verify both endpoint nodes exist
    for node_id in (from_id, to_id):
        rows = db.query("MATCH (n {id: $p_id}) RETURN n.id AS id", {"p_id": node_id})
        if not rows:
            raise ValueError(f"Node {node_id!r} not found in spec graph.")

    # Cycle check for DAG-intended relations
    if table in DAG_RELATIONS:
        if _check_cycle(db, table, from_id, to_id):
            raise ValueError(
                f"Adding {table} edge {from_id!r} → {to_id!r} would create a cycle. "
                "Redesign the dependency before committing."
            )

    # Build the edge
    params: dict[str, Any] = {"p_from": from_id, "p_to": to_id}
    if props:
        prop_spec, extra_prefixed = _prefix_params(props)
        params.update(extra_prefixed)
        rel_props = f" {{{prop_spec}}}"
    else:
        rel_props = ""

    db.execute(
        f"MATCH (a {{id: $p_from}}), (b {{id: $p_to}}) CREATE (a)-[:{table}{rel_props}]->(b)",
        params,
    )

    return {
        "status": "created",
        "table": table,
        "from_id": from_id,
        "to_id": to_id,
        "props": props or {},
    }


def delete_edge(db: SpecDB, table: str, from_id: str, to_id: str) -> dict:
    """Delete a specific edge between two nodes."""
    if table not in ALL_RELATIONS:
        raise ValueError(f"Unknown relation table: {table!r}.")

    db.execute(
        f"MATCH (a {{id: $p_from}})-[e:{table}]->(b {{id: $p_to}}) DELETE e",
        {"p_from": from_id, "p_to": to_id},
    )
    return {"status": "deleted", "table": table, "from_id": from_id, "to_id": to_id}


# ── Cycle detection ───────────────────────────────────────────────────────────

def detect_cycles(db: SpecDB) -> list[str]:
    """
    Find all nodes involved in cycles in any DAG-intended relation.

    Returns a list of node IDs that participate in circular dependency chains.
    An empty list means the graph is a valid DAG.
    """
    cycle_ids: set[str] = set()
    for rel in DAG_RELATIONS:
        try:
            rows = db.query(
                f"MATCH (n)-[:{rel}* ACYCLIC 1..{MAX_DEPTH}]->(n) RETURN n.id AS id"
            )
            for row in rows:
                cycle_ids.add(row["id"])
        except Exception:
            # Table may not exist or may be empty — skip
            pass
    return sorted(cycle_ids)


# ── Impact analysis ───────────────────────────────────────────────────────────

def get_affected_by(db: SpecDB, node_id: str, depth: int = 10) -> list[dict]:
    """
    Return all nodes that transitively depend on `node_id` via DependsOn.

    These are the nodes that would be affected if node_id changed.
    Depth is clamped to [1, MAX_DEPTH].
    """
    depth = max(1, min(MAX_DEPTH, int(depth)))
    # Literal integer in path expression (Kuzu does not support parameterized bounds)
    rows = db.query(
        f"MATCH (affected)-[:DependsOn*1..{depth}]->(target {{id: $p_id}}) "
        "RETURN affected.id AS id, label(affected) AS table",
        {"p_id": node_id},
    )
    return rows


def list_edges(db: SpecDB, table: str | None = None) -> list[dict]:
    """List all edges in one or all relation tables."""
    tables = [table] if table else sorted(ALL_RELATIONS)
    result: list[dict] = []
    for t in tables:
        if t not in ALL_RELATIONS:
            raise ValueError(f"Unknown relation table: {t!r}.")
        try:
            rows = db.query(
                f"MATCH (a)-[e:{t}]->(b) "
                "RETURN a.id AS from_id, b.id AS to_id"
            )
            for row in rows:
                result.append({"table": t, **row})
        except Exception:
            pass
    return result
