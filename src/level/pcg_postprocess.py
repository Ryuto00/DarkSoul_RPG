"""PCG postprocess - Phase 3: Functional Staircase builder + decorations.

This updated implementation adds two requested features:
 - A safe decorative pass that occasionally places small floating wall chunks.
 - A reverse-path builder from exits back to entrance so the player can return.

Fixes in this version:
 - Avoids counting/adding platforms where tiles are already wall.
 - Adds randomness control for decorations via `deco_chance`.
 - Ensures platform areas recorded reflect the actual changed contiguous tiles.
"""
from __future__ import annotations
from typing import Tuple, List, Optional, Set
from collections import deque
import random

from src.level.pcg_level_data import RoomData, PCGConfig
from src.utils.player_movement_profile import PlayerMovementProfile


def _is_excluded(room: RoomData, x: int, y: int) -> bool:
    areas = getattr(room, 'areas', []) or []
    for a in areas:
        if not isinstance(a, dict):
            continue
        if a.get('kind') == 'exclusion_zone':
            rects = a.get('rects') or []
            for r in rects:
                rx = int(r.get('x', 0))
                ry = int(r.get('y', 0))
                rw = int(r.get('w', 0))
                rh = int(r.get('h', 0))
                if rx <= x < rx + rw and ry <= y < ry + rh:
                    return True
    return False


def _is_in_door_carve_area(room: RoomData, x: int, y: int) -> bool:
    """Check if a position is within any door carve area."""
    areas = getattr(room, 'areas', []) or []
    for a in areas:
        if not isinstance(a, dict):
            continue
        if a.get('kind') == 'door_carve':
            rects = a.get('rects') or []
            for r in rects:
                rx = int(r.get('x', 0))
                ry = int(r.get('y', 0))
                rw = int(r.get('w', 0))
                rh = int(r.get('h', 0))
                if rx <= x < rx + rw and ry <= y < ry + rh:
                    return True
    return False


def _platform_intersects_door_area(room: RoomData, x: int, y: int, width: int, height: int = 1) -> bool:
    """Check if a platform rectangle intersects any door carve area."""
    # Check all tiles in the platform area
    for py in range(y, y + height):
        for px in range(x, x + width):
            if _is_in_door_carve_area(room, px, py):
                return True
    return False


def _add_platform_area(room: RoomData, x: int, y: int, width: int = 1, height: int = 1) -> None:
    areas = getattr(room, 'areas', []) or []
    areas.append({
        'kind': 'platform',
        'rects': [{'x': x, 'y': y, 'w': width, 'h': height}],
        'properties': {}
    })
    room.areas = areas


def _is_platform_too_close(
    room: RoomData, 
    new_x: int, new_y: int, new_w: int, new_h: int, 
    min_gap: int = 2
) -> bool:
    """
    Check whether a proposed platform (new_x,new_y,new_w,new_h) would be
    within min_gap tiles of any existing 'platform' area recorded in room.areas.

    This uses an AABB test where each existing platform rect is expanded by
    min_gap in all directions; if the proposed platform intersects that zone
    the function returns True (too close).
    """
    areas = getattr(room, 'areas', []) or []
    new_x_min = new_x
    new_y_min = new_y
    new_x_max = new_x + new_w
    new_y_max = new_y + new_h

    for a in areas:
        if not isinstance(a, dict) or a.get('kind') != 'platform':
            continue
        for rect in a.get('rects', []):
            ex = int(rect.get('x', 0))
            ey = int(rect.get('y', 0))
            ew = int(rect.get('w', 1))
            eh = int(rect.get('h', 1))

            zone_x_min = ex - min_gap
            zone_y_min = ey - min_gap
            zone_x_max = ex + ew + min_gap
            zone_y_max = ey + eh + min_gap

            x_overlaps = (new_x_min < zone_x_max) and (new_x_max > zone_x_min)
            y_overlaps = (new_y_min < zone_y_max) and (new_y_max > zone_y_min)

            if x_overlaps and y_overlaps:
                return True
    return False



def _find_entrance_positions(room: RoomData, tiles: List[List[int]], air_id: int) -> List[Tuple[int,int]]:
    areas = getattr(room, 'areas', []) or []
    out: List[Tuple[int,int]] = []
    h = len(tiles)
    w = len(tiles[0]) if h > 0 else 0
    for a in areas:
        if a.get('kind') == 'door_carve':
            for r in a.get('rects', []):
                if r.get('door_key') == 'entrance':
                    cx = int(r.get('x', 0) + (r.get('w', 1) // 2))
                    cy = int(r.get('y', 0) + (r.get('h', 1) // 2))
                    if 0 <= cx < w and 0 <= cy < h and tiles[cy][cx] == air_id:
                        out.append((cx, cy))
    # fallback: pick a low-left air tile
    if not out:
        for yy in range(h - 2, 0, -1):
            for xx in range(1, w - 1):
                if tiles[yy][xx] == air_id:
                    out.append((xx, yy))
                    break
            if out:
                break
    return out


def _collect_exit_rects(room: RoomData) -> List[Tuple[str, int, int, int, int]]:
    out: List[Tuple[str,int,int,int,int]] = []
    areas = getattr(room, 'areas', []) or []
    for a in areas:
        if not isinstance(a, dict):
            continue
        if a.get('kind') != 'door_carve':
            continue
        for r in a.get('rects', []):
            dk = r.get('door_key')
            if dk and dk.startswith('door_exit'):
                out.append((dk, int(r.get('x',0)), int(r.get('y',0)), int(r.get('w',1)), int(r.get('h',1))))
    return out


def _standable_tiles(tiles: List[List[int]], air_id: int, wall_id: int) -> Set[Tuple[int,int]]:
    h = len(tiles)
    w = len(tiles[0]) if h > 0 else 0
    out: Set[Tuple[int,int]] = set()
    for y in range(0, h - 1):
        for x in range(0, w):
            if tiles[y][x] == air_id and tiles[y+1][x] == wall_id:
                out.add((x,y))
    return out


def _reachable_from_entrance(
    tiles: List[List[int]],
    entrance_positions: List[Tuple[int,int]],
    profile: PlayerMovementProfile,
    config: PCGConfig,
    tile_size: int,
    consider_exclusion: Optional[callable] = None,  # type: ignore
) -> Set[Tuple[int,int]]:
    h = len(tiles)
    w = len(tiles[0]) if h > 0 else 0
    air_id = config.air_tile_id
    wall_id = config.wall_tile_id

    standable = _standable_tiles(tiles, air_id, wall_id)

    h_single_px, d_single_px = profile.compute_single_jump_metrics()
    use_double = (profile.double_jumps + profile.extra_jump_charges) > 0
    if use_double and getattr(profile, 'double_jumps', 0) > 0:
        h_double_px, d_double_px = profile.compute_double_jump_metrics()
    else:
        h_double_px, d_double_px = h_single_px, d_single_px

    max_h_px = max(h_single_px, h_double_px)
    max_d_px = max(d_single_px, d_double_px)
    tile_h = max(1, int(max_h_px // max(1, tile_size)))
    tile_d = max(1, int(max_d_px // max(1, tile_size)))

    q = deque()
    seen: Set[Tuple[int,int]] = set()

    for ex, ey in entrance_positions:
        if (ex, ey) in standable:
            q.append((ex, ey)); seen.add((ex, ey)); continue
        for fy in range(ey, h - 1):
            if (ex, fy) in standable:
                q.append((ex, fy)); seen.add((ex, fy)); break
        for dx in (-1, 1, -2, 2):
            nx = ex + dx
            if 0 <= nx < w:
                for fy in range(ey, h - 1):
                    if (nx, fy) in standable:
                        if (nx, fy) not in seen:
                            q.append((nx, fy)); seen.add((nx, fy)); break

    while q:
        x, y = q.popleft()
        for nx in (x - 1, x + 1):
            if 0 <= nx < w and (nx, y) in standable and (nx, y) not in seen:
                if consider_exclusion and consider_exclusion(nx, y):
                    pass
                else:
                    q.append((nx, y)); seen.add((nx, y))
        fy = y + 1
        while fy < h - 1:
            if (x, fy) in standable:
                if (x, fy) not in seen:
                    if consider_exclusion and consider_exclusion(x, fy):
                        break
                    q.append((x, fy)); seen.add((x, fy))
                break
            if tiles[fy][x] != air_id:
                break
            fy += 1
        y_min = max(0, y - tile_h)
        for ty in range(y_min, y):
            for tx in range(max(0, x - tile_d), min(w, x + tile_d + 1)):
                if (tx, ty) in standable and (tx, ty) not in seen:
                    clear = True
                    for cy in range(ty, y):
                        if tiles[cy][tx] != air_id:
                            clear = False; break
                    if not clear:
                        continue
                    if consider_exclusion and consider_exclusion(tx, ty):
                        continue
                    q.append((tx, ty)); seen.add((tx, ty))
    return seen


def _find_largest_run_in_list(sorted_positions: List[int], center: int) -> Tuple[int,int]:
    # sorted_positions is a sorted list of x positions where we changed tiles
    if not sorted_positions:
        return (0, 0)
    runs: List[Tuple[int,int]] = []
    start = sorted_positions[0]
    prev = start
    for p in sorted_positions[1:]:
        if p == prev + 1:
            prev = p
            continue
        runs.append((start, prev))
        start = p; prev = p
    runs.append((start, prev))
    # prefer run containing center
    for a,b in runs:
        if a <= center <= b:
            return (a, b - a + 1)
    # otherwise return largest run
    best = runs[0]
    best_len = best[1] - best[0] + 1
    for a,b in runs[1:]:
        l = b - a + 1
        if l > best_len:
            best = (a,b); best_len = l
    return (best[0], best[1] - best[0] + 1)


def add_floating_platforms(
    room: RoomData,
    profile: PlayerMovementProfile,
    config: PCGConfig,
    rng: Optional[random.Random] = None,
    tile_size: int = 24,
    max_platforms_per_room: int = 40,
    prefer_double_jump: bool = False,
    vertical_clearance: int = 2,
    deco_chance: float = 0.35,
) -> int:
    rng = rng or random.Random()
    tiles = getattr(room, 'tiles', None)
    if not tiles:
        return 0
    h = len(tiles)
    w = len(tiles[0])

    air_id = config.air_tile_id
    wall_id = config.wall_tile_id

    entrances = _find_entrance_positions(room, tiles, air_id)
    if not entrances:
        return 0

    exits = _collect_exit_rects(room)
    if not exits:
        return 0

    baseline_standable = _reachable_from_entrance(tiles, entrances, profile, config, tile_size, consider_exclusion=lambda x,y: _is_excluded(room, x, y))

    def exit_rect_tiles(x, y, w_rect, h_rect):
        out = []
        for yy in range(y, y + h_rect):
            for xx in range(x, x + w_rect):
                out.append((xx, yy))
        return out

    exit_initially_reachable = {}
    for dk, ex, ey, ew, eh in exits:
        reachable = False
        for tx, ty in exit_rect_tiles(ex, ey, ew, eh):
            if (tx, ty) in baseline_standable:
                reachable = True; break
            # conservative reachable test: check if any baseline standable tile can jump up to this tile
            for sx, sy in baseline_standable:
                if sy - ty <= 0:
                    continue
                vert = sy - ty
                h_single_px, d_single_px = profile.compute_single_jump_metrics()
                tile_h = max(1, int(h_single_px // max(1, tile_size)))
                if vert > tile_h:
                    continue
                dx = abs(sx - tx)
                tile_d = max(1, int(profile.compute_single_jump_metrics()[1] // max(1, tile_size)))
                if dx <= tile_d:
                    reachable = True; break
            if reachable:
                break
        exit_initially_reachable[dk] = reachable

    platforms_added = 0

    def exits_still_ok(tiles_grid) -> bool:
        st = _reachable_from_entrance(tiles_grid, entrances, profile, config, tile_size, consider_exclusion=lambda x,y: _is_excluded(room, x, y))
        for dk, was in exit_initially_reachable.items():
            if was:
                for edk, ex, ey, ew, eh in exits:
                    if edk == dk:
                        found = False
                        for tx, ty in exit_rect_tiles(ex, ey, ew, eh):
                            if (tx, ty) in st:
                                found = True; break
                        if not found:
                            return False
        return True

    # Enhanced staircase system: ensure bidirectional reachability
    # 1. Entrance → Exits (forward path)
    # 2. Pocket areas → Exits (escape path)  
    # 3. Exits → Entrance (return path)
    
    def build_connected_path(
        start_positions: List[Tuple[int,int]], 
        end_positions: List[Tuple[int,int]], 
        path_name: str, 
        rng: random.Random  # <-- MODIFIED: Added rng
    ):
        """Build a connected staircase path from start to end positions."""
        nonlocal platforms_added
        if platforms_added >= max_platforms_per_room:
            return
            
        # Find best start and end positions
        best_start = None
        best_end = None
        best_dist = None
        
        for sx, sy in start_positions:
            for ex, ey in end_positions:
                d = abs(sx - ex) + abs(sy - ey)
                if best_dist is None or d < best_dist:
                    best_start = (sx, sy)
                    best_end = (ex, ey)
                    best_dist = d
                    
        if not best_start or not best_end:
            return
            
        cur_x, cur_y = best_start
        target_x, target_y = best_end
        

        
        # Get player jump capabilities
        h_single_px, d_single_px = profile.compute_single_jump_metrics()
        tile_jump_h = max(2, int(h_single_px // max(1, tile_size)))  # At least 2 tiles high
        tile_jump_d = max(2, int(d_single_px // max(1, tile_size)))  # At least 2 tiles horizontal
        
        # Build connected staircase - each platform within jump range of previous
        steps = 0
        last_platform_x, last_platform_y = cur_x, cur_y
        
        # <-- MODIFIED: Increased step limit from 25
        consecutive_failures = 0
        while steps < 100 and platforms_added < max_platforms_per_room and consecutive_failures < 20:
            steps += 1
            
            # Check if target is reachable from current position
            if abs(cur_x - target_x) <= tile_jump_d and abs(cur_y - target_y) <= tile_jump_h:
                break
                
            # Calculate next platform position - move toward target
            dx = target_x - cur_x
            dy = target_y - cur_y
            
            # Prioritize vertical movement (upward), then horizontal
            if dy < -tile_jump_h:  # Need to go up significantly
                next_y = max(0, cur_y - tile_jump_h)
                # Move horizontally proportional to vertical change
                move_x_dir = 1 if dx > 0 else -1 if dx < 0 else 0
                next_x = max(1, min(w - 2, cur_x + (move_x_dir * (tile_jump_d // 2))))
            elif abs(dx) > tile_jump_d:  # Need horizontal movement
                move_x = tile_jump_d if dx > 0 else -tile_jump_d
                next_x = max(1, min(w - 2, cur_x + move_x))
                next_y = cur_y
            else:  # Fine adjustment (diagonal up-and-over)
                move_x_dir = 1 if dx > 0 else -1 if dx < 0 else 0
                next_x = max(1, min(w - 2, cur_x + (move_x_dir * tile_jump_d)))
                next_y = max(0, cur_y - (tile_jump_h // 2))
                
            # Platform should be below where we want to stand
            platform_y = next_y + 1
            if platform_y >= h - 1 or platform_y <= 0:
                break
                
            # Try to place platform with connected path logic
            placed = False
            for width in (3, 2, 1):
                x_start = max(1, min(w - width - 1, next_x - width // 2))
                
                # Check if this platform connects to previous platform
                can_connect = True
                if steps > 1:  # Not the first platform
                    # Check if we can jump from last platform to this one
                    dist_x = abs(x_start + width // 2 - last_platform_x)
                    dist_y = (last_platform_y) - (platform_y - 1) # vertical diff (positive=up)
                    
                    if dist_x > tile_jump_d or dist_y > tile_jump_h:
                        can_connect = False
                        # print(f"[DEBUG] CONNECTION FAILED: dist_x={dist_x} > jump_d={tile_jump_d} OR dist_y={dist_y} > jump_h={tile_jump_h}")
                    # else:
                        # print(f"[DEBUG] CONNECTION OK: dist_x={dist_x} <= jump_d={tile_jump_d} AND dist_y={dist_y} <= jump_h={tile_jump_h}")
                        
                if not can_connect:
                    continue
                    
                # Check if we can place platform here
                can_place = True
                
                # First check: Does the entire platform intersect any door carve area?
                if _platform_intersects_door_area(room, x_start, platform_y, width, 1):
                    can_place = False
                
                # Second check: Individual tile checks
                if can_place:
                    for xi in range(x_start, x_start + width):
                        if _is_excluded(room, xi, platform_y):
                            can_place = False; break
                        if tiles[platform_y][xi] != air_id:
                            can_place = False; break
                    if not can_place:
                        break
                        
                if can_place:
                    # --- NEW GAP CHECK ---
                    MIN_GAP = 3  # Increased from 2 to account for 2-tile high player
                    if _is_platform_too_close(room, x_start, platform_y, width, 1, MIN_GAP):
                        continue # Too close, try next width or position
                    # --- END NEW GAP CHECK ---

                    # <-- Tentative placement with safety check
                    saved_tiles = []
                    
                    # Place platform and save original tiles
                    for xi in range(x_start, x_start + width):
                        saved_tiles.append((xi, platform_y, tiles[platform_y][xi]))
                        tiles[platform_y][xi] = wall_id
                        # MODIFIED: Protect boundary by not modifying y=0
                        if platform_y - 1 >= 1:  # Changed from 0 to 1
                            saved_tiles.append((xi, platform_y - 1, tiles[platform_y - 1][xi]))
                            # Only clear to air if it's not a door tile
                            is_door_tile = False
                            
                            # Check if this tile is already a door tile by value
                            from src.tiles.tile_types import TileType
                            current_tile_value = tiles[platform_y - 1][xi]
                            if current_tile_value in (TileType.DOOR_ENTRANCE.value, TileType.DOOR_EXIT_1.value, TileType.DOOR_EXIT_2.value):
                                is_door_tile = True
                            else:
                                # Also check if this position is in a door carve area
                                room_areas = getattr(room, 'areas', []) or []
                                for a in room_areas:
                                    if a.get('kind') == 'door_carve':
                                        for r in a.get('rects', []):
                                            rx = int(r.get('x',0)); ry = int(r.get('y',0)); rw = int(r.get('w',1)); rh = int(r.get('h',1))
                                            if rx <= xi < rx + rw and ry <= (platform_y - 1) < ry + rh:
                                                is_door_tile = True; break
                                        if is_door_tile:
                                            break
                            
                            if not is_door_tile:
                                tiles[platform_y - 1][xi] = air_id
                    
                    # <-- NEW: Run safety check
                    if not exits_still_ok(tiles):
                        # REVERT: This platform blocked another path
                        for xi, yi, val in reversed(saved_tiles):
                            tiles[yi][xi] = val
                        continue # Try next width or position
                    # <-- END NEW
                        
                    _add_platform_area(room, x_start, platform_y, width=width, height=1)
                    platforms_added += width
                    
                    # Update positions for next iteration
                    last_platform_x, last_platform_y = x_start + width // 2, platform_y - 1
                    cur_x, cur_y = last_platform_x, last_platform_y
                    placed = True
                    consecutive_failures = 0
                    break
                    
            if not placed:
                # <-- MODIFIED: Smarter "get unstuck" logic
                # Can't place platform, try alternative approach by nudging
                # current position randomly to try a different path.
                
                consecutive_failures += 1
                
                # If we've failed too many times, give up on this path
                if consecutive_failures >= 10:
                    break
                
                # Nudge current position randomly - be more aggressive when stuck
                if consecutive_failures >= 5:
                    # After 5 failures, try bigger random jumps
                    cur_x = max(2, min(w - 2, rng.randint(2, w - 3)))
                    cur_y = max(2, min(h - 2, rng.randint(2, h - 3)))
                else:
                    # Normal nudging
                    cur_x = max(2, min(w - 2, last_platform_x + rng.randint(-tile_jump_d // 2, tile_jump_d // 2)))
                    cur_y = max(2, min(h - 2, last_platform_y + rng.randint(-tile_jump_h // 2, 0))) # Prefer nudging up, but stay away from top
                
                # Ensure new cur_pos is a valid standable spot
                if cur_y >= h - 1 or cur_y <= 1 or tiles[cur_y][cur_x] != air_id or tiles[cur_y + 1][cur_x] == air_id:
                    # Invalid start, revert to last good platform
                    cur_x, cur_y = last_platform_x, last_platform_y
                else:
                    consecutive_failures = 0
                
                continue

    # 1. Build paths from entrance to unreachable exits
    for dk, ex, ey, ew, eh in exits:
        if exit_initially_reachable.get(dk, False):
            continue  # Already reachable
            
        exit_centers = [(ex + ew // 2, ey + eh // 2)]
        build_connected_path(list(baseline_standable), exit_centers, f"entrance_to_{dk}", rng=rng)

    # 2. Build paths from pocket areas to exits (if pockets are trapped)
    pocket_areas = [a for a in getattr(room, 'areas', []) or [] if isinstance(a, dict) and a.get('kind') == 'pocket_room']
    for pocket in pocket_areas:
        rects = pocket.get('rects', []) or []
        if not rects:
            continue
        r = rects[0]
        rx, ry, rw, rh = int(r.get('x', 0)), int(r.get('y', 0)), int(r.get('w', 1)), int(r.get('h', 1))
        
        # Find standable tiles in pocket
        pocket_standable = []
        for yy in range(ry, ry + rh):
            for xx in range(rx, rx + rw):
                if (xx, yy) in baseline_standable:
                    pocket_standable.append((xx, yy))
                    
        if pocket_standable:
            continue  # Pocket already reachable
            
        # Try to connect pocket to nearest exit
        exit_centers = []
        for dk, ex, ey, ew, eh in exits:
            exit_centers.append((ex + ew // 2, ey + eh // 2))
            
        pocket_center = (rx + rw // 2, ry + rh // 2)
        build_connected_path([pocket_center], exit_centers, f"pocket_to_exit", rng=rng)

    # 3. Build return paths from exits back to entrance
    for dk, ex, ey, ew, eh in exits:
        exit_centers = [(ex + ew // 2, ey + eh // 2)]
        build_connected_path(exit_centers, list(baseline_standable), f"{dk}_to_entrance", rng=rng)

    # Reverse pass: ensure player can return from exits to entrances
    for dk, ex, ey, ew, eh in exits:
        if platforms_added >= max_platforms_per_room:
            break
        exit_starts: List[Tuple[int,int]] = []
        standable_all = _standable_tiles(tiles, air_id, wall_id)
        for yy in range(ey, ey + eh):
            for xx in range(ex, ex + ew):
                for fy in range(yy, h - 1):
                    if (xx, fy) in standable_all:
                        exit_starts.append((xx, fy)); break
                if exit_starts:
                    break
            if exit_starts:
                break
        if not exit_starts:
            continue
        exit_reach = _reachable_from_entrance(tiles, exit_starts, profile, config, tile_size, consider_exclusion=lambda x,y: _is_excluded(room, x, y))
        if baseline_standable.intersection(exit_reach):
            continue
        # otherwise attempt to build staircase from the exit side toward the nearest baseline_standable
        # pick nearest target standable tile from baseline_standable
        target = None; bestd = None; start = None
        # pick a representative start position from exit_reach (nearest to baseline)
        for sx, sy in exit_reach:
            for bx, by in baseline_standable:
                d = abs(sx - bx) + abs(sy - by)
                if start is None or bestd is None or d < bestd:
                    start = (sx, sy); target = (bx, by); bestd = d
        if start is None or target is None:
            continue
        cur_x, cur_y = start
        tx, ty = target
        attempts = 0
        while attempts < 60 and platforms_added < max_platforms_per_room:
            attempts += 1
            exit_reach = _reachable_from_entrance(tiles, exit_starts, profile, config, tile_size, consider_exclusion=lambda x,y: _is_excluded(room, x, y))
            if (tx, ty) in exit_reach:
                break
            h_single_px, _ = profile.compute_single_jump_metrics()
            tile_jump_h = max(1, int(h_single_px // max(1, tile_size)))
            desired_air_y = max(0, cur_y - tile_jump_h)
            new_solid_y = min(h-2, desired_air_y + 1)
            placed_this_iter = False
            for width in (1,2,3):
                center = (cur_x + tx) // 2
                x0 = max(1, min(w - width - 2, center - width // 2))
                for shift in (0, -1, 1, -2, 2):
                    x0_try = x0 + shift
                    if x0_try <= 0 or x0_try + width >= w:
                        continue
                    bad = False
                    
                    # First check: Does the entire platform intersect any door carve area?
                    if _platform_intersects_door_area(room, x0_try, new_solid_y, width, 1):
                        bad = True
                    
                    # Second check: Individual tile checks
                    if not bad:
                        for xi in range(x0_try, x0_try + width):
                            if _is_excluded(room, xi, new_solid_y):
                                bad = True; break
                        if bad:
                            break
                    if bad:
                        continue
                    
                    # --- NEW GAP CHECK ---
                    MIN_GAP = 3  # Increased from 2 to account for 2-tile high player
                    if _is_platform_too_close(room, x0_try, new_solid_y, width, 1, MIN_GAP):
                        continue # Too close, try next shift
                    # --- END NEW GAP CHECK ---

                    would_change = [xi for xi in range(x0_try, x0_try + width) if tiles[new_solid_y][xi] != wall_id]
                    if not would_change:
                        continue
                    saved = []
                    for xi in range(x0_try, x0_try + width):
                        saved.append((xi, new_solid_y, tiles[new_solid_y][xi]))
                        tiles[new_solid_y][xi] = wall_id
                        if new_solid_y - 1 >= 0:
                            saved.append((xi, new_solid_y - 1, tiles[new_solid_y - 1][xi]))
                            # Check if this is a door tile before clearing to air
                            from src.tiles.tile_types import TileType
                            current_tile_value = tiles[new_solid_y - 1][xi]
                            if current_tile_value not in (TileType.DOOR_ENTRANCE.value, TileType.DOOR_EXIT_1.value, TileType.DOOR_EXIT_2.value):
                                tiles[new_solid_y - 1][xi] = air_id
                    if not exits_still_ok(tiles):
                        for xi, yi, val in reversed(saved):
                            tiles[yi][xi] = val
                        continue
                    run_x0, run_w = _find_largest_run_in_list(sorted(would_change), center)
                    if run_w <= 0:
                        for xi, yi, val in reversed(saved):
                            tiles[yi][xi] = val
                        continue
                    _add_platform_area(room, run_x0, new_solid_y, width=run_w, height=1)
                    platforms_added += run_w
                    placed_this_iter = True
                    cur_x = run_x0 + (run_w // 2)
                    cur_y = new_solid_y - 1
                    break
                if placed_this_iter:
                    break
            if not placed_this_iter:
                if cur_x < tx:
                    cur_x = min(w-2, cur_x + 1)
                elif cur_x > tx:
                    cur_x = max(1, cur_x - 1)
                else:
                    if attempts > 30:
                        break
                continue

    # Pocket escape pass: ensure pocket_room areas are not trapping the player
    pocket_areas = [a for a in getattr(room, 'areas', []) or [] if isinstance(a, dict) and a.get('kind') == 'pocket_room']
    for a in pocket_areas:
        if platforms_added >= max_platforms_per_room:
            break
        rects = a.get('rects', []) or []
        if not rects:
            continue
        r = rects[0]
        rx = int(r.get('x', 0)); ry = int(r.get('y', 0)); rw = int(r.get('w', 1)); rh = int(r.get('h', 1))
        # pocket center
        pcx = rx + rw // 2; pcy = ry + rh // 2
        # find any standable tile inside the pocket that is baseline reachable
        pocket_standable = set()
        for yy in range(ry, ry + rh):
            for xx in range(rx, rx + rw):
                if (xx, yy) in baseline_standable:
                    pocket_standable.add((xx, yy))
        if pocket_standable:
            continue
        # attempt to build a short staircase from pocket toward nearest baseline_standable
        if not baseline_standable:
            continue
        # choose nearest baseline tile
        best = None; bestd = None
        for bx, by in baseline_standable:
            d = abs(bx - pcx) + abs(by - pcy)
            if best is None or bestd is None or d < bestd:
                best = (bx, by); bestd = d
        if best is None:
            continue
        target_x, target_y = best
        # start from pocket center; if center not standable try to make a start platform there
        cur_x, cur_y = pcx, pcy
        cur_solid_y = cur_y + 1
        # if center not air or inside exclusion, skip
        if _is_excluded(room, cur_x, cur_y) or tiles[cur_y][cur_x] != air_id:
            # find an air tile inside pocket
            found = False
            for yy in range(ry, ry + rh):
                for xx in range(rx, rx + rw):
                    if tiles[yy][xx] == air_id and not _is_excluded(room, xx, yy):
                        cur_x, cur_y = xx, yy
                        cur_solid_y = cur_y + 1
                        found = True; break
                if found:
                    break
            if not found:
                continue
        # try small staircase (limited attempts)
        attempts = 0
        while attempts < 40 and platforms_added < max_platforms_per_room:
            attempts += 1
            # check if any baseline standable is now reachable from this pocket start
            reach_from_pocket = _reachable_from_entrance(tiles, [(cur_x, cur_y)], profile, config, tile_size, consider_exclusion=lambda x,y: _is_excluded(room, x, y))
            if baseline_standable.intersection(reach_from_pocket):
                break
            # place small platform toward target
            h_single_px, _ = profile.compute_single_jump_metrics()
            tile_jump_h = max(1, int(h_single_px // max(1, tile_size)))
            desired_air_y = max(0, cur_y - tile_jump_h)
            new_solid_y = min(h-2, desired_air_y + 1)
            placed = False
            for width in (1,2):
                center = (cur_x + target_x) // 2
                x0 = max(rx, min(rx + rw - width, center - width // 2))
                for shift in (0, -1, 1):
                    x0_try = x0 + shift
                    if x0_try < rx or x0_try + width > rx + rw:
                        continue
                    bad = False
                    
                    # First check: Does entire platform intersect any door carve area?
                    if _platform_intersects_door_area(room, x0_try, new_solid_y, width, 1):
                        bad = True
                    
                    # Second check: Individual tile checks
                    if not bad:
                        for xi in range(x0_try, x0_try + width):
                            if _is_excluded(room, xi, new_solid_y):
                                bad = True; break
                        if bad:
                            break
                    if bad:
                        continue
                    
                    # --- NEW GAP CHECK ---
                    MIN_GAP = 3  # Increased from 2 to account for 2-tile high player
                    if _is_platform_too_close(room, x0_try, new_solid_y, width, 1, MIN_GAP):
                        continue # Too close, try next shift
                    # --- END NEW GAP CHECK ---
                    
                    # tentatively place
                    saved = []
                    for xi in range(x0_try, x0_try + width):
                        saved.append((xi, new_solid_y, tiles[new_solid_y][xi]))
                        tiles[new_solid_y][xi] = wall_id
                        if new_solid_y - 1 >= 0:
                            saved.append((xi, new_solid_y - 1, tiles[new_solid_y - 1][xi]))
                            # Check if this is a door tile before clearing to air
                            from src.tiles.tile_types import TileType
                            current_tile_value = tiles[new_solid_y - 1][xi]
                            if current_tile_value not in (TileType.DOOR_ENTRANCE.value, TileType.DOOR_EXIT_1.value, TileType.DOOR_EXIT_2.value):
                                tiles[new_solid_y - 1][xi] = air_id
                    if not exits_still_ok(tiles):
                        for xi, yi, val in reversed(saved):
                            tiles[yi][xi] = val
                        continue
                    _add_platform_area(room, x0_try, new_solid_y, width=width, height=1)
                    platforms_added += width
                    cur_x = x0_try + (width // 2)
                    cur_y = new_solid_y - 1
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                break
        # end pocket area attempts

    # Decorative pass: random floating chunks sometimes
    deco_limit = max(1, max_platforms_per_room // 4)
    deco_tries = 0
    deco_attempts = 0
    while deco_tries < deco_limit and platforms_added < max_platforms_per_room and deco_attempts < deco_limit * 8:
        deco_attempts += 1
        if rng.random() > deco_chance:
            continue
        row_y = rng.randint(1, max(1, h - 4))
        deco_width = rng.randint(1, min(4, max(1, w - 4)))
        x0 = rng.randint(2, max(2, w - deco_width - 2))
        x1 = x0 + deco_width
        ok = True
        would_change = []
        
        # First check: Does decorative platform intersect any door carve area?
        if _platform_intersects_door_area(room, x0, row_y, deco_width, 1):
            ok = False
        
        # Second check: Individual tile checks
        if ok:
            for xi in range(x0, x1):
                if xi <= 0 or xi >= w - 1 or tiles[row_y][xi] != air_id or _is_excluded(room, xi, row_y):
                    ok = False; break
                if (xi, row_y) in baseline_standable:
                    ok = False; break
                would_change.append(xi)
        if not ok or not would_change:
            continue

        # --- NEW GAP CHECK ---
        MIN_GAP = 3  # Increased from 2 to account for 2-tile high player
        # Note: We use deco_width, not run_w, for the check
        if _is_platform_too_close(room, x0, row_y, deco_width, 1, MIN_GAP):
            continue # Too close, try a new random spot
        # --- END NEW GAP CHECK ---

        saved = []
        for xi in range(x0, x1):
            saved.append((xi, row_y, tiles[row_y][xi]))
            tiles[row_y][xi] = wall_id
            if row_y - 1 >= 0:
                saved.append((xi, row_y - 1, tiles[row_y - 1][xi]))
                # Check if this is a door tile before clearing to air
                from src.tiles.tile_types import TileType
                current_tile_value = tiles[row_y - 1][xi]
                if current_tile_value not in (TileType.DOOR_ENTRANCE.value, TileType.DOOR_EXIT_1.value, TileType.DOOR_EXIT_2.value):
                    tiles[row_y - 1][xi] = air_id
        if not exits_still_ok(tiles):
            for xi, yi, val in reversed(saved):
                tiles[yi][xi] = val
            continue
        run_x0, run_w = _find_largest_run_in_list(sorted(would_change), x0 + deco_width // 2)
        if run_w <= 0:
            for xi, yi, val in reversed(saved):
                tiles[yi][xi] = val
            continue
        _add_platform_area(room, run_x0, row_y, width=run_w, height=1)
        platforms_added += run_w
        deco_tries += 1

    # Final repair pass: DISABLED FOR DEBUGGING
    # The repair pass was removing all platforms, so let's see if they get placed first
    return platforms_added


def add_enemy_spawn_areas(
    room: RoomData,
    config: PCGConfig,
    rng: Optional[random.Random] = None,
    min_regions: int = 1,
    max_regions: int = 4,
    min_size: int = 3,
    max_size: int = 7,
    allowed_enemy_types: Optional[List[str]] = None,
    air_clearance: int = 4,
) -> int:
    """
    Annotate the room with `spawn` areas (metadata only). Does NOT modify tiles.

    - Finds standable tiles and attempts to place small rectangular spawn regions.
    - Avoids `exclusion_zone`, `door_carve`, and `platform` areas.
    - Adds dicts to `room.areas` in the same shape used elsewhere so JSON is serializable.
    - Adds `properties.spawn_surface` = 'ground'|'air'|'both' to help runtime choose proper enemies.
    Returns number of regions added.
    """
    rng = rng or random.Random()
    tiles = getattr(room, 'tiles', None)
    if not tiles:
        return 0
    h = len(tiles)
    w = len(tiles[0]) if h > 0 else 0

    air_id = config.air_tile_id
    wall_id = config.wall_tile_id

    standable = _standable_tiles(tiles, air_id, wall_id)
    if not standable:
        return 0

    # build protected set from existing areas
    # Build protected tile set from areas we should avoid (exclusions, platforms)
    protected: Set[Tuple[int,int]] = set()
    pocket_rects: List[Tuple[int,int,int,int]] = []
    door_rects: List[Tuple[int,int,int,int]] = []
    for a in getattr(room, 'areas', []) or []:
        if not isinstance(a, dict):
            continue
        kind = a.get('kind')
        rects = a.get('rects') or []
        for r in rects:
            rx = int(r.get('x', 0)); ry = int(r.get('y', 0)); rw = int(r.get('w', 0)); rh = int(r.get('h', 0))
            if kind == 'pocket_room':
                pocket_rects.append((rx, ry, rw, rh))
            if kind == 'door_carve':
                door_rects.append((rx, ry, rw, rh))
            for yy in range(ry, ry + rh):
                for xx in range(rx, rx + rw):
                    if kind in ('exclusion_zone', 'platform'):
                        protected.add((xx, yy))

    # Also protect tiles within a radius around doors (pad), but allow tiles inside pocket rooms
    DOOR_PAD = 10
    for (drx, dry, drw, drh) in door_rects:
        x0 = max(0, drx - DOOR_PAD)
        x1 = min(w, drx + drw + DOOR_PAD)
        y0 = max(0, dry - DOOR_PAD)
        y1 = min(h, dry + drh + DOOR_PAD)
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                # skip if inside any pocket rect (pocket areas still allowed)
                inside_pocket = False
                for prx, pry, prw, prh in pocket_rects:
                    if prx <= xx < prx + prw and pry <= yy < pry + prh:
                        inside_pocket = True; break
                if not inside_pocket:
                    protected.add((xx, yy))

    # First: convert any pocket_room areas into full spawn regions (use 'both' surface)
    pocket_areas = [a for a in getattr(room, 'areas', []) or [] if isinstance(a, dict) and a.get('kind') == 'pocket_room']
    pocket_converted = 0
    if pocket_areas:
        # remove any existing spawn areas that overlap pocket rects, then add full-pocket spawn
        new_areas = []
        existing_areas = getattr(room, 'areas', []) or []
        for a in existing_areas:
            if not isinstance(a, dict) or a.get('kind') != 'spawn':
                new_areas.append(a)
                continue
            # check if this spawn overlaps any pocket rect; if so, drop it
            spawn_overlaps_pocket = False
            for pa in pocket_areas:
                for pr in pa.get('rects', []) or []:
                    prx = int(pr.get('x', 0)); pry = int(pr.get('y', 0)); prw = int(pr.get('w', 1)); prh = int(pr.get('h', 1))
                    for sr in a.get('rects', []) or []:
                        sx = int(sr.get('x', 0)); sy = int(sr.get('y', 0)); sw = int(sr.get('w', 1)); sh = int(sr.get('h', 1))
                        if not (prx + prw <= sx or sx + sw <= prx or pry + prh <= sy or sy + sh <= pry):
                            spawn_overlaps_pocket = True; break
                    if spawn_overlaps_pocket:
                        break
                if spawn_overlaps_pocket:
                    break
            if not spawn_overlaps_pocket:
                new_areas.append(a)
        # replace room.areas temporarily to avoid duplicate checks below
        room.areas = new_areas

        # now append pocket-based spawn regions
        for pa in pocket_areas:
            for r in pa.get('rects', []) or []:
                rx = int(r.get('x', 0)); ry = int(r.get('y', 0)); rw = int(r.get('w', 1)); rh = int(r.get('h', 1))
                if rw <= 0 or rh <= 0:
                    continue
                # determine allowed enemy types for pocket (default to both types)
                surface = 'both'
                if allowed_enemy_types is not None:
                    aet = allowed_enemy_types
                else:
                    if surface == 'ground':
                        aet = ['Bug','Frog','Archer','Assassin','Golem']
                    elif surface == 'air':
                        aet = ['Bee','WizardCaster']
                    else:
                        aet = ['Bug','Frog','Archer','Assassin','Bee','WizardCaster','Golem']

                props = {
                    'spawn_cap': max(1, (rw * rh) // 2),
                    'spawn_weight': max(1, 2 * rw * rh),
                    'allowed_enemy_types': aet,
                    'spawn_surface': 'both',
                }
                room.areas.append({
                    'kind': 'spawn',
                    'rects': [{'x': rx, 'y': ry, 'w': rw, 'h': rh}],
                    'properties': props,
                })
                pocket_converted += 1

    # Build horizontal runs of contiguous standable tiles (prefer bigger areas)
    runs: List[Tuple[int,int,int]] = []  # (x0, y, length)
    for y in range(0, h - 1):
        x = 1
        while x < w - 1:
            if (x, y) in standable and (x, y) not in protected:
                start = x
                x += 1
                while x < w - 1 and (x, y) in standable and (x, y) not in protected:
                    x += 1
                runs.append((start, y, x - start))
            else:
                x += 1

    # Filter runs that are at least min_size long
    runs = [r for r in runs if r[2] >= min_size]
    if not runs:
        return 0

    # sort runs by length descending (prefer larger contiguous areas)
    runs.sort(key=lambda r: r[2], reverse=True)

    to_place = max(0, rng.randint(min_regions, max_regions))
    placed = 0
    used_tiles: Set[Tuple[int,int]] = set()

    room.areas = getattr(room, 'areas', []) or []

    for start_x, ry, length in runs:
        if placed >= to_place:
            break
        # try to carve this run into one or more spawn rects
        remaining = length
        cur_x = start_x
        while remaining >= min_size and placed < to_place:
            # choose width up to max_size but not larger than remaining
            rw = min(max_size, remaining)
            # prefer larger widths: bias toward rw but allow smaller
            if rw > min_size and rng.random() < 0.5:
                # sometimes shrink a bit to produce multiple regions
                rw = rng.randint(min_size, rw)

            # pick rect's left edge within the run to avoid edge collisions
            x0 = cur_x + rng.randint(0, max(0, remaining - rw))
            # vertical placement: prefer the standable row (ry)
            rh = 1
            y0 = ry

            # validate rect is within bounds and tiles are air and not protected
            bad = False
            rect_tiles = []
            for yy in range(y0, y0 + rh):
                if yy < 0 or yy >= h:
                    bad = True; break
                for xx in range(x0, x0 + rw):
                    if xx < 0 or xx >= w:
                        bad = True; break
                    if (xx, yy) in protected:
                        bad = True; break
                    if tiles[yy][xx] != air_id:
                        bad = True; break
                    rect_tiles.append((xx, yy))
                if bad:
                    break
            if bad:
                # try shrinking width once
                if rw > min_size:
                    rw = max(min_size, rw - 1)
                    continue
                else:
                    break

            # determine surface classification
            has_ground = False
            below_y = y0 + rh
            for xx in range(x0, x0 + rw):
                if 0 <= below_y < h and tiles[below_y][xx] == wall_id:
                    has_ground = True; break
            has_clearance = True
            for xx in range(x0, x0 + rw):
                for dy in range(1, air_clearance + 1):
                    check_y = y0 - dy
                    if check_y < 0:
                        break
                    if tiles[check_y][xx] != air_id:
                        has_clearance = False; break
                if not has_clearance:
                    break

            if has_ground and not has_clearance:
                surface = 'ground'
            elif has_clearance and not has_ground:
                surface = 'air'
            else:
                surface = 'both'

            # require sensible surface
            if surface == 'air' and not has_clearance:
                # shrink/skip
                remaining -= rw
                cur_x += rw
                continue
            if surface == 'ground' and not has_ground:
                remaining -= rw
                cur_x += rw
                continue

            # determine allowed enemy types for this region
            if allowed_enemy_types is not None:
                aet = allowed_enemy_types
            else:
                if surface == 'ground':
                    aet = ['Bug','Frog','Archer','Assassin','Golem']
                elif surface == 'air':
                    aet = ['Bee','WizardCaster']
                else:
                    aet = ['Bug','Frog','Archer','Assassin','Bee','WizardCaster','Golem']

            props = {
                'spawn_cap': max(1, (rw * rh) // 1),
                'spawn_weight': max(1, 2 * rw * rh),
                'allowed_enemy_types': aet,
                'spawn_surface': surface,
            }

            # Ensure room.areas is a list
            if room.areas is None:
                room.areas = []
            room.areas.append({
                'kind': 'spawn',
                'rects': [{'x': x0, 'y': y0, 'w': rw, 'h': rh}],
                'properties': props,
            })

            for t in rect_tiles:
                used_tiles.add(t)

            placed += 1

            # advance past this placed rect inside the run
            # reduce remaining and move cur_x forward
            advance = (x0 + rw) - cur_x
            cur_x = x0 + rw
            remaining = start_x + length - cur_x
            if remaining <= 0:
                break

    return placed

    # Original repair pass code (disabled):
    # if any exits remain unreachable, try removing
    # individual platform areas (last placed first) to restore access.
    # This handles the case where a previously-accepted platform later
    # contributed to blocking a path.
    def exits_reachability_map(tiles_grid) -> dict:
        st = _reachable_from_entrance(tiles_grid, entrances, profile, config, tile_size, consider_exclusion=lambda x,y: _is_excluded(room, x, y))
        out = {}
        for dk, ex, ey, ew, eh in exits:
            ok = False
            for tx, ty in exit_rect_tiles(ex, ey, ew, eh):
                if (tx, ty) in st:
                    ok = True; break
            out[dk] = ok
        return out

    # TEMPORARILY DISABLED: Repair pass that removes platforms
    # current_map = exits_reachability_map(tiles)
    # print(f"[DEBUG] Exit reachability before repair: {current_map}")
    # # if any exit unreachable, attempt removals
    # # But be less aggressive - only remove if platform actually blocks reachability
    # if not all(current_map.values()) and platforms_added > 0:
        # collect platform areas with their indices
        platform_indices = [i for i, a in enumerate(getattr(room, 'areas', []) or []) if isinstance(a, dict) and a.get('kind') == 'platform']
        # try platforms in reverse (last placed first)
        changed = True
        while changed and not all(current_map.values()):
            changed = False
            for idx in reversed(platform_indices):
                areas_list = getattr(room, 'areas', []) or []
                if idx < 0 or idx >= len(areas_list):
                    continue
                a = areas_list[idx]
                if not isinstance(a, dict) or a.get('kind') != 'platform':
                    continue
                rects = a.get('rects', []) or []
                if not rects:
                    continue
                # support multiple rects in one area, but handle first rect primarily
                r = rects[0]
                rx = int(r.get('x', 0)); ry = int(r.get('y', 0)); rw = int(r.get('w', 1)); rh = int(r.get('h', 1))
                # save tiles
                saved = []
                for yy in range(ry, ry + rh):
                    if yy < 0 or yy >= h:
                        continue
                    for xx in range(rx, rx + rw):
                        if 0 <= xx < w:
                            saved.append((xx, yy, tiles[yy][xx]))
                # also ensure tile above cleared
                for yy in range(ry - 1, ry + rh):
                    if yy < 0 or yy >= h:
                        continue
                    for xx in range(rx, rx + rw):
                        if 0 <= xx < w:
                            saved.append((xx, yy, tiles[yy][xx]))
                # apply removal: set solid row(s) to air and above to air
                for yy in range(ry, ry + rh):
                    if yy < 0 or yy >= h:
                        continue
                    for xx in range(rx, rx + rw):
                        if 0 <= xx < w:
                            tiles[yy][xx] = air_id
                for yy in range(ry - 1, ry + rh):
                    if 0 <= yy < h:
                        for xx in range(rx, rx + rw):
                            if 0 <= xx < w:
                                tiles[yy][xx] = air_id
                # re-check reachability map
                new_map = exits_reachability_map(tiles)
                # acceptance condition: more exits reachable (or no regressions)
                # ensure we didn't lose any exit that was reachable before removal
                lost = False
                for k, v in current_map.items():
                    if v and not new_map.get(k, False):
                        lost = True; break
                improved = any((not current_map[k]) and new_map.get(k, False) for k in current_map)
                if not lost and (improved or not any(current_map.values())):
                    # accept removal: remove area entry
                    try:
                        del areas_list[idx]
                    except Exception:
                        pass
                    platforms_removed = 0
                    for xx, yy, val in saved:
                        # count removed solid tiles (only count those that were wall before)
                        if val == wall_id:
                            platforms_removed += 1
                    platforms_added = max(0, platforms_added - platforms_removed)
                    current_map = new_map
                    changed = True
                    # update platform_indices to reflect shorter areas list
                    platform_indices = [i for i, a in enumerate(getattr(room, 'areas', []) or []) if isinstance(a, dict) and a.get('kind') == 'platform']
                    # break to re-evaluate from newest platform again
                    break
                else:
                    # revert the tiles
                    for xx, yy, val in saved:
                        # MODIFIED: Changed bounds to protect the outer wall (1 instead of 0)
                        if 1 <= yy < h - 1 and 1 <= xx < w - 1:
                            tiles[yy][xx] = val
            # end for
        # end while
    return platforms_added
