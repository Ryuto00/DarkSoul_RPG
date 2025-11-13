"""PCG Level and Room Data System"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import json
import os
import sys

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from config import TILE_AIR, TILE_WALL


@dataclass
class PCGConfig:
    """Configuration for procedural level generation."""
    num_levels: int = 3
    rooms_per_level: int = 6
    room_width: int = 40
    room_height: int = 30
    
    # Tile IDs to use (aligned with config.py and tile system)
    air_tile_id: int = TILE_AIR
    wall_tile_id: int = TILE_WALL
    
    # Generation options
    add_doors: bool = True
    door_entrance_tile_id: int = 2  # DOOR_ENTRANCE
    door_exit_tile_id: int = 3     # DOOR_EXIT (legacy)
    door_exit_1_tile_id: int = 4   # DOOR_EXIT_1
    door_exit_2_tile_id: int = 5   # DOOR_EXIT_2


@dataclass
class RoomData:
    """Data structure for a single room."""
    level_id: int
    room_index: int
    room_letter: str
    room_code: str
    tiles: List[List[int]]  # 2D grid of tile IDs
    entrance_from: Optional[str] = None  # Which room this room's entrance comes from
    door_exits: Optional[Dict[str, str]] = None  # Maps "door_exit_1"/"door_exit_2" to target room codes
    
    def __post_init__(self):
        if self.door_exits is None:
            self.door_exits = {}


@dataclass
class LevelData:
    """Data structure for a single level containing multiple rooms."""
    level_id: int
    rooms: List[RoomData]


@dataclass
class LevelSet:
    """Complete set of levels with all rooms."""
    levels: List[LevelData]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LevelSet":
        """Create from dictionary."""
        levels = []
        for level_data in data["levels"]:
            rooms = []
            for room_data in level_data["rooms"]:
                rooms.append(RoomData(**room_data))
            levels.append(LevelData(
                level_id=level_data["level_id"],
                rooms=rooms
            ))
        return cls(levels=levels)
    
    def save_to_json(self, filepath: str) -> None:
        """Save level set to JSON file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load_from_json(cls, filepath: str) -> "LevelSet":
        """Load level set from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def get_room(self, level_id: int, room_code: str) -> Optional[RoomData]:
        """Get a specific room by level ID and room code."""
        for level in self.levels:
            if level.level_id == level_id:
                for room in level.rooms:
                    if room.room_code == room_code:
                        return room
        return None
    
    def get_level(self, level_id: int) -> Optional[LevelData]:
        """Get a specific level by ID."""
        for level in self.levels:
            if level.level_id == level_id:
                return level
        return None


def generate_room_tiles(
    level_id: int,
    room_index: int,
    room_letter: str,
    width: int,
    height: int,
    config: PCGConfig
) -> List[List[int]]:
    """
    Generate a 2D grid of tile IDs for a room.
    Replace this with your actual PCG algorithm.
    """
    # Simple placeholder: walls around border, floor inside
    grid: List[List[int]] = []
    
    for y in range(height):
        row: List[int] = []
        for x in range(width):
            # Border walls
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                row.append(config.wall_tile_id)
            else:
                row.append(config.air_tile_id)
        grid.append(row)
    
    # Add doors if enabled
    if config.add_doors:
        # Entrance door (left side, middle)
        entrance_y = height // 2
        if 0 < entrance_y < height - 1:
            grid[entrance_y][1] = config.door_entrance_tile_id
        
        # Exit doors (right side, two exits)
        exit1_y = height // 2 - 2  # Upper exit
        exit2_y = height // 2 + 2  # Lower exit
        
        if 0 < exit1_y < height - 1:
            grid[exit1_y][width - 2] = config.door_exit_1_tile_id
        if 0 < exit2_y < height - 1:
            grid[exit2_y][width - 2] = config.door_exit_2_tile_id
    
    return grid


def generate_level_set(config: PCGConfig) -> LevelSet:
    """
    Generate a complete set of levels with rooms and door routing.
    
    Returns:
        LevelSet: Complete level data structure
    """
    levels: List[LevelData] = []
    
    # First pass: create all rooms without routing
    all_rooms = []
    for level_id in range(1, config.num_levels + 1):
        for room_index in range(config.rooms_per_level):
            room_letter = chr(ord("A") + room_index)
            room_code = f"{level_id}{room_letter}"
            
            tiles = generate_room_tiles(
                level_id=level_id,
                room_index=room_index,
                room_letter=room_letter,
                width=config.room_width,
                height=config.room_height,
                config=config
            )
            
            room = RoomData(
                level_id=level_id,
                room_index=room_index,
                room_letter=room_letter,
                room_code=room_code,
                tiles=tiles
            )
            all_rooms.append(room)
    
    # Second pass: create routing connections
    for room in all_rooms:
        entrance_from, door_exits = create_room_routing(
            room, all_rooms, config
        )
        room.entrance_from = entrance_from
        room.door_exits = door_exits
    
    # Organize rooms by levels
    for level_id in range(1, config.num_levels + 1):
        level_rooms = [r for r in all_rooms if r.level_id == level_id]
        levels.append(LevelData(level_id=level_id, rooms=level_rooms))
    
    return LevelSet(levels=levels)


def create_room_routing(
    room: 'RoomData', 
    all_rooms: List['RoomData'], 
    config: PCGConfig
) -> tuple[Optional[str], Dict[str, str]]:
    """
    Create door routing for a room based on all rooms.
    
    Returns:
        Tuple of (entrance_from, door_exits)
    """
    # Find which rooms point to this room
    entrance_from = None
    for other_room in all_rooms:
        if other_room.door_exits:
            if room.room_code in other_room.door_exits.values():
                entrance_from = other_room.room_code
                break
    
    # Create door exits mapping
    door_exits = {}
    
    # Exit 1: goes to next room in same level
    same_level_rooms = [r for r in all_rooms if r.level_id == room.level_id]
    same_level_rooms.sort(key=lambda r: r.room_index)
    
    current_index = same_level_rooms.index(room)
    next_index = (current_index + 1) % len(same_level_rooms)
    next_room = same_level_rooms[next_index]
    door_exits["door_exit_1"] = next_room.room_code
    
    # Exit 2: goes to first room of next level (or first room of same level if last level)
    if room.level_id < config.num_levels:
        next_level_rooms = [r for r in all_rooms if r.level_id == room.level_id + 1]
        if next_level_rooms:
            next_level_rooms.sort(key=lambda r: r.room_index)
            door_exits["door_exit_2"] = next_level_rooms[0].room_code
        else:
            # Fallback to first room of current level
            door_exits["door_exit_2"] = same_level_rooms[0].room_code
    else:
        # Last level - go to first room of current level
        door_exits["door_exit_2"] = same_level_rooms[0].room_code
    
    return entrance_from, door_exits


# Convenience function for quick generation
def generate_and_save(
    config: Optional[PCGConfig] = None,
    output_path: str = "data/levels/generated_levels.json"
) -> LevelSet:
    """
    Generate levels and save to file.
    
    Args:
        config: PCG configuration (uses default if None)
        output_path: Where to save the JSON file
        
    Returns:
        LevelSet: The generated level set
    """
    if config is None:
        config = PCGConfig()
    
    level_set = generate_level_set(config)
    level_set.save_to_json(output_path)
    print(f"Generated {config.num_levels} levels with {config.rooms_per_level} rooms each")
    print(f"Saved to: {output_path}")
    
    return level_set


if __name__ == "__main__":
    # Test generation when run directly
    level_set = generate_and_save()
    
    # Print summary
    for level in level_set.levels:
        print(f"Level {level.level_id}: {len(level.rooms)} rooms")
        for room in level.rooms[:2]:  # Show first 2 rooms
            print(f"  Room {room.room_code}: {len(room.tiles)}x{len(room.tiles[0])} tiles")