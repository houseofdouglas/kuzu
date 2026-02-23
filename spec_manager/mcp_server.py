"""
FastMCP server — exposes 7 spec-management tools to Claude agents.

Start with:
    python3 -m spec_manager.mcp_server
    python3 -m spec_manager.mcp_server --db /path/to/spec.db --spec-dir /path/to/spec

Environment variables (fallback if args not provided):
    SPEC_DB_PATH   — path to spec.db
    SPEC_DIR       — path to spec/ directory
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

from fastmcp import FastMCP

from .db import DEFAULT_DB_PATH, DEFAULT_SPEC_DIR, SpecDB
from .nodes import read_node, write_node, update_node, delete_node, list_nodes
from .edges import write_edge, delete_edge, detect_cycles, get_affected_by, list_edges
from .export import export_to_files

# ── Server singleton — instantiated at module import ─────────────────────────

mcp = FastMCP(
    "spec-manager",
    instructions=(
        "You are connected to the Kuzu spec graph for this repository. "
        "Use these tools to read and write spec nodes (Feature, Component, Interface, Requirement), "
        "manage dependency edges, detect cycles, and export the graph to spec/ files. "
        "The graph tracks software features and their dependencies. "
        "Always call detect_cycles after writing edges to DAG-intended relations."
    ),
)

# Resolved lazily so CLI args can override defaults before first tool call
_db: SpecDB | None = None


def _get_db() -> SpecDB:
    global _db
    if _db is None:
        db_path = os.environ.get("SPEC_DB_PATH", str(DEFAULT_DB_PATH))
        _db = SpecDB(db_path)
    return _db


def _get_spec_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("SPEC_DIR", str(DEFAULT_SPEC_DIR)))


# ── Tool 1: read_spec_node ────────────────────────────────────────────────────

@mcp.tool()
def read_spec_node(id: str) -> dict:
    """
    Read a spec node by ID and return its properties plus immediate graph neighbors.

    Returns:
        {
          "node": {id, name, description, status, ...},
          "outbound": [{"rel": "DependsOn", "neighbor_id": "...", "neighbor_table": "..."}],
          "inbound":  [...]
        }
        or {"error": "not found"} if the node doesn't exist.
    """
    result = read_node(_get_db(), id)
    if result is None:
        return {"error": f"Node {id!r} not found in spec graph."}
    return result


# ── Tool 2: write_spec_node ───────────────────────────────────────────────────

@mcp.tool()
def write_spec_node(table: str, properties: dict[str, Any]) -> dict:
    """
    Create a new spec node.

    Args:
        table: Node type — one of Feature, Component, Interface, Requirement
        properties: Dict of node properties. Required keys by table:
            Feature:     id, name, description, status
            Component:   id, name, description, status, layer
            Interface:   id, name, description, status
            Requirement: id, name, description, priority, status

    Returns:
        {"status": "created", "table": ..., "id": ...}
        or {"error": "..."} on validation failure.
    """
    try:
        return write_node(_get_db(), table, properties)
    except ValueError as exc:
        return {"error": str(exc)}


# ── Tool 3: write_spec_edge ───────────────────────────────────────────────────

@mcp.tool()
def write_spec_edge(
    table: str,
    from_id: str,
    to_id: str,
    props: dict[str, Any] | None = None,
) -> dict:
    """
    Add a directed edge between two spec nodes.

    For DAG-intended relations (DependsOn, Implements, DerivedFrom), the edge is
    rejected if it would create a cycle.

    Args:
        table:   Relation type — DependsOn | Implements | DerivedFrom |
                                 Conflicts | RelatedTo | Satisfies
        from_id: Source node ID
        to_id:   Target node ID
        props:   Optional edge properties (e.g. {"strength": "required"} for DependsOn)

    Returns:
        {"status": "created", ...} or {"error": "..."} if rejected.
    """
    try:
        return write_edge(_get_db(), table, from_id, to_id, props)
    except ValueError as exc:
        return {"error": str(exc)}


# ── Tool 4: query_spec ────────────────────────────────────────────────────────

@mcp.tool()
def query_spec(cypher: str) -> list[dict]:
    """
    Execute a read-only Cypher query against the spec graph.

    Use this for custom traversals, counts, or searches not covered by other tools.

    Example queries:
        MATCH (f:Feature)-[:DependsOn*1..5]->(c:Component) RETURN f.id, c.id
        MATCH (n) WHERE n.status = 'deprecated' RETURN label(n) AS type, n.id
        MATCH (f:Feature)-[:Implements]->(c:Component {id: 'storage-engine'}) RETURN f.id

    Returns:
        List of result row dicts with column names as keys.
    """
    try:
        return _get_db().query(cypher)
    except Exception as exc:
        return [{"error": str(exc)}]


# ── Tool 5: detect_cycles ─────────────────────────────────────────────────────

@mcp.tool()
def detect_cycles_tool() -> dict:
    """
    Check the spec graph for cycles in DAG-intended relationships.

    Checks DependsOn, Implements, and DerivedFrom relation types.

    Returns:
        {"cycles": [], "clean": true}  — graph is a valid DAG
        {"cycles": ["node-id-1", ...], "clean": false}  — cycle detected
    """
    cycle_ids = detect_cycles(_get_db())
    return {"cycles": cycle_ids, "clean": len(cycle_ids) == 0}


# ── Tool 6: get_affected_by ───────────────────────────────────────────────────

@mcp.tool()
def get_affected_by_tool(node_id: str, depth: int = 10) -> dict:
    """
    Find all nodes that transitively depend on node_id (via DependsOn).

    These are the nodes that would be affected if node_id were changed or removed.

    Args:
        node_id: The node whose impact you want to assess
        depth:   Maximum traversal depth (default 10, max 50)

    Returns:
        {"node_id": ..., "affected": [{"id": ..., "table": ...}], "count": N}
    """
    affected = get_affected_by(_get_db(), node_id, depth)
    return {"node_id": node_id, "affected": affected, "count": len(affected)}


# ── Tool 7: export_to_files ───────────────────────────────────────────────────

@mcp.tool()
def export_to_files_tool() -> dict:
    """
    Serialize the current spec graph to the spec/ JSON files.

    Should be called after every write operation to keep spec/ in sync with spec.db.
    Overwrites existing files with clean JSON (JSONC comments are not preserved).

    Returns:
        {"status": "exported", "counts": {"features": N, "components": N, ...}}
    """
    try:
        counts = export_to_files(_get_db(), _get_spec_dir())
        return {"status": "exported", "counts": counts}
    except Exception as exc:
        return {"error": str(exc)}


# ── Bonus tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def list_spec_nodes(table: str | None = None) -> list[dict]:
    """
    List all spec nodes, optionally filtered to a single table type.

    Args:
        table: Optional — Feature | Component | Interface | Requirement
               If omitted, returns nodes from all tables.

    Returns:
        List of node dicts, each with a synthetic "table" key.
    """
    try:
        return list_nodes(_get_db(), table)
    except ValueError as exc:
        return [{"error": str(exc)}]


@mcp.tool()
def update_spec_node(node_id: str, updates: dict[str, Any]) -> dict:
    """
    Update properties on an existing spec node.

    Cannot change the node's primary key (id). Use write_spec_node for new nodes.

    Args:
        node_id: The node to update
        updates: Dict of property key → new value

    Returns:
        {"status": "updated", ...} or {"error": "..."}.
    """
    try:
        return update_node(_get_db(), node_id, updates)
    except ValueError as exc:
        return {"error": str(exc)}


@mcp.tool()
def delete_spec_node(node_id: str) -> dict:
    """
    Delete a spec node and all its edges. Returns the impact list first.

    Args:
        node_id: The node to delete

    Returns:
        {"status": "deleted", "impacted_inbound_edges": [...]} or {"error": "..."}.
    """
    try:
        return delete_node(_get_db(), node_id)
    except ValueError as exc:
        return {"error": str(exc)}


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Spec Manager MCP server")
    parser.add_argument("--db", default=None, help="Path to spec.db")
    parser.add_argument("--spec-dir", default=None, help="Path to spec/ directory")
    args = parser.parse_args()

    if args.db:
        os.environ["SPEC_DB_PATH"] = args.db
    if args.spec_dir:
        os.environ["SPEC_DIR"] = args.spec_dir

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
