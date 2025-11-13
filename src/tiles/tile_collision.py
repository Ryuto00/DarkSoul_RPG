import pygame
from typing import List, Tuple, Optional
from .tile_types import TileType
from .tile_registry import tile_registry


class TileCollision:
    """Handles collision detection and response for tiles."""

    def __init__(self, tile_size: int = None):
        from config import TILE
        self.tile_size = tile_size if tile_size is not None else TILE
        self.tile_size = tile_size

    def get_tile_at_pos(self, x: float, y: float, tile_grid: List[List[int]]) -> Optional[TileType]:
        """Get tile type at world position."""
        grid_x = int(x // self.tile_size)
        grid_y = int(y // self.tile_size)

        if (0 <= grid_y < len(tile_grid) and
            0 <= grid_x < len(tile_grid[grid_y])):
            tile_value = tile_grid[grid_y][grid_x]
            return TileType(tile_value) if tile_value >= 0 else None
        return None

    def get_tiles_in_rect(self, rect: pygame.Rect, tile_grid: List[List[int]]) -> List[Tuple[TileType, int, int]]:
        """Get all tiles within a rectangle."""
        tiles = []

        # Convert rect to tile coordinates
        start_x = max(0, int(rect.left // self.tile_size))
        end_x = min(len(tile_grid[0]) if tile_grid else 0, int(rect.right // self.tile_size) + 1)
        start_y = max(0, int(rect.top // self.tile_size))
        end_y = min(len(tile_grid), int(rect.bottom // self.tile_size) + 1)

        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                if x < len(tile_grid[y]):
                    tile_value = tile_grid[y][x]
                    if tile_value >= 0:
                        tile_type = TileType(tile_value)
                        tiles.append((tile_type, x, y))

        return tiles

    def check_tile_collision(self, entity_rect: pygame.Rect, tile_grid: List[List[int]],
                            velocity: Optional[pygame.Vector2] = None) -> List[dict]:
        """Check collision with tiles and return collision info."""
        collisions = []

        # Get tiles near the entity
        expanded_rect = entity_rect.inflate(2, 2)
        tiles = self.get_tiles_in_rect(expanded_rect, tile_grid)

        for tile_type, tile_x, tile_y in tiles:
            tile_data = tile_registry.get_tile(tile_type)
            if not tile_data or not tile_data.has_collision:
                continue

            # Calculate tile rect based on collision properties
            tile_world_x = tile_x * self.tile_size
            tile_world_y = tile_y * self.tile_size

            if tile_data.collision.collision_box_offset and tile_data.collision.collision_box_size:
                offset_x, offset_y = tile_data.collision.collision_box_offset
                collision_width, collision_height = tile_data.collision.collision_box_size
            else:
                # Fallback to full tile size
                offset_x, offset_y = 0, 0
                collision_width, collision_height = self.tile_size, self.tile_size

            tile_rect = pygame.Rect(
                tile_world_x + offset_x,
                tile_world_y + offset_y,
                collision_width,
                collision_height
            )

            # Check collision
            if entity_rect.colliderect(tile_rect):
                collision_info = {
                    'tile_type': tile_type,
                    'tile_data': tile_data,
                    'tile_rect': tile_rect,
                    'tile_x': tile_x,
                    'tile_y': tile_y,
                    'collision_type': tile_data.collision.collision_type
                }
                collisions.append(collision_info)

        return collisions

    def resolve_platform_collision(self, entity_rect: pygame.Rect, tile_rect: pygame.Rect,
                                  velocity: pygame.Vector2) -> Tuple[bool, pygame.Vector2]:
        """Resolve collision with platform tiles (top-only collision)."""
        # Only collide if entity is moving down and is above the platform
        if velocity.y > 0:
            feet_y = entity_rect.bottom
            platform_top = tile_rect.top

            # Check if entity's feet are within platform bounds
            if (feet_y - velocity.y <= platform_top and
                entity_rect.centerx >= tile_rect.left and
                entity_rect.centerx <= tile_rect.right):

                # Snap entity to platform top
                entity_rect.bottom = platform_top
                velocity.y = 0
                return True, velocity

        return False, velocity

    def resolve_top_only_collision(self, entity_rect: pygame.Rect, tile_rect: pygame.Rect,
                                  velocity: pygame.Vector2) -> Tuple[bool, pygame.Vector2]:
        """Resolve collision with top-only tiles (like floors)."""
        return self.resolve_platform_collision(entity_rect, tile_rect, velocity)

    def resolve_full_collision(
        self,
        entity_rect: pygame.Rect,
        tile_rect: pygame.Rect,
        velocity: pygame.Vector2,
    ) -> Tuple[str, float]:
        """Return collision side and penetration depth (no rect mutation here)."""
        overlap_left = entity_rect.right - tile_rect.left
        overlap_right = tile_rect.right - entity_rect.left
        overlap_top = entity_rect.bottom - tile_rect.top
        overlap_bottom = tile_rect.bottom - entity_rect.top

        # Smallest positive overlap decides axis
        min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)

        if min_overlap == overlap_left:
            return "left", overlap_left
        elif min_overlap == overlap_right:
            return "right", overlap_right
        elif min_overlap == overlap_top:
            return "top", overlap_top
        else:
            return "bottom", overlap_bottom

    def resolve_collisions(self, entity_rect: pygame.Rect, velocity: pygame.Vector2,
                          tile_grid: List[List[int]], delta_time: float) -> Tuple[pygame.Rect, pygame.Vector2, List[dict]]:
        """Resolve all tile collisions for an entity using separating axis method with directional checks."""
        collision_info_list = []
        
        # DEBUG: Track collision resolution
        debug_enabled = False  # Set to True to enable detailed logging

        if not tile_grid or len(tile_grid) == 0:
            return entity_rect, velocity, collision_info_list

        # Horizontal pass (X-axis) - apply velocity and resolve
        entity_rect.x += int(velocity.x)

        tiles = self.get_tiles_in_rect(entity_rect, tile_grid)
        for tile_type, tile_x, tile_y in tiles:
            tile_data = tile_registry.get_tile(tile_type)
            if not tile_data or not tile_data.has_collision:
                continue

            tile_world_x = tile_x * self.tile_size
            tile_world_y = tile_y * self.tile_size
            if tile_data.collision.collision_box_offset and tile_data.collision.collision_box_size:
                offset_x, offset_y = tile_data.collision.collision_box_offset
                collision_width, collision_height = tile_data.collision.collision_box_size
            else:
                # Fallback to full tile size
                offset_x, offset_y = 0, 0
                collision_width, collision_height = self.tile_size, self.tile_size

            tile_rect = pygame.Rect(
                tile_world_x + offset_x,
                tile_world_y + offset_y,
                collision_width,
                collision_height
            )

            if not entity_rect.colliderect(tile_rect):
                continue

            collision_type = tile_data.collision.collision_type
            


            if collision_type == "full":
                overlap_left = entity_rect.right - tile_rect.left
                overlap_right = tile_rect.right - entity_rect.left

                if overlap_left < overlap_right:
                    # Hit left side of tile: only if moving RIGHT into it
                    if velocity.x > 0:
                        entity_rect.right = tile_rect.left
                        velocity.x = 0

                        collision_info_list.append({
                            "tile_type": tile_type,
                            "side": "left",
                            "tile_data": tile_data,
                        })
                else:
                    # Hit right side of tile: only if moving LEFT into it
                    if velocity.x < 0:
                        entity_rect.left = tile_rect.right
                        velocity.x = 0

                        collision_info_list.append({
                            "tile_type": tile_type,
                            "side": "right",
                            "tile_data": tile_data,
                        })

        # Vertical pass (Y-axis) - apply velocity and resolve
        entity_rect.y += int(velocity.y)

        tiles = self.get_tiles_in_rect(entity_rect, tile_grid)
        for tile_type, tile_x, tile_y in tiles:
            tile_data = tile_registry.get_tile(tile_type)
            if not tile_data or not tile_data.has_collision:
                continue

            tile_world_x = tile_x * self.tile_size
            tile_world_y = tile_y * self.tile_size
            if tile_data.collision.collision_box_offset and tile_data.collision.collision_box_size:
                offset_x, offset_y = tile_data.collision.collision_box_offset
                collision_width, collision_height = tile_data.collision.collision_box_size
            else:
                # Fallback to full tile size
                offset_x, offset_y = 0, 0
                collision_width, collision_height = self.tile_size, self.tile_size

            tile_rect = pygame.Rect(
                tile_world_x + offset_x,
                tile_world_y + offset_y,
                collision_width,
                collision_height
            )

            if not entity_rect.colliderect(tile_rect):
                continue

            collision_type = tile_data.collision.collision_type

            if collision_type == "top_only":
                # One-way platform: only from above while falling
                if velocity.y > 0:
                    entity_rect.bottom = tile_rect.top
                    velocity.y = 0

                    collision_info_list.append({
                        "tile_type": tile_type,
                        "side": "top",
                        "tile_data": tile_data,
                    })

            elif collision_type == "full":
                # Compute overlaps
                overlap_top = entity_rect.bottom - tile_rect.top      # penetration when coming from above
                overlap_bottom = tile_rect.bottom - entity_rect.top   # penetration when coming from below

                # Skip if no vertical penetration
                if overlap_top <= 0 and overlap_bottom <= 0:
                    continue

                # Handle floor (standing ON tile): only when moving downward
                if overlap_top > 0 and overlap_top <= overlap_bottom and velocity.y >= 0:
                    entity_rect.bottom = tile_rect.top
                    velocity.y = 0

                    collision_info_list.append({
                        "tile_type": tile_type,
                        "side": "top",
                        "tile_data": tile_data,
                    })

                # Handle ceiling (hitting tile from below): only when moving upward
                elif overlap_bottom > 0 and overlap_bottom < overlap_top and velocity.y < 0:
                    entity_rect.top = tile_rect.bottom
                    velocity.y = 0

                    collision_info_list.append({
                        "tile_type": tile_type,
                        "side": "bottom",
                        "tile_data": tile_data,
                    })


        
        return entity_rect, velocity, collision_info_list

    def can_stand_on(self, tile_type: TileType) -> bool:
        """Check if entity can stand on a tile type."""
        tile_data = tile_registry.get_tile(tile_type)
        if not tile_data:
            return False
        return tile_data.collision.can_walk_on

    def get_friction_at_pos(self, x: float, y: float, tile_grid: List[List[int]]) -> float:
        """Get friction coefficient at position."""
        tile_type = self.get_tile_at_pos(x, y, tile_grid)
        if not tile_type:
            return 1.0

        tile_data = tile_registry.get_tile(tile_type)
        return tile_data.physics.friction if tile_data else 1.0

    def get_damage_at_pos(self, x: float, y: float, tile_grid: List[List[int]]) -> int:
        """Get damage dealt by tile at position."""
        tile_type = self.get_tile_at_pos(x, y, tile_grid)
        if not tile_type:
            return 0

        tile_data = tile_registry.get_tile(tile_type)
        return tile_data.collision.damage_on_contact if tile_data else 0