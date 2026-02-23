"""
Agent definitions for spec management.

These markdown files define Claude Code agents for the spec management pipeline:
- baseline-generator: Bootstrap spec from existing codebase
- repo-explorer: Explore bounded sections of a repo
- spec-author: Translate informal descriptions to spec proposals
- feature-analyst: Query and analyze the spec graph
- spec-manager: Validate and commit spec changes
- merge-coordinator: Reconcile branch spec divergence
"""

from pathlib import Path

AGENTS_DIR = Path(__file__).parent

AVAILABLE_AGENTS = [
    "baseline-generator",
    "repo-explorer",
    "spec-author",
    "feature-analyst",
    "spec-manager",
    "merge-coordinator",
]


def get_agent_path(agent_name: str) -> Path:
    """Return the path to an agent markdown file."""
    if agent_name not in AVAILABLE_AGENTS:
        raise ValueError(f"Unknown agent: {agent_name!r}. Available: {AVAILABLE_AGENTS}")
    return AGENTS_DIR / f"{agent_name}.md"


def get_all_agent_paths() -> list[Path]:
    """Return paths to all agent markdown files."""
    return [AGENTS_DIR / f"{name}.md" for name in AVAILABLE_AGENTS]
