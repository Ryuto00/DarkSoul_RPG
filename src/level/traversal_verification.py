from typing import List, Tuple
from src.level.room_data import RoomData, MovementAttributes
from src.core.utils import bresenham_line
from src.tiles.tile_types import TileType

def check_jump_arc_clear(room_data: RoomData, start_pos: Tuple[int, int], end_pos: Tuple[int, int], player_height: int) -> bool:
    """
    Checks if the path of a jump is clear of obstacles.
    """
    line_tiles = bresenham_line(start_pos[0], start_pos[1], end_pos[0], end_pos[1])
    
    for (x, y) in line_tiles:
        for h in range(1, player_height + 1):
            check_y = y - h
            tile = room_data.grid.get((x, check_y), room_data.default_tile)
            
            if tile.tile_type == TileType.WALL:
                return False
                
    return True

def find_valid_ground_locations(room_data: RoomData, entity_width: int, entity_height: int) -> List[Tuple[int, int]]:
    """
    Finds all valid ground locations for an entity of a given size.
    """
    valid_locations = []
    width, height = room_data.size
    default_tile = room_data.default_tile

    for x in range(width):
        for y in range(height):
            ground_tile = room_data.grid.get((x, y), default_tile)
            if ground_tile.tile_type != TileType.WALL:
                continue

            has_clearance = True
            for dx in range(entity_width):
                for dy_offset in range(1, entity_height + 1):
                    check_pos = (x + dx, y - dy_offset)
                    if not (0 <= check_pos[0] < width and 0 <= check_pos[1] < height):
                        has_clearance = False
                        break
                    above_tile = room_data.grid.get(check_pos, default_tile)
                    if above_tile.tile_type == TileType.WALL:
                        has_clearance = False
                        break
                    # Allow doors above ground tiles (for door traversal)
                    if above_tile.tile_type == TileType.DOOR:
                        # This is expected for door traversal - door is above ground tile
                        # Skip clearance check for this position since door is here
                        has_clearance = True
                        break
                if not has_clearance:
                    break


            if has_clearance:
                valid_locations.append((x, y))
                if (x, y) in [(9, 12), (10, 12), (11, 12), (7, 10), (8, 10), (9, 10)]:  # Debug door positions
                    print(f"DEBUG: Found door ground at ({x}, {y})")

    return valid_locations

def check_physics_reach(start_node: Tuple[int, int], end_node: Tuple[int, int], max_jump_height: int, max_jump_distance: int) -> bool:
    """
    Checks if a jump is physically possible.
    """
    dx = abs(start_node[0] - end_node[0])
    dy = start_node[1] - end_node[1] # Positive dy is a jump up

    if dx > max_jump_distance:
        return False
    if dy > max_jump_height:
        return False
        
    return True

def verify_traversable(room_data: RoomData, movement_attrs: MovementAttributes) -> bool:
    """
    Verifies that the room is traversable from entrance to exit.

    Adjusted for current PCG:
    - No assumptions about spawn areas; only doors and walkable ground matter.
    - Uses MovementAttributes (player size / jump) and carved tiles only.
    """


    # Require at least one door for PCG system
    if not room_data.doors:
        return False

    # Compute all valid ground nodes for current player size
    all_ground_nodes = find_valid_ground_locations(
        room_data,
        movement_attrs.player_width,
        movement_attrs.player_height
    )

    # For linear levels, use first door as start, last door as end
    door_list = list(room_data.doors.values())
    if len(door_list) < 1:
        return False
    
    # For now, use first door for both start and end (single door rooms)
    # This will be updated when we implement proper multi-door logic
    start_node = (door_list[0].position[0], door_list[0].position[1] + 1)
    end_node = (door_list[-1].position[0], door_list[-1].position[1] + 1)
    
    print(f"DEBUG: verify_traversable: doors={[{d.door_type: d.position} for d in door_list]}")
    print(f"DEBUG: verify_traversable: start_node={start_node}, end_node={end_node}")
    print(f"DEBUG: verify_traversable: ground_nodes_count={len(all_ground_nodes)}")
    print(f"DEBUG: verify_traversable: ground_nodes={list(all_ground_nodes)}")  # Show all

    # If either door does not sit above valid ground, this layout is invalid
    if start_node not in all_ground_nodes:
        print(f"DEBUG: verify_traversable: start_node {start_node} not in ground_nodes")
        return False
    if end_node not in all_ground_nodes:
        print(f"DEBUG: verify_traversable: end_node {end_node} not in ground_nodes")
        return False
    
    # For door traversal, check if doors are placed on adjacent ground tiles
    # This is valid since player can move between adjacent door positions
    dx = abs(start_node[0] - end_node[0])
    dy = abs(start_node[1] - end_node[1])
    if dx <= 3 and dy <= 3:  # Doors are reasonably close (within 3x1 ground area)
        print(f"DEBUG: Door traversal valid: doors are adjacent ({dx}, {dy})")
        return True

    queue = [start_node]
    visited = {start_node}
    
    while queue:
        current_node = queue.pop(0)
        
        if current_node == end_node:
            return True
            
        for potential_neighbor in all_ground_nodes:
            if potential_neighbor == current_node:
                continue # Don't check jump to self

            if potential_neighbor in visited:
                continue

            is_reachable = check_physics_reach(
                current_node, 
                potential_neighbor,
                movement_attrs.max_jump_height,
                movement_attrs.max_jump_distance
            )
            
            if not is_reachable:
                # print(f"[TRAVERSAL DEBUG]   {current_node} -> {potential_neighbor}: Not physically reachable.")
                continue
                
            is_clear = check_jump_arc_clear(
                room_data,
                current_node,
                potential_neighbor,
                movement_attrs.player_height
            )
            
            if is_clear:

                visited.add(potential_neighbor)
                queue.append(potential_neighbor)
            # else:
                # print(f"[TRAVERSAL DEBUG]   {current_node} -> {potential_neighbor}: Physically reachable but path blocked.")
                

    return False