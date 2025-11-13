from enum import IntEnum, auto


class TileType(IntEnum):
    """Enumeration of all tile types in the game."""

    # Basic tiles
    AIR = 0
    WALL = 1
    DOOR_ENTRANCE = auto()
    DOOR_EXIT = auto()
    DOOR_EXIT_1 = auto()
    DOOR_EXIT_2 = auto()



    @property
    def is_solid(self) -> bool:
        """Return True if tile blocks movement completely."""
        return self == TileType.WALL



    

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
            TileType.DOOR_ENTRANCE: "DoorEntrance",
            TileType.DOOR_EXIT: "DoorExit",
            TileType.DOOR_EXIT_1: "DoorExit1",
            TileType.DOOR_EXIT_2: "DoorExit2",
        }.get(self, f"Tile_{self.value}")