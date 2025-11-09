from typing import List, Dict, Tuple, Optional
from .tile_types import TileType


class TileParser:
    """Parses ASCII level definitions to tile grids."""

    def __init__(self):
        # Default ASCII to tile type mapping
        self.ascii_map: Dict[str, TileType] = {
            ' ': TileType.AIR,
            '.': TileType.FLOOR,
            '#': TileType.WALL,
            '~': TileType.SOLID,
            '_': TileType.PLATFORM,  # Underscore for platform
            '@': TileType.BREAKABLE_WALL,  # @ for breakable wall
            '%': TileType.BREAKABLE_FLOOR,  # % for breakable floor
        }

        # Entity markers (not converted to tiles)
        self.entity_markers = {
            'S': 'spawn',
            'E': 'enemy',
            'D': 'door',
            'f': 'enemy_fast',
            'r': 'enemy_ranged',
            'w': 'enemy_wizard',
            'a': 'enemy_armor',
            'b': 'enemy_bee',
            'G': 'enemy_boss',
        }

    def parse_ascii_level(self, ascii_level: List[str]) -> Tuple[List[List[int]], Dict[str, List[Tuple[int, int]]]]:
        """
        Parse ASCII level definition to tile grid and entity positions.

        Returns:
            Tuple of (tile_grid, entity_positions)
        """
        if not ascii_level:
            return [], {}

        # Find max dimensions
        max_width = max(len(line) for line in ascii_level)
        height = len(ascii_level)

        # Initialize tile grid with air
        tile_grid = [[TileType.AIR.value for _ in range(max_width)] for _ in range(height)]
        entity_positions: Dict[str, List[Tuple[int, int]]] = {}

        # Parse each line
        for y, line in enumerate(ascii_level):
            for x, char in enumerate(line):
                if char in self.ascii_map:
                    # It's a tile
                    tile_type = self.ascii_map[char]
                    tile_grid[y][x] = tile_type.value
                elif char in self.entity_markers:
                    # It's an entity
                    entity_type = self.entity_markers[char]
                    if entity_type not in entity_positions:
                        entity_positions[entity_type] = []
                    entity_positions[entity_type].append((x, y))
                # Unknown characters are ignored (treated as air)

        return tile_grid, entity_positions

    def set_custom_mapping(self, ascii_char: str, tile_type: TileType):
        """Set a custom ASCII character to tile type mapping."""
        self.ascii_map[ascii_char] = tile_type

    def set_entity_marker(self, ascii_char: str, entity_type: str):
        """Set a custom ASCII character as an entity marker."""
        self.entity_markers[ascii_char] = entity_type

    def get_ascii_representation(self, tile_grid: List[List[int]],
                                entity_positions: Optional[Dict[str, List[Tuple[int, int]]]] = None) -> List[str]:
        """
        Convert tile grid back to ASCII representation.
        Useful for debugging or saving levels.
        """
        if not tile_grid:
            return []

        # Create reverse mapping
        tile_to_ascii = {tile_type: char for char, tile_type in self.ascii_map.items()}

        # Initialize with spaces
        height = len(tile_grid)
        width = max(len(row) for row in tile_grid) if tile_grid else 0
        ascii_lines = [[' ' for _ in range(width)] for _ in range(height)]

        # Convert tiles
        for y in range(height):
            for x in range(len(tile_grid[y])):
                tile_value = tile_grid[y][x]
                tile_type = TileType(tile_value)
                if tile_type in tile_to_ascii:
                    ascii_lines[y][x] = tile_to_ascii[tile_type]

        # Add entity markers
        if entity_positions:
            for entity_type, positions in entity_positions.items():
                entity_char = None
                for char, e_type in self.entity_markers.items():
                    if e_type == entity_type:
                        entity_char = char
                        break

                if entity_char:
                    for x, y in positions:
                        if 0 <= y < height and 0 <= x < width:
                            ascii_lines[y][x] = entity_char

        # Convert to strings
        return [''.join(line) for line in ascii_lines]

    def validate_ascii_level(self, ascii_level: List[str]) -> List[str]:
        """
        Validate ASCII level and return list of issues found.
        """
        issues = []

        if not ascii_level:
            issues.append("Level is empty")
            return issues

        # Check for consistent line lengths
        line_lengths = [len(line) for line in ascii_level]
        if len(set(line_lengths)) > 1:
            issues.append(f"Inconsistent line lengths: {line_lengths}")

        # Check for valid characters
        valid_chars = set(self.ascii_map.keys()) | set(self.entity_markers.keys())
        for y, line in enumerate(ascii_level):
            for x, char in enumerate(line):
                if char not in valid_chars and char != ' ':
                    issues.append(f"Unknown character '{char}' at position ({x}, {y})")

        # Check for spawn points
        has_spawn = any('S' in line for line in ascii_level)
        if not has_spawn:
            issues.append("No spawn point 'S' found")

        return issues

    def get_tile_info(self, ascii_char: str) -> Optional[str]:
        """Get information about what a character represents."""
        if ascii_char in self.ascii_map:
            tile_type = self.ascii_map[ascii_char]
            return f"Tile: {tile_type.name} ({tile_type.value})"
        elif ascii_char in self.entity_markers:
            return f"Entity: {self.entity_markers[ascii_char]}"
        elif ascii_char == ' ':
            return "Air/Empty"
        else:
            return "Unknown"

    def print_legend(self):
        """Print a legend of all recognized characters."""
        print("=== Tile Legend ===")
        for char, tile_type in self.ascii_map.items():
            print(f"  '{char}' : {tile_type.name}")
        print("\n=== Entity Legend ===")
        for char, entity_type in self.entity_markers.items():
            print(f"  '{char}' : {entity_type}")
        print(f"  ' '  : Air/Empty")