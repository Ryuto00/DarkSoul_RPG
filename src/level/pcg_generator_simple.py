"""Simple PCG level generator using pcg_level_data structures.

This module:
- Loads PCGConfig from JSON via config_loader
- Generates 1..num_levels levels
- For each level, creates 6 "room numbers" (1-6)
  - Each number spawns 1 or 2 rooms (A, or A and B)
- Assigns room_code as f"{level_id}{slot}{letter}" (e.g. 11A, 12B)
- Fills tiles with wall boundary + air interior
- Wires doors according to rules:
  - Only transitions from number N -> N+1
  - No same-number transitions (no 1A -> 1B)
  - If next number has only A: exit_1 -> A, no exit_2
  - If next number has A and B: exit_1 -> A, exit_2 -> B
  - End of last number in level N routes to first number in level N+1
    using same rule as above
  - Last level's last number has no exits
- Computes entrance_from as the first room that leads into a room

Door tiles are NOT placed in the tile grid here; this module only
manages logical connectivity via door_exits and entrance_from.
"""

from __future__ import annotations

import random
from typing import List, Dict, Optional, Tuple, Set
import os
import sys

# Ensure project root is on path when running this module directly
if __name__ == "__main__":
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from src.level.config_loader import load_pcg_config
from src.level.pcg_level_data import (
    PCGConfig,
    RoomData,
    LevelData,
    LevelSet,
)


# ----- Quadrant System for Door Placement -----

def get_room_quadrants(width: int, height: int, radius: int = 10) -> Dict[str, Tuple[int, int, int, int]]:
    """Divide room into 4 quadrants with 10x10 square areas from corners.
    
    Returns:
        Dict mapping quadrant names to (x, y, w, h) tuples for the 10x10 carve areas
    """
    quadrants = {}
    
    # Top-left quadrant
    tl_x = 1  # Start after wall
    tl_y = 1  # Start after wall
    tl_w = min(radius, width // 2 - 1)
    tl_h = min(radius, height // 2 - 1)
    quadrants['TL'] = (tl_x, tl_y, tl_w, tl_h)
    
    # Top-right quadrant
    tr_x = max(width // 2 + 1, width - radius - 1)
    tr_y = 1
    tr_w = min(radius, width - tr_x - 1)
    tr_h = min(radius, height // 2 - 1)
    quadrants['TR'] = (tr_x, tr_y, tr_w, tr_h)
    
    # Bottom-left quadrant
    bl_x = 1
    bl_y = max(height // 2 + 1, height - radius - 1)
    bl_w = min(radius, width // 2 - 1)
    bl_h = min(radius, height - bl_y - 1)
    quadrants['BL'] = (bl_x, bl_y, bl_w, bl_h)
    
    # Bottom-right quadrant
    br_x = max(width // 2 + 1, width - radius - 1)
    br_y = max(height // 2 + 1, height - radius - 1)
    br_w = min(radius, width - br_x - 1)
    br_h = min(radius, height - br_y - 1)
    quadrants['BR'] = (br_x, br_y, br_w, br_h)
    
    return quadrants


def select_available_quadrant(used_quadrants: Set[str], available_quadrants: List[str], rng: random.Random) -> Optional[str]:
    """Select a random quadrant from available ones that hasn't been used."""
    available = [q for q in available_quadrants if q not in used_quadrants]
    if not available:
        return None
    return rng.choice(available)


def get_random_position_in_quadrant(quadrant: Tuple[int, int, int, int], carve_size: int = 3, rng: random.Random = None) -> Optional[Tuple[int, int]]:
    """Get random position within quadrant for placing a carve area.
    
    Args:
        quadrant: (x, y, w, h) tuple defining the quadrant area
        carve_size: Size of the carve area (default 3x3)
        rng: Random number generator
    
    Returns:
        (x, y) position for top-left of carve area, or None if no space
    """
    if rng is None:
        rng = random.Random()
    
    qx, qy, qw, qh = quadrant
    
    # Ensure quadrant is large enough for carve area
    if qw < carve_size or qh < carve_size:
        return None
    
    # Random position within quadrant bounds
    max_x = qx + qw - carve_size
    max_y = qy + qh - carve_size
    
    if max_x < qx or max_y < qy:
        return None
    
    x = rng.randint(qx, max_x)
    y = rng.randint(qy, max_y)
    
    return (x, y)


def is_first_room_first_level(room: RoomData) -> bool:
    """Check if this is the first room of the first level (11A)."""
    return room.level_id == 1 and room.room_index == 0 and room.room_letter == 'A'


def generate_simple_room_tiles(config: PCGConfig) -> List[List[int]]:
    """Generate a room with wall boundary and air interior.

    Uses tile IDs from PCGConfig (loaded from config/pcg_config.json).
    """
    from src.level.pcg_level_data import generate_room_tiles
    # Delegate to helper to keep generation logic centralized
    return generate_room_tiles(
        level_id=1, room_index=0, room_letter="A",
        width=config.room_width,
        height=config.room_height,
        config=config
    )


def generate_rooms_for_level(
    level_id: int,
    config: PCGConfig,
    rng: random.Random,
) -> List[RoomData]:
    """Generate 6-12 rooms for a single level.

    For numeric slots 1..6 (room_index 0..5):
    - Each slot spawns 1 or 2 rooms:
      - A only, or A and B
    - room_code = f"{level_id}{slot}{letter}" (e.g. 11A, 12B)
    """
    rooms: List[RoomData] = []

    for room_index in range(6):
        slot = room_index + 1
        count = rng.randint(1, 2)  # 1 or 2 rooms

        letters = ["A"] if count == 1 else ["A", "B"]

        for letter in letters:
            room_code = f"{level_id}{slot}{letter}"
            # Generate tiles using the centralized helper so room tiles vary by room
            from src.level.pcg_level_data import generate_room_tiles
            tiles = generate_room_tiles(
                level_id=level_id,
                room_index=room_index,
                room_letter=letter,
                width=config.room_width,
                height=config.room_height,
                config=config,
            )

            rooms.append(
                RoomData(
                    level_id=level_id,
                    room_index=room_index,
                    room_letter=letter,
                    room_code=room_code,
                    tiles=tiles,
                )
            )

    # Sort for deterministic order: by (room_index, room_letter)
    rooms.sort(key=lambda r: (r.room_index, r.room_letter))

    return rooms


def _group_rooms_by_index(level_rooms: List[RoomData]) -> Dict[int, List[RoomData]]:
    by_index: Dict[int, List[RoomData]] = {}
    for room in level_rooms:
        by_index.setdefault(room.room_index, []).append(room)
    # Ensure A before B in each group
    for rooms in by_index.values():
        rooms.sort(key=lambda r: r.room_letter)
    return by_index


def _wire_intra_level_doors(level_rooms: List[RoomData]) -> None:
    """Wire doors within a single level based on N -> N+1 rule.

    For each index i (0..4):
      - Look at rooms of i+1 (next index):
        - If only A:
            all rooms of i: exit_1 -> (i+1)A
        - If A and B:
            all rooms of i: exit_1 -> (i+1)A, exit_2 -> (i+1)B
    Index 5 (last) is handled by cross-level routing.
    """
    by_index = _group_rooms_by_index(level_rooms)
    indices = sorted(by_index.keys())

    # Clear any existing exits
    for r in level_rooms:
        r.door_exits = {}

    for pos, idx in enumerate(indices):
        # Skip last index here; cross-level routing will handle it
        if pos == len(indices) - 1:
            continue

        current_group = by_index[idx]
        next_idx = indices[pos + 1]
        next_group = by_index.get(next_idx, [])
        if not next_group:
            continue

        # Determine primary (A) and secondary (B if exists)
        primary = next_group[0]
        secondary = next_group[1] if len(next_group) > 1 else None

        for room in current_group:
            room.door_exits["door_exit_1"] = {"level_id": primary.level_id, "room_code": primary.room_code}
            if secondary is not None:
                room.door_exits["door_exit_2"] = {"level_id": secondary.level_id, "room_code": secondary.room_code}


def _wire_cross_level_doors(all_levels_rooms: List[List[RoomData]]) -> None:
    """Wire doors from last index of level N to first index of level N+1.

    Uses same branching rules as intra-level:
      - If next level's first index has only A:
            exit_1 -> A
      - If it has A and B:
            exit_1 -> A, exit_2 -> B
    Last level's last index has no exits added here.
    """
    num_levels = len(all_levels_rooms)

    for level_idx in range(num_levels - 1):
        current_rooms = all_levels_rooms[level_idx]
        next_rooms = all_levels_rooms[level_idx + 1]

        if not current_rooms or not next_rooms:
            continue

        current_by_index = _group_rooms_by_index(current_rooms)
        next_by_index = _group_rooms_by_index(next_rooms)

        # Last index in current level (room_index 5 if present)
        if not current_by_index:
            continue
        last_index = max(current_by_index.keys())
        last_group = current_by_index.get(last_index, [])
        if not last_group:
            continue

        # First index in next level (room_index 0 if present)
        if not next_by_index:
            continue
        first_index = min(next_by_index.keys())
        first_group = next_by_index.get(first_index, [])
        if not first_group:
            continue

        primary = first_group[0]
        secondary = first_group[1] if len(first_group) > 1 else None

        for room in last_group:
            room.door_exits["door_exit_1"] = {"level_id": primary.level_id, "room_code": primary.room_code}
            if secondary is not None:
                room.door_exits["door_exit_2"] = {"level_id": secondary.level_id, "room_code": secondary.room_code}


def _compute_entrances(all_levels_rooms: List[List[RoomData]]) -> None:
    """Compute entrance_from based on door_exits across all levels."""
    code_to_room: Dict[str, RoomData] = {
        room.room_code: room
        for level_rooms in all_levels_rooms
        for room in level_rooms
    }

    # Reset entrances
    for room in code_to_room.values():
        room.entrance_from = None

    # First source that points to a room becomes its entrance_from
    for source in code_to_room.values():
        if not source.door_exits:
            continue
        for target_entry in source.door_exits.values():
            # target_entry may be a structured dict or legacy string
            if isinstance(target_entry, dict):
                target_code = target_entry.get('room_code')
            else:
                target_code = target_entry
            target = code_to_room.get(target_code)
            if target is not None and target.entrance_from is None:
                target.entrance_from = source.room_code


def _carve_spawn_and_exits_for_room(room: RoomData, config: PCGConfig, rng: random.Random, place_entrance_fn=None, place_exit_fn=None, allow_entrance: bool = True) -> None:
    """Carve 3x3 entrance/exit areas using quadrant system.

    - Entrance: if `room.entrance_from` exists OR this is first room of first level,
      carve a 3x3 area in a randomly selected quadrant.
    - Exits: for each exit in `room.door_exits`, carve a 3x3 area in different quadrants
      from each other and from the entrance.

    The carved areas are recorded in `room.areas` as dicts so placement helpers
    can find the bottom-center tile for door placement. This function is
    idempotent (safe to call multiple times).
    """
    TILE_AIR = config.air_tile_id
    tiles = room.tiles
    h = len(tiles)
    w = len(tiles[0]) if h > 0 else 0
    if h < 3 or w < 3:
        return

    room.areas = getattr(room, 'areas', []) or []

    def _add_area(kind: str, rect):
        room.areas.append({
            'kind': kind,
            'rects': [rect],
            'properties': {}
        })

    # Get room quadrants using the configured radius
    quadrants = get_room_quadrants(w, h, config.quadrant_radius)
    used_quadrants: Set[str] = set()
    
    # Determine if we should place entrance
    should_place_entrance = allow_entrance and (
        getattr(room, 'entrance_from', None) or is_first_room_first_level(room)
    )
    
    # Entrance carve using quadrant system
    if should_place_entrance:
        available_quadrants = ['TL', 'TR', 'BL', 'BR']
        entrance_quadrant = select_available_quadrant(used_quadrants, available_quadrants, rng)
        
        if entrance_quadrant:
            quadrant_rect = quadrants[entrance_quadrant]
            pos = get_random_position_in_quadrant(quadrant_rect, 3, rng)
            
            if pos:
                left_x, top_y = pos
                # carve 3x3 to air
                for yy in range(top_y, top_y + 3):
                    for xx in range(left_x, left_x + 3):
                        if 0 <= yy < h and 0 <= xx < w:
                            tiles[yy][xx] = TILE_AIR
                _add_area('door_carve', {'x': left_x, 'y': top_y, 'w': 3, 'h': 3, 'door_key': 'entrance'})
                # add 3x1 exclusion row below
                excl_y = top_y + 3
                if excl_y < h - 1:
                    _add_area('exclusion_zone', {'x': left_x, 'y': excl_y, 'w': 3, 'h': 1})
                used_quadrants.add(entrance_quadrant)
    
    # Exit carves using quadrant system
    door_exits = getattr(room, 'door_exits', {})
    if door_exits:
        available_quadrants = ['TL', 'TR', 'BL', 'BR']
        
        for door_key in door_exits.keys():
            exit_quadrant = select_available_quadrant(used_quadrants, available_quadrants, rng)
            
            if exit_quadrant:
                quadrant_rect = quadrants[exit_quadrant]
                pos = get_random_position_in_quadrant(quadrant_rect, 3, rng)
                
                if pos:
                    left_x, top_y = pos
                    # carve 3x3 to air
                    for yy in range(top_y, top_y + 3):
                        for xx in range(left_x, left_x + 3):
                            if 0 <= yy < h and 0 <= xx < w:
                                tiles[yy][xx] = TILE_AIR
                    _add_area('door_carve', {'x': left_x, 'y': top_y, 'w': 3, 'h': 3, 'door_key': door_key})
                    # add 3x1 exclusion row below
                    excl_y = top_y + 3
                    if excl_y < h - 1:
                        _add_area('exclusion_zone', {'x': left_x, 'y': excl_y, 'w': 3, 'h': 1})
                    used_quadrants.add(exit_quadrant)



# ----- Drunken Walk carving helpers -----

def _carve_drunken_walk_paths(room: RoomData, config: PCGConfig, rng: random.Random) -> None:
    """
    Finds the entrance/exits for the room and carves paths between them.
    This version respects `exclusion_zone` areas recorded in `room.areas`.
    """
    tile_grid = getattr(room, 'tiles', None)
    if not tile_grid:
        return

    # Build exclusion set from room.areas (rects)
    exclusion_set: Set[Tuple[int, int]] = set()
    areas = getattr(room, 'areas', []) or []
    for area in areas:
        if not isinstance(area, dict):
            continue
        if area.get('kind') != 'exclusion_zone':
            continue
        rects = area.get('rects') or []
        for rect in rects:
            if not isinstance(rect, dict):
                continue
            rx = int(rect.get('x', 0))
            ry = int(rect.get('y', 0))
            rw = int(rect.get('w', 0))
            rh = int(rect.get('h', 0))
            for yy in range(ry, ry + rh):
                for xx in range(rx, rx + rw):
                    exclusion_set.add((xx, yy))

    # Find door carve centers (entrance and exits)
    start_pos = None
    exit_positions: List[Tuple[int, int]] = []

    for area in areas:
        if not isinstance(area, dict):
            continue
        if area.get('kind') != 'door_carve':
            continue
        rects = area.get('rects') or []
        if not rects:
            continue
        rect = rects[0]
        if not isinstance(rect, dict):
            continue
        tx = int(rect.get('x', 0) + (rect.get('w', 1) // 2))
        ty = int(rect.get('y', 0) + (rect.get('h', 1) // 2))
        door_key = rect.get('door_key')
        if door_key == 'entrance':
            start_pos = (tx, ty)
        elif door_key in ('door_exit_1', 'door_exit_2'):
            exit_positions.append((tx, ty))

    # Fallback start if none found
    h = len(tile_grid)
    w = len(tile_grid[0]) if h > 0 else 0
    if not start_pos:
        start_pos = (w // 2, h - 3)

    # If start is inside exclusion, try to find a nearby non-excluded tile
    if start_pos in exclusion_set:
        found = None
        for radius in (1, 2, 3):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    cand = (max(1, min(w - 2, start_pos[0] + dx)), max(1, min(h - 2, start_pos[1] + dy)))
                    if cand not in exclusion_set:
                        found = cand
                        break
                if found:
                    break
            if found:
                break
        if found:
            start_pos = found

    # If there are no exits, for the first room create a short walk to seed a cave
    if not exit_positions and is_first_room_first_level(room):
        # pick a fake exit not in exclusion
        fake_exit = None
        for _ in range(20):
            candidate = (rng.randint(max(2, w//4), max(2, 3*w//4)), rng.randint(max(2, h//4), max(2, 3*h//4)))
            if candidate not in exclusion_set:
                fake_exit = candidate
                break
        if fake_exit is None:
            fake_exit = (max(2, w//2), max(2, h//2))
        _run_single_walk(tile_grid, start_pos, fake_exit, config, rng, max_steps=max(1, config.dw_max_steps // 2), exclusion_set=exclusion_set)
        return

    all_paths: List[Tuple[int, int]] = []

    for exit_pos in exit_positions:
        # If exit is in exclusion, try to nudge it slightly outward
        ep = exit_pos
        if ep in exclusion_set:
            for _ in range(8):
                ep = (max(2, min(w - 3, ep[0] + rng.randint(-1, 1))), max(2, min(h - 3, ep[1] + rng.randint(-1, 1))))
                if ep not in exclusion_set:
                    break
        path = _run_single_walk(tile_grid, start_pos, ep, config, rng, max_steps=config.dw_max_steps, exclusion_set=exclusion_set)
        all_paths.extend(path)

    # Possibly spawn an extra random walk from an existing carved tile to make loops
    if all_paths and config.dw_extra_drunk_chance and rng.random() < config.dw_extra_drunk_chance:
        # pick a non-excluded start tile
        tries = 0
        random_start_pos = None
        while tries < 20 and random_start_pos is None:
            cand = rng.choice(all_paths)
            if cand not in exclusion_set:
                random_start_pos = cand
            tries += 1
        if random_start_pos is not None:
            # pick non-excluded target
            random_target = None
            for _ in range(20):
                cand = (rng.randint(2, max(2, w - 3)), rng.randint(2, max(2, h - 3)))
                if cand not in exclusion_set:
                    random_target = cand
                    break
            if random_target is None:
                random_target = random_start_pos
            _run_single_walk(tile_grid, random_start_pos, random_target, config, rng, max_steps=config.dw_extra_drunk_steps, exclusion_set=exclusion_set)


def _run_single_walk(tile_grid: List[List[int]], start_pos: Tuple[int, int], end_pos: Tuple[int, int], config: PCGConfig, rng: random.Random, max_steps: int, exclusion_set: Optional[Set[Tuple[int,int]]] = None) -> List[Tuple[int, int]]:
    """Run a single drunkard walk carving into tile_grid and return carved tiles.

    The walk respects `exclusion_set` (doesn't carve there and won't step into it).
    """
    if exclusion_set is None:
        exclusion_set = set()

    h = len(tile_grid)
    w = len(tile_grid[0]) if h > 0 else 0
    current = start_pos
    carved: List[Tuple[int, int]] = []

    last_move: Optional[Tuple[int,int]] = None
    for _ in range(max(1, int(max_steps))):
        # If current is excluded, try to nudge to nearest non-excluded tile
        if current in exclusion_set:
            moved = False
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    cand = (max(1, min(w - 2, current[0] + dx)), max(1, min(h - 2, current[1] + dy)))
                    if cand not in exclusion_set:
                        current = cand
                        last_move = (dx, dy)
                        moved = True
                        break
                if moved:
                    break
            if not moved:
                # give up on this walk
                break

        _carve_at(tile_grid, current, config.dw_carve_radius, config, exclusion_set=exclusion_set)
        if current not in carved:
            carved.append(current)

        # stop if close enough (use Manhattan)
        if abs(current[0] - end_pos[0]) + abs(current[1] - end_pos[1]) <= 3:
            break

        dx, dy = _get_drunken_move(current, end_pos, config, rng, last_move=last_move)
        nx = max(1, min(w - 2, current[0] + dx))
        ny = max(1, min(h - 2, current[1] + dy))

        # If next step would land in exclusion, try alternatives (random tries)
        next_pos = (nx, ny)
        next_move = (dx, dy)
        if next_pos in exclusion_set:
            alt_found = False
            # try including diagonals if allowed
            move_pool = [(0,1),(0,-1),(1,0),(-1,0)]
            if getattr(config, 'dw_allow_diagonals', True):
                move_pool += [(1,1),(1,-1),(-1,1),(-1,-1)]
            for _ in range(12):
                adx, ady = rng.choice(move_pool)
                candx = max(1, min(w - 2, current[0] + adx))
                candy = max(1, min(h - 2, current[1] + ady))
                if (candx, candy) not in exclusion_set:
                    next_pos = (candx, candy)
                    next_move = (adx, ady)
                    alt_found = True
                    break
            if not alt_found:
                # cannot move without hitting exclusion, end walk
                break

        last_move = next_move
        current = next_pos

    return carved


def _carve_at(tile_grid: List[List[int]], pos: Tuple[int, int], radius: int, config: PCGConfig, exclusion_set: Optional[Set[Tuple[int,int]]] = None) -> None:
    """Carve a simple square of air centered on pos using config.air_tile_id.

    Respects `exclusion_set` by skipping any tile coordinates that are excluded.
    """
    if exclusion_set is None:
        exclusion_set = set()
    h = len(tile_grid)
    w = len(tile_grid[0]) if h > 0 else 0
    cx, cy = pos
    r = max(1, int(radius))
    offset = r - 1
    for yy in range(cy - offset, cy + r):
        for xx in range(cx - offset, cx + r):
            if 0 <= yy < h and 0 <= xx < w and (xx, yy) not in exclusion_set:
                tile_grid[yy][xx] = config.air_tile_id


def _get_drunken_move(current_pos: Tuple[int, int], target_pos: Tuple[int, int], config: PCGConfig, rng: random.Random, last_move: Optional[Tuple[int,int]] = None) -> Tuple[int, int]:
    """Decide next step; biased toward target but with persistence to meander.

    - `dw_exit_bias` still biases moves toward the target.
    - `dw_persistence` is chance to repeat last_move (inertia).
    - `dw_allow_diagonals` permits diagonal steps occasionally.
    """
    # Possible move pool
    cardinal = [(0,1),(0,-1),(1,0),(-1,0)]
    diag = [(1,1),(1,-1),(-1,1),(-1,-1)]
    allow_diags = bool(getattr(config, 'dw_allow_diagonals', True))

    # Persistence: sometimes keep last move
    if last_move and rng.random() < float(getattr(config, 'dw_persistence', 0.6)):
        return last_move

    # Bias toward target
    if rng.random() < float(getattr(config, 'dw_exit_bias', 0.4)):
        dx = target_pos[0] - current_pos[0]
        dy = target_pos[1] - current_pos[1]
        step_x = 0
        step_y = 0
        if dx != 0:
            step_x = 1 if dx > 0 else -1
        if dy != 0:
            step_y = 1 if dy > 0 else -1
        if allow_diags and step_x != 0 and step_y != 0:
            return (step_x, step_y)
        # prefer larger delta
        if abs(dx) > abs(dy):
            return (step_x, 0)
        else:
            return (0, step_y)

    # Random move: choose from allowed set (cardinal + maybe diagonal)
    pool = list(cardinal)
    if allow_diags and rng.random() < 0.25:
        pool.extend(diag)
    return rng.choice(pool)


# ----- Connectivity check and repair -----

def _flood_fill_reachable(tile_grid: List[List[int]], start: Tuple[int,int], config: PCGConfig) -> Set[Tuple[int,int]]:
    """Return set of reachable air tiles from start using 4-way movement."""
    h = len(tile_grid)
    w = len(tile_grid[0]) if h>0 else 0
    sx, sy = start
    if sx < 0 or sx >= w or sy < 0 or sy >= h:
        return set()
    if tile_grid[sy][sx] != config.air_tile_id:
        return set()

    q = [start]
    seen = {start}
    for x,y in q:
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = x+dx, y+dy
            if 0<=nx<w and 0<=ny<h and (nx,ny) not in seen and tile_grid[ny][nx]==config.air_tile_id:
                seen.add((nx,ny))
                q.append((nx,ny))
    return seen


def _find_door_centers(room: RoomData) -> List[Tuple[str, Tuple[int,int]]]:
    """Return list of (door_key, center) from room.areas."""
    centers = []
    areas = getattr(room, 'areas', []) or []
    for area in areas:
        if not isinstance(area, dict):
            continue
        if area.get('kind')!='door_carve':
            continue
        rects = area.get('rects') or []
        if not rects:
            continue
        r = rects[0]
        if not isinstance(r, dict):
            continue
        cx = int(r.get('x',0)+ (r.get('w',1)//2))
        cy = int(r.get('y',0)+ (r.get('h',1)//2))
        centers.append((r.get('door_key'), (cx,cy)))
    return centers


def _ensure_doors_reachable(room: RoomData, config: PCGConfig, rng: random.Random) -> None:
    """Ensure every carved door area is reachable from the entrance; if not, repair by targeted walks."""
    tile_grid = room.tiles
    h = len(tile_grid)
    w = len(tile_grid[0]) if h>0 else 0

    # find entrance center
    door_centers = _find_door_centers(room)
    entrance_center = None
    exits = []
    for key, pos in door_centers:
        if key=='entrance':
            entrance_center = pos
        else:
            exits.append((key,pos))
    if entrance_center is None:
        return

    reachable = _flood_fill_reachable(tile_grid, entrance_center, config)

    # For each exit, if unreachable, try targeted carving from closest reachable tile
    for key,pos in exits:
        if pos in reachable:
            continue
        # find closest reachable tile by Manhattan distance
        if not reachable:
            continue
        best = min(reachable, key=lambda p: abs(p[0]-pos[0]) + abs(p[1]-pos[1]))
        # attempt multiple repairs with increasing carve radius
        repaired = False
        for attempt_radius in (config.dw_carve_radius, max(1, config.dw_carve_radius-1), config.dw_carve_radius+1, config.dw_carve_radius+2):
            # run a short drunk walk from best -> pos with this brush
            _run_single_walk(tile_grid, best, pos, config, rng, max_steps=max(10, config.dw_max_steps//10))
            # re-evaluate reachable
            reachable = _flood_fill_reachable(tile_grid, entrance_center, config)
            if pos in reachable:
                repaired = True
                break
        if not repaired:
            # fallback: carve a straight corridor between best and pos
            x0,y0 = best
            x1,y1 = pos
            x,y = x0,y0
            while (x,y)!=(x1,y1):
                if x<x1:
                    x+=1
                elif x>x1:
                    x-=1
                elif y<y1:
                    y+=1
                elif y>y1:
                    y-=1
                # carve 3x3 at x,y
                _carve_at(tile_grid, (x,y), max(2, config.dw_carve_radius), config)
            # final check
            reachable = _flood_fill_reachable(tile_grid, entrance_center, config)
        # done for this exit

    # no return (room.tiles modified in place)


# ----- Cellular Automata smoothing (preserve protected areas) -----

def _run_cellular_automata(room: RoomData, config: PCGConfig, rng: random.Random) -> None:
    """
    Applies CA smoothing to the room's tile grid.
    Respects `door_carve` (keeps them as air) and `exclusion_zone` (keeps them as walls).
    """
    iterations = int(getattr(config, 'ca_smoothing_iterations', 0))
    if iterations <= 0:
        return

    # Build protected sets from room.areas
    door_set: Set[Tuple[int,int]] = set()
    exclusion_set: Set[Tuple[int,int]] = set()
    areas = getattr(room, 'areas', []) or []
    for area in areas:
        if not isinstance(area, dict):
            continue
        kind = area.get('kind')
        rects = area.get('rects') or []
        for rect in rects:
            if not isinstance(rect, dict):
                continue
            rx = int(rect.get('x', 0))
            ry = int(rect.get('y', 0))
            rw = int(rect.get('w', 0))
            rh = int(rect.get('h', 0))
            for yy in range(ry, ry + rh):
                for xx in range(rx, rx + rw):
                    if kind == 'door_carve':
                        door_set.add((xx, yy))
                    elif kind == 'exclusion_zone':
                        exclusion_set.add((xx, yy))

    current_grid = room.tiles
    for _ in range(iterations):
        current_grid = _ca_smoothing_step(current_grid, config, door_set=door_set, exclusion_set=exclusion_set)

    room.tiles = current_grid


def _ca_smoothing_step(tile_grid: List[List[int]], config: PCGConfig, door_set: Optional[Set[Tuple[int,int]]] = None, exclusion_set: Optional[Set[Tuple[int,int]]] = None) -> List[List[int]]:
    """
    Runs a single iteration of the CA simulation.

    Preserves tiles in `door_set` as air and tiles in `exclusion_set` as walls.
    """
    if door_set is None:
        door_set = set()
    if exclusion_set is None:
        exclusion_set = set()

    h = len(tile_grid)
    w = len(tile_grid[0]) if h > 0 else 0
    if h == 0 or w == 0:
        return tile_grid

    new_grid: List[List[int]] = [[0] * w for _ in range(h)]

    threshold = int(getattr(config, 'ca_wall_neighbor_threshold', 5))
    include_diagonals = bool(getattr(config, 'ca_include_diagonals', True))

    for y in range(h):
        for x in range(w):
            # Preserve border
            if x == 0 or x == w - 1 or y == 0 or y == h - 1:
                new_grid[y][x] = config.wall_tile_id
                continue

            # Preserve door carve as air
            if (x, y) in door_set:
                new_grid[y][x] = config.air_tile_id
                continue

            # Preserve exclusion zones as walls
            if (x, y) in exclusion_set:
                new_grid[y][x] = config.wall_tile_id
                continue

            neighbor_count = _get_wall_neighbor_count(tile_grid, x, y, include_diagonals, config, door_set, exclusion_set)

            if neighbor_count >= threshold:
                new_grid[y][x] = config.wall_tile_id
            else:
                new_grid[y][x] = config.air_tile_id

    return new_grid


def _get_wall_neighbor_count(tile_grid: List[List[int]], x: int, y: int, include_diagonals: bool, config: PCGConfig, door_set: Optional[Set[Tuple[int,int]]] = None, exclusion_set: Optional[Set[Tuple[int,int]]] = None) -> int:
    """
    Counts the number of wall neighbors for a given tile. Treats out-of-bounds tiles as walls.
    Respects door_set (treated as air) and exclusion_set (treated as wall).
    """
    if door_set is None:
        door_set = set()
    if exclusion_set is None:
        exclusion_set = set()

    h = len(tile_grid)
    w = len(tile_grid[0])
    count = 0

    for iy in range(y - 1, y + 2):
        for ix in range(x - 1, x + 2):
            if ix == x and iy == y:
                continue
            if not include_diagonals and (ix != x and iy != y):
                continue

            # Out of bounds counts as wall
            if ix < 0 or ix >= w or iy < 0 or iy >= h:
                count += 1
                continue

            # Protected areas override raw grid value
            if (ix, iy) in door_set:
                # door carve considered air
                continue
            if (ix, iy) in exclusion_set:
                count += 1
                continue

            if tile_grid[iy][ix] == config.wall_tile_id:
                count += 1

    return count



def generate_simple_pcg_level_set(
    seed: Optional[int] = None,
) -> LevelSet:
    """Generate a LevelSet following the agreed simple PCG rules.

    - Uses PCGConfig loaded from config/pcg_config.json
    - Generates config.num_levels levels
    - Each level: 6 room indices, each with 1-2 rooms (A/B)
    - Applies intra-level and cross-level door routing
    """
    rng = random.Random(seed)
    config = load_pcg_config()

    num_levels = config.num_levels
    if num_levels <= 0:
        raise ValueError("PCGConfig.num_levels must be positive")

    all_levels_rooms: List[List[RoomData]] = []

    for level_id in range(1, num_levels + 1):
        level_rooms = generate_rooms_for_level(level_id, config, rng)
        _wire_intra_level_doors(level_rooms)
        all_levels_rooms.append(level_rooms)

    _wire_cross_level_doors(all_levels_rooms)
    _compute_entrances(all_levels_rooms)

    # Carve spawn/exit regions (no tile writes) and delegate all door tile writes
    # to the centralized placement module so `room.placed_doors` is always authoritative.
    try:
        from src.level.door_placement import place_all_doors_for_room
    except Exception:
        place_all_doors_for_room = None

    for level_rooms in all_levels_rooms:
        for room in level_rooms:
            # Step 1: Carve the 3x3 door areas (this also finds their locations)
            try:
                _carve_spawn_and_exits_for_room(room, config, rng, place_entrance_fn=None, place_exit_fn=None, allow_entrance=True)
            except Exception as e:
                # Log and continue; do not let carve failures stop generation
                try:
                    import logging
                    logging.getLogger(__name__).error(f"Failed _carve_spawn_and_exits_for_room: {e}")
                except Exception:
                    pass
                pass

            # --- NEW STEP 2: Carve main paths with Drunken Walk ---
            try:
                _carve_drunken_walk_paths(room, config, rng)
            except Exception as e:
                try:
                    import logging
                    logging.getLogger(__name__).error(f"Failed _carve_drunken_walk_paths: {e}")
                except Exception:
                    pass
                pass
            
            # --- NEW STEP 3: Smooth tunnels with Cellular Automata ---
            try:
                _run_cellular_automata(room, config, rng)
                # Ensure doors remain reachable after smoothing
                _ensure_doors_reachable(room, config, rng)
            except Exception as e:
                try:
                    import logging
                    logging.getLogger(__name__).error(f"Failed _run_cellular_automata or connectivity check: {e}")
                except Exception:
                    pass
                pass

            # Step 4: Place the actual door tiles into the carved-out grid
            if getattr(room, 'placed_doors', None) is None:
                room.placed_doors = []
            try:
                if place_all_doors_for_room:
                    place_all_doors_for_room(room, rng=rng)
            except Exception as e:
                try:
                    import logging
                    logging.getLogger(__name__).error(f"Failed place_all_doors_for_room: {e}")
                except Exception:
                    pass
                pass

    levels: List[LevelData] = []
    for level_id, rooms in enumerate(all_levels_rooms, start=1):
        levels.append(LevelData(level_id=level_id, rooms=rooms))

    return LevelSet(levels=levels, seed=seed)


def generate_and_save_simple_pcg(
    output_path: str = "data/levels/generated_levels.json",
    seed: Optional[int] = None,
) -> LevelSet:
    """Generate the simple PCG level set and save it to JSON."""
    level_set = generate_simple_pcg_level_set(seed=seed)
    level_set.save_to_json(output_path)
    return level_set


if __name__ == "__main__":
    import logging
    logger = logging.getLogger(__name__)
    # Quick manual test: generate and log summary
    ls = generate_and_save_simple_pcg()
    for level in ls.levels:
        logger.info("Level %d: %d rooms", level.level_id, len(level.rooms))
        # Show a couple of rooms for inspection
        shown = set()
        for room in level.rooms:
            if room.room_index not in shown:
                logger.info("  Room %s: index=%d, letter=%s, entrance_from=%s, exits=%s",
                            room.room_code, room.room_index, room.room_letter, room.entrance_from, room.door_exits)
                shown.add(room.room_index)
        logger.info("")
