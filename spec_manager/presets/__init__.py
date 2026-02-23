"""
Schema presets for different project types.

Each preset provides a schema.cypher file and empty node/edge JSON files
tailored to the domain.
"""

from pathlib import Path

PRESETS_DIR = Path(__file__).parent

AVAILABLE_PRESETS = ["generic", "spring-boot", "java", "nextjs"]


def get_preset_dir(preset: str) -> Path:
    """Return the directory containing the preset's schema files."""
    if preset not in AVAILABLE_PRESETS:
        raise ValueError(f"Unknown preset: {preset!r}. Available: {AVAILABLE_PRESETS}")
    return PRESETS_DIR / preset
