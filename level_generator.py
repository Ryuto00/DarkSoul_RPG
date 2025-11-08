"""
Level Generator - Main orchestrator for procedural level generation
"""

import time
from typing import Dict, List, Tuple, Optional, Any
import pygame

from config import TILE
from seed_manager import SeedManager
from generation_algorithms import HybridGenerator
from level_validator import LevelValidator
from terrain_system import TerrainTypeRegistry, init_defaults as init_terrain_defaults
from area_system import AreaMap, AreaType, AreaRegistry, build_default_areas, init_defaults as init_area_defaults

# Procedural enemy spawn tuning constants (used only in GeneratedLevel._spawn_enemies)
BUG_WIDTH = 28
BUG_HEIGHT = 22
ENEMY_PADDING = 4        # Horizontal margin between enemies for spacing checks
PLAYER_SAFETY_PAD_X = 32 # Extra horizontal buffer around player spawn
PLAYER_SAFETY_PAD_Y = 16 # Extra vertical buffer around player spawn


class GeneratedLevel:
    """
    Represents a procedurally generated level.

    This class is shaped to be drop-in compatible with the existing Level API
    used by main.py and other systems:
      - Attributes:
          solids: List[pygame.Rect]
          enemies: List[Enemy]
          doors: List[pygame.Rect]
          spawn: (x, y)
          w, h: pixel dimensions
          is_procedural: bool
      - Methods:
          draw(surf, camera): renders basic tiles/doors
    """
    
    def __init__(self, grid: List[List[int]], rooms: List, spawn_points: List[Tuple[int, int]],
                 level_type: str,
                 terrain_grid: Optional[List[List[str]]] = None,
                 areas: Optional[AreaMap] = None):
        """
        terrain_grid:
            2D list of terrain_id strings. If None, a trivial mapping is created.
        areas:
            AreaMap describing logical areas (spawn zones, portal zone, water, etc.).
            Optional for backward compatibility.
        """
        self.grid = grid
        self.rooms = rooms
        self.spawn_points = spawn_points
        self.level_type = level_type
        self.terrain_grid = terrain_grid or self._create_default_terrain(grid)
        self.areas: AreaMap = areas or AreaMap()
        
        # Core gameplay/physics data expected by the game
        self.solids: List[pygame.Rect] = []
        self.enemies: List = []
        self.doors: List[pygame.Rect] = []
        self.spawn: Tuple[int, int] = (TILE * 2, TILE * 2)

        # Portal position in pixel coordinates (x, y)
        self.portal_pos: Optional[Tuple[int, int]] = None

        # Meta
        self.is_procedural: bool = True

        # Derived sizes in pixels for compatibility with camera/terrain_system
        if self.grid and len(self.grid) > 0 and len(self.grid[0]) > 0:
            self.w = len(self.grid[0]) * TILE
            self.h = len(self.grid) * TILE
        else:
            # Fallback to config sizes
            self.w = 40 * TILE
            self.h = 30 * TILE
        
        self._process_level()
    
    def _create_default_terrain(self, grid: List[List[int]]) -> List[List[str]]:
        """
        Create a default terrain grid from level grid.

        This uses TerrainTypeRegistry defaults:
        - Walls -> "wall_solid"
        - Floors -> "floor_normal"
        """
        # Ensure defaults are initialized (idempotent).
        init_terrain_defaults()

        terrain_grid: List[List[str]] = []
        for row in grid:
            terrain_row: List[str] = []
            for tile in row:
                if tile == 1:
                    terrain_row.append("wall_solid")
                else:
                    terrain_row.append("floor_normal")
            terrain_grid.append(terrain_row)
        return terrain_grid
    
    def _process_level(self):
        """Process generated level into game-compatible format.

        Guarantees:
        - Player spawn:
            - Only placed on walkable floor tiles (grid == 0).
            - Prefer tiles inside AreaType.PLAYER_SPAWN areas if provided.
        - Enemy spawns:
            - Never inside PLAYER_SPAWN areas or overlapping the player safety zone.
        """
        from area_system import AreaType  # local import to avoid cycles

        height = len(self.grid)
        width = len(self.grid[0]) if height > 0 else 0

        # Convert grid to solid rectangles
        for y, row in enumerate(self.grid):
            for x, tile in enumerate(row):
                if tile == 1:  # Wall
                    rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                    self.solids.append(rect)

        # Compute helper: tiles that belong to PLAYER_SPAWN areas (if any)
        player_spawn_area_tiles = set()
        if hasattr(self, "areas") and self.areas:
            try:
                spawn_areas = self.areas.find_areas_by_type(getattr(AreaType, "PLAYER_SPAWN", "PLAYER_SPAWN"))
                for a in spawn_areas:
                    for tx, ty in a.tiles():
                        if 0 <= tx < width and 0 <= ty < height:
                            player_spawn_area_tiles.add((tx, ty))
            except Exception:
                # Defensive: area issues must not break generation.
                player_spawn_area_tiles = set()

        # Set spawn point in pixels:
        # - Prefer first spawn_point that is floor (0).
        # - If PLAYER_SPAWN areas exist, restrict to tiles within those areas.
        # - Fallback: any valid floor spawn_point.
        if self.spawn_points:
            chosen = None

            # 1) Prefer spawn points that lie inside a PLAYER_SPAWN area (if such areas exist)
            if player_spawn_area_tiles:
                for sx, sy in self.spawn_points:
                    if (
                        0 <= sy < height
                        and 0 <= sx < width
                        and self.grid[sy][sx] == 0
                        and (sx, sy) in player_spawn_area_tiles
                    ):
                        chosen = (sx, sy)
                        break

            # 2) Otherwise, pick first spawn point on floor.
            if chosen is None:
                for sx, sy in self.spawn_points:
                    if 0 <= sy < height and 0 <= sx < width and self.grid[sy][sx] == 0:
                        chosen = (sx, sy)
                        break

            # 3) Fallback to raw first spawn point if still nothing (will be rechecked)
            if chosen is None:
                sx, sy = self.spawn_points[0]
            else:
                sx, sy = chosen

            # Final safety: only accept if on floor.
            if 0 <= sy < height and 0 <= sx < width and self.grid[sy][sx] == 0:
                self.spawn = (sx * TILE, sy * TILE)

        # Place portal strictly inside a PORTAL_ZONE area if available and reachable.
        self.portal_pos = self._place_portal()

        # Spawn at least one enemy (reachable from player, not on portal, and not in PLAYER_SPAWN areas)
        self._spawn_enemies(player_spawn_area_tiles=player_spawn_area_tiles)

    def _is_reachable(self, start: Tuple[int, int], target: Tuple[int, int]) -> bool:
        """
        Lightweight BFS reachability on the tile grid.
        Used locally to avoid depending on validator and to prevent cycles.
        """
        if start == target:
            return True

        height = len(self.grid)
        width = len(self.grid[0]) if height > 0 else 0
        sx, sy = start
        tx, ty = target

        if not (0 <= sx < width and 0 <= sy < height and
                0 <= tx < width and 0 <= ty < height):
            return False
        if self.grid[sy][sx] != 0 or self.grid[ty][tx] != 0:
            return False

        from collections import deque
        q = deque()
        q.append((sx, sy))
        visited = { (sx, sy) }

        while q:
            x, y = q.popleft()
            if (x, y) == (tx, ty):
                return True
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (0 <= nx < width and 0 <= ny < height and
                        self.grid[ny][nx] == 0 and (nx, ny) not in visited):
                    visited.add((nx, ny))
                    q.append((nx, ny))

        return False

    def _place_portal(self) -> Optional[Tuple[int, int]]:
        """
        Select a portal position:

        - Prefer tiles inside AreaType.PORTAL_ZONE areas when defined.
        - Otherwise, fall back to legacy behavior: any interior floor tile.
        - Must be on a floor tile (grid == 0).
        - Must be reachable from player spawn via local BFS.
        - Prefer tiles far from player.

        Returns pixel coordinates (x, y) if successful, else None.
        """
        height = len(self.grid)
        width = len(self.grid[0]) if height > 0 else 0
        if width == 0 or height == 0 or not self.spawn_points:
            return None

        # Player spawn tile from authoritative pixel spawn
        spawn_tile_x = self.spawn[0] // TILE
        spawn_tile_y = self.spawn[1] // TILE
        sx, sy = spawn_tile_x, spawn_tile_y
        if not (0 <= sx < width and 0 <= sy < height):
            return None
        if self.grid[sy][sx] != 0:
            return None

        candidates: List[Tuple[int, int, int]] = []

        def is_valid_portal_tile(tx: int, ty: int) -> bool:
            if not (0 <= tx < width and 0 <= ty < height):
                return False
            # Must be floor tile in grid; tests/validator expect this.
            if self.grid[ty][tx] != 0:
                return False
            return True

        # Prefer tiles inside PORTAL_ZONE areas if any exist.
        portal_zones = self.areas.find_areas_by_type(getattr(AreaType, "PORTAL_ZONE", "PORTAL_ZONE"))
        if portal_zones:
            for zone in portal_zones:
                for tx, ty in zone.tiles():
                    if is_valid_portal_tile(tx, ty):
                        dist = abs(tx - sx) + abs(ty - sy)
                        candidates.append((dist, tx, ty))

        # Fallback: legacy behavior across all interior floor tiles if no zone candidates.
        if not candidates:
            for y in range(1, height - 1):
                for x in range(1, width - 1):
                    if is_valid_portal_tile(x, y):
                        dist = abs(x - sx) + abs(y - sy)
                        candidates.append((dist, x, y))

        if not candidates:
            return None

        # Prefer farthest distance first
        candidates.sort(reverse=True)

        for _, px, py in candidates:
            if self._is_reachable((sx, sy), (px, py)):
                return (px * TILE, py * TILE)

        return None

    def _spawn_enemies(self, player_spawn_area_tiles: Optional[set] = None) -> None:
        """
        Populate self.enemies with at least one enemy:

        Constraints:
        - Only on valid floor tiles.
        - Never on/overlapping player spawn tile.
        - Never inside PLAYER_SPAWN areas (player-safe zone).
        - Never overlapping the player safety rect.
        - Never on portal tile.
        - Must be reachable from player spawn by local BFS.
        - Do not stack enemies on top of each other.
        Keep simple and deterministic; uses a small fixed set of candidates.
        """
        from enemy_entities import Bug

        if player_spawn_area_tiles is None:
            player_spawn_area_tiles = set()

        height = len(self.grid)
        width = len(self.grid[0]) if height > 0 else 0
        if width == 0 or height == 0 or not self.spawn_points:
            return

        # Player spawn tile (from authoritative pixel spawn)
        spawn_tile_x = self.spawn[0] // TILE
        spawn_tile_y = self.spawn[1] // TILE
        spawn_tile = (spawn_tile_x, spawn_tile_y)
        sx, sy = spawn_tile

        # Safety rect around player spawn
        player_spawn_x, player_spawn_y = self.spawn
        player_width, player_height = 18, 30
        player_spawn_rect = pygame.Rect(player_spawn_x, player_spawn_y, player_width, player_height)
        player_safety_rect = player_spawn_rect.inflate(
            PLAYER_SAFETY_PAD_X * 2,
            PLAYER_SAFETY_PAD_Y * 2,
        )

        portal_tile: Optional[Tuple[int, int]] = None
        if self.portal_pos:
            portal_tile = (self.portal_pos[0] // TILE, self.portal_pos[1] // TILE)

        candidates: List[Tuple[int, int, int]] = []

        def is_adjacent_to_spawn(tx: int, ty: int) -> bool:
            return abs(tx - sx) + abs(ty - sy) == 1

        # Base candidate selection (on-grid, non-wall, respecting spawn/portal/area buffers)
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                if self.grid[y][x] != 0:
                    continue
                if (x, y) == spawn_tile:
                    continue
                if is_adjacent_to_spawn(x, y):
                    continue
                if portal_tile and (x, y) == portal_tile:
                    continue
                # Exclude any tile marked as part of PLAYER_SPAWN areas
                if (x, y) in player_spawn_area_tiles:
                    continue
                dist = abs(x - sx) + abs(y - sy)
                candidates.append((dist, x, y))

        if not candidates:
            return

        # Deterministic: closest first
        candidates.sort()

        placed_enemy_rects: List[pygame.Rect] = []
        placed = 0
        max_enemies = max(1, (width * height) // 300)

        for _, ex, ey in candidates:
            if placed >= max_enemies:
                break

            # Reachability on grid
            if not self._is_reachable(spawn_tile, (ex, ey)):
                continue

            # Build canonical Bug rect
            enemy_width = BUG_WIDTH
            enemy_height = BUG_HEIGHT
            enemy_x = ex * TILE + TILE // 2
            ground_y = (ey + 1) * TILE
            enemy_rect = pygame.Rect(
                enemy_x - enemy_width // 2,
                ground_y - enemy_height,
                enemy_width,
                enemy_height,
            )
            test_enemy_rect = enemy_rect.inflate(ENEMY_PADDING * 2, 0)

            # Do not overlap player safety zone
            if enemy_rect.colliderect(player_safety_rect):
                continue

            # Do not overlap previously placed enemies
            blocked = False
            for r in placed_enemy_rects:
                if test_enemy_rect.colliderect(r):
                    blocked = True
                    break
            if blocked:
                continue

            # Spawn enemy
            bug = Bug(enemy_x, ground_y)
            bug.x = float(bug.rect.centerx)
            bug.y = float(bug.rect.bottom)

            self.enemies.append(bug)
            placed_enemy_rects.append(enemy_rect)
            placed += 1

        # If for some reason none were placed but candidates existed, place one safe fallback.
        if not self.enemies and candidates:
            # Pick the first candidate that still respects area/safety constraints.
            for _, ex, ey in candidates:
                if (ex, ey) == spawn_tile:
                    continue
                if (ex, ey) in player_spawn_area_tiles:
                    continue
                if not self._is_reachable(spawn_tile, (ex, ey)):
                    continue

                enemy_x = ex * TILE + TILE // 2
                ground_y = (ey + 1) * TILE
                enemy_rect = pygame.Rect(
                    enemy_x - BUG_WIDTH // 2,
                    ground_y - BUG_HEIGHT,
                    BUG_WIDTH,
                    BUG_HEIGHT,
                )
                if enemy_rect.colliderect(player_safety_rect):
                    continue

                bug = Bug(enemy_x, ground_y)
                bug.x = float(bug.rect.centerx)
                bug.y = float(bug.rect.bottom)
                self.enemies.append(bug)
                break


    def draw(self, surf, camera):
        """
        Minimal renderer compatible with Level.draw used by main.py.
        Uses TILE_COL for solids and CYAN for doors/portal indicator.
        """
        from config import TILE_COL, CYAN  # local import to avoid cycles

        for r in self.solids:
            pygame.draw.rect(surf, TILE_COL, camera.to_screen_rect(r), border_radius=6)
        for d in self.doors:
            pygame.draw.rect(surf, CYAN, camera.to_screen_rect(d), width=2)

        # Optional simple portal visualization so it's obvious in debug:
        if self.portal_pos:
            px, py = self.portal_pos
            portal_rect = pygame.Rect(px, py, TILE, TILE)
            pygame.draw.rect(surf, CYAN, camera.to_screen_rect(portal_rect), width=2)

        # Note: enemies draw themselves; this method mirrors level.Level.draw.
        

class LevelGenerator:
    """Main level generation orchestrator"""
    
    def __init__(self, width: int = 40, height: int = 30):
        self.width = width
        self.height = height
        self.seed_manager = SeedManager()
        self.hybrid_generator = HybridGenerator(width, height)
        self.validator = LevelValidator()
        
        # Performance tracking
        self.generation_time_ms = 0
        self.validation_attempts = 0
    
    def generate_level(self, level_index: int, level_type: str = "dungeon", 
                    difficulty: int = 1, seed: Optional[int] = None) -> GeneratedLevel:
        """
        Generate a complete level
        
        Args:
            level_index: Index of level to generate
            level_type: Type of level ("dungeon", "cave", "outdoor", "hybrid")
            difficulty: Difficulty level (1-3)
            seed: Optional seed override
            
        Returns:
            GeneratedLevel instance
        """
        start_time = time.time()
        
        # Set seed if provided
        if seed is not None:
            self.seed_manager.set_world_seed(seed)
        
        # Generate level seed
        level_seed = self.seed_manager.generate_level_seed(level_index)
        
        # Generate sub-seeds
        sub_seeds = self.seed_manager.generate_sub_seeds(level_seed)
        
        # Generate raw level data
        level_data = self.hybrid_generator.generate(level_seed, level_type)
        
        # Apply difficulty modifications
        level_data = self._apply_difficulty(level_data, difficulty)
        
        # Validate and repair if needed
        validated_data = self._validate_and_repair(level_data)
        
        # Initialize data-driven registries (idempotent safe).
        init_terrain_defaults()
        init_area_defaults()

        # Generate terrain IDs grid
        terrain_grid = self._generate_terrain(validated_data, sub_seeds['terrain'])

        # Build default areas overlay (PLAYER_SPAWN, PORTAL_ZONE, WATER_AREA, etc.)
        # Pass tile_size for correct portal conversion.
        level_data_with_meta = dict(validated_data)
        level_data_with_meta["terrain_grid"] = terrain_grid
        level_data_with_meta.setdefault("tile_size", TILE)
        areas = build_default_areas(level_data_with_meta, terrain_grid)

        # Ensure enemy spawn metadata from validation is preserved if present.
        enemy_spawns = validated_data.get('enemy_spawns')

        # Create final level
        generated_level = GeneratedLevel(
            validated_data['grid'],
            validated_data['rooms'],
            validated_data['spawn_points'],
            validated_data['type'],
            terrain_grid,
            areas,
        )

        # Attach additional metadata for downstream systems.
        if enemy_spawns is not None:
            setattr(generated_level, 'enemy_spawns', enemy_spawns)
        setattr(generated_level, 'areas', areas)
        setattr(generated_level, 'terrain_grid', terrain_grid)
        
        # Track performance
        self.generation_time_ms = (time.time() - start_time) * 1000
        
        return generated_level
    
    def _apply_difficulty(self, level_data: Dict[str, Any], difficulty: int) -> Dict[str, Any]:
        """Apply difficulty modifications to level data"""
        if difficulty == 1:  # Easy
            # Reduce enemy density (will be handled in entity placement)
            # Increase treasure frequency
            # Simplify terrain
            pass  # No modifications for easy
        elif difficulty == 2:  # Normal
            # Standard settings
            pass  # No modifications for normal
        elif difficulty == 3:  # Hard
            # Increase enemy density
            # Add more complex terrain
            # Reduce open space
            grid = level_data['grid']
            if grid:
                # Add some extra walls for complexity
                for _ in range(int(len(grid) * len(grid[0]) * 0.05)):  # 5% extra walls
                    y = self.seed_manager.get_random('terrain').randint(1, len(grid) - 2)
                    x = self.seed_manager.get_random('terrain').randint(1, len(grid[0]) - 2)
                    grid[y][x] = 1  # Wall
                
                level_data['grid'] = grid
        
        return level_data
    
    def _validate_and_repair(self, level_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and repair structural aspects of the level.

        IMPORTANT:
        - This runs BEFORE GeneratedLevel spawns real enemies/portal.
        - We therefore validate only structural properties (grid, rooms,
          boundaries, connectivity, spawn_points).
        - We DO NOT enforce presence/positions of enemies/portal here to avoid
          false failures and double-specifying behavior already covered by
          GeneratedLevel + tests.
        """
        max_attempts = 3
        current_data = level_data.copy()

        # Ensure required keys exist for structural checks
        current_data.setdefault("rooms", [])
        current_data.setdefault("spawn_points", current_data.get("spawn_points", []))
        current_data.setdefault("enemy_spawns", [])
        # Do NOT inject fake enemies/portal_pos; that is handled later.

        for attempt in range(max_attempts):
            self.validation_attempts += 1

            # Run validator but ignore issues that are explicitly about
            # missing enemies/portal, since those are populated post-process.
            result = self.validator.validate(current_data)

            if result.is_valid:
                return current_data

            # Filter issues to see if any structural problems remain.
            structural_issues = []
            for issue in result.issues:
                low = issue.lower()
                if ("no portal position found" in low) or ("no enemies found" in low):
                    # Defer these to GeneratedLevel/_spawn_enemies/_place_portal.
                    continue
                structural_issues.append(issue)

            if not structural_issues:
                # Only non-structural complaints (like missing portal/enemies); accept.
                return current_data

            # Attempt repair for structural problems if we have attempts left.
            if attempt < max_attempts - 1:
                current_data = self.validator.repair_level(current_data, result)

        # If still failing, fall back to the best structural data we have.
        return current_data
    
    def _generate_terrain(self, level_data: Dict[str, Any], terrain_seed: int) -> List[List[str]]:
        """Generate terrain for the level"""
        grid = level_data.get('grid', [])
        level_type = level_data.get('type', 'dungeon')
        
        if not grid:
            return []
        
        terrain_rng = self.seed_manager.get_random('terrain')
        terrain_rng.seed(terrain_seed)
        
        terrain_grid = []
        
        for y, row in enumerate(grid):
            terrain_row = []
            for x, tile in enumerate(row):
                if tile == 1:  # Wall
                    # Apply terrain variation to walls
                    terrain_type = self._select_wall_terrain(x, y, level_type, terrain_rng)
                    terrain_row.append(terrain_type)
                else:  # Floor
                    # Apply terrain variation to floors
                    terrain_type = self._select_floor_terrain(x, y, level_type, terrain_rng)
                    terrain_row.append(terrain_type)
            terrain_grid.append(terrain_row)
        
        return terrain_grid
    
    def _select_wall_terrain(self, x: int, y: int, level_type: str, rng):
        """Select terrain type for wall tiles"""
        if level_type == "dungeon":
            # Mix of normal and rough terrain
            if rng.random() < 0.8:
                return "normal"
            else:
                return "rough"
        elif level_type == "cave":
            # More rough terrain
            if rng.random() < 0.6:
                return "rough"
            elif rng.random() < 0.8:
                return "steep"
            else:
                return "normal"
        elif level_type == "outdoor":
            # More varied terrain
            rand = rng.random()
            if rand < 0.3:
                return "normal"
            elif rand < 0.5:
                return "rough"
            elif rand < 0.7:
                return "mud"
            elif rand < 0.85:
                return "water"
            else:
                return "ice"
        else:  # hybrid
            # Mix of all types
            rand = rng.random()
            if rand < 0.5:
                return "normal"
            elif rand < 0.7:
                return "rough"
            elif rand < 0.85:
                return "steep"
            else:
                return "destructible"
    
    def _select_floor_terrain(self, x: int, y: int, level_type: str, rng):
        """Select terrain type for floor tiles"""
        if level_type == "dungeon":
            # Mostly normal with some variation
            if rng.random() < 0.9:
                return "normal"
            else:
                return "rough"
        elif level_type == "cave":
            # More rough and steep
            if rng.random() < 0.4:
                return "normal"
            elif rng.random() < 0.7:
                return "rough"
            elif rng.random() < 0.9:
                return "steep"
            else:
                return "mud"
        elif level_type == "outdoor":
            # Natural terrain
            rand = rng.random()
            if rand < 0.6:
                return "normal"
            elif rand < 0.8:
                return "rough"
            else:
                return "mud"
        else:  # hybrid
            # Balanced mix
            rand = rng.random()
            if rand < 0.7:
                return "normal"
            elif rand < 0.85:
                return "rough"
            else:
                return "steep"
    
    def get_generation_stats(self) -> Dict[str, Any]:
        """Get statistics about last generation"""
        return {
            'generation_time_ms': self.generation_time_ms,
            'validation_attempts': self.validation_attempts,
            'world_seed': self.seed_manager.get_world_seed(),
            'seed_info': self.seed_manager.get_seed_info()
        }
    
    def set_world_seed(self, seed: int):
        """Set the world seed for deterministic generation"""
        self.seed_manager.set_world_seed(seed)
    
    def get_world_seed(self) -> int:
        """Get the current world seed"""
        return self.seed_manager.get_world_seed()


# Integration function for existing game
def generate_procedural_level(level_index: int, level_type: str = "dungeon",
                           difficulty: int = 1, seed: Optional[int] = None) -> GeneratedLevel:
    """
    Convenience function for generating levels

    Args:
        level_index: Index of level to generate
        level_type: Type of level ("dungeon", "cave", "outdoor", "hybrid")
        difficulty: Difficulty level (1-3)
        seed: Optional seed override

    Returns:
        GeneratedLevel instance compatible with existing game
    """
    generator = LevelGenerator()
    return generator.generate_level(level_index, level_type, difficulty, seed)


def generate_terrain_test_level() -> GeneratedLevel:
    """
    Build a deterministic terrain/area coverage test level.

    Requirements (per test_terrain_level.md):
    - 40x30 grid, fully sealed by walls.
    - Includes all terrain IDs:
      floor_normal, floor_sticky, floor_icy, floor_fire,
      platform_normal, platform_sticky, platform_icy, platform_fire,
      wall_solid, water.
    - Includes ALL area types:
      PLAYER_SPAWN, PORTAL_ZONE, GROUND_ENEMY_SPAWN,
      FLYING_ENEMY_SPAWN, WATER_AREA, MERCHANT_AREA.
    - Must be exposed via generate_terrain_test_level() and used by F8 in Game.
    """
    from area_system import Area, AreaMap, AreaType
    from terrain_system import init_defaults as terrain_init

    # Ensure registries are initialized.
    terrain_init()
    init_area_defaults()

    width, height = 40, 30

    # Start with all floor (0).
    grid: List[List[int]] = [[0 for _ in range(width)] for _ in range(height)]

    # Outer ring walls (1) to fully seal boundaries.
    for x in range(width):
        grid[0][x] = 1
        grid[height - 1][x] = 1
    for y in range(height):
        grid[y][0] = 1
        grid[y][width - 1] = 1

    # Base terrain grid: start as floor_normal everywhere.
    terrain_grid: List[List[str]] = [["floor_normal" for _ in range(width)] for _ in range(height)]

    # Align terrain walls with grid walls using wall_solid.
    for x in range(width):
        terrain_grid[0][x] = "wall_solid"
        terrain_grid[height - 1][x] = "wall_solid"
    for y in range(height):
        terrain_grid[y][0] = "wall_solid"
        terrain_grid[y][width - 1] = "wall_solid"

    # Bands / patches for floor_* variants.
    for x in range(2, 10):
        terrain_grid[3][x] = "floor_sticky"
    for x in range(2, 10):
        terrain_grid[5][x] = "floor_icy"
    for x in range(2, 10):
        terrain_grid[7][x] = "floor_fire"

    # Patches for platform_* variants (grid stays 0 so they are walkable).
    for x in range(12, 20):
        terrain_grid[4][x] = "platform_normal"
    for x in range(12, 20):
        terrain_grid[6][x] = "platform_sticky"
    for x in range(12, 20):
        terrain_grid[8][x] = "platform_icy"
    for x in range(12, 20):
        terrain_grid[10][x] = "platform_fire"

    # Water pool region for WATER and WATER_AREA testing.
    for y in range(20, 25):
        for x in range(5, 15):
            terrain_grid[y][x] = "water"

    # Spawn points: anchor under PLAYER_SPAWN area, on clear floor.
    spawn_points = [(6, 10)]
    rooms: List[Any] = []

    # Build AreaMap containing all required area types.
    areas = AreaMap()

    # PLAYER_SPAWN area: small region around spawn.
    areas.add_area(Area(
        id="test_player_spawn",
        type=AreaType.PLAYER_SPAWN,
        x=5,
        y=9,
        width=3,
        height=3,
        attributes={},
    ))

    # PORTAL_ZONE: safe floor/platform region on the right side.
    # Sized >= 3x3 to satisfy AreaRegistry constraints.
    areas.add_area(Area(
        id="test_portal_zone",
        type=AreaType.PORTAL_ZONE,
        x=26,
        y=10,
        width=4,
        height=4,
        attributes={},
    ))

    # GROUND_ENEMY_SPAWN: floor band mid-map.
    areas.add_area(Area(
        id="test_ground_enemy_spawn",
        type=AreaType.GROUND_ENEMY_SPAWN,
        x=8,
        y=13,
        width=4,
        height=3,
        attributes={},
    ))

    # FLYING_ENEMY_SPAWN: open-air region (no strict terrain constraints).
    areas.add_area(Area(
        id="test_flying_enemy_spawn",
        type=AreaType.FLYING_ENEMY_SPAWN,
        x=20,
        y=5,
        width=5,
        height=4,
        attributes={},
    ))

    # WATER_AREA: exactly over the water pool.
    areas.add_area(Area(
        id="test_water_area",
        type=AreaType.WATER_AREA,
        x=5,
        y=20,
        width=10,
        height=5,
        attributes={},
    ))

    # MERCHANT_AREA: solid floor/platform patch, no enemies/portal.
    areas.add_area(Area(
        id="test_merchant_area",
        type=AreaType.MERCHANT_AREA,
        x=26,
        y=6,
        width=5,
        height=3,
        attributes={},
    ))

    # Construct deterministic GeneratedLevel.
    test_level = GeneratedLevel(
        grid=grid,
        rooms=rooms,
        spawn_points=spawn_points,
        level_type="terrain_test",
        terrain_grid=terrain_grid,
        areas=areas,
    )

    # Ensure metadata is accessible for overlay + tests.
    setattr(test_level, "areas", areas)
    setattr(test_level, "terrain_grid", terrain_grid)
    test_level.is_procedural = True

    return test_level