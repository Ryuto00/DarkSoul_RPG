from typing import List, Tuple
from src.level.room_data import RoomData, MovementAttributes
from src.core.utils import bresenham_line

def check_jump_arc_clear(room_data: RoomData, start_pos: Tuple[int, int], end_pos: Tuple[int, int], player_height: int) -> bool:
    """
    Checks if the path of a jump is clear of obstacles.
    """
    line_tiles = bresenham_line(start_pos[0], start_pos[1], end_pos[0], end_pos[1])
    
    for (x, y) in line_tiles:
        for h in range(1, player_height + 1):
            check_y = y - h
            tile = room_data.grid.get((x, check_y), room_data.default_tile)
            
            if tile.t == "WALL":
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
            if ground_tile.t != "WALL":
                continue

            has_clearance = True
            for dx in range(entity_width):
                for dy_offset in range(1, entity_height + 1):
                    check_pos = (x + dx, y - dy_offset)
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
    print(f"[TRAVERSAL DEBUG] Verifying traversability for room size {room_data.size}")
    print(f"[TRAVERSAL DEBUG] Entrance: {room_data.entrance_coords}, Exit: {room_data.exit_coords}")
    print(f"[TRAVERSAL DEBUG] Movement Attributes: max_jump_height={movement_attrs.max_jump_height}, max_jump_distance={movement_attrs.max_jump_distance}, player_height={movement_attrs.player_height}")

    # Require valid entrance/exit; PCG promises to set these via place_doors
    if not room_data.entrance_coords or not room_data.exit_coords:
        print("[TRAVERSAL DEBUG] Entrance or Exit coords not set.")
        return False

    # Compute all valid ground nodes for current player size
    all_ground_nodes = find_valid_ground_locations(
        room_data,
        movement_attrs.player_width,
        movement_attrs.player_height
    )
    print(f"[TRAVERSAL DEBUG] Found {len(all_ground_nodes)} valid ground locations.")

    # Ground nodes directly under the door tiles (where player stands)
    start_node = (room_data.entrance_coords[0], room_data.entrance_coords[1] + 1)
    end_node = (room_data.exit_coords[0], room_data.exit_coords[1] + 1)

    print(f"[TRAVERSAL DEBUG] Start Node (ground below entrance): {start_node}")
    print(f"[TRAVERSAL DEBUG] End Node (ground below exit): {end_node}")

    # If either door does not sit above valid ground, this layout is invalid
    if start_node not in all_ground_nodes:
        print(f"[TRAVERSAL DEBUG] Start node {start_node} not in valid ground locations.")
        return False
    if end_node not in all_ground_nodes:
        print(f"[TRAVERSAL DEBUG] End node {end_node} not in valid ground locations.")
        return False

    queue = [start_node]
    visited = {start_node}
    
    while queue:
        current_node = queue.pop(0)
        print(f"[TRAVERSAL DEBUG] Exploring from {current_node}")
        
        if current_node == end_node:
            print(f"[TRAVERSAL DEBUG] Path found to end node {end_node}!")
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
                print(f"[TRAVERSAL DEBUG]   {current_node} -> {potential_neighbor}: Reachable and clear. Adding to queue.")
                visited.add(potential_neighbor)
                queue.append(potential_neighbor)
            # else:
                # print(f"[TRAVERSAL DEBUG]   {current_node} -> {potential_neighbor}: Physically reachable but path blocked.")
                
    print("[TRAVERSAL DEBUG] No path found to exit.")
    return False