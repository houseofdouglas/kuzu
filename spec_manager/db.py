"""
SpecDB — core Kuzu connection, schema init, and rebuild from spec/ files.

All other spec_manager modules accept a SpecDB instance rather than managing
their own connections. This centralises the Kuzu quirks in one place:
  - JSONC comment stripping before json.loads()
  - Parameter names prefixed "p_" to avoid Cypher keyword collisions
    ($desc → $p_description, $from → $p_from, etc.)
  - get_next()/has_next() iteration (no get_as_df() — avoids numpy dep)
  - Return scalar columns with AS aliases, not raw NODE objects
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

import kuzu

from .schema import discover_schema, SchemaInfo

# ── Default paths ─────────────────────────────────────────────────────────────
# These can be overridden via environment variables or CLI arguments

def _get_default_paths() -> tuple[pathlib.Path, pathlib.Path]:
    """
    Get default paths for spec.db and spec/ directory.

    Priority:
    1. Environment variables SPEC_DB_PATH and SPEC_DIR
    2. Relative to current working directory
    """
    db_path = os.environ.get("SPEC_DB_PATH")
    spec_dir = os.environ.get("SPEC_DIR")

    if db_path:
        db_path = pathlib.Path(db_path)
    else:
        db_path = pathlib.Path.cwd() / "spec.db"

    if spec_dir:
        spec_dir = pathlib.Path(spec_dir)
    else:
        spec_dir = pathlib.Path.cwd() / "spec"

    return db_path, spec_dir


DEFAULT_DB_PATH, DEFAULT_SPEC_DIR = _get_default_paths()


def strip_comments(text: str) -> str:
    """Strip // line comments from JSONC / .cypher text."""
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    return "\n".join(lines)


def parse_statements(sql: str) -> list[str]:
    """Split a .cypher file into individual statements, ignoring comments."""
    return [s.strip() for s in strip_comments(sql).split(";") if s.strip()]


def _prefix_params(props: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    Return (col_spec, prefixed_params) where col_spec is e.g. "id: $p_id, name: $p_name"
    and prefixed_params maps "p_id" → value, etc.
    Prefixing avoids Kuzu reserved keywords like $desc, $from, $to, $status.
    """
    col_spec = ", ".join(f"{k}: $p_{k}" for k in props)
    prefixed = {f"p_{k}": v for k, v in props.items()}
    return col_spec, prefixed


class SpecDB:
    """
    Wraps a Kuzu database connection with spec-aware helpers.

    Usage:
        db = SpecDB()                    # opens spec.db at default location
        db = SpecDB("/path/to/spec.db")  # custom path
        db = SpecDB(":memory:")          # in-memory (for diff/merge)
    """

    def __init__(
        self,
        db_path: str | pathlib.Path = DEFAULT_DB_PATH,
        spec_dir: str | pathlib.Path = DEFAULT_SPEC_DIR,
        read_only: bool = False,
    ) -> None:
        self.db_path = str(db_path)
        self.spec_dir = pathlib.Path(spec_dir)
        self._db = kuzu.Database(self.db_path, read_only=read_only)
        self._conn = kuzu.Connection(self._db)
        self._schema_info: SchemaInfo | None = None

    @property
    def schema_info(self) -> SchemaInfo:
        """Lazily load and cache schema information."""
        if self._schema_info is None:
            self._schema_info = discover_schema(self.spec_dir)
        return self._schema_info

    def refresh_schema_info(self) -> SchemaInfo:
        """Force refresh of schema information."""
        self._schema_info = discover_schema(self.spec_dir)
        return self._schema_info

    # ── Raw execution ────────────────────────────────────────────────────────

    def execute(self, cypher: str, params: dict[str, Any] | None = None):
        """Execute Cypher, returning the raw Kuzu result object."""
        return self._conn.execute(cypher, params or {})

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Execute Cypher and return results as a list of column-name→value dicts."""
        result = self._conn.execute(cypher, params or {})
        cols = result.get_column_names()
        rows: list[dict] = []
        while result.has_next():
            rows.append(dict(zip(cols, result.get_next())))
        return rows

    # ── Schema management ────────────────────────────────────────────────────

    def init_schema(self, spec_dir: str | pathlib.Path | None = None) -> None:
        """Create all node and relationship tables from schema.cypher if they don't exist."""
        spec_dir = pathlib.Path(spec_dir) if spec_dir else self.spec_dir
        schema_file = spec_dir / "schema.cypher"
        for stmt in parse_statements(schema_file.read_text()):
            try:
                self._conn.execute(stmt)
            except Exception as exc:
                msg = str(exc).lower()
                if "already exist" not in msg:
                    raise

    # ── Rebuild from spec/ files ─────────────────────────────────────────────

    @classmethod
    def fresh(
        cls,
        db_path: str | pathlib.Path = DEFAULT_DB_PATH,
        spec_dir: str | pathlib.Path = DEFAULT_SPEC_DIR,
    ) -> "SpecDB":
        """
        Delete any existing database at db_path, create a fresh one, and rebuild
        from the spec/ source files. Returns the populated SpecDB instance.
        """
        db_path = pathlib.Path(db_path)
        if db_path != pathlib.Path(":memory:") and db_path.exists():
            import shutil
            if db_path.is_dir():
                shutil.rmtree(db_path)
            else:
                db_path.unlink()
            # Kuzu also creates a .wal and lock file
            for suffix in [".wal", ".lock"]:
                sib = db_path.with_suffix(suffix)
                if sib.exists():
                    sib.unlink()
        instance = cls(db_path, spec_dir)
        instance.rebuild(spec_dir)
        return instance

    def rebuild(self, spec_dir: str | pathlib.Path | None = None) -> dict[str, int]:
        """
        Rebuild the database from the spec/ JSON source files.

        For a clean rebuild from scratch, use SpecDB.fresh() instead —
        this method will fail if nodes already exist (duplicate primary key).

        Returns counts of nodes and edges loaded per type.
        """
        spec_dir = pathlib.Path(spec_dir) if spec_dir else self.spec_dir
        self.spec_dir = spec_dir
        self.init_schema(spec_dir)

        # Refresh schema info to pick up any changes
        schema = self.refresh_schema_info()

        counts: dict[str, int] = {}

        # Load nodes
        nodes_dir = spec_dir / "nodes"
        for node_file in sorted(nodes_dir.glob("*.json")):
            table = schema.node_file_to_table.get(node_file.stem)
            if not table:
                continue
            data = json.loads(strip_comments(node_file.read_text()))
            for node in data:
                col_spec, prefixed = _prefix_params(node)
                self._conn.execute(f"CREATE (:{table} {{{col_spec}}})", prefixed)
            counts[table] = len(data)

        # Build a lookup of id → node table from what we just loaded
        id_to_table: dict[str, str] = {}
        for tbl in schema.node_tables:
            try:
                rows = self._conn.execute(f"MATCH (n:{tbl}) RETURN n.id AS id")
                while rows.has_next():
                    nid = rows.get_next()[0]
                    if nid:
                        id_to_table[nid] = tbl
            except Exception:
                # Table might have different primary key (e.g. branch_id for MergeRequest)
                pass

        # Load edges
        edges_dir = spec_dir / "edges"
        for edge_file in sorted(edges_dir.glob("*.json")):
            table = schema.edge_file_to_table.get(edge_file.stem)
            if not table:
                continue
            data = json.loads(strip_comments(edge_file.read_text()))
            loaded = 0
            for edge in data:
                frm = edge["from"]
                to = edge["to"]
                frm_tbl = id_to_table.get(frm)
                to_tbl = id_to_table.get(to)
                if not frm_tbl or not to_tbl:
                    continue  # skip edges with missing endpoint nodes
                extra = {k: v for k, v in edge.items() if k not in ("from", "to")}
                params: dict[str, Any] = {"p_from": frm, "p_to": to}
                if extra:
                    prop_col, extra_prefixed = _prefix_params(extra)
                    params.update(extra_prefixed)
                    rel_props = f" {{{prop_col}}}"
                else:
                    rel_props = ""
                self._conn.execute(
                    f"MATCH (a:{frm_tbl} {{id: $p_from}}), (b:{to_tbl} {{id: $p_to}}) "
                    f"CREATE (a)-[:{table}{rel_props}]->(b)",
                    params,
                )
                loaded += 1
            counts[f"{table}(edges)"] = loaded

        return counts

    def __repr__(self) -> str:
        return f"SpecDB({self.db_path!r})"
