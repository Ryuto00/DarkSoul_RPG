"""
PRESERVED LEGACY LEVEL SYSTEM - DO NOT MODIFY
This contains the original hardcoded ASCII room system.
AI agents should NOT modify this file - it is preserved for historical compatibility.

The legacy system uses hardcoded ASCII room definitions with entity markers.
This is kept for backward compatibility and can be accessed via menu toggle.
"""

import pygame
from typing import List, Optional
from config import TILE, CYAN, WIDTH, HEIGHT
from ..entities.entities import Bug, Boss, Frog, Archer, WizardCaster, Assassin, Bee, Golem
from ..tiles import TileParser, TileRenderer, TileRegistry, TileType
from ..tiles.tile_collision import TileCollision

# Rooms (tilemaps). Legend:
#   Tiles: # wall, . air/empty, _ platform, @ breakable wall, % breakable floor
#   Entities: S spawn, D door->next room
#   Enemies: E=Bug, f=Frog, r=Archer, w=WizardCaster, a=Assassin, b=Bee, G=Golem boss
ROOMS = [
    # Room 1 (larger)
     [
        "########################################",
        "#......................................#",
        "#...............................r..r...#",
        "#.................f.............#####..#",
        "#.............#########................#",
        "#.............#.......#................#",
        "#..S..........#.......#................#",
        "#####.........#...#####................#",
        "#.............#.......#................#",
        "#.............#.......#########........#",
        "#.........a...#........................#",
        "#.....#########....D...................#",
        "#.............#........................#",
        "#.............#############............#",
        "#..............................b.......#",
        "#......................................#",
        "#...w...........w......................#",
        "########################################",
    ],
    # Room 2 (larger)
    [
        "########################################",
        "#......................................#",
        "#......................w...............#",
        "#.....................######...........#",
        "#..........######......................#",
        "#...........r...........b..............#",
        "#####......######......................#",
        "#..........#....#......................#",
        "#........###....#...................a..#",
        "#..........#....######.................#",
        "#.....s....#...........................#",
        "############...................b.......#",
        "#...........#..........................#",
        "#...........###########................#",
        "#......................................#",
        "#......................................#",
        "#..E..........E........f......D........#",
        "########################################",
    ],
    # Room 3 (bigger, more enemies)
    [
        "########################################",
        "#..,...................................#",
        "#......................................#",
        "#........b...#####.....................#",
        "#...........#..D..#....................#",
        "######......#.....#.....b..............#",
        "#...........#.....#....................#",
        "#...........#.....#....................#",
        "#...b.......#.....#....r...............#",
        "#...........#.....######...............#",
        "#........w..#..........................#",
        "#.....####..#..........................#",
        "#...........#..a...................E...#",
        "#...........############################",
        "#.......................b..............#",
        "#...S..................................#",
        "#.........................r............#",
        "########################################",
    ],
    # Room 4 (bigger, platform variation)
    [
        "########################################",
        "#......................................#",
        "#..............r.......................#",
        "#...........######.............b.......#",
        "###...b.... #..........................#",
        "#...........#..........................#",
        "#...........#..........................#",
        "#....S...a..#....E...........a.........#",
        "##################################...###",
        "#......................................#",
        "#..................w...................#",
        "#.....D............##....b.............#",
        "#.....####.............................#",
        "#.................r....................#",
        "#................##....................#",
        "#..........................a...........#",
        "#.........................##...........#",
        "#.EE...................................#",
        "########################################",
    ],
    # Room 5 (even bigger open arena)
    [
        "########################################",
        "#....................b...............###",
        "#................................#######",
        "#............r...................#######",
        "#...........######................######",
        "#...........#....#....f............#####",
        "#..S........#....#...............#######",
        "#############..###.............#########",
        "#...........#....#...........###########",
        "#...........#....######..........#######",
        "#......D....###....................#####",
        "#.....####..#.........................##",
        "#...........#.....a................b..##",
        "#...........###########...............##",
        "#............b........................##",
        "#......................................#",
        "#.........f...............f...........##",
        "########################################",
    ],
    # Boss room (room 6) - boss at center (only the boss, no regular enemies)
    [
        "########################################",
        "#......................................#",
        "#......................................#",
        "#......................................#",
        "#......................................#",
        "#......................................#",
        "#......................................#",
        "#...............######.................#",
        "#......................................#",
        "#......................................#",
        "#....######.................######.....#",
        "#......................................#",
        "#..................G...................#",
        "#..............#########...........D...#",
        "#......................................#",
        "#..................S...................#",
        "#......................................#",
        "########################################",
    ],
]

# Useful constant for other modules (eg. Game.switch_room)
ROOM_COUNT = len(ROOMS)


class LegacyLevel:
    """
    Legacy level system using hardcoded ASCII room definitions.
    
    This class preserves the original hardcoded room system for backward compatibility.
    It uses ASCII room definitions with entity markers and legacy parsing.
    """
    
    def __init__(self, index: Optional[int] = None):
        """
        Initialize a legacy level from static ASCII rooms.
        
        Args:
            index: Room index to load from ROOMS array
        """
        # Core containers
        self.solids: List[pygame.Rect] = []
        self.enemies: List[object] = []  # Can contain any enemy type
        self.doors: List[pygame.Rect] = []
        self.spawn = (TILE * 2, TILE * 2)

        # Initialize tile/physics systems
        self.tile_parser = TileParser()
        self.tile_renderer = TileRenderer(TILE)
        self.tile_registry = TileRegistry()
        self.tile_collision = TileCollision(TILE)

        # Load static room
        self.index = (index or 0) % len(ROOMS)
        self.current_room_id = f'legacy_room_{self.index}'
        
        # Initialize from ASCII
        self._init_from_ascii()

        # Level dimensions based on numeric grid
        self.w = len(self.grid[0]) * TILE if self.grid else 0
        self.h = len(self.grid) * TILE

        # Validate spawn position
        self.spawn = self._validate_spawn_position(self.spawn)
    
    def _init_from_ascii(self) -> None:
        """
        Initialize level state from ASCII ROOMS using TileParser.
        """
        # Get ASCII room definition
        raw = ROOMS[self.index]

        # Parse ASCII as legacy
        self.grid, entity_positions = self.tile_parser.parse_ascii_level(
            raw,
            legacy=True,
        )

        # Load entities/doors from parsed markers
        self._load_entities(entity_positions)

        # Build solids from tile collision data
        self._update_solids_from_grid()

    def _load_entities(self, entity_positions: dict):
        """
        Load enemies and special objects from parsed ASCII positions.
        """
        # Check if boss is present
        boss_present = 'enemy_boss' in entity_positions or len(entity_positions.get('boss', [])) > 0
        self.is_boss_room = boss_present

        # Load spawn point (legacy 'S' markers)
        if 'spawn' in entity_positions:
            for x, y in entity_positions['spawn']:
                # Position player's feet at spawn point, accounting for player height
                # Player height is 30px, so we offset by player height to place feet on tile
                raw_spawn = (x * TILE, y * TILE)
                self.spawn = raw_spawn

        # Load enemies from legacy markers
        for entity_type, positions in entity_positions.items():
            for x, y in positions:
                world_x = x * TILE
                world_y = y * TILE
                rect = pygame.Rect(world_x, world_y, TILE, TILE)

                # Skip regular enemies in boss rooms
                if boss_present and entity_type != 'enemy_boss':
                    continue

                if entity_type == 'enemy':
                    self.enemies.append(Bug(rect.centerx, rect.bottom))
                elif entity_type == 'enemy_fast':
                    self.enemies.append(Frog(rect.centerx, rect.bottom))
                elif entity_type == 'enemy_ranged':
                    self.enemies.append(Archer(rect.centerx, rect.bottom))
                elif entity_type == 'enemy_wizard':
                    self.enemies.append(WizardCaster(rect.centerx, rect.bottom))
                elif entity_type == 'enemy_armor':
                    self.enemies.append(Assassin(rect.centerx, rect.bottom))
                elif entity_type == 'enemy_bee':
                    self.enemies.append(Bee(rect.centerx, rect.bottom))
                elif entity_type == 'enemy_boss':
                    self.enemies.append(Golem(rect.centerx, rect.bottom))
                elif entity_type == 'door':
                    self.doors.append(rect)

    def _update_solids_from_grid(self):
        """Update solids list from tile grid."""
        self.solids = []
        for y, row in enumerate(self.grid):
            for x, tile_value in enumerate(row):
                if tile_value >= 0:
                    from ..tiles import TileType
                    tile_type = TileType(tile_value)
                    tile_data = self.tile_registry.get_tile(tile_type)

                    # Add solids for tiles with full collision
                    if tile_data and tile_data.collision.collision_type == "full":
                        rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                        self.solids.append(rect)

    def _validate_spawn_position(self, spawn_pos):
        """Validate and adjust spawn position to prevent spawning inside walls."""
        x, y = spawn_pos
        player_rect = pygame.Rect(x, y, 18, 30)  # Player dimensions: 18x30

        # Check if spawn position is inside a solid tile
        tiles_in_rect = self.tile_collision.get_tiles_in_rect(player_rect, self.grid)
        for tile_type, tile_x, tile_y in tiles_in_rect:
            tile_data = self.tile_registry.get_tile(tile_type)
            if tile_data and tile_data.collision.collision_type == "full":
                # Spawn position is inside a solid tile, find a better position
                # Try to spawn above this tile (not below - we want player standing on top)
                new_y = tile_y * TILE - 30  # Player's top at tile_y * TILE - player_height
                return (x, new_y)

        # Also check if there's a solid tile directly below player's feet
        feet_y = y + 30
        tile_below = self.tile_collision.get_tile_at_pos(x + 9, feet_y + 1, self.grid)  # Center of player's feet
        if tile_below:
            tile_data = self.tile_registry.get_tile(tile_below)
            if tile_data and tile_data.collision.collision_type != "none":
                # Player is on solid ground, this spawn is valid
                return (x, y)

        # If no solid ground below, try to find the nearest solid ground below
        for check_y in range(int(feet_y), self.h, TILE):
            tile_at_y = self.tile_collision.get_tile_at_pos(x + 9, check_y, self.grid)
            if tile_at_y:
                tile_data = self.tile_registry.get_tile(tile_at_y)
                if tile_data and tile_data.collision.collision_type != "none":
                    # Found solid ground, adjust spawn position
                    new_y = check_y - 30
                    return (x, new_y)

        # If no solid ground found, return original position
        return (x, y)

    def get_tile_at(self, x: int, y: int) -> int:
        """Get tile value at grid position."""
        if 0 <= y < len(self.grid) and 0 <= x < len(self.grid[0]):
            return self.grid[y][x]
        return -1

    def set_tile_at(self, x: int, y: int, tile_value: int):
        """Set tile value at grid position."""
        if 0 <= y < len(self.grid) and 0 <= x < len(self.grid[0]):
            self.grid[y][x] = tile_value
            self._update_solids_from_grid()

    def draw(self, surf, camera):
        # Draw tiles using the new tile renderer
        camera_offset = (camera.x, camera.y)
        # visible_rect should be screen coordinates in pixels, not world coords
        visible_rect = pygame.Rect(0, 0, WIDTH, HEIGHT)
        self.tile_renderer.render_tile_grid(surf, self.grid, camera_offset, visible_rect, zoom=camera.zoom)

        # Draw doors (over tiles)
        for d in self.doors:
            # Locked (red) if boss room and boss still alive
            locked = getattr(self, 'is_boss_room', False) and any(getattr(e, 'alive', False) for e in self.enemies)
            col = (200, 80, 80) if locked else CYAN
            pygame.draw.rect(surf, col, camera.to_screen_rect(d), width=2)

    def draw_debug(self, surf, camera, show_collision_boxes=False):
        """Draw debug information about tiles."""
        camera_offset = (camera.x, camera.y)
        self.tile_renderer.render_debug_grid(surf, self.grid, camera_offset, show_collision_boxes, zoom=camera.zoom)