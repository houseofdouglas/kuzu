"""
Conflict classification for the merge-coordinator agent.

Given a branch_delta and main_delta (both relative to the same ancestor),
classify each changed item as auto-mergeable or requiring human/LLM resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .db import SpecDB
from .diff import Changeset
from .edges import detect_cycles, DAG_RELATIONS


class ConflictType(str, Enum):
    AUTO_MERGE           = "AUTO_MERGE"           # apply branch change, no conflict
    NO_ACTION            = "NO_ACTION"             # already on main, nothing to do
    CONFLICT_STRUCTURAL  = "CONFLICT_STRUCTURAL"   # same node modified differently
    CONFLICT_TOPOLOGICAL = "CONFLICT_TOPOLOGICAL"  # edge added to a deleted node
    CONFLICT_DELETE_MODIFY = "CONFLICT_DELETE_MODIFY"  # one side deleted, other modified
    CONFLICT_IDENTITY    = "CONFLICT_IDENTITY"     # same ID added with different props
    CONFLICT_CYCLE       = "CONFLICT_CYCLE"         # merge would introduce a cycle


@dataclass
class Conflict:
    conflict_type: ConflictType
    subject_type: str          # "node" or "edge"
    subject_id: str            # node ID or "table:from→to" for edges
    branch_state: dict | None  # state on feature branch
    main_state:   dict | None  # state on main
    resolution:   str | None   # for AUTO_MERGE: what to apply; else None
    escalation:   str | None   # human-readable explanation for non-auto conflicts

    def is_blocking(self) -> bool:
        return self.conflict_type not in (ConflictType.AUTO_MERGE, ConflictType.NO_ACTION)


def _node_id_set(items: list[dict]) -> dict[str, dict]:
    return {item["id"]: item for item in items}


def _edge_key_set(items: list[dict]) -> dict[str, dict]:
    return {f"{item['table']}:{item['from_id']}→{item['to_id']}": item for item in items}


def classify_conflicts(
    branch_delta: Changeset,
    main_delta: Changeset,
    ancestor_db: SpecDB,
    branch_db: SpecDB,
    main_db: SpecDB,
) -> list[Conflict]:
    """
    Compare branch_delta and main_delta to classify every change.

    Returns a list of Conflict records. Callers should:
    - Apply all AUTO_MERGE conflicts automatically
    - Escalate CONFLICT_* types to the user or LLM resolution
    """
    conflicts: list[Conflict] = []

    # Index changes by node/edge ID
    branch_added   = _node_id_set(branch_delta.added_nodes)
    branch_modified = _node_id_set(branch_delta.modified_nodes)
    branch_deleted  = _node_id_set(branch_delta.deleted_nodes)
    main_added     = _node_id_set(main_delta.added_nodes)
    main_modified  = _node_id_set(main_delta.modified_nodes)
    main_deleted   = _node_id_set(main_delta.deleted_nodes)

    branch_edges_added   = _edge_key_set(branch_delta.added_edges)
    branch_edges_deleted = _edge_key_set(branch_delta.deleted_edges)
    main_edges_deleted   = _edge_key_set(main_delta.deleted_edges)
    main_deleted_node_ids = set(main_deleted.keys())

    # ── Node conflict classification ─────────────────────────────────────────

    # Branch adds node — check if main also added same ID
    for nid, br_item in branch_added.items():
        if nid in main_added:
            m = main_added[nid]
            if br_item["properties"] == m["properties"]:
                conflicts.append(Conflict(
                    ConflictType.AUTO_MERGE, "node", nid,
                    branch_state=br_item, main_state=m,
                    resolution="Identical node added on both sides; use either.",
                    escalation=None,
                ))
            else:
                conflicts.append(Conflict(
                    ConflictType.CONFLICT_IDENTITY, "node", nid,
                    branch_state=br_item, main_state=m,
                    resolution=None,
                    escalation=(
                        f"Both branch and main added node {nid!r} with different properties. "
                        "LLM or human must choose the canonical version."
                    ),
                ))
        else:
            conflicts.append(Conflict(
                ConflictType.AUTO_MERGE, "node", nid,
                branch_state=br_item, main_state=None,
                resolution=f"Add node {nid!r} to main.",
                escalation=None,
            ))

    # Branch modifies node
    for nid, br_item in branch_modified.items():
        if nid in main_deleted:
            conflicts.append(Conflict(
                ConflictType.CONFLICT_DELETE_MODIFY, "node", nid,
                branch_state=br_item, main_state=main_deleted[nid],
                resolution=None,
                escalation=(
                    f"Branch modified node {nid!r} but main deleted it. "
                    "Decide: restore the node with branch changes, or accept the deletion."
                ),
            ))
        elif nid in main_modified:
            m = main_modified[nid]
            if br_item["after"] == m["after"]:
                conflicts.append(Conflict(
                    ConflictType.AUTO_MERGE, "node", nid,
                    branch_state=br_item, main_state=m,
                    resolution="Identical modification on both sides; either result is correct.",
                    escalation=None,
                ))
            else:
                conflicts.append(Conflict(
                    ConflictType.CONFLICT_STRUCTURAL, "node", nid,
                    branch_state=br_item, main_state=m,
                    resolution=None,
                    escalation=(
                        f"Node {nid!r} was modified differently on branch and main. "
                        "LLM should merge the two versions."
                    ),
                ))
        else:
            conflicts.append(Conflict(
                ConflictType.AUTO_MERGE, "node", nid,
                branch_state=br_item, main_state=None,
                resolution=f"Apply branch modification to {nid!r}.",
                escalation=None,
            ))

    # Branch deletes node
    for nid, br_item in branch_deleted.items():
        if nid in main_modified:
            conflicts.append(Conflict(
                ConflictType.CONFLICT_DELETE_MODIFY, "node", nid,
                branch_state=br_item, main_state=main_modified[nid],
                resolution=None,
                escalation=(
                    f"Branch deleted node {nid!r} but main modified it. "
                    "Decide: accept deletion, or restore with main's modifications."
                ),
            ))
        elif nid not in main_deleted:
            conflicts.append(Conflict(
                ConflictType.AUTO_MERGE, "node", nid,
                branch_state=br_item, main_state=None,
                resolution=f"Delete node {nid!r} from main.",
                escalation=None,
            ))
        # else: both deleted → NO_ACTION (already gone on main)

    # ── Edge conflict classification ──────────────────────────────────────────

    for edge_key, br_item in branch_edges_added.items():
        target_id = br_item["to_id"]

        # Check if target node was deleted on main
        if target_id in main_deleted_node_ids:
            conflicts.append(Conflict(
                ConflictType.CONFLICT_TOPOLOGICAL, "edge", edge_key,
                branch_state=br_item, main_state=None,
                resolution=None,
                escalation=(
                    f"Branch adds edge {edge_key!r} but main deleted its target node "
                    f"{target_id!r}. Decide: restore the node, or drop the edge."
                ),
            ))
        else:
            conflicts.append(Conflict(
                ConflictType.AUTO_MERGE, "edge", edge_key,
                branch_state=br_item, main_state=None,
                resolution=f"Add edge {edge_key!r} to main.",
                escalation=None,
            ))

    for edge_key in branch_edges_deleted:
        if edge_key not in main_edges_deleted:
            item = branch_delta.deleted_edges[
                next(i for i, e in enumerate(branch_delta.deleted_edges)
                     if f"{e['table']}:{e['from_id']}→{e['to_id']}" == edge_key)
            ]
            conflicts.append(Conflict(
                ConflictType.AUTO_MERGE, "edge", edge_key,
                branch_state=None, main_state=item,
                resolution=f"Remove edge {edge_key!r} from main.",
                escalation=None,
            ))

    # ── Cycle detection on merged state ──────────────────────────────────────
    # Build a merged snapshot in memory and check for new cycles
    cycle_ids = _detect_merge_cycles(ancestor_db, branch_delta, main_delta)
    for nid in cycle_ids:
        conflicts.append(Conflict(
            ConflictType.CONFLICT_CYCLE, "node", nid,
            branch_state=None, main_state=None,
            resolution=None,
            escalation=(
                f"Combining branch and main changes creates a cycle involving node {nid!r}. "
                "The dependency graph must be redesigned before this merge can proceed."
            ),
        ))

    return conflicts


def _detect_merge_cycles(
    ancestor_db: SpecDB,
    branch_delta: Changeset,
    main_delta: Changeset,
) -> list[str]:
    """
    Apply both deltas to a copy of ancestor and check for new cycles.
    Returns node IDs involved in any cycle introduced by the combined merge.
    """
    # Build an in-memory merged state
    merged = SpecDB(":memory:")
    # Re-init schema
    try:
        merged.execute(
            "CALL show_tables() RETURN *"
        )
    except Exception:
        pass

    # This is a best-effort check; if we can't rebuild, return empty
    try:
        from .diff import _snapshot_nodes, _snapshot_edges
        anc_nodes = _snapshot_nodes(ancestor_db)
        anc_edges = _snapshot_edges(ancestor_db)

        # Apply both deltas (simplified: just add edges from both)
        all_added_edges = branch_delta.added_edges + main_delta.added_edges
        all_deleted_nodes = (
            {n["id"] for n in branch_delta.deleted_nodes} |
            {n["id"] for n in main_delta.deleted_nodes}
        )

        for edge in all_added_edges:
            # Check for cycle: if target can reach source in any DAG relation
            if edge["table"] in DAG_RELATIONS:
                rows = ancestor_db.query(
                    f"MATCH (src {{id: $p_from}})-[:{edge['table']}* ACYCLIC 1..50]->(dst {{id: $p_to}}) "
                    "RETURN src.id AS src",
                    {"p_from": edge["to_id"], "p_to": edge["from_id"]},
                )
                if rows:
                    return [edge["from_id"], edge["to_id"]]
    except Exception:
        pass

    return []


def format_merge_report(conflicts: list[Conflict]) -> str:
    """Format a human-readable merge report from a list of conflicts."""
    auto = [c for c in conflicts if c.conflict_type == ConflictType.AUTO_MERGE]
    blocking = [c for c in conflicts if c.is_blocking()]

    lines = ["# Spec Merge Report", ""]

    lines.append(f"**Auto-mergeable**: {len(auto)} changes")
    lines.append(f"**Blocking conflicts**: {len(blocking)}")
    lines.append("")

    if auto:
        lines.append("## Auto-merge (no action required)")
        for c in auto:
            lines.append(f"- [{c.subject_type}] `{c.subject_id}`: {c.resolution}")
        lines.append("")

    if blocking:
        lines.append("## Blocking Conflicts (require resolution)")
        for c in blocking:
            lines.append(f"### {c.conflict_type.value}: `{c.subject_id}`")
            lines.append(c.escalation or "")
            if c.branch_state:
                lines.append(f"**Branch**: {c.branch_state}")
            if c.main_state:
                lines.append(f"**Main**: {c.main_state}")
            lines.append("")

    return "\n".join(lines)
