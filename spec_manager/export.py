"""
Export spec.db → spec/ JSON files.

Writes clean JSON (no JSONC comments). The spec.db is the source of truth in
the MCP workflow; the spec/ files are its serialized form for git versioning.
"""

from __future__ import annotations

import json
import pathlib

from .db import (
    SpecDB,
    DEFAULT_SPEC_DIR,
    TABLE_TO_NODE_FILE,
    TABLE_TO_EDGE_FILE,
)
from .nodes import NODE_COLUMNS

# Properties to export per relation table (all have at least from/to)
EDGE_EXTRA_PROPS: dict[str, list[str]] = {
    "DependsOn":   ["strength"],
    "Implements":  [],
    "DerivedFrom": [],
    "Conflicts":   ["reason"],
    "RelatedTo":   [],
    "Satisfies":   [],
}


def export_to_files(
    db: SpecDB,
    spec_dir: str | pathlib.Path = DEFAULT_SPEC_DIR,
) -> dict[str, int]:
    """
    Serialize the full spec graph from spec.db into spec/ JSON files.

    Overwrites existing files with clean JSON (JSONC comments are not preserved
    — they are a human authoring convenience from before the MCP workflow).

    Returns counts of nodes and edges written per file.
    """
    spec_dir = pathlib.Path(spec_dir)
    nodes_dir = spec_dir / "nodes"
    edges_dir = spec_dir / "edges"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    edges_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}

    # ── Export nodes ─────────────────────────────────────────────────────────
    for table, filename in TABLE_TO_NODE_FILE.items():
        cols = NODE_COLUMNS.get(table, ["id", "name"])
        select = ", ".join(f"n.{c} AS {c}" for c in cols)
        try:
            rows = db.query(f"MATCH (n:{table}) RETURN {select} ORDER BY n.id")
        except Exception:
            rows = []

        out_path = nodes_dir / f"{filename}.json"
        out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
        counts[filename] = len(rows)

    # ── Export edges ─────────────────────────────────────────────────────────
    for table, filename in TABLE_TO_EDGE_FILE.items():
        extra = EDGE_EXTRA_PROPS.get(table, [])
        extra_select = (", " + ", ".join(f"e.{p} AS {p}" for p in extra)) if extra else ""
        try:
            rows = db.query(
                f"MATCH (a)-[e:{table}]->(b) "
                f"RETURN a.id AS `from`, b.id AS `to`{extra_select} "
                "ORDER BY a.id, b.id"
            )
        except Exception:
            rows = []

        # Rename backtick-quoted keys to plain "from"/"to"
        clean_rows = []
        for row in rows:
            entry: dict = {}
            for k, v in row.items():
                plain_k = k.strip("`")
                if v is not None:
                    entry[plain_k] = v
            # Ensure from/to come first
            ordered: dict = {}
            if "from" in entry:
                ordered["from"] = entry.pop("from")
            if "to" in entry:
                ordered["to"] = entry.pop("to")
            ordered.update(entry)
            clean_rows.append(ordered)

        out_path = edges_dir / f"{filename}.json"
        out_path.write_text(json.dumps(clean_rows, indent=2, ensure_ascii=False) + "\n")
        counts[filename] = len(clean_rows)

    return counts
