import pygame
from config import WHITE
from config import TILE

def los_clear(level, a, b, step=None):
    """Return True if the line segment a->b does not hit any solid tile.
    a,b are (x,y) world coordinates. Uses simple sampling along the line.
    """
    x1, y1 = a
    x2, y2 = b
    dx = x2 - x1
    dy = y2 - y1
    dist = max(1.0, (dx*dx + dy*dy) ** 0.5)
    # sample roughly every quarter-tile unless overridden
    step = step or max(2, int(TILE // 4))
    n = int(dist // step) + 1
    for i in range(n+1):
        t = i / max(1, n)
        px = x1 + dx * t
        py = y1 + dy * t
        p = pygame.Rect(int(px)-1, int(py)-1, 2, 2)
        for s in level.solids:
            if p.colliderect(s):
                return False
    return True

def find_intermediate_visible_point(level, enemy_pos, player_pos, radii=(TILE*2, TILE*3, TILE*4)):
    """Find a waypoint around player that has LOS to both enemy and player.
    Returns (x,y) or None if not found.
    """
    import math
    ex, ey = enemy_pos
    px, py = player_pos
    for r in radii:
        # sample around a circle
        for ang_deg in range(0, 360, 30):
            ang = math.radians(ang_deg)
            cx = int(px + r * math.cos(ang))
            cy = int(py + r * math.sin(ang))
            c = pygame.Rect(cx-2, cy-2, 4, 4)
            if any(c.colliderect(s) for s in level.solids):
                continue
            if los_clear(level, (cx, cy), (px, py)) and los_clear(level, (cx, cy), (ex, ey)):
                return (cx, cy)
    return None

def find_idle_patrol_target(level, home_pos, radius_tiles=4):
    """Pick a nearby point with LOS to home for idle patrol."""
    import random, math
    hx, hy = home_pos
    for _ in range(30):
        ang = random.uniform(0, 2*3.14159)
        r = random.randint(1, max(1, radius_tiles)) * TILE
        cx = int(hx + r * math.cos(ang))
        cy = int(hy + r * math.sin(ang))
        c = pygame.Rect(cx-2, cy-2, 4, 4)
        if any(c.colliderect(s) for s in level.solids):
            continue
        if los_clear(level, (cx, cy), (hx, hy)):
            return (cx, cy)
    return home_pos

# Lazy font getter to avoid init-order issues
_fonts = {}

def get_font(size=18, bold=False):
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont("consolas", size, bold=bold)
    return _fonts[key]

def draw_text(surf, text, pos, col=WHITE, size=18, bold=False):
    font = get_font(size=size, bold=bold)
    surf.blit(font.render(text, True, col), pos)

def sign(x):
    return (x > 0) - (x < 0)
