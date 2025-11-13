import pygame
from typing import Optional, Tuple, Callable, List, Any
from ..tiles.tile_types import TileType
from ..tiles.tile_registry import tile_registry


def handle_proximity_interactions(
    player_rect: pygame.Rect,
    tile_grid: List[List[int]],
    tile_size: int,
    is_e_pressed: bool,
    on_interact: Callable[[Any, Tuple[int, int]], None]
) -> Optional[Tuple[str, int, int]]:
    """
    Handle proximity-based tile interactions.
    
    Args:
        player_rect: Player's collision rectangle
        tile_grid: 2D list of tile values for current level
        tile_size: Size of each tile (usually 24)
        is_e_pressed: Whether E key was pressed this frame
        on_interact: Callback function called when player interacts
                    (receives tile_data and (tx, ty) coordinates)
    
    Returns:
        Tuple of (prompt_text, world_x, world_y) for UI display,
        or None if no interactable tile is nearby.
    """
    if not tile_grid:
        return None
    
    # Calculate tile bounds to check around player
    start_tx = max(0, player_rect.left // tile_size - 1)
    end_tx = min(len(tile_grid[0]), (player_rect.right // tile_size) + 2)
    start_ty = max(0, player_rect.top // tile_size - 1)
    end_ty = min(len(tile_grid), (player_rect.bottom // tile_size) + 2)
    
    for ty in range(start_ty, end_ty):
        for tx in range(start_tx, end_tx):
            tile_value = tile_grid[ty][tx]
            if tile_value < 0:
                continue
                
            tile_type = TileType(tile_value)
            tile_data = tile_registry.get_tile(tile_type)
            
            if not tile_data or not tile_data.interaction.interactable:
                continue
            
            # Check proximity requirement
            if tile_data.interaction.requires_proximity:
                tile_rect = pygame.Rect(
                    tx * tile_size,
                    ty * tile_size,
                    tile_size,
                    tile_size
                )
                
                # Expand proximity check if radius is larger than tile size
                if tile_data.interaction.proximity_radius > tile_size:
                    expanded_rect = tile_rect.inflate(
                        tile_data.interaction.proximity_radius - tile_size,
                        tile_data.interaction.proximity_radius - tile_size
                    )
                    if not player_rect.colliderect(expanded_rect):
                        continue
                else:
                    if not player_rect.colliderect(tile_rect):
                        continue
            
            # Found interactable tile
            prompt = tile_data.interaction.prompt or "Press E"
            world_x = tx * tile_size + tile_size // 2
            world_y = ty * tile_size - 10  # Position above tile
            
            if is_e_pressed:
                on_interact(tile_data, (tx, ty))
            
            return (prompt, world_x, world_y)
    
    return None


def find_spawn_point(
    tile_grid: List[List[int]],
    entrance_id: Optional[str] = None
) -> Optional[Tuple[int, int]]:
    """
    Find a spawn point (DOOR_ENTRANCE) in the tile grid.
    
    Args:
        tile_grid: 2D list of tile values
        entrance_id: Optional entrance ID to match. If None, finds any spawn point.
    
    Returns:
        Tuple of (tile_x, tile_y) for spawn point, or None if not found.
    """
    if not tile_grid:
        return None
    
    for ty, row in enumerate(tile_grid):
        for tx, tile_value in enumerate(row):
            if tile_value < 0:
                continue
                
            tile_type = TileType(tile_value)
            tile_data = tile_registry.get_tile(tile_type)
            
            if not tile_data or not tile_data.interaction.is_spawn_point:
                continue
            
            # If entrance_id is specified, match it
            if entrance_id:
                expected_id = f"entrance:{entrance_id}"
                if tile_data.interaction.on_interact_id != expected_id:
                    continue
            
            return (tx, ty)
    
    return None


def parse_door_target(on_interact_id: str) -> Optional[Tuple[str, str]]:
    """
    Parse door target from on_interact_id.
    
    Args:
        on_interact_id: String in format "goto:<level_name>:<entrance_id>"
    
    Returns:
        Tuple of (level_name, entrance_id) or None if format is invalid.
    """
    if not on_interact_id.startswith("goto:"):
        return None
    
    parts = on_interact_id.split(":")
    if len(parts) != 3:
        return None
    
    _, level_name, entrance_id = parts
    return (level_name, entrance_id)