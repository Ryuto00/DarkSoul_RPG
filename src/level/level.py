import pygame
from config import TILE, TILE_COL, CYAN, TILE_SYMBOLS
from ..entities.entities import Bug, Boss, Frog, Archer, WizardCaster, Assassin, Bee, Golem

# Rooms (tilemaps). Legend: # wall, . floor/empty, S spawn, E enemy, D door->next room
# Extra enemies: f=Frog, r=Archer, w=WizardCaster, a=Assassin, b=Bee, G=Golem boss
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
        self.spawn = (TILE * 2, TILE * 2)

        # detect if this room contains a boss tile; boss rooms should not
        # spawn normal 'E' enemies so the boss is the sole opponent
        boss_present = any(('B' in row) or ('G' in row) for row in raw)
        self.is_boss_room = boss_present

        # Normalize all rows to the same width so each ASCII character maps
        # 1:1 to a tile. Pad with '.' (empty space) so we don't accidentally
        # introduce solids, and treat unknown chars as empty terrain.
        max_w = max(len(row) for row in raw)
        rows = []
        for row in raw:
            if len(row) < max_w:
                pad_char = row[-1] if row else '.'
                row = row + (pad_char * (max_w - len(row)))
            rows.append(row)

        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                # Sanitize stray characters to empty terrain for a clean 1:1 map
                if ch not in {'#', '.', 'S', 'E', 'B', 'f', 'r', 'w', 'a', 'b', 'G', 'D'}:
                    ch = '.'
                r = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                if ch == '#':
                    self.solids.append(r)
                elif ch == 'S':
                    self.spawn = (x * TILE, y * TILE)
                elif ch == 'E':
                    # skip regular enemies in boss rooms
                    if not boss_present:
                        self.enemies.append(Bug(r.centerx, r.bottom))
                elif ch == 'B':
                    # spawn the boss (placed at tile center x, bottom y)
                    self.enemies.append(Boss(r.centerx, r.bottom))
                elif ch == 'f':
                    if not boss_present:
                        self.enemies.append(Frog(r.centerx, r.bottom))
                elif ch == 'r':
                    if not boss_present:
                        self.enemies.append(Archer(r.centerx, r.bottom))
                elif ch == 'w':
                    if not boss_present:
                        self.enemies.append(WizardCaster(r.centerx, r.bottom))
                elif ch == 'a':
                    if not boss_present:
                        self.enemies.append(Assassin(r.centerx, r.bottom))
                elif ch == 'b':
                    if not boss_present:
                        self.enemies.append(Bee(r.centerx, r.bottom))
                elif ch == 'G':
                    # golem boss
                    self.enemies.append(Golem(r.centerx, r.bottom))
                elif ch == 'D':
                    self.doors.append(r)

        self.w = max_w * TILE
        self.h = len(rows) * TILE

    def draw(self, surf, camera):
        for r in self.solids:
            pygame.draw.rect(surf, TILE_COL, camera.to_screen_rect(r), border_radius=6)
        for d in self.doors:
            # Locked (red) if boss room and boss still alive
            locked = getattr(self, 'is_boss_room', False) and any(getattr(e, 'alive', False) for e in self.enemies)
            col = (200, 80, 80) if locked else CYAN
            pygame.draw.rect(surf, col, camera.to_screen_rect(d), width=2)

# Expose ROOM_COUNT via module-level constant; kept for backward compatibility.
# Note: main.py now imports ROOM_COUNT directly from this module.
