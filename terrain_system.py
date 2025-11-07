"""
Terrain System - Handles different terrain types and their effects on enemy movement
"""

import math
import random
import pygame
from typing import Dict, List, Tuple, Optional, Any, Union
from enum import Enum

from config import TILE


class TerrainType(Enum):
    """Enumeration of different terrain types"""
    NORMAL = "normal"
    ROUGH = "rough"
    WATER = "water"
    MUD = "mud"
    ICE = "ice"
    LAVA = "lava"
    TOXIC = "toxic"
    STEEP = "steep"
    NARROW = "narrow"
    DESTRUCTIBLE = "destructible"


class TerrainProperties:
    """Defines properties and effects of terrain types"""
    
    def __init__(self,
                 speed_modifier: float = 1.0,
                 accessibility: Union[List[str], None] = None,
                 special_effects: Union[Dict[str, Any], None] = None,
                 color: Tuple[int, int, int] = (100, 100, 100)):
        self.speed_modifier = speed_modifier
        self.accessibility = accessibility or ['all']
        self.special_effects = special_effects or {}
        self.color = color


class TerrainSystem:
    """Manages terrain types and their effects on enemy movement"""
    
    def __init__(self):
        self.terrain_properties = self._initialize_terrain_properties()
        self.terrain_map = {}  # Will be populated by level data
        self.terrain_grid = None  # Grid-based terrain data
        
    def _initialize_terrain_properties(self) -> Dict[TerrainType, TerrainProperties]:
        """Initialize properties for all terrain types"""
        return {
            TerrainType.NORMAL: TerrainProperties(
                speed_modifier=1.0,
                accessibility=['all'],
                color=(139, 90, 43)  # Brown
            ),
            TerrainType.ROUGH: TerrainProperties(
                speed_modifier=0.7,
                accessibility=['ground', 'flying'],
                special_effects={'stamina_drain': 0.1, 'noise': True},
                color=(160, 120, 80)  # Dark brown
            ),
            TerrainType.WATER: TerrainProperties(
                speed_modifier=0.5,
                accessibility=['amphibious', 'flying'],
                special_effects={'slow_effect': 0.3, 'wet': True},
                color=(64, 164, 223)  # Blue
            ),
            TerrainType.MUD: TerrainProperties(
                speed_modifier=0.4,
                accessibility=['ground', 'flying'],
                special_effects={'stuck_chance': 0.1, 'slow_decay': 0.95},
                color=(101, 67, 33)  # Dark brown
            ),
            TerrainType.ICE: TerrainProperties(
                speed_modifier=1.5,
                accessibility=['all'],
                special_effects={'slide': True, 'control_reduction': 0.5, 'friction': 0.1},
                color=(200, 230, 255)  # Light blue
            ),
            TerrainType.LAVA: TerrainProperties(
                speed_modifier=0.8,
                accessibility=['fire_resistant', 'flying'],
                special_effects={'damage': 2, 'heat': True},
                color=(255, 69, 0)  # Red-orange
            ),
            TerrainType.TOXIC: TerrainProperties(
                speed_modifier=0.6,
                accessibility=['poison_resistant', 'flying'],
                special_effects={'poison': 1, 'damage_over_time': 0.5},
                color=(128, 0, 128)  # Purple
            ),
            TerrainType.STEEP: TerrainProperties(
                speed_modifier=0.6,
                accessibility=['climbing', 'flying'],
                special_effects={'climb_check': True, 'fall_risk': True},
                color=(105, 105, 105)  # Gray
            ),
            TerrainType.NARROW: TerrainProperties(
                speed_modifier=0.8,
                accessibility=['small', 'flying'],
                special_effects={'squeeze': True, 'restricted_movement': True},
                color=(80, 80, 80)  # Dark gray
            ),
            TerrainType.DESTRUCTIBLE: TerrainProperties(
                speed_modifier=1.0,
                accessibility=['strong', 'flying'],
                special_effects={'breakable': True, 'health': 50},
                color=(139, 69, 19)  # Brown
            )
        }
    
    def get_terrain_at(self, position: Tuple[int, int], level) -> TerrainType:
        """Get terrain type at given position"""
        x, y = position
        
        # DEBUG: Log terrain lookup
        print(f"[DEBUG] Terrain lookup at ({x}, {y}) - terrain_grid initialized: {self.terrain_grid is not None}")
        
        # Check if position is within level bounds
        if not (0 <= x < level.w * TILE and 0 <= y < level.h * TILE):
            print(f"[DEBUG] Position ({x}, {y}) out of bounds, returning NORMAL")
            return TerrainType.NORMAL
        
        # Check terrain grid if available
        if self.terrain_grid:
            grid_x = x // TILE
            grid_y = y // TILE
            
            if (0 <= grid_x < len(self.terrain_grid[0]) and
                0 <= grid_y < len(self.terrain_grid)):
                terrain_name = self.terrain_grid[grid_y][grid_x]
                terrain_type = TerrainType(terrain_name)
                print(f"[DEBUG] Found terrain: {terrain_type} at grid ({grid_x}, {grid_y})")
                return terrain_type
            else:
                print(f"[DEBUG] Grid coordinates ({grid_x}, {grid_y}) out of range")
        else:
            print(f"[DEBUG] No terrain grid available, using default NORMAL")
        
        # Default to normal terrain
        return TerrainType.NORMAL
    
    def can_access(self, enemy, terrain_type: TerrainType) -> bool:
        """Check if enemy can access given terrain type"""
        if terrain_type not in self.terrain_properties:
            return True
        
        terrain = self.terrain_properties[terrain_type]
        
        # Check if all enemies can access
        if 'all' in terrain.accessibility:
            return True
        
        # Check enemy-specific traits
        enemy_traits = getattr(enemy, 'terrain_traits', [])
        
        # Check for flying enemies
        if 'flying' in enemy_traits and 'flying' in terrain.accessibility:
            return True
        
        # Check for specific traits
        for trait in enemy_traits:
            if trait in terrain.accessibility:
                return True
        
        return False
    
    def apply_terrain_effects(self, enemy, terrain_type: TerrainType) -> bool:
        """Apply terrain effects to enemy"""
        if terrain_type not in self.terrain_properties:
            return True
        
        terrain = self.terrain_properties[terrain_type]
        
        # Check if enemy can access this terrain
        if not self.can_access(enemy, terrain_type):
            return False
        
        # Apply speed modifier
        enemy.speed_multiplier = terrain.speed_modifier
        
        # Apply special effects
        for effect, value in terrain.special_effects.items():
            self._apply_special_effect(enemy, effect, value)
        
        return True
    
    def _apply_special_effect(self, enemy, effect: str, value: Any):
        """Apply special terrain effects to enemy"""
        if effect == 'stamina_drain':
            if hasattr(enemy, 'stamina'):
                enemy.stamina = max(0, enemy.stamina - value)
        
        elif effect == 'slow_effect':
            current_slow = getattr(enemy, 'slow_mult', 1.0)
            enemy.slow_mult = max(0.1, current_slow - value)
        
        elif effect == 'slide':
            enemy.sliding = True
            enemy.friction = 0.05  # Very low friction for ice
        
        elif effect == 'control_reduction':
            enemy.control_modifier = max(0.1, getattr(enemy, 'control_modifier', 1.0) - value)
        
        elif effect == 'damage':
            if hasattr(enemy, 'take_damage'):
                enemy.take_damage(value)
        
        elif effect == 'poison':
            if hasattr(enemy, 'apply_poison'):
                enemy.apply_poison(value)
        
        elif effect == 'stuck_chance':
            if random.random() < value:
                enemy.stuck = True
                enemy.stuck_timer = 30  # Stuck for 0.5 seconds
        
        elif effect == 'wet':
            enemy.wet = True
            # Wet enemies might have reduced friction
            enemy.friction = getattr(enemy, 'friction', 0.8) * 0.7
        
        elif effect == 'noise':
            # Rough terrain makes noise, might alert other enemies
            enemy.making_noise = True
    
    def find_alternative_path(self, enemy, start_pos: Tuple[int, int],
                           goal_pos, level) -> Optional[List[Tuple[int, int]]]:
        """Find alternative path that avoids inaccessible terrain"""
        # Simple implementation - try to find path around terrain
        # In a full implementation, this would use A* with terrain costs
        
        # Convert goal_pos to tuple if it's not already
        if hasattr(goal_pos, 'rect'):
            # It's an enemy or player object
            goal_tuple = (goal_pos.rect.centerx, goal_pos.rect.centery)
        elif isinstance(goal_pos, (list, tuple)) and len(goal_pos) >= 2:
            # It's already a coordinate
            goal_tuple = (int(goal_pos[0]), int(goal_pos[1]))
        else:
            # Fallback
            goal_tuple = start_pos
        
        path = []
        current = start_pos
        
        # Try direct path first
        if self._is_path_clear(current, goal_tuple, enemy, level):
            return [goal_tuple]
        
        # Try to go around obstacles
        mid_points = self._find_waypoints(current, goal_tuple, enemy, level)
        
        for point in mid_points:
            path.append(point)
        
        path.append(goal_tuple)
        return path if len(path) > 1 else None
    
    def _is_path_clear(self, start: Tuple[int, int], end: Tuple[int, int], 
                       enemy, level) -> bool:
        """Check if path is clear for enemy"""
        steps = 20
        for i in range(steps + 1):
            t = i / steps
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            
            terrain = self.get_terrain_at((int(x), int(y)), level)
            if not self.can_access(enemy, terrain):
                return False
        
        return True
    
    def _find_waypoints(self, start: Tuple[int, int], goal: Tuple[int, int], 
                       enemy, level) -> List[Tuple[int, int]]:
        """Find waypoints to navigate around terrain"""
        waypoints = []
        
        # Try perpendicular directions
        dx = goal[0] - start[0]
        dy = goal[1] - start[1]
        
        # Try going around from the sides
        if abs(dx) > abs(dy):
            # Try going up or down first
            for offset in [-100, 100]:
                waypoint = (start[0], start[1] + offset)
                if self._is_valid_waypoint(waypoint, enemy, level):
                    waypoints.append(waypoint)
                    break
        else:
            # Try going left or right first
            for offset in [-100, 100]:
                waypoint = (start[0] + offset, start[1])
                if self._is_valid_waypoint(waypoint, enemy, level):
                    waypoints.append(waypoint)
                    break
        
        return waypoints
    
    def _is_valid_waypoint(self, position: Tuple[int, int], enemy, level) -> bool:
        """Check if waypoint is valid for enemy"""
        terrain = self.get_terrain_at(position, level)
        return self.can_access(enemy, terrain)
    
    def load_terrain_from_level(self, level):
        """Load terrain data from level"""
        # This would integrate with your level loading system
        # For now, create a simple default terrain grid
        if hasattr(level, 'terrain_data'):
            self.terrain_grid = level.terrain_data
            print(f"[DEBUG] Loaded terrain data from level: {len(self.terrain_grid)}x{len(self.terrain_grid[0]) if self.terrain_grid else 0}")
        else:
            # Create default terrain grid
            width = level.w // TILE  # Convert from pixels to tiles
            height = level.h // TILE  # Convert from pixels to tiles
            self.terrain_grid = [['normal' for _ in range(width)] for _ in range(height)]
            print(f"[DEBUG] Created default terrain grid: {width}x{height}")
    
    def draw_terrain_overlay(self, surface, camera, show_terrain=False):
        """Draw terrain overlay for debugging"""
        if not show_terrain or not self.terrain_grid:
            return
        
        for y, row in enumerate(self.terrain_grid):
            for x, terrain_name in enumerate(row):
                terrain_type = TerrainType(terrain_name)
                if terrain_type in self.terrain_properties:
                    color = self.terrain_properties[terrain_type].color
                    
                    # Draw semi-transparent rectangle
                    rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                    screen_rect = camera.to_screen_rect(rect)
                    
                    # Create surface with alpha
                    s = pygame.Surface((TILE, TILE))
                    s.set_alpha(50)  # Semi-transparent
                    s.fill(color)
                    surface.blit(s, screen_rect)


# Global terrain system instance
terrain_system = TerrainSystem()