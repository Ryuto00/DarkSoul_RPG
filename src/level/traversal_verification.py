from dataclasses import dataclass, field
from typing import Dict, Tuple, Set, Optional, List
from collections import deque
import random # Needed for find_valid_ground_locations if it uses random, but it doesn't. Still, good to have.

from src.core.utils import bresenham_line
from src.level.procedural_generator import TileCell, RoomData, MovementAttributes, GenerationConfig

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

def check_physics_reach(current_node: Tuple[int, int], potential_neighbor: Tuple[int, int],
                        max_jump_height: int, max_jump_distance: int) -> bool:
    """
    Checks if a player can physically reach a potential_neighbor from current_node
    given their max_jump_height and max_jump_distance.
    This function does NOT check for collisions, only physical possibility.
    """
    cx, cy = current_node
    nx, ny = potential_neighbor

    # Calculate horizontal and vertical distance
    dx = abs(nx - cx)
    dy = cy - ny  # Positive if jumping up, negative if jumping down

    # Check horizontal distance
    if dx > max_jump_distance:
        return False

    # Check vertical distance (can jump up max_jump_height, can fall any distance)
    if dy > max_jump_height:
        return False
    
    # If jumping down, ensure it's not too far horizontally for a fall
    # This is a simplification; a real physics engine would be more complex.
    # For now, assume any downward movement is fine if horizontal is within limits.
    if dy < 0 and dx > max_jump_distance: # Falling, but too far horizontally
        return False

    return True

def check_jump_arc_clear(room_data: RoomData, start_pos: Tuple[int, int],
                         end_pos: Tuple[int, int], player_height: int) -> bool:
    """
    Checks if the path between start_pos and end_pos is clear of WALL tiles,
    considering the player's height.
    Uses bresenham_line to get all tiles on the path.
    """
    # 1. Get all tiles on the line from start to end
    line_tiles = bresenham_line(start_pos[0], start_pos[1], end_pos[0], end_pos[1])
    
    # 2. Check for collisions
    for x, y in line_tiles:
        # Check for a "head-bonk" collision
        # We check the tile itself and 'player_height' tiles above it
        for h_offset in range(1, player_height + 1):
            check_y = y - h_offset # (assuming y-up, so player's head is at y - player_height + 1)
            
            # Ensure check_y is within room bounds
            if not (0 <= x < room_data.size[0] and 0 <= check_y < room_data.size[1]):
                # If the path goes out of bounds, it's considered blocked for simplicity
                return False

            tile = room_data.grid.get((x, check_y), room_data.default_tile)
            
            if tile.t == "WALL":
                return False # Path is blocked!
                
    return True

def verify_traversable(room_data: RoomData, config: GenerationConfig) -> bool:
    """
    Verifies if a path exists from the entrance to the exit using BFS,
    considering player physics and collision.
    """
    movement_attrs = config.movement_attributes
    
    # 1. Get all "nodes" for the graph (valid ground locations)
    all_ground_nodes = find_valid_ground_locations(
        room_data, 
        movement_attrs.player_width, 
        movement_attrs.player_height
    )
    
    # Convert list to set for faster lookup
    all_ground_nodes_set = set(all_ground_nodes)

    # 2. Find the start and end nodes
    # The entrance_coords and exit_coords are the AIR tiles,
    # we need the ground tile directly below them.
    if not room_data.entrance_coords or not room_data.exit_coords:
        return False # Cannot verify if doors are not set

    start_node_candidate = (room_data.entrance_coords[0], room_data.entrance_coords[1] + 1)
    end_node_candidate = (room_data.exit_coords[0], room_data.exit_coords[1] + 1)

    # Ensure start and end nodes are actually valid ground locations
    if start_node_candidate not in all_ground_nodes_set or end_node_candidate not in all_ground_nodes_set:
        return False # Start or end is not a valid ground node

    start_node = start_node_candidate
    end_node = end_node_candidate
    
    # 3. Run the BFS pathfinding algorithm
    queue = deque([start_node])
    visited = {start_node}
    
    while queue:
        current_node = queue.popleft()
        
        if current_node == end_node:
            return True # Path found!
            
        # Check all other possible nodes as "neighbors"
        for potential_neighbor in all_ground_nodes:
            if potential_neighbor in visited:
                continue

            # --- This is the key logic ---
            
            # A) Physics Check: Can the player's jump *even reach* this node?
            is_reachable = check_physics_reach(
                current_node, 
                potential_neighbor,
                movement_attrs.max_jump_height,
                movement_attrs.max_jump_distance
            )
            
            if not is_reachable:
                continue # Skip, can't jump that far/high
                
            # B) Collision Check: Is the jump *path blocked* by a wall?
            is_clear = check_jump_arc_clear(
                room_data,
                current_node,
                potential_neighbor,
                movement_attrs.player_height
            )
            
            if is_clear:
                # This is a valid, traversable neighbor
                visited.add(potential_neighbor)
                queue.append(potential_neighbor)
                
    return False
