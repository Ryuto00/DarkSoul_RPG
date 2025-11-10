from enum import IntEnum, auto


class TileType(IntEnum):
    """Enumeration of all tile types in the game."""

    # Basic tiles
    AIR = 0
    WALL = 1

    # Special tiles
    PLATFORM = 2
    BREAKABLE_WALL = 3

    # Future extension slots
    # ONE_WAY_PLATFORM = auto()
    # WATER = auto()
    # DOOR = auto()
    @property
    def is_solid(self) -> bool:
        """Return True if tile blocks movement completely."""
        return self in (TileType.WALL, TileType.BREAKABLE_WALL)

    @property
    def is_platform(self) -> bool:
        """Return True if tile is a jump-through platform."""
        return self in (TileType.PLATFORM,)

    @property
    def is_breakable(self) -> bool:
        """Return True if tile can be destroyed."""
        return self in (TileType.BREAKABLE_WALL,)

    @property
    def has_collision(self) -> bool:
        """Return True if tile has any collision."""
        return self != TileType.AIR

    @property
    def name(self) -> str:
        """Return human-readable name."""
        return {
            TileType.AIR: "Air",
            TileType.WALL: "Wall",
            TileType.PLATFORM: "Platform",
            TileType.BREAKABLE_WALL: "Breakable Wall",
        }.get(self, f"Tile_{self.value}")