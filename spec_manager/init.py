"""
Initialize a new spec directory from a preset.

Usage:
    spec-manager init                        # Uses 'generic' preset
    spec-manager init --preset spring-boot   # Uses Spring Boot preset
    spec-manager init --spec-dir ./spec      # Custom spec directory
    spec-manager init-agents                 # Copy agent files to ./agents/
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .presets import AVAILABLE_PRESETS, get_preset_dir
from .agents import AGENTS_DIR, AVAILABLE_AGENTS


def init_spec(
    spec_dir: Path,
    preset: str = "generic",
    force: bool = False,
) -> dict[str, int]:
    """
    Initialize a new spec directory from a preset.

    Args:
        spec_dir: Target directory for the spec files
        preset: Preset name (generic, spring-boot, java)
        force: If True, overwrite existing spec directory

    Returns:
        Counts of files created by type
    """
    if preset not in AVAILABLE_PRESETS:
        raise ValueError(f"Unknown preset: {preset!r}. Available: {AVAILABLE_PRESETS}")

    preset_path = get_preset_dir(preset)

    if spec_dir.exists():
        if not force:
            raise FileExistsError(
                f"Spec directory already exists: {spec_dir}\n"
                "Use --force to overwrite."
            )
        shutil.rmtree(spec_dir)

    # Copy the preset directory structure
    shutil.copytree(preset_path, spec_dir)

    # Count what was created
    counts = {
        "schema": 1,
        "nodes": len(list((spec_dir / "nodes").glob("*.json"))),
        "edges": len(list((spec_dir / "edges").glob("*.json"))),
    }

    return counts


def generate_mcp_config(spec_dir: Path, db_path: Path) -> dict:
    """
    Generate .mcp.json configuration for Claude Code.

    Args:
        spec_dir: Path to spec directory
        db_path: Path to spec.db file

    Returns:
        Dict suitable for writing to .mcp.json
    """
    return {
        "mcpServers": {
            "spec-manager": {
                "command": "python3",
                "args": [
                    "-m", "spec_manager.mcp_server",
                    "--db", str(db_path),
                    "--spec-dir", str(spec_dir),
                ],
            }
        }
    }


def generate_gitignore_entries() -> list[str]:
    """Return .gitignore entries for spec system."""
    return [
        "# Spec system (derived database)",
        "spec.db",
        "spec.db.wal",
        "spec.db.lock",
    ]


def init_agents(
    agents_dir: Path,
    force: bool = False,
) -> dict[str, int]:
    """
    Copy agent markdown files to the target directory.

    Args:
        agents_dir: Target directory for agent files
        force: If True, overwrite existing files

    Returns:
        Count of agents copied
    """
    if agents_dir.exists() and not force:
        existing = list(agents_dir.glob("*.md"))
        if existing:
            raise FileExistsError(
                f"Agents directory already has files: {agents_dir}\n"
                "Use --force to overwrite."
            )

    agents_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for agent_name in AVAILABLE_AGENTS:
        src = AGENTS_DIR / f"{agent_name}.md"
        dst = agents_dir / f"{agent_name}.md"
        if src.exists():
            shutil.copy2(src, dst)
            copied += 1

    return {"agents": copied}
