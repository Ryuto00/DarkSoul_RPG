# src/core/constants.py
"""
Global constants for the game, including tile definitions and coordinate system rules.

Coordinate System:
- Origin: Top-left corner of the screen/level.
- X-axis: Increases from left to right (0 to W-1).
- Y-axis: Increases from top to bottom (0 to H-1).
"""
from ..tiles.tile_types import TileType

# === Tile Character Definitions ===
# The canonical mapping of ASCII characters to tile types.
# The level parser will use this as the source of truth.
# NOTE: In legacy maps (like the currently hardcoded rooms), '.' is used for AIR.
# The parser will be updated to handle this distinction.

TILE_CHAR_MAP = {
    '#': TileType.WALL,
    '.': TileType.AIR,  # Corrected: '.' now represents AIR
    ' ': TileType.AIR,
}

# Legacy character aliases. The parser should handle these.
# For example, '=' should be treated as ' '.
LEGACY_CHAR_ALIASES = {
    '=': ' ',
}

# === Entity Character Definitions ===
# These characters represent entities, not tiles.

ENTITY_CHAR_MAP = {
    'S': 'spawn',
    'D': 'door',
    'E': 'enemy',
    'f': 'enemy_fast',
    'r': 'enemy_ranged',
    'w': 'enemy_wizard',
    'a': 'enemy_armor',
    'b': 'enemy_bee',
    'k': 'enemy_knight',
    'G': 'enemy_boss',
}

# === Door Scanning Order ===
# As per the rules, doors should be scanned top-to-bottom, then left-to-right.
# This is the default behavior of iterating through the level data and is noted here for clarity.

# === Door Size ===
# Currently 1x1. The schema is designed to support 1x2 in the future, but this is disabled.
DOOR_SIZE = (1, 1)
