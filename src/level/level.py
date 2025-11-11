import pygame
from typing import Optional, List
from config import TILE, TILE_COL, CYAN, WIDTH, HEIGHT
from ..entities.entities import Bug, Boss, Frog, Archer, WizardCaster, Assassin, Bee, Golem
from ..tiles import TileParser, TileRenderer, TileRegistry, TileType
from ..tiles.tile_collision import TileCollision
from src.level.room_data import GenerationConfig, MovementAttributes, RoomData
from src.level.level_data import LevelData, LevelGenerationConfig
from src.level.graph_generator import generate_complete_level

# Rooms (tilemaps). Legend:
#   Tiles: # wall, . air/empty, _ platform, @ breakable wall, % breakable floor
#   Entities: S spawn, D door->next room
#   Enemies: E=Bug, f=Frog, r=Archer, w=WizardCaster, a=Assassin, b=Bee, G=Golem boss
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
    def __init__(self, index=0, room_data: Optional[RoomData] = None, level_data: Optional[LevelData] = None, room_id: Optional[str] = None):
        """
        Initialize a level, either from static rooms (legacy) or procedural generation.
        
        Args:
            index: Legacy room index (unused if room_data provided)
            room_data: Procedurally generated room (new system)
            level_data: Complete level data for multi-room dungeons
            room_id: Which room in level_data to load
        """
        self.index = index
        self.level_data = level_data  # Store for room transitions
        self.current_room_id = room_id  # Track current room in level
        
        # NEW: Use procedural room if provided
        if room_data is not None:
            raw = self._convert_roomdata_to_ascii(room_data)
            print("\n[DEBUG] Generated Room ASCII:")
            for line in raw:
                print(line)
            print("[DEBUG] End Room ASCII\n")
            self.procedural = True
            
            # NEW: Use player_spawn from procedural room when entering fresh level
            if hasattr(room_data, 'player_spawn') and room_data.player_spawn:
                # Convert procedural spawn center to world coordinates
                spawn_x, spawn_y = room_data.player_spawn
                self.spawn = (spawn_x * TILE, spawn_y * TILE)
                print(f"[LEVEL DEBUG] Using procedural player spawn at ({spawn_x}, {spawn_y}) -> world {self.spawn}")
        else:
            # LEGACY: Use static rooms
            self.index = index % len(ROOMS)
            raw = ROOMS[self.index]
            self.procedural = False
        
        self.solids = []
        self.enemies = []
        self.doors = []
        self.spawn = (TILE * 2, TILE * 2)
        
        # Initialize tile system
        self.tile_parser = TileParser()
        self.tile_renderer = TileRenderer(TILE)
        self.tile_registry = TileRegistry()
        
        # Parse ASCII (legacy mode for static rooms, normal mode for procedural)
        self.grid, entity_positions = self.tile_parser.parse_ascii_level(
            raw, 
            legacy=(not self.procedural)
        )
        
        # Load entities
        self._load_entities(entity_positions)
        self._update_solids_from_grid()
        
        # Level dimensions
        self.w = len(self.grid[0]) * TILE if self.grid else 0
        self.h = len(self.grid) * TILE
        
        self.tile_collision = TileCollision(TILE)
        self.spawn = self._validate_spawn_position(self.spawn)
    
    def _convert_roomdata_to_ascii(self, room_data: RoomData) -> List[str]:
        """
        Convert RoomData (sparse grid) to ASCII format for TileParser.
        
        Returns:
            List of strings, one per row
        """
        width, height = room_data.size
        ascii_rows = []
        
        for y in range(height):
            row = []
            for x in range(width):
                tile = room_data.get_tile(x, y)
                
                # Map tile types to ASCII characters
                if tile.t == "WALL":
                    if "PLATFORM" in tile.flags:
                        row.append('_')  # Platform (can jump through from below)
                    else:
                        row.append('#')  # Solid wall
                elif tile.t == "AIR":
                    # Check for doors
                    if (x, y) == room_data.entrance_coords:
                        row.append('S')  # Spawn/entrance
                    elif (x, y) == room_data.exit_coords:
                        row.append('D')  # Door/exit
                    else:
                        row.append('.')  # Empty air
                else:
                    row.append('.')  # Unknown → air
            
            ascii_rows.append(''.join(row))
        
        return ascii_rows

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
                raw_spawn = (x * TILE, y * TILE)
                print(f"[LEVEL DEBUG] Raw spawn position from 'S': ({x}, {y}) -> {raw_spawn}")
                self.spawn = raw_spawn

        print(f"[LEVEL DEBUG] Final spawn before validation: {self.spawn}")

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
                elif entity_type == 'enemy_bee':
                    self.enemies.append(Bee(rect.centerx, rect.bottom))
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
        print(f"[SPAWN VALIDATION] Validating spawn at ({x}, {y})")
        player_rect = pygame.Rect(x, y, 18, 30)  # Player dimensions: 18x30
        print(f"[SPAWN VALIDATION] Player rect: {player_rect}")

        # Check if spawn position is inside a solid tile
        tiles_in_rect = self.tile_collision.get_tiles_in_rect(player_rect, self.grid)
        print(f"[SPAWN VALIDATION] Tiles in player rect: {len(tiles_in_rect)}")
        for tile_type, tile_x, tile_y in tiles_in_rect:
            tile_data = self.tile_registry.get_tile(tile_type)
            print(f"[SPAWN VALIDATION] Found tile {tile_type} at ({tile_x}, {tile_y}): collision_type={getattr(tile_data.collision, 'collision_type', 'none') if tile_data else 'no data'}")
            if tile_data and tile_data.collision.collision_type == "full":
                # Spawn position is inside a solid tile, find a better position
                # Try to spawn below this tile
                new_y = tile_y * TILE - 30  # Player's top at tile_y * TILE - player_height
                print(f"[SPAWN VALIDATION] Spawn inside solid! Adjusting to ({x}, {new_y})")
                return (x, new_y)

        # Also check if there's a solid tile directly below the player's feet
        feet_y = y + 30
        tile_below = self.tile_collision.get_tile_at_pos(x + 9, feet_y + 1, self.grid)  # Center of player's feet
        print(f"[SPAWN VALIDATION] Tile below feet at ({x+9}, {feet_y+1}): {tile_below}")
        if tile_below:
            tile_data = self.tile_registry.get_tile(tile_below)
            if tile_data and tile_data.collision.collision_type != "none":
                # Player is on solid ground, this spawn is valid
                print(f"[SPAWN VALIDATION] Valid spawn on solid ground")
                return (x, y)

        # If no solid ground below, try to find the nearest solid ground below
        print(f"[SPAWN VALIDATION] No ground below, searching for ground...")
        for check_y in range(int(feet_y), self.h, TILE):
            tile_at_y = self.tile_collision.get_tile_at_pos(x + 9, check_y, self.grid)
            if tile_at_y:
                tile_data = self.tile_registry.get_tile(tile_at_y)
                if tile_data and tile_data.collision.collision_type != "none":
                    # Found solid ground, adjust spawn position
                    new_y = check_y - 30
                    print(f"[SPAWN VALIDATION] Found ground at y={check_y}, adjusted to ({x}, {new_y})")
                    return (x, new_y)

        # If no solid ground found, return original position
        print(f"[SPAWN VALIDATION] No ground found, using original position")
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
