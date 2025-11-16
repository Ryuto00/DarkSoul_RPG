"""PCG Level and Room Data System

Adds Area/Region dataclasses and helpers for PCG-driven area mappings
(spawn regions, biomes, exclusion zones, hazards, etc.).
"""

from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple
import json
import os
import sys

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from config import TILE_AIR, TILE_WALL


@dataclass
class PCGConfig:
    """Configuration for procedural level generation."""
    num_levels: int = 3
    rooms_per_level: int = 6
    room_width: int = 40
    room_height: int = 30
    
    # Tile IDs to use (aligned with config.py and tile system)
    air_tile_id: int = TILE_AIR
    wall_tile_id: int = TILE_WALL
    
    # Generation options
    add_doors: bool = True
    door_entrance_tile_id: int = 2  # DOOR_ENTRANCE
    door_exit_tile_id: int = 3     # DOOR_EXIT (legacy)
    door_exit_1_tile_id: int = 4   # DOOR_EXIT_1
    door_exit_2_tile_id: int = 5   # DOOR_EXIT_2

    # Prefill behavior: if True, rooms are filled entirely with wall and
    # carving operations will create air where needed.
    initial_fill_walls: bool = True
    # Radius (in tiles) from the quadrant corner where carve centers may be chosen
    quadrant_radius: int = 10

    # --- DRUNKEN WALK SETTINGS ---
    # The total number of steps the drunkard can take before giving up.
    dw_max_steps: int = 20000
    # The % chance (0.0 to 1.0) the drunkard moves toward the exit vs. a random direction.
    # 0.0 = pure random. 1.0 = a straight line. 0.4 is a good start.
    dw_exit_bias: float = 0.4
    # Carve radius: r -> square of size (2*r - 1). r=2 -> 3x3 carve
    dw_carve_radius: int = 2
    # Direction persistence: chance to keep last move (inertia), 0.0..1.0
    dw_persistence: float = 0.6
    # Allow diagonal moves sometimes (makes meandering more organic)
    dw_allow_diagonals: bool = True
    # % chance to spawn an "extra" drunkard from a random point on an existing path.
    # This creates side-rooms and loops. Increase to create more coverage.
    dw_extra_drunk_chance: float = 0.35
    # How long the "extra" drunkards walk for.
    dw_extra_drunk_steps: int = 1500

    # --- Pocket room (unused quadrant) settings ---
    # Size of the pocket room carved in unused quadrants (square side length)
    pocket_room_size: int = 9
    # Chance to create a pocket room in an unused quadrant
    pocket_room_chance: float = 0.95

    # --- Post-CA dilation (grows caves slightly to use more area) ---
    # Number of dilation iterations (0 disables)
    post_ca_dilation_iterations: int = 1
    # Dilation radius (Manhattan) applied each iteration
    post_ca_dilation_radius: int = 1

    # --- Vertical movement safety ---
    # During S-shaped carving, insert a horizontal offset every N vertical tiles
    dw_vertical_step_interval: int = 3


    # --- CELLULAR AUTOMATA SETTINGS ---
    # The number of "smoothing" iterations to run. 3-5 is usually good.
    # 0 will disable smoothing.
    ca_smoothing_iterations: int = 5
    # The "5-step" rule: if a tile (air or wall) has this many or more
    # wall neighbors, it becomes a wall in the next iteration.
    ca_wall_neighbor_threshold: int = 5
    # Whether to check 8 neighbors (diagonals=True) or 4 (diagonals=False).
    # True is better for organic caves.
    ca_include_diagonals: bool = True


@dataclass
class RoomData:
    """Data structure for a single room."""
    level_id: int
    room_index: int
    room_letter: str
    room_code: str
    tiles: List[List[int]]  # 2D grid of tile IDs
    entrance_from: Optional[str] = None  # Which room this room's entrance comes from
    door_exits: Optional[Dict[str, Dict[str, object]]] = None  # Maps exit keys to structured targets
    # Optional areas metadata as a list of dicts (keeps JSON-compatible shape)
    areas: Optional[List[Dict[str, Any]]] = None
    # Optional placed doors metadata (populated by PCG generator)
    placed_doors: Optional[List[Dict[str, Any]]] = None

    def __post_init__(self):
        if self.door_exits is None:
            self.door_exits = {}
        # keep areas as-is (may be list of dicts)


@dataclass
class LevelData:
    """Data structure for a single level containing multiple rooms."""
    level_id: int
    rooms: List[RoomData]


@dataclass
class LevelSet:
    """Complete set of levels with all rooms.

    Added `seed` field so saved JSON includes which RNG seed produced this
    LevelSet. This makes it trivial to inspect the saved file and know which
    seed was used for generation.
    """
    levels: List[LevelData]
    seed: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary, include metadata first.

        Produces an object with `seed` and `generated_at` first followed by
        `levels` for readability and to act as a file header.
        """
        # Build levels representation manually to control ordering and avoid
        # exposing internal dataclass quirks
        levels_out: List[Dict[str, Any]] = []
        for level in self.levels:
            rooms_out: List[Dict[str, Any]] = []
            for room in level.rooms:
                rooms_out.append(asdict(room))
            levels_out.append({"level_id": level.level_id, "rooms": rooms_out})

        # metadata header
        out: Dict[str, Any] = {}
        out["seed"] = int(self.seed) if self.seed is not None else None
        # ISO timestamp to indicate when this file was written
        from datetime import datetime
        out["generated_at"] = datetime.utcnow().isoformat() + "Z"
        out["levels"] = levels_out
        return out
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LevelSet":
        """Create from dictionary.

        Room `areas` are left as raw dict lists and can be converted by
        helper functions when needed by the loader.
        """
        levels: List[LevelData] = []
        for level_data in data.get("levels", []):
            rooms: List[RoomData] = []
            for room_data in level_data.get("rooms", []):
                rooms.append(RoomData(**room_data))
            levels.append(LevelData(
                level_id=level_data["level_id"],
                rooms=rooms
            ))
        seed = data.get("seed")
        try:
            seed = int(seed) if seed is not None else None
        except Exception:
            seed = None
        return cls(levels=levels, seed=seed)
    
    def save_to_json(self, filepath: str) -> None:
        """Save level set to JSON file (includes seed)."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load_from_json(cls, filepath: str) -> "LevelSet":
        """Load level set from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def get_room(self, level_id: int, room_code: str) -> Optional[RoomData]:
        """Get a specific room by level ID and room code."""
        for level in self.levels:
            if level.level_id == level_id:
                for room in level.rooms:
                    if room.room_code == room_code:
                        return room
        return None
    
    def get_level(self, level_id: int) -> Optional[LevelData]:
        """Get a specific level by ID."""
        for level in self.levels:
            if level.level_id == level_id:
                return level
        return None


# ----- Area / Region dataclasses and helpers -----

@dataclass
class AreaRect:
    x: int
    y: int
    w: int
    h: int

    def tiles(self) -> List[Tuple[int, int]]:
        tiles: List[Tuple[int, int]] = []
        for yy in range(self.y, self.y + self.h):
            for xx in range(self.x, self.x + self.w):
                tiles.append((xx, yy))
        return tiles


@dataclass
class AreaRegion:
    region_id: str
    label: Optional[str] = None
    kind: str = "spawn"  # e.g. spawn, no_spawn, hazard, biome, player_spawn
    rects: List[AreaRect] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    allowed_enemy_types: Optional[List[str]] = None
    banned_enemy_types: Optional[List[str]] = None
    spawn_cap: Optional[int] = None
    priority: int = 0

    def contains_tile(self, x: int, y: int) -> bool:
        for r in self.rects:
            if r.x <= x < r.x + r.w and r.y <= y < r.y + r.h:
                return True
        return False

    def area_size(self) -> int:
        s = 0
        for r in self.rects:
            s += r.w * r.h
        return s

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "label": self.label,
            "kind": self.kind,
            "rects": [{"x": r.x, "y": r.y, "w": r.w, "h": r.h} for r in self.rects],
            "properties": self.properties,
            "allowed_enemy_types": self.allowed_enemy_types,
            "banned_enemy_types": self.banned_enemy_types,
            "spawn_cap": self.spawn_cap,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AreaRegion":
        rects = []
        for r in data.get("rects", []):
            # Filter only valid AreaRect fields
            rect_data = {k: v for k, v in r.items() if k in ['x', 'y', 'w', 'h']}
            rects.append(AreaRect(**rect_data))
        props = data.get("properties", {}) or {}
        aet = data.get("allowed_enemy_types")
        # If allowed_enemy_types not provided, infer from properties.spawn_surface
        if not aet:
            surface = props.get("spawn_surface")
            if surface == 'ground':
                aet = ['Bug','Frog','Archer','Assassin','KnightMonster','Golem']
            elif surface == 'air':
                aet = ['Bee','WizardCaster']
            else:
                aet = ['Bug','Frog','Archer','Assassin','Bee','WizardCaster','KnightMonster','Golem']

        return cls(
            region_id=str(data.get("region_id", f"{data.get('kind', 'unknown')}_{id(data)}")),
            label=data.get("label"),
            kind=str(data.get("kind", "spawn")),
            rects=rects,
            properties=props,
            allowed_enemy_types=aet,
            banned_enemy_types=data.get("banned_enemy_types"),
            spawn_cap=data.get("spawn_cap"),
            priority=int(data.get("priority", 0)),
        )


def expand_rects_to_tiles(rects: List[AreaRect]) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for r in rects:
        out.extend(r.tiles())
    return out


def build_tile_region_map(room_tiles_width: int, room_tiles_height: int, regions: List[AreaRegion]) -> Dict[Tuple[int,int], List[AreaRegion]]:
    """
    Build mapping: (x,y) -> list of AreaRegion sorted by priority (desc).
    Clamps rects to room bounds.
    """
    tile_map: Dict[Tuple[int,int], List[AreaRegion]] = {}
    for region in regions:
        for rect in region.rects:
            rx0 = max(0, rect.x)
            ry0 = max(0, rect.y)
            rx1 = min(room_tiles_width, rect.x + rect.w)
            ry1 = min(room_tiles_height, rect.y + rect.h)
            for yy in range(ry0, ry1):
                for xx in range(rx0, rx1):
                    tile_map.setdefault((xx, yy), []).append(region)
    # Sort region lists by priority (higher first)
    for coords, regs in tile_map.items():
        regs.sort(key=lambda r: r.priority, reverse=True)
    return tile_map


def top_region_for_tile(tile_map: Dict[Tuple[int,int], List[AreaRegion]], x: int, y: int) -> Optional[AreaRegion]:
    regs = tile_map.get((x, y))
    if not regs:
        return None
    return regs[0]


# ----- Room helper for legacy-friendly conversion -----

def room_areas_from_raw(raw: Optional[List[Dict[str, Any]]]) -> List[AreaRegion]:
    """Convert a raw list of dicts (as read from JSON) into AreaRegion objects."""
    if not raw:
        return []
    out: List[AreaRegion] = []
    for r in raw:
        if isinstance(r, AreaRegion):
            out.append(r)
        elif isinstance(r, dict):
            out.append(AreaRegion.from_dict(r))
    return out


# Generation helper remains unchanged

def generate_room_tiles(
    level_id: int,
    room_index: int,
    room_letter: str,
    width: int,
    height: int,
    config: PCGConfig
) -> List[List[int]]:
    """
    Generate a 2D grid of tile IDs for a room.

    If `config.initial_fill_walls` is True, the room will be entirely filled
    with wall tiles. Carving (air holes, doors, platforms) is handled by the
    generator later and must respect `room.areas` for exclusions.
    """
    grid: List[List[int]] = []

    if getattr(config, 'initial_fill_walls', False):
        # Fill entire room with wall tiles
        for y in range(height):
            row = [config.wall_tile_id] * width
            grid.append(row)
    else:
        # Backwards-compatible: border walls and air interior
        for y in range(height):
            row: List[int] = []
            for x in range(width):
                # Border walls
                if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                    row.append(config.wall_tile_id)
                else:
                    row.append(config.air_tile_id)
            grid.append(row)

    # Do not place door tiles here. Door tiles are placed at load time
    # based on the logical room.door_exits and room.entrance_from metadata.
    return grid

# Generation orchestration removed from this module.
# This file now provides dataclasses and helper functions only.
# Use `src/level/pcg_generator_simple.py` for full generation.

if __name__ == "__main__":
    import logging
    logger = logging.getLogger(__name__)
    # Test helpers when run directly (no full generation)
    from src.level.config_loader import load_pcg_config
    config = load_pcg_config()
    tiles = generate_room_tiles(
        level_id=1,
        room_index=0,
        room_letter="A",
        width=config.room_width,
        height=config.room_height,
        config=config
    )
    logger.info("Generated test room tiles: %dx%d", len(tiles), len(tiles[0]))
    logger.info("Helper functions work correctly.")

