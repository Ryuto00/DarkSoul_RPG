"""
Seed-based random dungeon generator for 2D action game.
Generates deterministic dungeons with rooms, corridors, and monster placements.
"""

import random
import pygame
from enum import Enum
from typing import List, Tuple, Set


class TileType(Enum):
    WALL = 0
    FLOOR = 1


class MonsterSpawn:
    """Represents a monster spawn point in the dungeon."""
    def __init__(self, x: int, y: int, type_name: str, max_hp: int, is_boss: bool = False):
        self.x = x
        self.y = y
        self.type_name = type_name
        self.max_hp = max_hp
        self.is_boss = is_boss


class Room:
    """Represents a room in the dungeon."""
    def __init__(self, rect: pygame.Rect, is_start: bool = False, is_boss: bool = False):
        self.rect = rect
        self.is_start = is_start
        self.is_boss = is_boss
        self.monsters: List[MonsterSpawn] = []


class Dungeon:
    """Complete dungeon data structure."""
    def __init__(self, width: int, height: int, tiles: List[List[TileType]], rooms: List[Room], start_room: Room):
        self.width = width
        self.height = height
        self.tiles = tiles
        self.rooms = rooms
        self.start_room = start_room


# Monster type definitions with base stats
MONSTER_TYPES = [
    {"name": "slime", "base_hp": 3, "hp_per_stage": 1},
    {"name": "bat", "base_hp": 2, "hp_per_stage": 1},
    {"name": "knight", "base_hp": 5, "hp_per_stage": 2},
    {"name": "archer", "base_hp": 4, "hp_per_stage": 1},
]

BOSS_TYPE = {"name": "boss", "base_hp": 20, "hp_per_stage": 5}


def generate_dungeon(stage_index: int, seed: int,
                     width: int = 80,
                     height: int = 45) -> Dungeon:
    """
    Generate a seeded dungeon layout for the given stage_index.
    
    Args:
        stage_index: Current stage number (1-based)
        seed: Random seed for deterministic generation
        width: Dungeon width in tiles
        height: Dungeon height in tiles
        
    Returns:
        Dungeon object with tiles, rooms, and monster spawns
    """
    rng = random.Random(seed + stage_index * 1000)
    
    # Step 1: Initialize tiles as all WALL
    tiles = [[TileType.WALL for _ in range(width)] for _ in range(height)]
    
    # Step 2: Carve out rooms
    rooms = _generate_rooms(tiles, width, height, rng, num_rooms=rng.randint(6, 10))
    
    if not rooms:
        # Fallback: create at least one room
        rooms = [Room(pygame.Rect(width // 2 - 5, height // 2 - 5, 10, 10))]
        _carve_room(tiles, rooms[0].rect)
    
    # Step 3: Connect rooms with corridors
    _connect_rooms(tiles, rooms, rng)
    
    # Step 4: Choose start room and boss room (if needed)
    start_room = rooms[0]
    start_room.is_start = True
    
    boss_room = None
    is_boss_stage = (stage_index % 5 == 0)
    
    if is_boss_stage and len(rooms) > 1:
        # Pick a room far from start as boss room
        boss_room = _pick_furthest_room(rooms, start_room, rng)
        boss_room.is_boss = True
    
    # Step 5: Ensure reachability
    reachable_rooms = _flood_fill_reachable_rooms(tiles, rooms, start_room)
    
    # If boss room is not reachable, force a connection
    if boss_room and boss_room not in reachable_rooms:
        _force_connect_room(tiles, start_room, boss_room, rng)
        reachable_rooms = _flood_fill_reachable_rooms(tiles, rooms, start_room)
    
    # Only use reachable rooms for monster placement
    valid_rooms = [r for r in reachable_rooms if not r.is_start]
    
    # Step 6: Spawn monsters with scaled HP
    _spawn_monsters(valid_rooms, stage_index, boss_room, rng)
    
    return Dungeon(width, height, tiles, rooms, start_room)


def _generate_rooms(tiles: List[List[TileType]], width: int, height: int, 
                    rng: random.Random, num_rooms: int) -> List[Room]:
    """Generate random rooms that don't overlap."""
    rooms: List[Room] = []
    max_attempts = num_rooms * 3
    
    for _ in range(max_attempts):
        if len(rooms) >= num_rooms:
            break
        
        # Random room size
        room_w = rng.randint(5, 12)
        room_h = rng.randint(5, 12)
        
        # Random position (with margin)
        x = rng.randint(1, width - room_w - 1)
        y = rng.randint(1, height - room_h - 1)
        
        new_rect = pygame.Rect(x, y, room_w, room_h)
        
        # Check if overlaps with existing rooms (with spacing)
        overlaps = False
        for room in rooms:
            # Inflate for spacing between rooms
            if new_rect.inflate(2, 2).colliderect(room.rect.inflate(2, 2)):
                overlaps = True
                break
        
        if not overlaps:
            room = Room(new_rect)
            rooms.append(room)
            _carve_room(tiles, new_rect)
    
    return rooms


def _carve_room(tiles: List[List[TileType]], rect: pygame.Rect) -> None:
    """Carve out a rectangular room in the tiles."""
    for y in range(rect.top, rect.bottom):
        for x in range(rect.left, rect.right):
            if 0 <= y < len(tiles) and 0 <= x < len(tiles[0]):
                tiles[y][x] = TileType.FLOOR


def _connect_rooms(tiles: List[List[TileType]], rooms: List[Room], rng: random.Random) -> None:
    """Connect all rooms with corridors."""
    for i in range(len(rooms) - 1):
        room_a = rooms[i]
        room_b = rooms[i + 1]
        _carve_corridor(tiles, room_a.rect.center, room_b.rect.center, rng)
    
    # Add some extra connections for variety
    extra_connections = len(rooms) // 3
    for _ in range(extra_connections):
        room_a = rng.choice(rooms)
        room_b = rng.choice(rooms)
        if room_a != room_b:
            _carve_corridor(tiles, room_a.rect.center, room_b.rect.center, rng)


def _carve_corridor(tiles: List[List[TileType]], start: Tuple[int, int], 
                   end: Tuple[int, int], rng: random.Random) -> None:
    """Carve an L-shaped corridor between two points."""
    x1, y1 = start
    x2, y2 = end
    
    # Randomly choose horizontal-then-vertical or vertical-then-horizontal
    if rng.random() < 0.5:
        # Horizontal then vertical
        for x in range(min(x1, x2), max(x1, x2) + 1):
            if 0 <= y1 < len(tiles) and 0 <= x < len(tiles[0]):
                tiles[y1][x] = TileType.FLOOR
        for y in range(min(y1, y2), max(y1, y2) + 1):
            if 0 <= y < len(tiles) and 0 <= x2 < len(tiles[0]):
                tiles[y][x2] = TileType.FLOOR
    else:
        # Vertical then horizontal
        for y in range(min(y1, y2), max(y1, y2) + 1):
            if 0 <= y < len(tiles) and 0 <= x1 < len(tiles[0]):
                tiles[y][x1] = TileType.FLOOR
        for x in range(min(x1, x2), max(x1, x2) + 1):
            if 0 <= y2 < len(tiles) and 0 <= x < len(tiles[0]):
                tiles[y2][x] = TileType.FLOOR


def _pick_furthest_room(rooms: List[Room], start_room: Room, rng: random.Random) -> Room:
    """Pick a room that is far from the start room."""
    start_center = start_room.rect.center
    
    # Calculate distances
    distances = []
    for room in rooms:
        if room == start_room:
            continue
        dx = room.rect.centerx - start_center[0]
        dy = room.rect.centery - start_center[1]
        dist = (dx * dx + dy * dy) ** 0.5
        distances.append((dist, room))
    
    # Sort by distance and pick from the furthest quarter
    distances.sort(reverse=True)
    furthest_quarter = distances[:max(1, len(distances) // 4)]
    
    return rng.choice(furthest_quarter)[1]


def _flood_fill_reachable_rooms(tiles: List[List[TileType]], rooms: List[Room], 
                                start_room: Room) -> List[Room]:
    """Find all rooms reachable from the start room using flood fill."""
    height = len(tiles)
    width = len(tiles[0]) if height > 0 else 0
    
    visited = set()
    queue = [start_room.rect.center]
    visited.add(start_room.rect.center)
    
    # Flood fill all connected floor tiles
    while queue:
        x, y = queue.pop(0)
        
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            
            if (0 <= nx < width and 0 <= ny < height and 
                (nx, ny) not in visited and tiles[ny][nx] == TileType.FLOOR):
                visited.add((nx, ny))
                queue.append((nx, ny))
    
    # Check which rooms contain visited tiles
    reachable_rooms = []
    for room in rooms:
        # Check if any tile in the room was visited
        room_reachable = False
        for y in range(room.rect.top, room.rect.bottom):
            for x in range(room.rect.left, room.rect.right):
                if (x, y) in visited:
                    room_reachable = True
                    break
            if room_reachable:
                break
        
        if room_reachable:
            reachable_rooms.append(room)
    
    return reachable_rooms


def _force_connect_room(tiles: List[List[TileType]], start_room: Room, 
                       target_room: Room, rng: random.Random) -> None:
    """Force a corridor connection between two rooms."""
    _carve_corridor(tiles, start_room.rect.center, target_room.rect.center, rng)


def _spawn_monsters(rooms: List[Room], stage_index: int, boss_room: Room, 
                   rng: random.Random) -> None:
    """
    Spawn monsters in rooms with difficulty scaling.
    Total monsters: 4-5 per map.
    """
    if not rooms:
        return
    
    # Spawn boss first if this is a boss stage
    if boss_room:
        boss_hp = BOSS_TYPE["base_hp"] + stage_index * BOSS_TYPE["hp_per_stage"]
        boss_pos = _get_random_floor_tile_in_room(boss_room)
        if boss_pos:
            boss_room.monsters.append(
                MonsterSpawn(boss_pos[0], boss_pos[1], BOSS_TYPE["name"], boss_hp, is_boss=True)
            )
    
    # Spawn regular monsters (4-5 total)
    total_monsters = rng.randint(4, 5)
    available_rooms = [r for r in rooms if r != boss_room]  # Don't spawn regular monsters in boss room
    
    if not available_rooms:
        return
    
    for _ in range(total_monsters):
        # Pick random room
        room = rng.choice(available_rooms)
        
        # Pick random monster type
        monster_type = rng.choice(MONSTER_TYPES)
        monster_hp = monster_type["base_hp"] + stage_index * monster_type["hp_per_stage"]
        
        # Get random position in room
        pos = _get_random_floor_tile_in_room(room)
        if pos:
            room.monsters.append(
                MonsterSpawn(pos[0], pos[1], monster_type["name"], monster_hp, is_boss=False)
            )


def _get_random_floor_tile_in_room(room: Room) -> Tuple[int, int]:
    """Get a random tile position inside a room."""
    # Pick a point inside the room (not on edges)
    x = room.rect.left + room.rect.width // 2
    y = room.rect.top + room.rect.height // 2
    return (x, y)
