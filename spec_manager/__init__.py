"""
spec_manager — Kuzu-backed spec graph for Claude agent pipelines.

Modules:
    db       — SpecDB class (connection, schema, rebuild)
    nodes    — Node CRUD with validation
    edges    — Edge CRUD with cycle detection
    export   — Serialize spec.db → spec/ JSON files
    diff     — 3-way changeset computation
    merge    — Conflict classification
    mcp_server — FastMCP server (7 tools for Claude agents)
    cli      — CLI entry point
"""

from .db import SpecDB, DEFAULT_DB_PATH, DEFAULT_SPEC_DIR
from .nodes import read_node, write_node, update_node, delete_node, list_nodes
from .edges import write_edge, detect_cycles, get_affected_by
from .export import export_to_files

__all__ = [
    "SpecDB",
    "DEFAULT_DB_PATH",
    "DEFAULT_SPEC_DIR",
    "read_node",
    "write_node",
    "update_node",
    "delete_node",
    "list_nodes",
    "write_edge",
    "detect_cycles",
    "get_affected_by",
    "export_to_files",
]
