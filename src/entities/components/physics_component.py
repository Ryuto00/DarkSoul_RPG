"""
Physics Component - Shared physics and collision handling for all entities
Eliminates code duplication across player and enemy classes
"""

import pygame
from typing import Optional
from config import GRAVITY, TERMINAL_VY, TILE
try:
    from ..utils.tile_utils import (
        has_side_collision, has_top_collision, has_bottom_collision,
        check_collision_at_tile, is_platform_tile
    )
except ImportError:
    # Fallback for different import paths
    from src.utils.tile_utils import (
        has_side_collision, has_top_collision, has_bottom_collision,
        check_collision_at_tile, is_platform_tile
    )


class PhysicsComponent:
    """Handles physics and collision detection for entities"""
    
    def __init__(self, entity):
        self.entity = entity
        self.gravity_multiplier = 1.0
        self.terminal_velocity = TERMINAL_VY
        self.friction = 0.8
        self.bounce_factor = 0.5
        
    def apply_gravity(self, gravity_multiplier=None):
        """Apply gravity to entity's vertical velocity"""
        if gravity_multiplier is None:
            gravity_multiplier = self.gravity_multiplier
            
        # Only apply if entity is gravity affected
        if getattr(self.entity, 'gravity_affected', True):
            self.entity.vy = min(
                self.entity.vy + GRAVITY * gravity_multiplier, 
                self.terminal_velocity
            )
    
    def handle_horizontal_movement(self, level):
        """Handle horizontal movement and collision"""
        if not hasattr(self.entity, 'vx') or self.entity.vx == 0:
            return
            
        old_x = self.entity.rect.x
        self.entity.rect.x += int(self.entity.vx)
        
        # Check collisions with solids
        for solid in level.solids:
            if self.entity.rect.colliderect(solid):
                if self.entity.vx > 0:
                    # Moving right, hit left side of solid
                    self.entity.rect.right = solid.left
                    self.entity.vx *= -self.bounce_factor
                    # Set wall collision flags for entities that need them
                    if hasattr(self.entity, 'on_right_wall'):
                        self.entity.on_right_wall = True
                else:
                    # Moving left, hit right side of solid
                    self.entity.rect.left = solid.right
                    self.entity.vx *= -self.bounce_factor
                    # Set wall collision flags for entities that need them
                    if hasattr(self.entity, 'on_left_wall'):
                        self.entity.on_left_wall = True
    
    def handle_vertical_movement(self, level):
        """Handle vertical movement and collision"""
        if not hasattr(self.entity, 'vy'):
            return
            
        old_y = self.entity.rect.y
        was_on_ground = getattr(self.entity, 'on_ground', False)
        self.entity.on_ground = False  # Reset ground detection
        
        self.entity.rect.y += int(self.entity.vy)
        
        # Check collisions with solids
        for solid in level.solids:
            if self.entity.rect.colliderect(solid):
                if self.entity.vy > 0:
                    # Moving down, hit top of solid
                    if self.entity.rect.bottom > solid.top and old_y + self.entity.rect.height <= solid.top:
                        self.entity.rect.bottom = solid.top
                        self.entity.vy = 0
                        self.entity.on_ground = True
                elif self.entity.vy < 0:
                    # Moving up, hit bottom of solid
                    if self.entity.rect.top < solid.bottom and old_y >= solid.bottom:
                        self.entity.rect.top = solid.bottom
                        self.entity.vy = 0
    
    def handle_ground_collision(self, level):
        """Check and handle ground collision specifically"""
        was_on_ground = getattr(self.entity, 'on_ground', False)
        self.entity.on_ground = False
        
        # Check if entity is standing on any solid
        for solid in level.solids:
            if self.entity.rect.colliderect(solid):
                if self.entity.rect.bottom > solid.top and self.entity.vy >= 0:
                    self.entity.rect.bottom = solid.top
                    self.entity.vy = 0
                    self.entity.on_ground = True
                    break
    
    def handle_wall_collision(self, level):
        """Check and handle wall collision specifically"""
        # Reset wall flags if they exist
        if hasattr(self.entity, 'on_left_wall'):
            self.entity.on_left_wall = False
        if hasattr(self.entity, 'on_right_wall'):
            self.entity.on_right_wall = False
            
        # Check for wall collisions
        expanded_rect = self.entity.rect.inflate(2, 0)  # Expand horizontally by 1 pixel each side
        for solid in level.solids:
            if expanded_rect.colliderect(solid):
                # Determine which side the wall is on
                if self.entity.rect.centerx < solid.centerx:  # Wall is to the right
                    if abs(self.entity.rect.right - solid.left) <= 2:  # Within 2 pixels
                        if hasattr(self.entity, 'on_right_wall'):
                            self.entity.on_right_wall = True
                else:  # Wall is to the left
                    if abs(self.entity.rect.left - solid.right) <= 2:  # Within 2 pixels
                        if hasattr(self.entity, 'on_left_wall'):
                            self.entity.on_left_wall = True
    
    def apply_friction(self):
        """Apply friction to horizontal movement"""
        if getattr(self.entity, 'on_ground', False) and hasattr(self.entity, 'vx'):
            self.entity.vx *= self.friction
            # Stop very small movement
            if abs(self.entity.vx) < 0.1:
                self.entity.vx = 0
    
    def clamp_to_level_bounds(self, level):
        """Keep entity within level boundaries"""
        level_width_px = getattr(level, "w", 0) * TILE if hasattr(level, "w") else 0
        level_height_px = getattr(level, "h", 0) * TILE if hasattr(level, "h") else 0
        
        # Horizontal bounds
        if level_width_px > 0:
            if self.entity.rect.left < 0:
                self.entity.rect.left = 0
                self.entity.vx = abs(getattr(self.entity, "vx", 0))
            elif self.entity.rect.right > level_width_px:
                self.entity.rect.right = level_width_px
                self.entity.vx = -abs(getattr(self.entity, "vx", 0))
        
        # Vertical bounds
        if self.entity.rect.top < 0:
            self.entity.rect.top = 0
            self.entity.vy = max(0, getattr(self.entity, "vy", 0))
        # Don't clamp bottom - allow falling off screen if that's intended
    
    def update_physics(self, level, gravity_multiplier=1.0, use_tile_collision=False):
        """Complete physics update for one frame"""
        # Apply gravity
        self.apply_gravity(gravity_multiplier)

        # Handle movement and collisions
        if use_tile_collision and hasattr(level, 'grid'):
            self.handle_tile_horizontal_collision(level)
            self.handle_tile_vertical_collision(level)
        else:
            self.handle_horizontal_movement(level)
            self.handle_vertical_movement(level)

        # Apply friction if on ground
        self.apply_friction()

        # Keep in bounds
        self.clamp_to_level_bounds(level)
    
    def update_physics_simple(self, level, gravity_multiplier=1.0):
        """Simplified physics update for entities with custom movement logic"""
        # Apply gravity only
        self.apply_gravity(gravity_multiplier)

        # Handle ground collision
        self.handle_ground_collision(level)

        # Handle wall collision if entity has wall flags
        if hasattr(self.entity, 'on_left_wall') or hasattr(self.entity, 'on_right_wall'):
            self.handle_wall_collision(level)

        # Keep in bounds
        self.clamp_to_level_bounds(level)

    def get_tile_at_pos(self, x: int, y: int, level) -> Optional[int]:
        """Get tile value at pixel position."""
        if hasattr(level, 'grid'):
            tile_x = x // TILE
            tile_y = y // TILE
            if 0 <= tile_y < len(level.grid) and 0 <= tile_x < len(level.grid[0]):
                return level.grid[tile_y][tile_x]
        return None

    def check_tile_collision_horizontal(self, level, new_x: int) -> bool:
        """Check if moving to new_x would cause horizontal collision with tiles."""
        if not hasattr(level, 'grid'):
            # Fall back to solid list for backward compatibility
            temp_rect = self.entity.rect.copy()
            temp_rect.x = new_x
            for solid in level.solids:
                if temp_rect.colliderect(solid):
                    return True
            return False

        # Check tile-based collision
        left_x = new_x
        right_x = new_x + self.entity.rect.width
        top_y = self.entity.rect.y
        bottom_y = self.entity.rect.y + self.entity.rect.height

        # Check corners and midpoints
        check_points = [
            (left_x, top_y),
            (left_x, bottom_y - 1),
            (right_x - 1, top_y),
            (right_x - 1, bottom_y - 1),
            (left_x, (top_y + bottom_y) // 2),
            (right_x - 1, (top_y + bottom_y) // 2)
        ]

        for px, py in check_points:
            tile = self.get_tile_at_pos(px, py, level)
            if tile and has_side_collision(tile):
                return True

        return False

    def check_tile_collision_vertical(self, level, new_y: int, vy: float) -> bool:
        """Check if moving to new_y would cause vertical collision with tiles."""
        if not hasattr(level, 'grid'):
            # Fall back to solid list for backward compatibility
            temp_rect = self.entity.rect.copy()
            temp_rect.y = new_y
            for solid in level.solids:
                if temp_rect.colliderect(solid):
                    return True
            return False

        # Check tile-based collision
        left_x = self.entity.rect.x
        right_x = self.entity.rect.x + self.entity.rect.width
        top_y = new_y
        bottom_y = new_y + self.entity.rect.height

        if vy > 0:  # Moving down - check for landing
            # Check bottom edge points
            for px in range(left_x, right_x, max(1, TILE // 4)):
                tile = self.get_tile_at_pos(px, bottom_y - 1, level)
                if tile and has_top_collision(tile):
                    # Special handling for platform tiles - can jump through
                    if is_platform_tile(tile):
                        # Only collide if we're above the platform
                        current_bottom = self.entity.rect.y + self.entity.rect.height
                        platform_top = (bottom_y - 1) // TILE * TILE
                        if current_bottom <= platform_top + 4:  # Small tolerance
                            return True
                    else:
                        return True
        elif vy < 0:  # Moving up - check for ceiling collision
            # Check top edge points
            for px in range(left_x, right_x, max(1, TILE // 4)):
                tile = self.get_tile_at_pos(px, top_y, level)
                if tile and has_bottom_collision(tile):
                    return True

        return False

    def handle_tile_horizontal_collision(self, level):
        """Handle horizontal movement with tile-based collision."""
        if not hasattr(self.entity, 'vx') or self.entity.vx == 0:
            return

        new_x = self.entity.rect.x + int(self.entity.vx)

        if self.check_tile_collision_horizontal(level, new_x):
            # Collision detected - stop at wall
            if self.entity.vx > 0:
                # Moving right - find the wall position
                tile_x = (self.entity.rect.right) // TILE
                for check_x in range(tile_x, tile_x + 5):
                    if not self.check_tile_collision_horizontal(level, check_x * TILE - self.entity.rect.width):
                        self.entity.rect.right = check_x * TILE
                        break
                else:
                    self.entity.rect.x = new_x - int(self.entity.vx)
            else:
                # Moving left - find the wall position
                tile_x = self.entity.rect.left // TILE
                for check_x in range(tile_x, max(-1, tile_x - 5), -1):
                    if not self.check_tile_collision_horizontal(level, check_x * TILE):
                        self.entity.rect.left = check_x * TILE
                        break
                else:
                    self.entity.rect.x = new_x - int(self.entity.vx)

            self.entity.vx = 0

            # Update wall flags
            if hasattr(self.entity, 'on_left_wall') or hasattr(self.entity, 'on_right_wall'):
                self.handle_wall_collision(level)
        else:
            # No collision - move normally
            self.entity.rect.x = new_x

    def handle_tile_vertical_collision(self, level):
        """Handle vertical movement with tile-based collision."""
        if not hasattr(self.entity, 'vy'):
            return

        old_y = self.entity.rect.y
        new_y = self.entity.rect.y + int(self.entity.vy)
        was_on_ground = getattr(self.entity, 'on_ground', False)
        self.entity.on_ground = False

        if self.check_tile_collision_vertical(level, new_y, self.entity.vy):
            # Collision detected
            if self.entity.vy > 0:
                # Moving down - land on surface
                tile_y = (self.entity.rect.bottom - 1) // TILE
                for check_y in range(tile_y, min(len(level.grid), tile_y + 5)):
                    test_bottom = check_y * TILE
                    if not self.check_tile_collision_vertical(level, test_bottom - self.entity.rect.height, self.entity.vy):
                        self.entity.rect.bottom = test_bottom
                        self.entity.on_ground = True
                        break
                else:
                    self.entity.rect.y = old_y
                self.entity.vy = 0
            else:
                # Moving up - hit ceiling
                tile_y = self.entity.rect.top // TILE
                for check_y in range(tile_y, max(-1, tile_y - 5), -1):
                    test_top = check_y * TILE
                    if not self.check_tile_collision_vertical(level, test_top, self.entity.vy):
                        self.entity.rect.top = test_top
                        break
                else:
                    self.entity.rect.y = old_y
                self.entity.vy = 0
        else:
            # No collision - move normally
            self.entity.rect.y = new_y
    