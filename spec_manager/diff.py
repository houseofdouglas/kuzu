"""
3-way changeset computation for merge-coordinator.

Loads spec states at specific git refs into in-memory Kuzu instances,
then computes what changed between two states (ancestor → branch, ancestor → main).
"""

from __future__ import annotations

import subprocess
import tempfile
import pathlib
from dataclasses import dataclass, field
from typing import Any

from .db import SpecDB, DEFAULT_SPEC_DIR, strip_comments, parse_statements
from .nodes import NODE_COLUMNS
from .export import EDGE_EXTRA_PROPS

import json


@dataclass
class Changeset:
    """Represents all changes from one spec state to another."""
    added_nodes:    list[dict] = field(default_factory=list)  # {table, id, properties}
    modified_nodes: list[dict] = field(default_factory=list)  # {table, id, before, after}
    deleted_nodes:  list[dict] = field(default_factory=list)  # {table, id}
    added_edges:    list[dict] = field(default_factory=list)  # {table, from_id, to_id, props}
    deleted_edges:  list[dict] = field(default_factory=list)  # {table, from_id, to_id}

    def is_empty(self) -> bool:
        return not any([
            self.added_nodes, self.modified_nodes, self.deleted_nodes,
            self.added_edges, self.deleted_edges,
        ])

    def summary(self) -> str:
        parts = []
        if self.added_nodes:    parts.append(f"+{len(self.added_nodes)} nodes")
        if self.modified_nodes: parts.append(f"~{len(self.modified_nodes)} nodes")
        if self.deleted_nodes:  parts.append(f"-{len(self.deleted_nodes)} nodes")
        if self.added_edges:    parts.append(f"+{len(self.added_edges)} edges")
        if self.deleted_edges:  parts.append(f"-{len(self.deleted_edges)} edges")
        return ", ".join(parts) if parts else "no changes"


def _git_show(git_ref: str, rel_path: str, repo_root: pathlib.Path) -> str | None:
    """Return file content at git_ref, or None if the file didn't exist at that ref."""
    try:
        result = subprocess.run(
            ["git", "show", f"{git_ref}:{rel_path}"],
            capture_output=True, text=True, cwd=repo_root, check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def load_at_ref(
    git_ref: str,
    spec_dir: str | pathlib.Path = DEFAULT_SPEC_DIR,
    repo_root: str | pathlib.Path | None = None,
) -> SpecDB:
    """
    Load the spec at a given git ref into a temporary in-memory Kuzu instance.

    spec_dir is the path relative to the repo root (e.g. "spec").
    """
    spec_dir = pathlib.Path(spec_dir)
    if repo_root is None:
        # Walk up from spec_dir to find the git root
        repo_root = pathlib.Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, cwd=spec_dir, check=True,
            ).stdout.strip()
        )
    repo_root = pathlib.Path(repo_root)

    db = SpecDB(":memory:")

    # Load schema at ref
    schema_rel = str(spec_dir.relative_to(repo_root) / "schema.cypher")
    schema_text = _git_show(git_ref, schema_rel, repo_root)
    if schema_text:
        for stmt in parse_statements(schema_text):
            try:
                db.execute(stmt)
            except Exception as exc:
                if "already exist" not in str(exc).lower():
                    raise

    # Load nodes
    from .db import NODE_FILE_TO_TABLE, EDGE_FILE_TO_TABLE
    nodes_rel_base = str(spec_dir.relative_to(repo_root) / "nodes")
    for stem, table in NODE_FILE_TO_TABLE.items():
        content = _git_show(git_ref, f"{nodes_rel_base}/{stem}.json", repo_root)
        if not content:
            continue
        nodes = json.loads(strip_comments(content))
        from .db import _prefix_params
        for node in nodes:
            col_spec, prefixed = _prefix_params(node)
            try:
                db.execute(f"CREATE (:{table} {{{col_spec}}})", prefixed)
            except Exception:
                pass

    # Load edges
    edges_rel_base = str(spec_dir.relative_to(repo_root) / "edges")
    for stem, table in EDGE_FILE_TO_TABLE.items():
        content = _git_show(git_ref, f"{edges_rel_base}/{stem}.json", repo_root)
        if not content:
            continue
        edges = json.loads(strip_comments(content))
        for edge in edges:
            frm = edge["from"]
            to = edge["to"]
            extra = {k: v for k, v in edge.items() if k not in ("from", "to")}
            params: dict[str, Any] = {"p_from": frm, "p_to": to}
            rel_props = ""
            if extra:
                prop_spec, ep = _prefix_params(extra)
                params.update(ep)
                rel_props = f" {{{prop_spec}}}"
            try:
                db.execute(
                    f"MATCH (a {{id: $p_from}}), (b {{id: $p_to}}) "
                    f"CREATE (a)-[:{table}{rel_props}]->(b)",
                    params,
                )
            except Exception:
                pass

    return db


def _snapshot_nodes(db: SpecDB) -> dict[str, dict]:
    """
    Return {node_id: {table, properties}} for all nodes in the database.
    """
    snapshot: dict[str, dict] = {}
    for table, cols in NODE_COLUMNS.items():
        select = ", ".join(f"n.{c} AS {c}" for c in cols)
        try:
            rows = db.query(f"MATCH (n:{table}) RETURN {select}")
        except Exception:
            continue
        pk = "branch_id" if table == "MergeRequest" else "id"
        for row in rows:
            node_id = row.get(pk, row.get("id"))
            if node_id:
                snapshot[node_id] = {"table": table, "properties": row}
    return snapshot


def _snapshot_edges(db: SpecDB) -> dict[tuple, dict]:
    """
    Return {(table, from_id, to_id): extra_props} for all edges.
    """
    from .db import EDGE_FILE_TO_TABLE
    snapshot: dict[tuple, dict] = {}
    for table in EDGE_FILE_TO_TABLE.values():
        extra = EDGE_EXTRA_PROPS.get(table, [])
        extra_sel = (", " + ", ".join(f"e.{p} AS {p}" for p in extra)) if extra else ""
        try:
            rows = db.query(
                f"MATCH (a)-[e:{table}]->(b) "
                f"RETURN a.id AS from_id, b.id AS to_id{extra_sel}"
            )
        except Exception:
            continue
        for row in rows:
            key = (table, row["from_id"], row["to_id"])
            snapshot[key] = {k: v for k, v in row.items() if k not in ("from_id", "to_id")}
    return snapshot


def compute_delta(ancestor: SpecDB, branch: SpecDB) -> Changeset:
    """
    Compute what changed from ancestor to branch.

    Returns a Changeset describing added/modified/deleted nodes and edges.
    """
    anc_nodes = _snapshot_nodes(ancestor)
    br_nodes  = _snapshot_nodes(branch)
    anc_edges = _snapshot_edges(ancestor)
    br_edges  = _snapshot_edges(branch)

    cs = Changeset()

    # Nodes added
    for nid, info in br_nodes.items():
        if nid not in anc_nodes:
            cs.added_nodes.append({"table": info["table"], "id": nid, "properties": info["properties"]})

    # Nodes modified or deleted
    for nid, anc_info in anc_nodes.items():
        if nid not in br_nodes:
            cs.deleted_nodes.append({"table": anc_info["table"], "id": nid})
        else:
            br_info = br_nodes[nid]
            if anc_info["properties"] != br_info["properties"]:
                cs.modified_nodes.append({
                    "table": anc_info["table"],
                    "id": nid,
                    "before": anc_info["properties"],
                    "after": br_info["properties"],
                })

    # Edges added / deleted
    for key, props in br_edges.items():
        if key not in anc_edges:
            table, from_id, to_id = key
            cs.added_edges.append({"table": table, "from_id": from_id, "to_id": to_id, "properties": props})

    for key in anc_edges:
        if key not in br_edges:
            table, from_id, to_id = key
            cs.deleted_edges.append({"table": table, "from_id": from_id, "to_id": to_id})

    return cs
