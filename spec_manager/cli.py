"""
CLI entry point for spec_manager — for use via Bash in agent workflows.

Commands:
    spec-manager rebuild              Rebuild spec.db from spec/ files
    spec-manager detect-cycles        Check for cycles (exits 1 if found)
    spec-manager export               Serialize spec.db → spec/ files
    spec-manager query <cypher>       Run a Cypher query and print results
    spec-manager node <id>            Read a node and print as JSON
    spec-manager list [<table>]       List all nodes, optionally by table
    spec-manager counts               Print node/edge counts
"""

from __future__ import annotations

import json
import sys

from .db import SpecDB, DEFAULT_DB_PATH, DEFAULT_SPEC_DIR
from .nodes import read_node, list_nodes
from .edges import detect_cycles
from .export import export_to_files


def _db() -> SpecDB:
    return SpecDB(DEFAULT_DB_PATH)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    cmd = args[0]

    if cmd == "rebuild":
        db = SpecDB.fresh(DEFAULT_DB_PATH, DEFAULT_SPEC_DIR)
        rows = db.query("MATCH (n) RETURN label(n) AS label, count(n) AS cnt")
        counts = {row["label"]: row["cnt"] for row in rows}
        print(json.dumps(counts, indent=2))

    elif cmd == "detect-cycles":
        cycles = detect_cycles(_db())
        if cycles:
            print("CYCLES DETECTED:", ", ".join(cycles), file=sys.stderr)
            sys.exit(1)
        else:
            print("OK: no cycles detected")

    elif cmd == "export":
        counts = export_to_files(_db(), DEFAULT_SPEC_DIR)
        print(json.dumps(counts, indent=2))

    elif cmd == "query":
        if len(args) < 2:
            print("Usage: spec-manager query '<cypher>'", file=sys.stderr)
            sys.exit(1)
        rows = _db().query(args[1])
        print(json.dumps(rows, indent=2, default=str))

    elif cmd == "node":
        if len(args) < 2:
            print("Usage: spec-manager node <id>", file=sys.stderr)
            sys.exit(1)
        result = read_node(_db(), args[1])
        if result is None:
            print(f"Node {args[1]!r} not found.", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "list":
        table = args[1] if len(args) > 1 else None
        rows = list_nodes(_db(), table)
        print(json.dumps(rows, indent=2, default=str))

    elif cmd == "counts":
        db = _db()
        for label in ("Component", "Feature", "Interface", "Requirement"):
            rows = db.query(f"MATCH (n:{label}) RETURN count(n) AS cnt")
            cnt = rows[0]["cnt"] if rows else 0
            print(f"  {label}: {cnt}")
        for rel in ("DependsOn", "Implements", "Satisfies", "DerivedFrom", "Conflicts", "RelatedTo"):
            rows = db.query(f"MATCH ()-[e:{rel}]->() RETURN count(e) AS cnt")
            cnt = rows[0]["cnt"] if rows else 0
            print(f"  {rel}: {cnt}")

    else:
        print(f"Unknown command: {cmd!r}", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
