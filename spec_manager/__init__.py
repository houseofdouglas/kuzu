"""
spec_manager — Kuzu-backed spec graph for Claude agent pipelines.

Modules:
    db         — SpecDB class (connection, schema, rebuild)
    schema     — Schema parsing and discovery
    nodes      — Node CRUD with validation
    edges      — Edge CRUD with cycle detection
    export     — Serialize spec.db → spec/ JSON files
    diff       — 3-way changeset computation
    merge      — Conflict classification
    init       — Initialize new spec directories from presets
    mcp_server — FastMCP server (tools for Claude agents)
    cli        — CLI entry point
"""

from .db import SpecDB, DEFAULT_DB_PATH, DEFAULT_SPEC_DIR
from .schema import SchemaInfo, discover_schema, parse_schema
from .nodes import read_node, write_node, update_node, delete_node, list_nodes
from .edges import write_edge, detect_cycles, get_affected_by
from .export import export_to_files
from .init import init_spec, generate_mcp_config, generate_gitignore_entries
from .presets import AVAILABLE_PRESETS

__all__ = [
    # Core
    "SpecDB",
    "DEFAULT_DB_PATH",
    "DEFAULT_SPEC_DIR",
    # Schema
    "SchemaInfo",
    "discover_schema",
    "parse_schema",
    # Nodes
    "read_node",
    "write_node",
    "update_node",
    "delete_node",
    "list_nodes",
    # Edges
    "write_edge",
    "detect_cycles",
    "get_affected_by",
    # Export
    "export_to_files",
    # Init
    "init_spec",
    "generate_mcp_config",
    "generate_gitignore_entries",
    "AVAILABLE_PRESETS",
]
