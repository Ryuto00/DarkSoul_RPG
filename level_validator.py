"""
Enhanced Level Validator - Comprehensive validation system for generated levels
Ensures every generated map is fully playable according to architectural design
"""

import time
import math
import random
from typing import List, Tuple, Dict, Any, Optional, Set
from dataclasses import dataclass
from collections import defaultdict

from config import (
    TILE, LEVEL_WIDTH, LEVEL_HEIGHT, GENERATION_TIME_TARGET,
    MAX_VALIDATION_ATTEMPTS, REPAIR_ATTEMPTS
)
from terrain_system import TerrainTypeRegistry, TerrainTag
from area_system import AreaMap, AreaRegistry, Area, AreaType


@dataclass
class ValidationMetrics:
    """Performance and complexity metrics for validation"""
    generation_time_ms: float = 0.0
    validation_time_ms: float = 0.0
    memory_usage_mb: float = 0.0
    complexity_score: float = 0.0
    connectivity_ratio: float = 0.0
    pathfinding_success_rate: float = 0.0
    repair_attempts: int = 0
    validation_steps: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.validation_steps is None:
            self.validation_steps = []


@dataclass
class EntitySpawnPoint:
    """Represents a validated entity spawn point"""
    position: Tuple[int, int]
    entity_type: str
    terrain_compatible: bool
    safe_from_hazards: bool
    reachable_to_player: bool
    line_of_sight_to_player: bool = False


class ValidationResult:
    """Enhanced result of level validation with detailed reporting"""
    
    def __init__(self, is_valid: bool, message: str, issues: Optional[List[str]] = None,
                 metrics: Optional[ValidationMetrics] = None, suggestions: Optional[List[str]] = None):
        self.is_valid = is_valid
        self.message = message
        self.issues = issues if issues is not None else []
        self.metrics = metrics if metrics is not None else ValidationMetrics()
        self.suggestions = suggestions if suggestions is not None else []
        self.entity_spawns = []
        self.repair_history = []
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []
        if self.suggestions is None:
            self.suggestions = []
        if self.entity_spawns is None:
            self.entity_spawns = []
        if self.repair_history is None:
            self.repair_history = []


class EnhancedLevelValidator:
    """Comprehensive level validator ensuring full playability"""
    
    def __init__(self):
        # Validation thresholds from config
        self.min_spawn_points = 1
        self.max_empty_ratio = 0.8
        self.min_connectivity_ratio = 0.7
        self.min_room_size = 3
        self.max_isolated_tiles_ratio = 0.05
        
        # Performance tracking
        self.validation_start_time = 0
        self.metrics = ValidationMetrics()
        
        # Enemy type definitions for validation
        self.enemy_types = {
            'Bug': {'traits': ['ground', 'small', 'narrow'], 'size': (28, 22), 'vision_range': 200},
            'Boss': {'traits': ['ground', 'strong', 'destructible'], 'size': (64, 48), 'vision_range': 300},
            'Frog': {'traits': ['ground', 'amphibious'], 'size': (28, 22), 'vision_range': 220},
            'Archer': {'traits': ['ground'], 'size': (28, 22), 'vision_range': 350},
            'WizardCaster': {'traits': ['ground', 'floating'], 'size': (28, 22), 'vision_range': 280},
            'Assassin': {'traits': ['ground', 'small', 'narrow', 'jumping'], 'size': (28, 22), 'vision_range': 240},
            'Bee': {'traits': ['flying', 'air'], 'size': (24, 20), 'vision_range': 240},
            'Golem': {'traits': ['ground', 'strong', 'destructible', 'fire_resistant'], 'size': (56, 44), 'vision_range': 500}
        }
        
        # Player mechanics for validation
        self.player_traits = ['ground', 'jumping', 'dashing']
        self.player_size = (18, 30)
        self.player_jump_height = 10.2
        self.player_dash_distance = 12.0
        
        # Cache for performance optimization
        self.connectivity_cache = {}
        self.pathfinding_cache = {}
    
    def validate(self, level_data: Dict[str, Any]) -> ValidationResult:
        """
        Comprehensive validation of a generated level
        
        Args:
            level_data: Dictionary containing level data from generation algorithms
            
        Returns:
            Enhanced ValidationResult with detailed validation status and metrics
        """
        self.validation_start_time = time.time()
        self.metrics = ValidationMetrics()
        self.metrics.validation_steps = []
        
        issues = []
        suggestions = []
        
        # Extract level components
        grid = level_data.get('grid', [])
        terrain_grid = level_data.get('terrain_grid', [])
        rooms = level_data.get('rooms', [])
        spawn_points = level_data.get('spawn_points', [])
        enemy_spawns = level_data.get('enemy_spawns', [])
        level_type = level_data.get('type', 'dungeon')

        # Areas: accept either pre-built AreaMap or serializable structure.
        raw_areas = level_data.get('areas')
        if isinstance(raw_areas, AreaMap):
            areas_map = raw_areas
        else:
            areas_map = AreaMap()
            if isinstance(raw_areas, list):
                # Expect dictionaries with required fields; ignore malformed entries defensively.
                for i, a in enumerate(raw_areas):
                    if not isinstance(a, dict):
                        continue
                    try:
                        areas_map.add_area(
                            Area(
                                id=str(a.get("id", f"area_{i}")),
                                type=str(a.get("type", "")),
                                x=int(a.get("x", 0)),
                                y=int(a.get("y", 0)),
                                width=int(a.get("width", 0)),
                                height=int(a.get("height", 0)),
                                attributes=dict(a.get("attributes", {})),
                            )
                        )
                    except Exception:
                        # Do not break validation if some area entries are bad.
                        continue
        
        # Track validation steps
        self.metrics.validation_steps.append("extract_level_data")
        
        # Basic structure validation
        structure_issues = self._validate_basic_structure(grid)
        if structure_issues:
            issues.extend(structure_issues)
            self.metrics.validation_steps.append("basic_structure_failed")
            return self._create_result(False, "Basic structure validation failed", issues, suggestions)
        
        self.metrics.validation_steps.append("basic_structure_passed")
        
        # Enhanced structural validation
        structural_issues = self._validate_enhanced_structure(grid, rooms, level_type, level_data)
        issues.extend(structural_issues)
        self.metrics.validation_steps.append("enhanced_structure")
        
        # Gameplay validation
        gameplay_issues = self._validate_gameplay(grid, terrain_grid, spawn_points, level_type)
        issues.extend(gameplay_issues)
        self.metrics.validation_steps.append("gameplay_validation")

        # Area/zone validation (uses data-driven AreaRegistry if we have terrain + areas)
        # NOTE: This is additive and must NOT replace legacy critical checks that tests expect
        # (portal reachability, enemy reachability, etc.).
        if terrain_grid and 'areas' in level_data:
            try:
                if isinstance(level_data['areas'], AreaMap):
                    areas_map_for_rules = level_data['areas']
                elif isinstance(level_data['areas'], list):
                    # Reconstruct a temporary AreaMap from serializable form
                    tmp_map = AreaMap()
                    for i, a in enumerate(level_data['areas']):
                        if not isinstance(a, dict):
                            continue
                        try:
                            tmp_map.add_area(
                                Area(
                                    id=str(a.get("id", f"area_{i}")),
                                    type=str(a.get("type", "")),
                                    x=int(a.get("x", 0)),
                                    y=int(a.get("y", 0)),
                                    width=int(a.get("width", 0)),
                                    height=int(a.get("height", 0)),
                                    attributes=dict(a.get("attributes", {})),
                                )
                            )
                        except Exception:
                            continue
                    areas_map_for_rules = tmp_map
                else:
                    areas_map_for_rules = None

                if areas_map_for_rules and areas_map_for_rules.areas:
                    area_issues = AreaRegistry.validate_level_areas(
                        areas_map_for_rules,
                        level_data,
                        terrain_grid,
                    )
                    issues.extend(area_issues)
                    self.metrics.validation_steps.append("area_validation")
            except Exception:
                # Defensive: area-system issues must not break core validation contract
                issues.append("Area system validation error (non-fatal)")

        # Entity-specific validation
        entity_issues, valid_spawns = self._validate_entities(grid, terrain_grid, spawn_points, enemy_spawns)
        issues.extend(entity_issues)
        self.entity_spawns = valid_spawns
        self.metrics.validation_steps.append("entity_validation")

        # Legacy critical checks that tests explicitly assert on:
        # - Portal reachability
        # - Enemy reachability
        # These operate on level_data and must remain active.
        legacy_portal_issues = self._validate_portal_reachability(grid, level_data)
        issues.extend(legacy_portal_issues)
        self.metrics.validation_steps.append("legacy_portal_reachability")

        legacy_enemy_issues = self._validate_enemy_reachability(grid, level_data)
        issues.extend(legacy_enemy_issues)
        self.metrics.validation_steps.append("legacy_enemy_reachability")
        
        # Performance validation
        performance_issues = self._validate_performance(grid, terrain_grid)
        issues.extend(performance_issues)
        self.metrics.validation_steps.append("performance_validation")
        
        # Calculate final metrics
        self._calculate_metrics(grid, terrain_grid, issues)
        
        # Generate suggestions based on issues
        suggestions = self._generate_suggestions(issues, level_type)
        
        # Return final result
        is_valid = len(issues) == 0
        message = "Level is fully playable" if is_valid else f"Validation failed: {'; '.join(issues[:5])}"
        
        self.metrics.validation_time_ms = (time.time() - self.validation_start_time) * 1000
        
        return self._create_result(is_valid, message, issues, suggestions)
    
    def _validate_basic_structure(self, grid: List[List[int]]) -> List[str]:
        """Validate basic level structure"""
        issues = []
        
        if not grid:
            return ["No grid data found"]
        
        height = len(grid)
        width = len(grid[0]) if height > 0 else 0
        
        if width == 0 or height == 0:
            return ["Empty grid dimensions"]
        
        # Validate grid consistency
        expected_width = len(grid[0])
        for row_idx, row in enumerate(grid):
            if len(row) != expected_width:
                issues.append(f"Inconsistent grid row length at row {row_idx}")
        
        return issues
    
    def _validate_enhanced_structure(self, grid: List[List[int]], rooms: List, level_type: str, level_data: Dict[str, Any]) -> List[str]:
        """Enhanced structural validation including connectivity, boundaries, rooms, and paths"""
        issues = []
        
        # Boundary validation
        boundary_issues = self._validate_boundaries(grid)
        issues.extend(boundary_issues)
        
        # Connectivity validation
        connectivity_issues = self._validate_connectivity(grid)
        issues.extend(connectivity_issues)
        
        # Room validation
        room_issues = self._validate_rooms(grid, rooms, level_type)
        issues.extend(room_issues)
        
        # Path validation
        path_issues = self._validate_paths(grid)
        issues.extend(path_issues)
        
        return issues
    
    def _validate_boundaries(self, grid: List[List[int]]) -> List[str]:
        """Validate level boundaries are properly sealed"""
        issues = []
        height = len(grid)
        width = len(grid[0]) if height > 0 else 0
        
        # STRICT: All outer boundary tiles must be walls for generated levels
        # Check top and bottom boundaries
        for x in range(width):
            if grid[0][x] != 1:  # Not a wall
                issues.append(f"Top boundary at ({x}, 0) is not a wall - must be sealed")
            if grid[height - 1][x] != 1:  # Not a wall
                issues.append(f"Bottom boundary at ({x}, {height-1}) is not a wall - must be sealed")
        
        # Check left and right boundaries
        for y in range(height):
            if grid[y][0] != 1:  # Not a wall
                issues.append(f"Left boundary at (0, {y}) is not a wall - must be sealed")
            if grid[y][width - 1] != 1:  # Not a wall
                issues.append(f"Right boundary at ({width-1}, {y}) is not a wall - must be sealed")
        
        return issues

    def _validate_portal_reachability(self, grid: List[List[int]], level_data: Dict[str, Any]) -> List[str]:
        """Validate that portal is reachable from player spawn"""
        issues = []
        
        # Extract player spawn and portal position
        spawn_points = level_data.get('spawn_points', [])
        if not spawn_points:
            issues.append("No player spawn points found")
            return issues
        
        # Get player spawn (use first spawn point)
        player_spawn = spawn_points[0]
        sx, sy = player_spawn
        
        # Validate player spawn is on floor
        height = len(grid)
        width = len(grid[0]) if height > 0 else 0
        if not (0 <= sy < height and 0 <= sx < width):
            issues.append(f"Player spawn ({sx}, {sy}) is out of bounds")
            return issues
        
        if grid[sy][sx] != 0:
            issues.append(f"Player spawn ({sx}, {sy}) is not on floor")
            return issues
        
        # Check for portal in level data
        portal_pos = level_data.get('portal_pos')
        if portal_pos is None:
            issues.append("No portal position found in level data")
            return issues
        
        # Convert portal pixel coordinates to tile coordinates
        from config import TILE
        portal_tx = portal_pos[0] // TILE
        portal_ty = portal_pos[1] // TILE
        
        # Validate portal position
        if not (0 <= portal_ty < height and 0 <= portal_tx < width):
            issues.append(f"Portal position ({portal_tx}, {portal_ty}) is out of bounds")
            return issues
        
        if grid[portal_ty][portal_tx] != 0:
            issues.append(f"Portal position ({portal_tx}, {portal_ty}) is not on floor")
            return issues
        
        # Check reachability using BFS
        if not self._can_pathfind(grid, player_spawn, (portal_tx, portal_ty)):
            issues.append(f"Portal at ({portal_tx}, {portal_ty}) is not reachable from player spawn ({sx}, {sy})")
        
        return issues

    def _validate_enemy_reachability(self, grid: List[List[int]], level_data: Dict[str, Any]) -> List[str]:
        """Validate that at least one enemy exists and is reachable from player"""
        issues = []
        
        # Extract player spawn
        spawn_points = level_data.get('spawn_points', [])
        if not spawn_points:
            issues.append("No player spawn points found for enemy validation")
            return issues
        
        player_spawn = spawn_points[0]
        sx, sy = player_spawn
        
        # Validate player spawn is on floor
        height = len(grid)
        width = len(grid[0]) if height > 0 else 0
        if not (0 <= sy < height and 0 <= sx < width):
            issues.append(f"Player spawn ({sx}, {sy}) is out of bounds")
            return issues
        
        if grid[sy][sx] != 0:
            issues.append(f"Player spawn ({sx}, {sy}) is not on floor")
            return issues
        
        # Check for enemies in level
        enemies = level_data.get('enemies', [])
        if not enemies:
            issues.append("No enemies found in level - at least one enemy must be present")
            return issues
        
        # Count reachable enemies
        reachable_enemies = 0
        for enemy in enemies:
            # Extract enemy position (assuming enemy has x, y attributes like the GeneratedLevel spawns)
            if hasattr(enemy, 'x') and hasattr(enemy, 'y'):
                # x, y are pixel coordinates; convert to integer tile coordinates
                enemy_x = int(enemy.x) // TILE
                enemy_y = int(enemy.y) // TILE
            else:
                # If enemy doesn't have x,y, try to find position in other ways
                continue

            # Validate enemy position (must be inside grid and on floor)
            if not (0 <= enemy_y < height and 0 <= enemy_x < width):
                continue
            if grid[enemy_y][enemy_x] != 0:
                continue
            
            # Check if reachable from player
            if self._can_pathfind(grid, player_spawn, (enemy_x, enemy_y)):
                reachable_enemies += 1
        
        # Require at least one reachable enemy
        if reachable_enemies == 0:
            issues.append(f"No reachable enemies found - found {len(enemies)} enemies but none are reachable from player spawn")
        
        return issues
    
    def _validate_connectivity(self, grid: List[List[int]]) -> List[str]:
        """Validate that all reachable areas are connected"""
        issues = []
        
        # Find all floor tiles
        floor_tiles = []
        for y, row in enumerate(grid):
            for x, tile in enumerate(row):
                if tile == 0:  # Floor
                    floor_tiles.append((x, y))
        
        if not floor_tiles:
            return ["No floor tiles found"]
        
        # Find connected components using flood fill
        visited = set()
        components = []
        
        for tile in floor_tiles:
            if tile not in visited:
                component = self._flood_fill(grid, tile)
                visited.update(component)
                components.append(component)
        
        # Check if main component is large enough
        if components:
            main_component_size = max(len(comp) for comp in components)
            connectivity_ratio = main_component_size / len(floor_tiles)
            self.metrics.connectivity_ratio = connectivity_ratio
            
            if connectivity_ratio < self.min_connectivity_ratio:
                issues.append(f"Poor connectivity: only {connectivity_ratio:.1%} of floor is connected")
            
            # Check for isolated small components
            small_components = [comp for comp in components if len(comp) < 5]
            if len(small_components) > len(floor_tiles) * 0.1:
                issues.append(f"Too many isolated small areas: {len(small_components)}")
        
        return issues
    
    def _flood_fill(self, grid: List[List[int]], start: Tuple[int, int]) -> Set[Tuple[int, int]]:
        """Flood fill algorithm to find connected floor tiles"""
        visited = set()
        to_check = [start]
        height, width = len(grid), len(grid[0])
        
        while to_check:
            x, y = to_check.pop()
            if (x, y) in visited:
                continue
            
            if 0 <= x < width and 0 <= y < height and grid[y][x] == 0:
                visited.add((x, y))
                
                # Check 4-directional neighbors
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    nx, ny = x + dx, y + dy
                    if (nx, ny) not in visited:
                        to_check.append((nx, ny))
        
        return visited
    
    def _validate_rooms(self, grid: List[List[int]], rooms: List, level_type: str) -> List[str]:
        """Validate rooms have proper size and accessibility"""
        issues = []
        
        if not rooms:
            return ["No rooms defined for level"]
        
        # Check room sizes
        small_rooms = 0
        inaccessible_rooms = 0
        
        for room in rooms:
            room_width = getattr(room, 'width', 0)
            room_height = getattr(room, 'height', 0)
            room_x = getattr(room, 'x', 0)
            room_y = getattr(room, 'y', 0)
            
            # Check minimum room size
            if room_width < self.min_room_size or room_height < self.min_room_size:
                small_rooms += 1
            
            # Check room accessibility (has floor tiles)
            has_floor = False
            for y in range(max(0, room_y), min(len(grid), room_y + room_height)):
                for x in range(max(0, room_x), min(len(grid[0]), room_x + room_width)):
                    if grid[y][x] == 0:
                        has_floor = True
                        break
                if has_floor:
                    break
            
            if not has_floor:
                inaccessible_rooms += 1
        
        if small_rooms > len(rooms) * 0.5:
            issues.append(f"Too many small rooms: {small_rooms}/{len(rooms)}")
        
        if inaccessible_rooms > 0:
            issues.append(f"Inaccessible rooms found: {inaccessible_rooms}")
        
        # Level-specific room validation
        if level_type == "dungeon" and len(rooms) < 2:
            issues.append("Insufficient rooms for dungeon level")
        
        return issues
    
    def _validate_paths(self, grid: List[List[int]]) -> List[str]:
        """Validate valid paths exist between key points"""
        issues = []
        
        # Find all floor tiles
        floor_tiles = []
        for y, row in enumerate(grid):
            for x, tile in enumerate(row):
                if tile == 0:
                    floor_tiles.append((x, y))
        
        if len(floor_tiles) < 2:
            return ["Insufficient floor tiles for path validation"]
        
        # Check pathfinding between distant points
        pathfinding_successes = 0
        total_tests = min(10, len(floor_tiles) // 2)
        
        for i in range(total_tests):
            # Pick random start and end points
            start = floor_tiles[i * 2]
            end = floor_tiles[min(i * 2 + 1, len(floor_tiles) - 1)]
            
            # Simple pathfinding check (A* would be better but this is faster)
            if self._can_pathfind(grid, start, end):
                pathfinding_successes += 1
        
        self.metrics.pathfinding_success_rate = pathfinding_successes / total_tests if total_tests > 0 else 0
        
        if self.metrics.pathfinding_success_rate < 0.8:
            issues.append(f"Poor pathfinding: only {self.metrics.pathfinding_success_rate:.1%} paths valid")
        
        return issues
    
    def _can_pathfind(self, grid: List[List[int]], start: Tuple[int, int], end: Tuple[int, int]) -> bool:
        """Simple pathfinding check between two points"""
        if start == end:
            return True
        
        # Use BFS for pathfinding
        visited = set()
        to_check = [start]
        height, width = len(grid), len(grid[0])
        
        while to_check:
            x, y = to_check.pop(0)
            if (x, y) == end:
                return True
            
            if (x, y) in visited:
                continue
            
            visited.add((x, y))
            
            # Check 4-directional neighbors
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if (0 <= nx < width and 0 <= ny < height and 
                    grid[ny][nx] == 0 and (nx, ny) not in visited):
                    to_check.append((nx, ny))
        
        return False
    
    def _validate_gameplay(self, grid: List[List[int]], terrain_grid: List[List[str]], 
                         spawn_points: List[Tuple[int, int]], level_type: str) -> List[str]:
        """Validate gameplay factors including player spawn, combat space, and terrain traversal"""
        issues = []
        
        # Player spawn validation
        spawn_issues = self._validate_player_spawn(grid, terrain_grid, spawn_points)
        issues.extend(spawn_issues)
        
        # Combat space validation
        combat_issues = self._validate_combat_space(grid, terrain_grid)
        issues.extend(combat_issues)
        
        # Terrain traversal validation - simplified since terrain system is removed
        terrain_issues = self._validate_terrain_traversal_simple(grid, terrain_grid)
        issues.extend(terrain_issues)
        
        return issues
    
    def _validate_player_spawn(self, grid: List[List[int]], terrain_grid: List[List[str]], 
                            spawn_points: List[Tuple[int, int]]) -> List[str]:
        """Validate player spawn points are safe and accessible"""
        issues = []
        
        if len(spawn_points) < self.min_spawn_points:
            issues.append(f"Insufficient spawn points: {len(spawn_points)} < {self.min_spawn_points}")
        
        for i, (x, y) in enumerate(spawn_points):
            # Check bounds
            if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
                issues.append(f"Spawn point {i} ({x}, {y}) is out of bounds")
                continue
            
            # Check if spawn point is on floor
            if grid[y][x] != 0:  # Not on floor
                issues.append(f"Spawn point {i} ({x}, {y}) is not on floor")
                continue
            
            # Check spawn point safety
            safety_issues = self._check_spawn_safety(grid, terrain_grid, x, y)
            if safety_issues:
                issues.extend([f"Spawn point {i}: {issue}" for issue in safety_issues])
        
        return issues
    
    def _check_spawn_safety(self, grid: List[List[int]], terrain_grid: List[List[str]], 
                          x: int, y: int) -> List[str]:
        """Check if spawn point has adequate safety and space"""
        issues = []
        
        # Check 3x3 area around spawn point for walls
        wall_count = 0
        
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                nx, ny = x + dx, y + dy
                
                # Skip center point (spawn point itself)
                if dx == 0 and dy == 0:
                    continue
                
                # Check bounds
                if not (0 <= ny < len(grid) and 0 <= nx < len(grid[0])):
                    wall_count += 1
                    continue
                
                # Check for walls
                if grid[ny][nx] == 1:  # Wall
                    wall_count += 1
        
        # Too many walls around spawn point
        if wall_count >= 6:
            issues.append("spawn point surrounded by walls")
        
        return issues
    
    def _validate_combat_space(self, grid: List[List[int]], terrain_grid: List[List[str]]) -> List[str]:
        """Validate adequate space for combat encounters"""
        issues = []
        
        # Find open areas suitable for combat
        open_areas = []
        current_area = []
        
        for y, row in enumerate(grid):
            for x, tile in enumerate(row):
                if tile == 0:  # Floor
                    # Check if this tile has enough space around it
                    space_score = self._calculate_space_score(grid, x, y)
                    if space_score >= 4:  # At least 4 open neighbors
                        current_area.append((x, y))
                    else:
                        if current_area:
                            open_areas.append(current_area)
                            current_area = []
                else:
                    if current_area:
                        open_areas.append(current_area)
                        current_area = []
        
        # Add the last area if it exists
        if current_area:
            open_areas.append(current_area)
        
        # Check if there are enough combat areas
        combat_areas = [area for area in open_areas if len(area) >= 9]  # 3x3 minimum
        if len(combat_areas) < 2:
            issues.append(f"Insufficient combat areas: {len(combat_areas)}")
        
        # Check for chokepoints that might make combat difficult
        chokepoints = self._find_chokepoints(grid)
        if len(chokepoints) > len(grid) * len(grid[0]) * 0.05:  # More than 5% chokepoints
            issues.append(f"Too many chokepoints: {len(chokepoints)}")
        
        return issues
    
    def _calculate_space_score(self, grid: List[List[int]], x: int, y: int) -> int:
        """Calculate space score for a tile based on open neighbors"""
        score = 0
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = x + dx, y + dy
                if (0 <= ny < len(grid) and 0 <= nx < len(grid[0]) and 
                    grid[ny][nx] == 0):
                    score += 1
        return score
    
    def _find_chokepoints(self, grid: List[List[int]]) -> List[Tuple[int, int]]:
        """Find tiles that act as chokepoints (narrow passages)"""
        chokepoints = []
        
        for y in range(1, len(grid) - 1):
            for x in range(1, len(grid[0]) - 1):
                if grid[y][x] == 0:  # Floor
                    # Check if this is a chokepoint (limited passage)
                    open_neighbors = 0
                    for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                        nx, ny = x + dx, y + dy
                        if grid[ny][nx] == 0:
                            open_neighbors += 1
                    
                    if open_neighbors == 2:  # Exactly 2 neighbors = potential chokepoint
                        chokepoints.append((x, y))
        
        return chokepoints
    
    def _validate_terrain_traversal_simple(self, grid: List[List[int]], terrain_grid: List[List[str]]) -> List[str]:
        """
        Validate terrain traversal using TerrainTypeRegistry where available.

        Still intentionally lightweight:
        - Ensure dimensions match.
        - Ensure terrain IDs resolve.
        - Ensure there is at least some variety.
        """
        issues: List[str] = []
        
        if not terrain_grid:
            return issues  # No terrain grid, nothing to validate
        
        # Dimension match
        if len(terrain_grid) != len(grid) or len(terrain_grid[0]) != len(grid[0]):
            issues.append("Terrain grid dimensions don't match level grid")
            return issues

        # Validate IDs and collect base/modifier variety.
        terrain_ids: Set[str] = set()
        base_types: Set[str] = set()
        try:
            for y, row in enumerate(terrain_grid):
                for x, tid in enumerate(row):
                    terrain_ids.add(tid)
                    try:
                        tag = TerrainTypeRegistry.get_terrain(tid)
                        base_types.add(tag.base_type)
                    except KeyError:
                        issues.append(f"Unknown terrain id '{tid}' at ({x},{y})")
        except Exception:
            # If anything goes wrong, keep issue generic to avoid crashes.
            if "terrain_resolution_error" not in issues:
                issues.append("Error while resolving terrain grid via TerrainTypeRegistry")
            return issues

        if not terrain_ids:
            issues.append("No terrain types found")
        return issues
    
    def _validate_entities(self, grid: List[List[int]], terrain_grid: List[List[str]], 
                        spawn_points: List[Tuple[int, int]], enemy_spawns: List) -> Tuple[List[str], List[EntitySpawnPoint]]:
        """Entity-specific validation including enemy reachability, terrain compatibility, and line of sight"""
        issues = []
        valid_spawns = []
        
        # Validate enemy spawns
        for i, enemy_spawn in enumerate(enemy_spawns):
            enemy_type = getattr(enemy_spawn, 'type', 'Bug')
            x, y = getattr(enemy_spawn, 'x', 0), getattr(enemy_spawn, 'y', 0)
            
            # Check if enemy type is valid
            if enemy_type not in self.enemy_types:
                issues.append(f"Unknown enemy type: {enemy_type}")
                continue
            
            # Check spawn bounds
            if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
                issues.append(f"Enemy {i} ({enemy_type}) spawn out of bounds")
                continue
            
            # Check if spawn is on floor
            if grid[y][x] != 0:
                issues.append(f"Enemy {i} ({enemy_type}) spawn not on floor")
                continue
            
            # Create spawn point validation
            spawn_validation = self._validate_enemy_spawn(grid, terrain_grid, x, y, enemy_type, spawn_points)
            valid_spawns.append(spawn_validation)
            
            # Check specific validation results
            if not spawn_validation.terrain_compatible:
                issues.append(f"Enemy {i} ({enemy_type}) terrain incompatible")
            
            if not spawn_validation.safe_from_hazards:
                issues.append(f"Enemy {i} ({enemy_type}) spawn in hazardous area")
            
            if not spawn_validation.reachable_to_player:
                issues.append(f"Enemy {i} ({enemy_type}) cannot reach player")
        
        return issues, valid_spawns
    
    def _validate_enemy_spawn(self, grid: List[List[int]], terrain_grid: List[List[str]], 
                           x: int, y: int, enemy_type: str, player_spawns: List[Tuple[int, int]]) -> EntitySpawnPoint:
        """Validate individual enemy spawn point"""
        enemy_info = self.enemy_types[enemy_type]
        
        # Check terrain compatibility - simplified
        terrain_compatible = True
        if terrain_grid and y < len(terrain_grid) and x < len(terrain_grid[0]):
            terrain_type = terrain_grid[y][x]
            terrain_compatible = self._check_terrain_compatibility(enemy_info['traits'], terrain_type)
        
        # Check safety from hazards - simplified
        safe_from_hazards = True
        # terrain system removed - assuming all terrain is safe for now
        
        # Check reachability to player
        reachable_to_player = False
        if player_spawns:
            for player_spawn in player_spawns:
                if self._can_pathfind(grid, (x, y), player_spawn):
                    reachable_to_player = True
                    break
        
        # Check line of sight to player (for ranged enemies)
        line_of_sight_to_player = False
        if enemy_type in ['Archer', 'WizardCaster'] and player_spawns:
            # Simple line of sight check (would need actual level geometry for proper check)
            player_spawn = player_spawns[0]
            line_of_sight_to_player = self._has_line_of_sight(grid, (x, y), player_spawn)
        
        return EntitySpawnPoint(
            position=(x, y),
            entity_type=enemy_type,
            terrain_compatible=terrain_compatible,
            safe_from_hazards=safe_from_hazards,
            reachable_to_player=reachable_to_player,
            line_of_sight_to_player=line_of_sight_to_player
        )
    
    def _check_terrain_compatibility(self, enemy_traits: List[str], terrain_type: str) -> bool:
        """Check if enemy traits are compatible with terrain type"""
        # terrain system removed - simplified terrain compatibility check
        # Since we don't have terrain properties, assume terrain is compatible
        # unless it's obviously hazardous
        return terrain_type not in ['lava', 'toxic', 'steep']
    
    def _has_line_of_sight(self, grid: List[List[int]], start: Tuple[int, int], end: Tuple[int, int]) -> bool:
        """Simple line of sight check between two points"""
        x1, y1 = start
        x2, y2 = end
        
        # Bresenham's line algorithm
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        
        while True:
            if grid[y1][x1] == 1:  # Wall blocks line of sight
                return False
            
            if x1 == x2 and y1 == y2:
                break
            
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x1 += sx
            if e2 < dx:
                err += dx
                y1 += sy
        
        return True
    
    def _validate_performance(self, grid: List[List[int]], terrain_grid: List[List[str]]) -> List[str]:
        """Validate performance metrics including generation time, memory usage, and complexity"""
        issues = []
        
        # Calculate complexity score
        total_tiles = len(grid) * len(grid[0])
        wall_tiles = sum(row.count(1) for row in grid)
        floor_tiles = total_tiles - wall_tiles
        
        # Complexity based on wall-to-floor ratio and level size
        wall_ratio = wall_tiles / total_tiles
        size_complexity = (total_tiles / (LEVEL_WIDTH * LEVEL_HEIGHT))  # Normalized to expected size
        self.metrics.complexity_score = wall_ratio * size_complexity
        
        # Check if complexity is too high
        if self.metrics.complexity_score > 0.8:
            issues.append(f"Level complexity too high: {self.metrics.complexity_score:.2f}")
        
        # Estimate memory usage (rough calculation)
        grid_memory = len(grid) * len(grid[0]) * 4  # 4 bytes per tile
        terrain_memory = 0
        if terrain_grid:
            terrain_memory = len(terrain_grid) * len(terrain_grid[0]) * 20  # 20 bytes per terrain type string
        
        self.metrics.memory_usage_mb = (grid_memory + terrain_memory) / (1024 * 1024)
        
        # Check memory usage
        if self.metrics.memory_usage_mb > 10:  # More than 10MB for level data
            issues.append(f"High memory usage: {self.metrics.memory_usage_mb:.1f}MB")
        
        return issues
    
    def _calculate_metrics(self, grid: List[List[int]], terrain_grid: List[List[str]], issues: List[str]):
        """Calculate final validation metrics"""
        # Count tiles
        total_tiles = len(grid) * len(grid[0])
        floor_tiles = sum(row.count(0) for row in grid)
        wall_tiles = total_tiles - floor_tiles
        
        # Calculate ratios
        floor_ratio = floor_tiles / total_tiles
        wall_ratio = wall_tiles / total_tiles
        
        # Update metrics
        self.metrics.complexity_score = wall_ratio * (total_tiles / (LEVEL_WIDTH * LEVEL_HEIGHT))
        
        # Count isolated tiles
        isolated_tiles = self._find_isolated_tiles(grid)
        isolated_ratio = len(isolated_tiles) / total_tiles
        
        # Add to metrics for reporting
        if self.metrics.validation_steps is not None:
            self.metrics.validation_steps.append(f"floor_ratio:{floor_ratio:.2f}")
            self.metrics.validation_steps.append(f"wall_ratio:{wall_ratio:.2f}")
            self.metrics.validation_steps.append(f"isolated_ratio:{isolated_ratio:.2f}")
    
    def _find_isolated_tiles(self, grid: List[List[int]]) -> List[Tuple[int, int]]:
        """Find floor tiles that are completely surrounded by walls"""
        isolated = []
        
        for y, row in enumerate(grid):
            for x, tile in enumerate(row):
                if tile != 0:  # Not floor
                    continue
                
                # Check all 8 neighbors
                wall_count = 0
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        if dx == 0 and dy == 0:
                            continue
                        
                        nx, ny = x + dx, y + dy
                        
                        # Check bounds
                        if not (0 <= ny < len(grid) and 0 <= nx < len(grid[0])):
                            wall_count += 1
                        elif grid[ny][nx] == 1:  # Wall
                            wall_count += 1
                
                # If all 8 neighbors are walls, tile is isolated
                if wall_count >= 8:
                    isolated.append((x, y))
        
        return isolated
    
    def _generate_suggestions(self, issues: List[str], level_type: str) -> List[str]:
        """Generate suggestions for fixing validation issues"""
        suggestions = []
        
        # Analyze issues and generate targeted suggestions
        issue_text = ' '.join(issues).lower()
        
        if 'connectivity' in issue_text:
            suggestions.append("Increase corridor width or add more connections between rooms")
        
        if 'boundary' in issue_text:
            suggestions.append("Ensure level boundaries are properly sealed except for designated exits")
        
        if 'spawn' in issue_text:
            suggestions.append("Add more valid spawn points away from walls and hazards")
        
        if 'room' in issue_text:
            suggestions.append("Increase minimum room size or add more rooms")
        
        if 'combat' in issue_text:
            suggestions.append("Create larger open areas suitable for combat encounters")
        
        if 'terrain' in issue_text:
            suggestions.append("Reduce hazardous terrain or ensure enemy types match terrain")
        
        if 'enemy' in issue_text:
            suggestions.append("Check enemy spawn positions and ensure they can reach the player")
        
        if 'complexity' in issue_text:
            suggestions.append("Reduce level complexity by simplifying layout or reducing size")
        
        # Level-specific suggestions
        if level_type == "dungeon" and 'room' in issue_text:
            suggestions.append("Dungeon levels should have multiple connected rooms")
        elif level_type == "cave" and 'connectivity' in issue_text:
            suggestions.append("Cave levels need more natural, winding corridors")
        elif level_type == "outdoor" and 'terrain' in issue_text:
            suggestions.append("Outdoor levels should have varied but traversable terrain")
        
        return suggestions
    
    def _create_result(self, is_valid: bool, message: str, issues: List[str], suggestions: List[str]) -> ValidationResult:
        """Create validation result with current metrics"""
        return ValidationResult(
            is_valid=is_valid,
            message=message,
            issues=issues,
            metrics=self.metrics,
            suggestions=suggestions
        )
    
    def repair_level(self, level_data: Dict[str, Any], validation_result: ValidationResult) -> Dict[str, Any]:
        """
        Enhanced auto-repair mechanisms for common level issues
        
        Args:
            level_data: Original level data
            validation_result: Validation result with issues to fix
            
        Returns:
            Repaired level data
        """
        if validation_result.is_valid:
            return level_data
        
        grid = level_data.get('grid', []).copy()
        terrain_grid = level_data.get('terrain_grid', []).copy()
        repaired_data = level_data.copy()
        repair_history = []
        
        repair_attempts = 0
        max_repairs = REPAIR_ATTEMPTS
        
        while repair_attempts < max_repairs and validation_result.issues:
            repair_attempts += 1
            issues_repaired = 0
            
            for issue in validation_result.issues:
                repaired = False
                
                # Boundary repair
                if "boundary" in issue.lower():
                    grid, repaired = self._repair_boundaries(grid)
                    if repaired:
                        repair_history.append(f"Attempt {repair_attempts}: Fixed boundary gaps")
                        issues_repaired += 1
                
                # Connectivity repair
                elif "connectivity" in issue.lower():
                    grid, repaired = self._repair_connectivity(grid)
                    if repaired:
                        repair_history.append(f"Attempt {repair_attempts}: Fixed connectivity issues")
                        issues_repaired += 1
                
                # Isolated tiles repair
                elif "isolated" in issue.lower():
                    grid, repaired = self._repair_isolated_tiles(grid)
                    if repaired:
                        repair_history.append(f"Attempt {repair_attempts}: Removed isolated tiles")
                        issues_repaired += 1
                
                # Spawn point repair
                elif "spawn" in issue.lower():
                    spawn_points = level_data.get('spawn_points', [])
                    grid, spawn_points, repaired = self._repair_spawn_points(grid, spawn_points)
                    if repaired:
                        repaired_data['spawn_points'] = spawn_points
                        repair_history.append(f"Attempt {repair_attempts}: Fixed spawn points")
                        issues_repaired += 1
                
                # Room repair
                elif "room" in issue.lower():
                    rooms = level_data.get('rooms', [])
                    grid, rooms, repaired = self._repair_rooms(grid, rooms)
                    if repaired:
                        repaired_data['rooms'] = rooms
                        repair_history.append(f"Attempt {repair_attempts}: Fixed room issues")
                        issues_repaired += 1
                
                # Terrain repair - simplified
                elif "terrain" in issue.lower():
                    grid, terrain_grid, repaired = self._repair_terrain_simple(grid, terrain_grid)
                    if repaired:
                        repair_history.append(f"Attempt {repair_attempts}: Fixed terrain issues")
                        issues_repaired += 1
            
            # Update repaired data
            repaired_data['grid'] = grid
            repaired_data['terrain_grid'] = terrain_grid
            
            # Re-validate to check if issues are fixed
            validation_result = self.validate(repaired_data)
            
            # If no progress made, break to avoid infinite loop
            if issues_repaired == 0:
                break
        
        # Update repair history
        validation_result.repair_history = repair_history
        validation_result.metrics.repair_attempts = repair_attempts
        
        repaired_data['grid'] = grid
        repaired_data['terrain_grid'] = terrain_grid
        
        return repaired_data
    
    def _repair_boundaries(self, grid: List[List[int]]) -> Tuple[List[List[int]], bool]:
        """Repair open boundaries by sealing them"""
        height = len(grid)
        width = len(grid[0]) if height > 0 else 0
        repaired = False
        
        # Count boundary gaps before repair
        boundary_gaps = 0
        for x in range(width):
            if grid[0][x] == 0:
                boundary_gaps += 1
            if grid[height - 1][x] == 0:
                boundary_gaps += 1
        
        for y in range(height):
            if grid[y][0] == 0:
                boundary_gaps += 1
            if grid[y][width - 1] == 0:
                boundary_gaps += 1
        
        # Only repair if there are too many gaps
        max_boundary_gaps = 4
        if boundary_gaps <= max_boundary_gaps:
            return grid, False
        
        # Seal boundaries, but leave some gaps for exits
        exit_positions = random.sample(range(min(width, height)), min(2, max_boundary_gaps))
        
        # Seal top and bottom
        for x in range(width):
            if x not in exit_positions:
                grid[0][x] = 1  # Wall
                grid[height - 1][x] = 1  # Wall
        
        # Seal left and right
        for y in range(height):
            if y not in exit_positions:
                grid[y][0] = 1  # Wall
                grid[y][width - 1] = 1  # Wall
        
        return grid, True
    
    def _repair_connectivity(self, grid: List[List[int]]) -> Tuple[List[List[int]], bool]:
        """Repair connectivity issues by creating tunnels"""
        # Find all floor tiles
        floor_tiles = []
        for y, row in enumerate(grid):
            for x, tile in enumerate(row):
                if tile == 0:
                    floor_tiles.append((x, y))
        
        if len(floor_tiles) < 2:
            return grid, False
        
        # Find connected components
        visited = set()
        components = []
        
        for tile in floor_tiles:
            if tile not in visited:
                component = self._flood_fill(grid, tile)
                visited.update(component)
                components.append(component)
        
        # If only one component, no connectivity issues
        if len(components) <= 1:
            return grid, False
        
        # Connect components with tunnels
        repaired = False
        for i in range(len(components) - 1):
            # Find closest points between components
            comp1 = components[i]
            comp2 = components[i + 1]
            
            min_dist = float('inf')
            closest_pair = None
            
            for p1 in comp1:
                for p2 in comp2:
                    dist = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
                    if dist < min_dist:
                        min_dist = dist
                        closest_pair = (p1, p2)
            
            if closest_pair:
                self._create_tunnel(grid, closest_pair[0], closest_pair[1])
                repaired = True
        
        return grid, repaired
    
    def _create_tunnel(self, grid: List[List[int]], start: Tuple[int, int], end: Tuple[int, int]):
        """Create a tunnel between two points"""
        x1, y1 = start
        x2, y2 = end
        
        # L-shaped tunnel with some randomness
        if random.random() < 0.5:
            # Horizontal first, then vertical
            while x1 != x2:
                if 0 <= y1 < len(grid) and 0 <= x1 < len(grid[0]):
                    grid[y1][x1] = 0  # Floor
                x1 += 1 if x2 > x1 else -1
            
            while y1 != y2:
                if 0 <= y1 < len(grid) and 0 <= x1 < len(grid[0]):
                    grid[y1][x1] = 0  # Floor
                y1 += 1 if y2 > y1 else -1
        else:
            # Vertical first, then horizontal
            while y1 != y2:
                if 0 <= y1 < len(grid) and 0 <= x1 < len(grid[0]):
                    grid[y1][x1] = 0  # Floor
                y1 += 1 if y2 > y1 else -1
            
            while x1 != x2:
                if 0 <= y1 < len(grid) and 0 <= x1 < len(grid[0]):
                    grid[y1][x1] = 0  # Floor
                x1 += 1 if x2 > x1 else -1
    
    def _repair_isolated_tiles(self, grid: List[List[int]]) -> Tuple[List[List[int]], bool]:
        """Repair isolated tiles by removing them"""
        isolated_tiles = self._find_isolated_tiles(grid)
        
        if not isolated_tiles:
            return grid, False
        
        for x, y in isolated_tiles:
            grid[y][x] = 1  # Convert to wall
        
        return grid, True
    
    def _repair_spawn_points(self, grid: List[List[int]], spawn_points: List[Tuple[int, int]]) -> Tuple[List[List[int]], List[Tuple[int, int]], bool]:
        """Repair spawn points by finding safe locations"""
        repaired = False
        new_spawn_points = []
        
        # Validate existing spawn points
        for x, y in spawn_points:
            if (0 <= y < len(grid) and 0 <= x < len(grid[0]) and 
                grid[y][x] == 0 and len(self._check_spawn_safety(grid, [], x, y)) == 0):
                new_spawn_points.append((x, y))
            else:
                repaired = True
        
        # Add new spawn points if needed
        while len(new_spawn_points) < self.min_spawn_points:
            # Find a safe spawn location
            for y in range(1, len(grid) - 1):
                for x in range(1, len(grid[0]) - 1):
                    if grid[y][x] == 0 and len(self._check_spawn_safety(grid, [], x, y)) == 0:
                        new_spawn_points.append((x, y))
                        repaired = True
                        break
                if len(new_spawn_points) >= self.min_spawn_points:
                    break
        
        return grid, new_spawn_points, repaired
    
    def _repair_rooms(self, grid: List[List[int]], rooms: List) -> Tuple[List[List[int]], List, bool]:
        """Repair room issues by expanding small rooms"""
        repaired = False
        
        for room in rooms:
            room_width = getattr(room, 'width', 0)
            room_height = getattr(room, 'height', 0)
            room_x = getattr(room, 'x', 0)
            room_y = getattr(room, 'y', 0)
            
            # Expand small rooms
            if room_width < self.min_room_size or room_height < self.min_room_size:
                new_width = max(self.min_room_size, room_width)
                new_height = max(self.min_room_size, room_height)
                
                # Clear space for expanded room
                for y in range(max(0, room_y), min(len(grid), room_y + new_height)):
                    for x in range(max(0, room_x), min(len(grid[0]), room_x + new_width)):
                        grid[y][x] = 0  # Floor
                
                # Update room dimensions
                setattr(room, 'width', new_width)
                setattr(room, 'height', new_height)
                repaired = True
        
        return grid, rooms, repaired
    
    def _repair_terrain_simple(self, grid: List[List[int]], terrain_grid: List[List[str]]) -> Tuple[List[List[int]], List[List[str]], bool]:
        """Repair terrain issues - simplified since terrain system is removed"""
        # terrain system removed - no terrain repair needed
        return grid, terrain_grid, False


# Global validator instance
level_validator = EnhancedLevelValidator()


# Legacy compatibility
class LevelValidator(EnhancedLevelValidator):
    """Legacy compatibility wrapper"""
    pass