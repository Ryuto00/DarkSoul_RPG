import pygame
from config import TILE, TILE_COL, CYAN, TILE_SYMBOLS, WIDTH, HEIGHT
from ..entities.entities import Bug, Boss, Frog, Archer, WizardCaster, Assassin, Bee, Golem
from ..tiles import TileParser, TileRenderer, TileRegistry
from ..tiles.tile_collision import TileCollision

# Rooms (tilemaps). Legend:
#   # wall, . floor/empty, S spawn, E enemy, D door->next room
#   Extra enemies: f=Frog, r=Archer, w=WizardCaster, a=Assassin, b=Bee, G=Golem boss
#   New tiles: B=Breakable Wall, b=Breakable Floor, _=Platform
# NOTE:
#   Procedural generation has been removed. These static rooms are now the
#   canonical and only level layouts used by the game.
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
        "#.....................................#",
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

class Level:
    def __init__(self, index=0):
        self.index = index % len(ROOMS)
        raw = ROOMS[self.index]
        self.solids = []
        self.enemies = []
        self.doors = []
        # Default spawn position - offset by player height to place feet on tile
        self.spawn = (TILE * 2, TILE * 2 - 30)

        # Initialize new tile system components
        self.tile_parser = TileParser()
        self.tile_renderer = TileRenderer(TILE)
        self.tile_registry = TileRegistry()

        # Parse ASCII level to tile grid
        self.grid, entity_positions = self.tile_parser.parse_ascii_level(raw)

        # Load entities from parsed positions
        self._load_entities(entity_positions)

        # Keep solids list for backward compatibility with physics system
        self._update_solids_from_grid()

        # Level dimensions
        self.w = len(self.grid[0]) * TILE if self.grid else 0
        self.h = len(self.grid) * TILE

        # Tile collision handler used by entities (e.g., player).
        # This is the authoritative TileCollision used by moving entities.
        self.tile_collision = TileCollision(TILE)

        # Validate spawn position to ensure player doesn't spawn inside walls
        self.spawn = self._validate_spawn_position(self.spawn)

    def _load_entities(self, entity_positions):
        """Load enemies and special objects from parsed positions."""
        # Check if boss is present
        boss_present = 'enemy_boss' in entity_positions or len(entity_positions.get('boss', [])) > 0
        self.is_boss_room = boss_present

        # Load spawn point
        if 'spawn' in entity_positions:
            for x, y in entity_positions['spawn']:
                # Position player's feet at the spawn point, accounting for player height
                # Player height is 30px, so we offset by player height to place feet on tile
                self.spawn = (x * TILE, y * TILE - 30)

        # Load enemies
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
                elif entity_type == 'enemy_boss':
                    self.enemies.append(Golem(rect.centerx, rect.bottom))
                elif entity_type == 'door':
                    self.doors.append(rect)

    def _update_solids_from_grid(self):
        """Update solids list from tile grid for backward compatibility."""
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
                # Try to spawn below this tile
                new_y = (tile_y + 1) * TILE - 30  # Place player's feet on the tile below
                return (x, new_y)

        # Also check if there's a solid tile directly below the player's feet
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

# Expose ROOM_COUNT via module-level constant; kept for backward compatibility.
# Note: main.py now imports ROOM_COUNT directly from this module.
