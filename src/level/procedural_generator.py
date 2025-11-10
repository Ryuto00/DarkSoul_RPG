from dataclasses import dataclass, field
from typing import Dict, Tuple, Set, Optional, List
from collections import deque
from src.core.utils import bresenham_line

@dataclass
class TileCell:
    """
    Represents a single tile in the procedural generation grid.
    't' is the tile type (e.g., "AIR", "WALL").
    'flags' is a set of strings for additional properties (e.g., {"DOOR_ENTRANCE"}).
    """
    t: str
    flags: Set[str] = field(default_factory=set)

@dataclass
class RoomData:
    """
    Represents the generated data for a single room.
    grid: A sparse grid mapping (x, y) coordinates to TileCell objects.
    size: (width, height) of the room.
    default_tile: The TileCell to assume for coordinates not explicitly in the grid.
    entrance_coords: (x, y) of the entrance door's AIR tile.
    exit_coords: (x, y) of the exit door's AIR tile.
    """
    size: Tuple[int, int]
    default_tile: TileCell
    grid: Dict[Tuple[int, int], TileCell] = field(default_factory=dict)
    entrance_coords: Optional[Tuple[int, int]] = None
    exit_coords: Optional[Tuple[int, int]] = None

@dataclass
class MovementAttributes:
    """
    Defines player movement capabilities for pathfinding.
    All values are in tile units.
    """
    player_width: int = 1
    player_height: int = 2 # Assuming player is 2 tiles high
    max_jump_height: int = 4 # Max vertical distance player can jump
    max_jump_distance: int = 6 # Max horizontal distance player can jump

@dataclass
class GenerationConfig:
    """
    Configuration parameters for room generation.
    """
    min_room_size: int = 20
    max_room_size: int = 40
    drunkard_walk_iterations: int = 1000
    drunkard_walk_step_length: int = 5
    drunkard_walk_fill_percentage: float = 0.4
    movement_attributes: MovementAttributes = field(default_factory=MovementAttributes)

import random
from src.level.traversal_verification import find_valid_ground_locations, verify_traversable

def generate_fallback_room(config: GenerationConfig) -> RoomData:
    """
    Creates a simple rectangular room with a flat floor and no platforms.
    Guaranteed to be traversable.
    """
    # Use min_room_size for fallback to ensure it's always small and manageable
    fallback_width = config.min_room_size
    fallback_height = config.min_room_size

    room = RoomData(
        size=(fallback_width, fallback_height),
        default_tile=TileCell(t="AIR"), # Default to AIR for fallback room
        grid={}
    )

    # Create solid floor at the bottom
    floor_y = fallback_height - 1
    for x in range(fallback_width):
        room.grid[(x, floor_y)] = TileCell(t="WALL")

    # Place entrance and exit on opposite sides, one tile above the floor
    room.entrance_coords = (1, floor_y - 1) # 1 tile from left edge, 1 tile above floor
    room.exit_coords = (fallback_width - 2, floor_y - 1) # 1 tile from right edge, 1 tile above floor

    # Ensure the entrance and exit spots are AIR (door openings)
    room.grid[room.entrance_coords] = TileCell(t="AIR", flags={"DOOR_ENTRANCE"})
    room.grid[room.exit_coords] = TileCell(t="AIR", flags={"DOOR_EXIT"})

    return room

def find_valid_ground_locations(room_data: RoomData,
                                entity_width: int,
                                entity_height: int) -> List[Tuple[int, int]]:
    valid_locations = []
    width, height = room_data.size
    default_tile = room_data.default_tile

    for x in range(width):
        for y in range(height):
            # Check ground
            ground_tile = room_data.grid.get((x, y), default_tile)
            if ground_tile.t != "WALL":
                continue

            # Check clearance above - MUST handle default_tile
            has_clearance = True
            for dx in range(entity_width):
                for dy_offset in range(1, entity_height + 1): # Check from 1 tile above ground up to entity_height
                    check_pos = (x + dx, y - dy_offset)
                    # Ensure check_pos is within room bounds
                    if not (0 <= check_pos[0] < width and 0 <= check_pos[1] < height):
                        has_clearance = False
                        break
                    above_tile = room_data.grid.get(check_pos, default_tile)
                    if above_tile.t == "WALL":
                        has_clearance = False
                        break
                if not has_clearance:
                    break

            if has_clearance:
                valid_locations.append((x, y))

    return valid_locations

def generate_room_layout(config: GenerationConfig) -> RoomData:
    """
    Generates a room layout using a Drunkard's Walk algorithm.
    The room conceptually starts as all WALL, and the walk carves out AIR.
    """
    width = random.randint(config.min_room_size, config.max_room_size)
    height = random.randint(config.min_room_size, config.max_room_size)

    room = RoomData(
        size=(width, height),
        default_tile=TileCell(t="WALL"), # Room starts as all WALL
        grid={} # Sparse grid, only AIR tiles will be added
    )

    # Start the drunkard in the middle-ish
    current_x = width // 2
    current_y = height // 2

    # Keep track of visited cells to ensure a certain fill percentage
    visited_cells = set()

    for _ in range(config.drunkard_walk_iterations):
        # Mark current position as AIR
        if (current_x, current_y) not in room.grid:
            room.grid[(current_x, current_y)] = TileCell(t="AIR")
            visited_cells.add((current_x, current_y))

        # Randomly move the drunkard
        direction = random.choice([(0, 1), (0, -1), (1, 0), (-1, 0)]) # Down, Up, Right, Left
        for _ in range(config.drunkard_walk_step_length):
            next_x = current_x + direction[0]
            next_y = current_y + direction[1]

            # Keep drunkard within bounds
            if 0 < next_x < width - 1 and 0 < next_y < height - 1: # Avoid edges for now
                current_x = next_x
                current_y = next_y
                if (current_x, current_y) not in room.grid:
                    room.grid[(current_x, current_y)] = TileCell(t="AIR")
                    visited_cells.add((current_x, current_y))
            else:
                # If hit boundary, change direction
                break
        
        # Optional: Carve a wider path
        # For simplicity, I'll skip this for now and focus on the core algorithm.
        # This can be added later if needed.

        # Check fill percentage
        if len(visited_cells) / (width * height) >= config.drunkard_walk_fill_percentage:
            break

    # Ensure there's at least one AIR tile if the walk was too short
    if not room.grid:
        room.grid[(width // 2, height // 2)] = TileCell(t="AIR")
        visited_cells.add((width // 2, height // 2))

    # For now, entrance and exit coordinates are not set here.
    # They will be set in place_doors_and_spawn using find_valid_ground_locations.
    return room

def place_doors_and_spawn(room_data: RoomData, config: GenerationConfig):
    """
    Places entrance and exit doors in the room, ensuring they are traversable.
    """
    width, height = room_data.size
    player_width = config.movement_attributes.player_width
    player_height = config.movement_attributes.player_height

    # Find valid ground locations for the player
    all_valid_ground_locations = find_valid_ground_locations(room_data, player_width, player_height)

    # Filter for potential entrance locations (left side)
    potential_entrance_locations = [
        (x, y) for x, y in all_valid_ground_locations
        if x < width // 4 # Within the first quarter of the room
    ]

    # Filter for potential exit locations (right side)
    potential_exit_locations = [
        (x, y) for x, y in all_valid_ground_locations
        if x > width * 3 // 4 # Within the last quarter of the room
    ]

    # Choose entrance
    if potential_entrance_locations:
        room_data.entrance_coords = random.choice(potential_entrance_locations)
    else:
        # Fallback: if no suitable location found, try to place near the bottom left
        # This might overwrite an existing tile, but it's a fallback for generation failure
        fallback_x = 1
        fallback_y = height - 2 # One tile above the floor
        room_data.entrance_coords = (fallback_x, fallback_y)
        # Ensure there's a wall below
        room_data.grid[(fallback_x, fallback_y + 1)] = TileCell(t="WALL")


    # Choose exit
    if potential_exit_locations:
        room_data.exit_coords = random.choice(potential_exit_locations)
    else:
        # Fallback: if no suitable location found, try to place near the bottom right
        fallback_x = width - 2
        fallback_y = height - 2
        room_data.exit_coords = (fallback_x, fallback_y)
        # Ensure there's a wall below
        room_data.grid[(fallback_x, fallback_y + 1)] = TileCell(t="WALL")

    # Place the actual door TileCells (AIR with flags)
    if room_data.entrance_coords:
        room_data.grid[room_data.entrance_coords] = TileCell(t="AIR", flags={"DOOR_ENTRANCE"})
        # Ensure a WALL tile exists directly below the door opening
        room_data.grid[(room_data.entrance_coords[0], room_data.entrance_coords[1] + 1)] = TileCell(t="WALL")
    
    if room_data.exit_coords:
        room_data.grid[room_data.exit_coords] = TileCell(t="AIR", flags={"DOOR_EXIT"})
        # Ensure a WALL tile exists directly below the door opening
        room_data.grid[(room_data.exit_coords[0], room_data.exit_coords[1] + 1)] = TileCell(t="WALL")





def generate_procedural_room(config: GenerationConfig, max_attempts: int = 10) -> RoomData:
    """
    Orchestrates the procedural room generation process.
    Attempts to generate a traversable room, falling back to a simple room if unsuccessful.
    """
    for attempt in range(max_attempts):
        print(f"Attempting to generate room (attempt {attempt + 1}/{max_attempts})...")
        room = generate_room_layout(config)
        place_doors_and_spawn(room, config)

        if room.entrance_coords and room.exit_coords:
            if verify_traversable(room, config):
                print(f"Successfully generated a traversable room on attempt {attempt + 1}.")
                return room
            else:
                print(f"Room generated but not traversable. Retrying...")
        else:
            print(f"Could not place entrance/exit in generated room. Retrying...")

    print(f"Failed to generate a traversable room after {max_attempts} attempts. Generating fallback room.")
    return generate_fallback_room(config)








