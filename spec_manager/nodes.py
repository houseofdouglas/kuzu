"""
Node CRUD for the spec graph.

All writes use CREATE (not MERGE) — Kuzu does not support MERGE ... SET.
All reads return plain dicts with string-typed values (no Kuzu NODE objects).
"""

from __future__ import annotations

from typing import Any

from .db import SpecDB, _prefix_params

# ── Schema knowledge ──────────────────────────────────────────────────────────

NODE_TABLES = {"Feature", "Component", "Interface", "Requirement", "MergeRequest"}

# Properties returned for each table (ordered for consistent output)
NODE_COLUMNS: dict[str, list[str]] = {
    "Feature":      ["id", "name", "description", "status"],
    "Component":    ["id", "name", "description", "status", "layer"],
    "Interface":    ["id", "name", "description", "status"],
    "Requirement":  ["id", "name", "description", "priority", "status"],
    "MergeRequest": ["branch_id", "status", "created_at", "completed_at", "merged_by"],
}

NODE_REQUIRED: dict[str, list[str]] = {
    "Feature":      ["id", "name", "description", "status"],
    "Component":    ["id", "name", "description", "status", "layer"],
    "Interface":    ["id", "name", "description", "status"],
    "Requirement":  ["id", "name", "description", "priority", "status"],
    "MergeRequest": ["branch_id", "status"],
}

# Primary key per table (most use "id"; MergeRequest uses "branch_id")
NODE_PK: dict[str, str] = {t: "id" for t in NODE_TABLES}
NODE_PK["MergeRequest"] = "branch_id"


def _select_cols(table: str) -> str:
    """Build RETURN clause: 'n.id AS id, n.name AS name, ...'"""
    return ", ".join(f"n.{c} AS {c}" for c in NODE_COLUMNS.get(table, ["id", "name"]))


# ── Read ──────────────────────────────────────────────────────────────────────

def find_node_table(db: SpecDB, node_id: str) -> str | None:
    """Identify which table a node with the given ID lives in."""
    for table in ("Feature", "Component", "Interface", "Requirement"):
        rows = db.query(
            f"MATCH (n:{table} {{id: $p_id}}) RETURN n.id AS id",
            {"p_id": node_id},
        )
        if rows:
            return table
    return None


def read_node(db: SpecDB, node_id: str) -> dict | None:
    """
    Read a node by ID plus its immediate graph neighborhood.

    Returns:
        {
          "node": {id, name, ...},
          "outbound": [{"rel": "DependsOn", "neighbor_id": "...", "neighbor_table": "..."}],
          "inbound":  [...],
        }
        or None if not found.
    """
    table = find_node_table(db, node_id)
    if not table:
        return None

    select = _select_cols(table)
    node_rows = db.query(
        f"MATCH (n:{table} {{id: $p_id}}) RETURN {select}",
        {"p_id": node_id},
    )
    if not node_rows:
        return None

    outbound = db.query(
        f"MATCH (n:{table} {{id: $p_id}})-[e]->(m) "
        "RETURN label(e) AS rel, m.id AS neighbor_id, label(m) AS neighbor_table",
        {"p_id": node_id},
    )
    inbound = db.query(
        f"MATCH (m)-[e]->(n:{table} {{id: $p_id}}) "
        "RETURN label(e) AS rel, m.id AS neighbor_id, label(m) AS neighbor_table",
        {"p_id": node_id},
    )

    return {"node": node_rows[0], "outbound": outbound, "inbound": inbound}


def list_nodes(db: SpecDB, table: str | None = None) -> list[dict]:
    """
    List all nodes, optionally filtered to a single table.

    Each dict includes a synthetic "table" key for easy identification.
    """
    tables = [table] if table else list(NODE_COLUMNS.keys())
    result: list[dict] = []
    for t in tables:
        if t not in NODE_COLUMNS:
            raise ValueError(f"Unknown node table: {t!r}. Valid: {sorted(NODE_COLUMNS)}")
        select = _select_cols(t)
        rows = db.query(f"MATCH (n:{t}) RETURN {select} ORDER BY n.id")
        for row in rows:
            result.append({"table": t, **row})
    return result


# ── Write ─────────────────────────────────────────────────────────────────────

def write_node(db: SpecDB, table: str, properties: dict[str, Any]) -> dict:
    """
    Create a new spec node after validation.

    Raises ValueError if:
    - table is unknown
    - required properties are missing
    - a node with this ID already exists
    """
    if table not in NODE_TABLES:
        raise ValueError(f"Unknown node table: {table!r}. Valid: {sorted(NODE_TABLES)}")

    required = NODE_REQUIRED.get(table, [])
    missing = [k for k in required if k not in properties or properties[k] is None]
    if missing:
        raise ValueError(f"Missing required properties for {table}: {missing}")

    pk = NODE_PK[table]
    pk_val = properties[pk]

    existing = db.query(
        f"MATCH (n:{table} {{{pk}: $p_pk}}) RETURN n.{pk} AS pk",
        {"p_pk": pk_val},
    )
    if existing:
        raise ValueError(
            f"{table} node {pk_val!r} already exists. "
            "Use update_node() to modify existing nodes."
        )

    col_spec, prefixed = _prefix_params(properties)
    db.execute(f"CREATE (:{table} {{{col_spec}}})", prefixed)

    return {"status": "created", "table": table, "id": pk_val}


def update_node(db: SpecDB, node_id: str, updates: dict[str, Any]) -> dict:
    """
    Update properties on an existing node.

    Uses SET n.prop = $value for each updated key.
    Cannot change the primary key.
    """
    table = find_node_table(db, node_id)
    if not table:
        raise ValueError(f"Node {node_id!r} not found in any table.")

    pk = NODE_PK[table]
    if pk in updates:
        raise ValueError(f"Cannot update primary key {pk!r} on node {node_id!r}.")

    set_clauses = ", ".join(f"n.{k} = $p_{k}" for k in updates)
    prefixed = {f"p_{k}": v for k, v in updates.items()}
    prefixed["p_id"] = node_id
    db.execute(f"MATCH (n:{table} {{id: $p_id}}) SET {set_clauses}", prefixed)

    return {"status": "updated", "table": table, "id": node_id, "updated_keys": list(updates)}


def delete_node(db: SpecDB, node_id: str) -> dict:
    """
    Delete a node and all its edges after computing the impact.

    Returns the impact list (which nodes referenced this one) before deletion.
    """
    table = find_node_table(db, node_id)
    if not table:
        raise ValueError(f"Node {node_id!r} not found.")

    # Compute impact first
    inbound = db.query(
        f"MATCH (m)-[e]->(n:{table} {{id: $p_id}}) "
        "RETURN label(e) AS rel, m.id AS source_id",
        {"p_id": node_id},
    )

    # DELETE detaches all edges automatically in Kuzu
    db.execute(f"MATCH (n:{table} {{id: $p_id}}) DETACH DELETE n", {"p_id": node_id})

    return {
        "status": "deleted",
        "table": table,
        "id": node_id,
        "impacted_inbound_edges": inbound,
    }
