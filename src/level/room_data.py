from dataclasses import dataclass, field
from typing import Tuple, Dict, Set, Optional, Any, List

@dataclass
class TileCell:
    """
    Represents a single tile in the game world.
    
    TileCell objects are treated as IMMUTABLE.
    
    Attributes:
        t: Tile type string (e.g., "WALL", "AIR")
        flags: Set of property flags
        entity_id: Optional reference to an entity occupying this tile
        metadata: Additional tile-specific data (for special tile types)
    """
    t: str = "AIR"
    flags: Set[str] = field(default_factory=set)
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        parts = [f"t='{self.t}'"]
        if self.flags:
            parts.append(f"flags={self.flags}")
        if self.entity_id:
            parts.append(f"entity_id='{self.entity_id}'")
        if self.metadata:
            parts.append(f"metadata={self.metadata}")
        return f"TileCell({', '.join(parts)})"

@dataclass
class RoomData:
    """
    Represents a single generated room using sparse grid representation.
    
    Attributes:
        size: Tuple of (width, height) in tiles
        default_tile: The TileCell used for coordinates not in the grid
        grid: Sparse dictionary mapping (x, y) -> TileCell
        entrance_coords: Coordinate of the entrance door
        exit_coords: Coordinate of the exit door
        spawn_areas: List of defined spawn zones
        difficulty_rating: Assigned difficulty score
        depth_from_start: Distance in rooms from level start
    """
    size: Tuple[int, int]
    default_tile: TileCell
    grid: Dict[Tuple[int, int], TileCell] = field(default_factory=dict)
    entrance_coords: Optional[Tuple[int, int]] = None
    exit_coords: Optional[Tuple[int, int]] = None
    spawn_areas: List['SpawnArea'] = field(default_factory=list)
    difficulty_rating: int = 1
    depth_from_start: int = 0
    player_spawn: Optional[Tuple[int, int]] = None  # 3x3 spawn center for player start

    def is_in_bounds(self, x: int, y: int) -> bool:
        """Check if coordinate is within room bounds."""
        return 0 <= x < self.size[0] and 0 <= y < self.size[1]

    def get_tile(self, x: int, y: int) -> TileCell:
        """
        Get the tile at coordinate (x, y).
        Returns default_tile if coordinate not in grid.
        """
        return self.grid.get((x, y), self.default_tile)

    def set_tile(self, x: int, y: int, tile: TileCell) -> None:
        """
        Set the tile at coordinate (x, y).
        If tile equals default_tile, it's still added to grid
        (optimization to remove it can be done later).
        """
        self.grid[(x, y)] = tile

@dataclass
class MovementAttributes:
    player_width: int = 1
    player_height: int = 2
    max_jump_height: int = 4
    max_jump_distance: int = 6
    min_corridor_height: int = 2

@dataclass
class SpawnArea:
    """
    Defines a region where entities can spawn.
    
    Used for both enemy spawning and item placement.
    Can also act as exclusion zones (where spawning is NOT allowed).
    
    Attributes:
        position: Top-left corner (x, y) of the spawn area
        size: (width, height) of the spawn area in tiles
        spawn_rules: Dictionary of rules for this area
            Example: {'allow_enemies': True, 'max_enemies': 5, 'difficulty_min': 1}
        possible_entities: List of entity IDs that can spawn here
        allowed_entity_tags: List of entity tags (categories) allowed
    """
    position: Tuple[int, int]
    size: Tuple[int, int]
    spawn_rules: Dict[str, Any] = field(default_factory=dict)
    possible_entities: List[str] = field(default_factory=list)
    allowed_entity_tags: List[str] = field(default_factory=list)
    
    def contains_point(self, x: int, y: int) -> bool:
        """Check if point (x, y) is within this spawn area."""
        px, py = self.position
        w, h = self.size
        return px <= x < px + w and py <= y < py + h
    
    def get_all_coords(self) -> List[Tuple[int, int]]:
        """Return all (x, y) coordinates covered by this spawn area."""
        px, py = self.position
        w, h = self.size
        coords = []
        for dy in range(h):
            for dx in range(w):
                coords.append((px + dx, py + dy))
        return coords

@dataclass
class GenerationConfig:
    min_room_size: int = 20
    max_room_size: int = 40
    max_room_generation_attempts: int = 100
    walk_length: int = 10
    
    movement_attributes: MovementAttributes = field(default_factory=MovementAttributes)
    min_corridor_width: int = 2
    spawn_area_spacing: int = 5
    base_enemy_density: float = 0.01
    max_enemies_per_room: int = 20
    
    drunkard_walk_iterations: int = 500
    drunkard_walk_fill_percentage: float = 0.4
    
    platform_min_width: int = 3
    platform_max_width: int = 6
    platform_placement_attempts: int = 50
    seed: Optional[int] = None

    # Spawn area configuration (ADD THESE)
    min_spawn_areas_per_room: int = 1
    max_spawn_areas_per_room: int = 5
    spawn_area_min_size: int = 3  # Minimum spawn area dimension
    spawn_area_max_size: int = 6  # Maximum spawn area dimension
    
    # Difficulty scaling (ADD THESE)
    difficulty_scale_factor: float = 0.5  # Logarithmic scaling multiplier
    max_difficulty_rating: int = 10  # Cap on difficulty
