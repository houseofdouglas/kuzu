"""
CLI entry point for spec_manager.

Commands:
    spec-manager init [--preset NAME] [--spec-dir PATH] [--force]
                                      Initialize a new spec directory
    spec-manager rebuild              Rebuild spec.db from spec/ files
    spec-manager detect-cycles        Check for cycles (exits 1 if found)
    spec-manager export               Serialize spec.db → spec/ files
    spec-manager query <cypher>       Run a Cypher query and print results
    spec-manager node <id>            Read a node and print as JSON
    spec-manager list [<table>]       List all nodes, optionally by table
    spec-manager counts               Print node/edge counts
    spec-manager schema               Show discovered schema info

Global options:
    --db PATH                         Path to spec.db (default: ./spec.db)
    --spec-dir PATH                   Path to spec/ directory (default: ./spec)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .db import SpecDB
from .nodes import read_node, list_nodes
from .edges import detect_cycles
from .export import export_to_files
from .init import init_spec, generate_mcp_config, generate_gitignore_entries
from .presets import AVAILABLE_PRESETS
from .schema import discover_schema


def _get_db(args: argparse.Namespace) -> SpecDB:
    """Create SpecDB from parsed arguments."""
    return SpecDB(args.db, args.spec_dir)


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new spec directory."""
    spec_dir = Path(args.spec_dir)

    try:
        counts = init_spec(spec_dir, preset=args.preset, force=args.force)
    except FileExistsError as e:
        print(str(e), file=sys.stderr)
        return 1
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"Initialized spec directory: {spec_dir}")
    print(f"  Preset: {args.preset}")
    print(f"  Schema: 1 file")
    print(f"  Node types: {counts['nodes']} files")
    print(f"  Edge types: {counts['edges']} files")
    print()

    # Show next steps
    print("Next steps:")
    print(f"  1. Review/customize: {spec_dir}/schema.cypher")
    print(f"  2. Build database:   spec-manager rebuild --spec-dir {spec_dir}")
    print(f"  3. Add to .gitignore:")
    for entry in generate_gitignore_entries():
        print(f"       {entry}")
    print()

    # Show MCP config
    if args.show_mcp:
        db_path = Path(args.db)
        config = generate_mcp_config(spec_dir, db_path)
        print("MCP configuration (.mcp.json):")
        print(json.dumps(config, indent=2))

    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    """Rebuild spec.db from spec/ files."""
    db = SpecDB.fresh(args.db, args.spec_dir)
    rows = db.query("MATCH (n) RETURN label(n) AS label, count(n) AS cnt")
    counts = {row["label"]: row["cnt"] for row in rows}
    print(json.dumps(counts, indent=2))
    return 0


def cmd_detect_cycles(args: argparse.Namespace) -> int:
    """Check for cycles in DAG relations."""
    cycles = detect_cycles(_get_db(args))
    if cycles:
        print("CYCLES DETECTED:", ", ".join(cycles), file=sys.stderr)
        return 1
    else:
        print("OK: no cycles detected")
        return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export spec.db to spec/ JSON files."""
    counts = export_to_files(_get_db(args), args.spec_dir)
    print(json.dumps(counts, indent=2))
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Run a Cypher query."""
    rows = _get_db(args).query(args.cypher)
    print(json.dumps(rows, indent=2, default=str))
    return 0


def cmd_node(args: argparse.Namespace) -> int:
    """Read a specific node."""
    result = read_node(_get_db(args), args.id)
    if result is None:
        print(f"Node {args.id!r} not found.", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all nodes."""
    rows = list_nodes(_get_db(args), args.table)
    print(json.dumps(rows, indent=2, default=str))
    return 0


def cmd_counts(args: argparse.Namespace) -> int:
    """Print node/edge counts."""
    db = _get_db(args)
    schema = db.schema_info

    print("Nodes:")
    for label in schema.node_tables:
        try:
            rows = db.query(f"MATCH (n:{label}) RETURN count(n) AS cnt")
            cnt = rows[0]["cnt"] if rows else 0
            print(f"  {label}: {cnt}")
        except Exception:
            print(f"  {label}: (error)")

    print("Edges:")
    for rel in schema.edge_tables:
        try:
            rows = db.query(f"MATCH ()-[e:{rel}]->() RETURN count(e) AS cnt")
            cnt = rows[0]["cnt"] if rows else 0
            print(f"  {rel}: {cnt}")
        except Exception:
            print(f"  {rel}: (error)")

    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    """Show discovered schema information."""
    spec_dir = Path(args.spec_dir)
    schema = discover_schema(spec_dir)

    print(f"Schema discovered from: {spec_dir}")
    print()
    print("Node tables:")
    for table in schema.node_tables:
        filename = schema.table_to_node_file.get(table, "?")
        print(f"  {table} -> nodes/{filename}.json")

    print()
    print("Edge tables:")
    for table in schema.edge_tables:
        filename = schema.table_to_edge_file.get(table, "?")
        print(f"  {table} -> edges/{filename}.json")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="spec-manager",
        description="Kuzu-backed spec graph management for Claude agents",
    )

    # Global options
    parser.add_argument(
        "--db",
        default="./spec.db",
        help="Path to spec.db (default: ./spec.db)",
    )
    parser.add_argument(
        "--spec-dir",
        default="./spec",
        help="Path to spec/ directory (default: ./spec)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new spec directory")
    p_init.add_argument(
        "--preset",
        choices=AVAILABLE_PRESETS,
        default="generic",
        help=f"Schema preset to use (default: generic). Available: {', '.join(AVAILABLE_PRESETS)}",
    )
    p_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing spec directory",
    )
    p_init.add_argument(
        "--show-mcp",
        action="store_true",
        help="Show MCP configuration for Claude Code",
    )
    p_init.set_defaults(func=cmd_init)

    # rebuild
    p_rebuild = subparsers.add_parser("rebuild", help="Rebuild spec.db from spec/ files")
    p_rebuild.set_defaults(func=cmd_rebuild)

    # detect-cycles
    p_cycles = subparsers.add_parser("detect-cycles", help="Check for cycles (exits 1 if found)")
    p_cycles.set_defaults(func=cmd_detect_cycles)

    # export
    p_export = subparsers.add_parser("export", help="Serialize spec.db → spec/ files")
    p_export.set_defaults(func=cmd_export)

    # query
    p_query = subparsers.add_parser("query", help="Run a Cypher query")
    p_query.add_argument("cypher", help="Cypher query to execute")
    p_query.set_defaults(func=cmd_query)

    # node
    p_node = subparsers.add_parser("node", help="Read a node and print as JSON")
    p_node.add_argument("id", help="Node ID to read")
    p_node.set_defaults(func=cmd_node)

    # list
    p_list = subparsers.add_parser("list", help="List all nodes")
    p_list.add_argument("table", nargs="?", help="Optional: filter by table name")
    p_list.set_defaults(func=cmd_list)

    # counts
    p_counts = subparsers.add_parser("counts", help="Print node/edge counts")
    p_counts.set_defaults(func=cmd_counts)

    # schema
    p_schema = subparsers.add_parser("schema", help="Show discovered schema info")
    p_schema.set_defaults(func=cmd_schema)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
