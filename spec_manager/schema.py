"""
Schema parsing and discovery.

Parses schema.cypher to dynamically discover node and edge table names,
avoiding the need for hardcoded mappings.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple


class SchemaInfo(NamedTuple):
    """Parsed schema information."""
    node_tables: list[str]  # e.g. ["Feature", "Component", "Service"]
    edge_tables: list[str]  # e.g. ["DependsOn", "Implements"]
    node_file_to_table: dict[str, str]  # e.g. {"features": "Feature"}
    edge_file_to_table: dict[str, str]  # e.g. {"depends-on": "DependsOn"}
    table_to_node_file: dict[str, str]  # e.g. {"Feature": "features"}
    table_to_edge_file: dict[str, str]  # e.g. {"DependsOn": "depends-on"}
    node_columns: dict[str, list[str]]  # e.g. {"Feature": ["id", "name", "description", "status"]}
    edge_columns: dict[str, list[str]]  # e.g. {"DependsOn": ["strength"]}


def _table_to_filename(table_name: str) -> str:
    """
    Convert a PascalCase table name to a kebab-case plural filename.

    Examples:
        Feature -> features
        DependsOn -> depends-on
        UsesDTO -> uses-dto
        Repository -> repositories
        DTO -> dtos
        Exposes -> exposes (already plural-looking)
    """
    # Handle common acronyms - keep them together
    result = table_name
    for acronym in ["DTO", "API", "URL", "HTTP", "SQL", "ID"]:
        result = result.replace(acronym, acronym.capitalize())

    # Insert hyphens before uppercase letters (except first)
    result = re.sub(r'(?<!^)([A-Z])', r'-\1', result).lower()

    # Don't pluralize if already looks plural (ends in 's' but not 'ss')
    if result.endswith("s") and not result.endswith("ss"):
        return result

    # Pluralize (simple rules)
    if result.endswith("y") and not result.endswith(("ay", "ey", "oy", "uy")):
        result = result[:-1] + "ies"
    elif result.endswith(("x", "ch", "sh")):
        result = result + "es"
    else:
        result = result + "s"

    return result


def _filename_to_table(filename: str, tables: list[str]) -> str | None:
    """
    Find the table name that matches a given filename.

    Uses the reverse mapping to find the best match.
    """
    for table in tables:
        if _table_to_filename(table) == filename:
            return table
    return None


def _extract_columns(table_def: str) -> list[str]:
    """
    Extract column names from a table definition block.

    Example input: "id STRING, name STRING, description STRING, PRIMARY KEY (id)"
    Returns: ["id", "name", "description"]
    """
    columns = []
    # Split by comma, but be careful about nested parentheses
    parts = table_def.split(",")
    for part in parts:
        part = part.strip()
        # Skip FROM...TO declarations in REL tables
        if part.upper().startswith("FROM "):
            continue
        # Skip PRIMARY KEY declarations
        if part.upper().startswith("PRIMARY KEY"):
            continue
        # Extract column name (first word before type)
        match = re.match(r"(\w+)\s+\w+", part)
        if match:
            columns.append(match.group(1))
    return columns


def parse_schema(schema_path: Path) -> SchemaInfo:
    """
    Parse schema.cypher and extract node and edge table information.

    Args:
        schema_path: Path to schema.cypher file

    Returns:
        SchemaInfo with all discovered tables and mappings
    """
    text = schema_path.read_text()

    # Strip comments
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    text = "\n".join(lines)

    # Find node tables with their definitions
    node_pattern = r"CREATE\s+NODE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\(([^;]+)\)"
    node_matches = re.findall(node_pattern, text, re.IGNORECASE | re.DOTALL)
    node_tables = [m[0] for m in node_matches]
    node_columns = {m[0]: _extract_columns(m[1]) for m in node_matches}

    # Find edge tables with their definitions
    edge_pattern = r"CREATE\s+REL\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\(([^;]+)\)"
    edge_matches = re.findall(edge_pattern, text, re.IGNORECASE | re.DOTALL)
    edge_tables = [m[0] for m in edge_matches]
    edge_columns = {m[0]: _extract_columns(m[1]) for m in edge_matches}

    # Build mappings
    node_file_to_table = {}
    table_to_node_file = {}
    for table in node_tables:
        filename = _table_to_filename(table)
        node_file_to_table[filename] = table
        table_to_node_file[table] = filename

    edge_file_to_table = {}
    table_to_edge_file = {}
    for table in edge_tables:
        filename = _table_to_filename(table)
        edge_file_to_table[filename] = table
        table_to_edge_file[table] = filename

    return SchemaInfo(
        node_tables=node_tables,
        edge_tables=edge_tables,
        node_file_to_table=node_file_to_table,
        edge_file_to_table=edge_file_to_table,
        table_to_node_file=table_to_node_file,
        table_to_edge_file=table_to_edge_file,
        node_columns=node_columns,
        edge_columns=edge_columns,
    )


def discover_schema(spec_dir: Path) -> SchemaInfo:
    """
    Discover schema from a spec directory.

    If schema.cypher exists, parse it. Otherwise, infer from JSON files.
    """
    schema_path = spec_dir / "schema.cypher"

    if schema_path.exists():
        return parse_schema(schema_path)

    # Fallback: infer from existing JSON files
    import json

    node_tables = []
    edge_tables = []
    node_file_to_table = {}
    edge_file_to_table = {}
    node_columns: dict[str, list[str]] = {}
    edge_columns: dict[str, list[str]] = {}

    nodes_dir = spec_dir / "nodes"
    if nodes_dir.exists():
        for f in nodes_dir.glob("*.json"):
            # Best-effort: convert filename to PascalCase table name
            table = "".join(word.title() for word in f.stem.replace("-", " ").split())
            # Handle plurals
            if table.endswith("ies"):
                table = table[:-3] + "y"
            elif table.endswith("es") and not table.endswith("ces"):
                table = table[:-2]
            elif table.endswith("s"):
                table = table[:-1]
            node_tables.append(table)
            node_file_to_table[f.stem] = table

            # Infer columns from JSON content
            try:
                content = f.read_text()
                # Strip comments
                lines = [ln for ln in content.splitlines() if not ln.strip().startswith("//")]
                data = json.loads("\n".join(lines))
                if data and isinstance(data, list) and data[0]:
                    node_columns[table] = list(data[0].keys())
                else:
                    node_columns[table] = ["id", "name"]
            except Exception:
                node_columns[table] = ["id", "name"]

    edges_dir = spec_dir / "edges"
    if edges_dir.exists():
        for f in edges_dir.glob("*.json"):
            table = "".join(word.title() for word in f.stem.replace("-", " ").split())
            if table.endswith("s") and not table.endswith("ss"):
                table = table[:-1]
            edge_tables.append(table)
            edge_file_to_table[f.stem] = table

            # Infer extra columns from JSON content (excluding from/to)
            try:
                content = f.read_text()
                lines = [ln for ln in content.splitlines() if not ln.strip().startswith("//")]
                data = json.loads("\n".join(lines))
                if data and isinstance(data, list) and data[0]:
                    extra = [k for k in data[0].keys() if k not in ("from", "to")]
                    edge_columns[table] = extra
                else:
                    edge_columns[table] = []
            except Exception:
                edge_columns[table] = []

    table_to_node_file = {v: k for k, v in node_file_to_table.items()}
    table_to_edge_file = {v: k for k, v in edge_file_to_table.items()}

    return SchemaInfo(
        node_tables=node_tables,
        edge_tables=edge_tables,
        node_file_to_table=node_file_to_table,
        edge_file_to_table=edge_file_to_table,
        table_to_node_file=table_to_node_file,
        table_to_edge_file=table_to_edge_file,
        node_columns=node_columns,
        edge_columns=edge_columns,
    )
