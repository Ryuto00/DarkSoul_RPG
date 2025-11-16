"""Level loader utility for integrating PCG levels with the game."""

import os
from typing import Optional, List, Dict
import sys

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.level.pcg_level_data import LevelSet, LevelData, RoomData, AreaRegion, AreaRect, room_areas_from_raw, build_tile_region_map, expand_rects_to_tiles, top_region_for_tile
from typing import Tuple, Callable
import random


class LevelLoader:
    """Utility class for loading and accessing PCG-generated levels."""
    
    def __init__(self, levels_file: str = "data/levels/generated_levels.json"):
        """
        Initialize the level loader.
        
        Args:
            levels_file: Path to the JSON file containing generated levels
        """
        self.levels_file = levels_file
        self._level_set: Optional[LevelSet] = None
    
    def load_levels(self) -> LevelSet:
        """
        Load levels from JSON file.
        
        Returns:
            LevelSet: Loaded level data
        """
        if not os.path.exists(self.levels_file):
            raise FileNotFoundError(f"Levels file not found: {self.levels_file}")
        
        self._level_set = LevelSet.load_from_json(self.levels_file)
        # Populate missing allowed_enemy_types based on spawn_surface for compatibility
        try:
            for level in self._level_set.levels:
                for room in level.rooms:
                    areas = getattr(room, 'areas', []) or []
                    for a in areas:
                        try:
                            if not isinstance(a, dict):
                                continue
                            if a.get('kind') != 'spawn':
                                continue
                            props = a.get('properties') or {}
                            aet = a.get('allowed_enemy_types')
                            if aet is None or (isinstance(aet, list) and len(aet) == 0):
                                surface = props.get('spawn_surface', 'both')
                                if surface == 'ground':
                                    a['allowed_enemy_types'] = ['Bug','Frog','Archer','Assassin','KnightMonster','Golem']
                                elif surface == 'air':
                                    a['allowed_enemy_types'] = ['Bee','WizardCaster']
                                else:
                                    a['allowed_enemy_types'] = ['Bug','Frog','Archer','Assassin','Bee','WizardCaster','KnightMonster','Golem']
                        except Exception:
                            continue
        except Exception:
            pass

        # Apply PCG postprocessing (floating platforms) to loaded rooms so saved levels
        # generated before this change also receive platform fixes at load time.
        try:
            from src.level.pcg_postprocess import add_floating_platforms
            from src.utils.player_movement_profile import PlayerMovementProfile
            from src.level.config_loader import load_pcg_config
            config = load_pcg_config()
            # default profile; project may later pass specific presets
            profile = PlayerMovementProfile()
            for level in self._level_set.levels:
                for room in level.rooms:
                    try:
                        add_floating_platforms(room, profile=profile, config=config, rng=None)
                    except Exception:
                        # don't let postprocess failures block loading
                        pass
        except Exception:
            pass
        return self._level_set
    
    def get_level_set(self) -> Optional[LevelSet]:
        """Get the currently loaded level set."""
        return self._level_set
    
    def get_room(self, level_id: int, room_code: str) -> Optional[RoomData]:
        """
        Get a specific room by level ID and room code.
        
        Args:
            level_id: The level number (1-based)
            room_code: Room code like "1A", "2B", etc.
            
        Returns:
            RoomData if found, None otherwise
        """
        if self._level_set is None:
            self.load_levels()
        
        if self._level_set is not None:
            return self._level_set.get_room(level_id, room_code)
        return None
    
    def get_level(self, level_id: int) -> Optional[LevelData]:
        """
        Get a specific level by ID.
        
        Args:
            level_id: The level number (1-based)
            
        Returns:
            LevelData if found, None otherwise
        """
        if self._level_set is None:
            self.load_levels()
        
        if self._level_set is not None:
            return self._level_set.get_level(level_id)
        return None
    
    def get_room_tiles(self, level_id: int, room_code: str) -> Optional[List[List[int]]]:
        """
        Get just the tile grid for a specific room.
        
        Args:
            level_id: The level number (1-based)
            room_code: Room code like "1A", "2B", etc.
            
        Returns:
            2D list of tile IDs if found, None otherwise
        """
        room = self.get_room(level_id, room_code)
        return room.tiles if room else None
    
    def get_room_exits(self, level_id: int, room_code: str) -> Dict[str, Dict[str, object]]:
        """
        Get door exits mapping for a specific room.

        Normalized return format (strict):
            {
                "door_exit_1": {"level_id": 1, "room_code": "11A"},
                "door_exit_2": {"level_id": 2, "room_code": "21A"}
            }

        This method expects exits to be structured objects in the JSON. If
        legacy string targets are present, this method will raise a ValueError
        so levels must be regenerated with structured exits.
        """
        room = self.get_room(level_id, room_code)
        if not room:
            return {}

        raw_exits = room.door_exits or {}
        normalized: Dict[str, Dict[str, object]] = {}

        for k, v in raw_exits.items():
            if not isinstance(v, dict):
                raise ValueError(f"Legacy string exit found for {level_id}/{room_code}: {k} -> {v}; regenerate levels with structured exits")
            try:
                lid = int(v["level_id"])
                rcode = str(v["room_code"])
            except Exception as e:
                raise ValueError(f"Invalid structured exit for {level_id}/{room_code}: {k} -> {v}: {e}")
            normalized[k] = {"level_id": lid, "room_code": rcode}

        return normalized

    
    def get_room_entrance_from(self, level_id: int, room_code: str) -> Optional[str]:
        """
        Get which room this room's entrance comes from.
        
        Args:
            level_id: The level number (1-based)
            room_code: Room code like "1A", "2B", etc.
            
        Returns:
            Room code this entrance comes from, or None if no entrance
        """
        room = self.get_room(level_id, room_code)
        return room.entrance_from if room else None
    
    def list_rooms_in_level(self, level_id: int) -> List[str]:
        """
        Get list of room codes for a level.
        
        Args:
            level_id: The level number (1-based)
            
        Returns:
            List of room codes like ["1A", "1B", ...]
        """
        level = self.get_level(level_id)
        if level:
            return [room.room_code for room in level.rooms]
        return []
    
    def get_starting_room(self, level_id: int) -> Optional[RoomData]:
        """
        Get the starting room for a level (first room).
        
        Args:
            level_id: The level number (1-based)
            
        Returns:
            RoomData for the first room if found, None otherwise
        """
        level = self.get_level(level_id)
        if level and level.rooms:
            return level.rooms[0]
        return None

    # ----- Area / Region helpers -----
    def get_room_areas(self, level_id: int, room_code: str) -> List[AreaRegion]:
        """Return list of AreaRegion for a room (converts raw dicts to objects)."""
        room = self.get_room(level_id, room_code)
        if not room:
            return []
        raw = getattr(room, "areas", None)
        return room_areas_from_raw(raw)

    def find_regions_by_kind(self, level_id: int, room_code: str, kind: str) -> List[AreaRegion]:
        return [r for r in self.get_room_areas(level_id, room_code) if r.kind == kind]

    def build_room_tile_region_map(self, level_id: int, room_code: str) -> Dict[Tuple[int,int], List[AreaRegion]]:
        regions = self.get_room_areas(level_id, room_code)
        room = self.get_room(level_id, room_code)
        if not room:
            return {}
        # width = number of columns (x), height = number of rows (y)
        height = len(room.tiles) if room.tiles else 0
        width = len(room.tiles[0]) if height > 0 else 0
        return build_tile_region_map(width, height, regions)

    def query_region_for_tile(self, level_id: int, room_code: str, x: int, y: int) -> Optional[AreaRegion]:
        tile_map = self.build_room_tile_region_map(level_id, room_code)
        return top_region_for_tile(tile_map, x, y)

    def choose_spawn_tile(
        self,
        level_id: int,
        room_code: str,
        kind: str = "spawn",
        rng: Optional[random.Random] = None,
        walkable_check: Optional[Callable[[int,int], bool]] = None,
        avoid_positions: Optional[List[Tuple[int,int]]] = None,
        min_distance: int = 0,
        allowed_surfaces: Optional[Tuple[str, ...]] = None,
    ) -> Optional[Tuple[int,int]]:
        """Choose a spawn tile from regions of type `kind` in the room.

        Improvements:
        - Can filter regions by `allowed_surfaces` (tuple of 'ground','air','both').
        - Prefers central tiles in a chosen region so spawns are less edge-biased.

        - `walkable_check(x,y)` should return True when a tile is valid for spawn.
        - `avoid_positions` is a list of tile positions to avoid (e.g., player).
        - `min_distance` is Euclidean minimum distance in tiles to any avoid position.
        """
        rng = rng or random.Random()
        regions = self.find_regions_by_kind(level_id, room_code, kind)
        if not regions:
            return None
        weighted: List[Tuple[AreaRegion, float]] = []
        for r in regions:
            if r.properties.get("no_enemy_spawn"):
                continue
            # surface filtering
            if allowed_surfaces is not None:
                surface = r.properties.get("spawn_surface", "both")
                if surface not in allowed_surfaces:
                    continue
            weight = float(r.properties.get("spawn_weight", max(1, r.area_size())))
            weighted.append((r, weight))
        if not weighted:
            return None
        # Build weighted per-tile candidate list from all allowed regions
        tile_candidates: List[Tuple[Tuple[int,int], float, AreaRegion]] = []  # ((x,y), weight, region)
        for r, rwgt in weighted:
            rect_tiles = expand_rects_to_tiles(r.rects)
            if not rect_tiles:
                continue
            # compute region center
            cx_sum = 0.0; cy_sum = 0.0; cnt = 0
            for rect in r.rects:
                rx = int(rect.x); ry = int(rect.y); rw = int(rect.w); rh = int(rect.h)
                cx_sum += rx + rw / 2.0
                cy_sum += ry + rh / 2.0
                cnt += 1
            if cnt == 0:
                cnt = 1
            center = (cx_sum / cnt, cy_sum / cnt)

            # assign per-tile weight with mild bias toward center (not squared distance)
            # Use linear distance instead of squared to reduce clustering
            for (tx, ty) in rect_tiles:
                dx = (tx + 0.5) - center[0]
                dy = (ty + 0.5) - center[1]
                dist = (dx * dx + dy * dy) ** 0.5  # Linear distance, not squared
                # Reduce center bias: use larger constant and smaller divisor
                tile_weight = rwgt / (5.0 + dist * 0.5)  # Much less biased toward center
                tile_candidates.append(((tx, ty), float(tile_weight), r))

        if not tile_candidates:
            return None

        # optionally shuffle to add randomness for equal weights
        rng.shuffle(tile_candidates)

        # filter by walkable_check and avoid_positions, build final weighted list
        final_tiles: List[Tuple[Tuple[int,int], float]] = []
        for (tx, ty), tw, reg in tile_candidates:
            if walkable_check and not walkable_check(tx, ty):
                continue
            if avoid_positions:
                bad = False
                for ax, ay in avoid_positions:
                    dx = ax - tx
                    dy = ay - ty
                    if dx * dx + dy * dy <= min_distance * min_distance:
                        bad = True
                        break
                if bad:
                    continue
            final_tiles.append(((tx, ty), tw))

        if not final_tiles:
            return None

        # sample a tile by weight
        total = sum(w for _, w in final_tiles)
        pick = rng.random() * total
        upto = 0.0
        for (tx, ty), w in final_tiles:
            upto += w
            if pick <= upto:
                return (tx, ty)
        # fallback
        return final_tiles[-1][0]


# Global level loader instance
level_loader = LevelLoader()


def get_room_tiles(level_id: int, room_code: str) -> Optional[List[List[int]]]:
    """
    Convenience function to get room tiles.
    
    Args:
        level_id: The level number (1-based)
        room_code: Room code like "1A", "2B", etc.
        
    Returns:
        2D list of tile IDs if found, None otherwise
    """
    return level_loader.get_room_tiles(level_id, room_code)


def get_starting_room(level_id: int) -> Optional[RoomData]:
    """
    Convenience function to get starting room for a level.
    
    Args:
        level_id: The level number (1-based)
        
    Returns:
        RoomData for the first room if found, None otherwise
    """
    return level_loader.get_starting_room(level_id)


def get_room_exits(level_id: int, room_code: str) -> Dict[str, Dict[str, object]]:
    """
    Convenience function to get room exits (normalized form).

    Returns a mapping where each exit key maps to a structured target:
        {"door_exit_1": {"level_id": 1, "room_code": "11A"}, ...}
    """
    return level_loader.get_room_exits(level_id, room_code)


def get_room_entrance_from(level_id: int, room_code: str) -> Optional[str]:
    """
    Convenience function to get room entrance source.
    
    Args:
        level_id: The level number (1-based)
        room_code: Room code like "1A", "2B", etc.
        
    Returns:
        Room code this entrance comes from, or None if no entrance
    """
    return level_loader.get_room_entrance_from(level_id, room_code)


def list_all_levels() -> List[int]:
    """
    Get list of all available level IDs.
    
    Returns:
        List of level IDs
    """
    level_set = level_loader.get_level_set()
    if level_set is None:
        level_loader.load_levels()
        level_set = level_loader.get_level_set()
    
    return [level.level_id for level in level_set.levels] if level_set else []