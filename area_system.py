"""
Area system: defines typed rectangular areas over the tile grid plus
extensible, data-driven constraints for spawning and behaviors.

Key concepts:

- AreaType: string constants like:
    - "PLAYER_SPAWN"
    - "PORTAL_ZONE"
    - "GROUND_ENEMY_SPAWN"
    - "FLYING_ENEMY_SPAWN"
    - "WATER_AREA"
    - "MERCHANT_AREA"
  (More can be registered.)

- Area:
    - A rectangular region in tile coordinates with attributes.

- AreaMap:
    - Collection of Area objects with query helpers.

- AreaTypeDefinition + AreaRegistry:
    - Declarative constraints:
        - min_size / max_size
        - required_underlying_bases (TerrainBaseType)
        - allowed_spawns / forbidden_spawns labels
        - extra_rules callbacks for advanced checks.

Integration expectations (not enforced here directly):
- Level generation:
    - Uses AreaRegistry + helper functions to stamp areas during/after layout.
- Level validation:
    - Uses AreaRegistry.validate_level_areas to enforce constraints.
- Enemy spawn:
    - Uses AreaMap.find_areas_by_type + constraints for ground/flying.
- Merchant/shop:
    - Uses MERCHANT_AREA areas for merchant placement.

This module is pure logic and data; it does not import pygame or game entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
)

from terrain_system import TerrainTypeRegistry, TerrainBaseType, TerrainTag


# Public constants for known area types.
class AreaType:
    PLAYER_SPAWN: str = "PLAYER_SPAWN"
    PORTAL_ZONE: str = "PORTAL_ZONE"
    GROUND_ENEMY_SPAWN: str = "GROUND_ENEMY_SPAWN"
    FLYING_ENEMY_SPAWN: str = "FLYING_ENEMY_SPAWN"
    WATER_AREA: str = "WATER_AREA"
    MERCHANT_AREA: str = "MERCHANT_AREA"
    # Additional types can be added via AreaRegistry.register_area_type.


@dataclass
class Area:
    """
    Rectangular area in tile coordinates.

    Coordinates are in tile units (not pixels).

    Attributes:
        id: unique identifier within a level (for referencing, debugging).
        type: logical area type string.
        x, y: top-left tile coordinate.
        width, height: size in tiles.
        attributes: arbitrary metadata (difficulty, tags, spawn configs, etc.).
    """
    id: str
    type: str
    x: int
    y: int
    width: int
    height: int
    attributes: Dict[str, Any] = field(default_factory=dict)

    def contains(self, tx: int, ty: int) -> bool:
        return self.x <= tx < self.x + self.width and self.y <= ty < self.y + self.height

    def tiles(self) -> Iterable[Tuple[int, int]]:
        for yy in range(self.y, self.y + self.height):
            for xx in range(self.x, self.x + self.width):
                yield xx, yy


@dataclass
class AreaMap:
    """
    Holds areas for a level and provides spatial queries.
    """
    areas: List[Area] = field(default_factory=list)
    _tile_index: Optional[Dict[Tuple[int, int], List[Area]]] = field(default=None, init=False, repr=False)

    def _ensure_index(self) -> None:
        if self._tile_index is not None:
            return
        index: Dict[Tuple[int, int], List[Area]] = {}
        for area in self.areas:
            for tx, ty in area.tiles():
                index.setdefault((tx, ty), []).append(area)
        self._tile_index = index

    def add_area(self, area: Area) -> None:
        self.areas.append(area)
        # Invalidate index to keep lazy-build semantics simple.
        self._tile_index = None

    def areas_at(self, x: int, y: int) -> List[Area]:
        """
        Return list of areas covering tile (x, y).

        Uses a lazily-built index. The None-check and local variable
        keep static type checkers satisfied.
        """
        if self._tile_index is None:
            self._ensure_index()
        index = self._tile_index or {}
        return list(index.get((x, y), ()))  # copy for safety

    def find_areas_by_type(self, area_type: str) -> List[Area]:
        return [a for a in self.areas if a.type == area_type]


# Validation rule function signature.
AreaRuleFn = Callable[
    [
        Dict[str, Any],    # level_data or context
        Area,              # the area being validated
        Callable[[int, int], TerrainTag],  # terrain_at(tx, ty): TerrainTag
    ],
    List[str],            # list of issue strings (empty if ok)
]


@dataclass
class AreaTypeDefinition:
    """
    Declarative definition for a given AreaType.

    Constraints are intentionally generic; game-specific meaning is layered via:
    - spawn labels
    - required underlying terrain bases
    - extra_rules callbacks
    """
    name: str
    min_size: Optional[Tuple[int, int]] = None
    max_size: Optional[Tuple[int, int]] = None
    required_underlying_bases: Optional[Set[str]] = None
    allowed_spawns: Set[str] = field(default_factory=set)
    forbidden_spawns: Set[str] = field(default_factory=set)
    extra_rules: List[AreaRuleFn] = field(default_factory=list)


class _AreaRegistry:
    """
    Registry for AreaTypeDefinition and validation helpers.
    """

    def __init__(self) -> None:
        self._defs: Dict[str, AreaTypeDefinition] = {}

    # --- Registration API ---

    def register_area_type(self, defn: AreaTypeDefinition) -> None:
        """
        Register or overwrite an AreaTypeDefinition.
        """
        if not defn.name:
            raise ValueError("AreaTypeDefinition.name must be non-empty")
        self._defs[defn.name] = defn

    def get(self, area_type: str) -> AreaTypeDefinition:
        if area_type not in self._defs:
            raise KeyError(f"Unknown AreaType '{area_type}'")
        return self._defs[area_type]

    # --- Validation helpers ---

    def validate_area(
        self,
        area: Area,
        level_data: Dict[str, Any],
        terrain_at: Callable[[int, int], TerrainTag],
    ) -> List[str]:
        """
        Validate a single area against its AreaTypeDefinition.
        Returns a list of issues (empty if valid).
        """
        issues: List[str] = []
        try:
            defn = self.get(area.type)
        except KeyError:
            return [f"Area '{area.id}' has unknown type '{area.type}'"]

        # Size constraints.
        if defn.min_size:
            min_w, min_h = defn.min_size
            if area.width < min_w or area.height < min_h:
                issues.append(
                    f"Area '{area.id}' ({area.type}) too small: {area.width}x{area.height}, "
                    f"min {min_w}x{min_h}"
                )
        if defn.max_size:
            max_w, max_h = defn.max_size
            if area.width > max_w or area.height > max_h:
                issues.append(
                    f"Area '{area.id}' ({area.type}) too large: {area.width}x{area.height}, "
                    f"max {max_w}x{max_h}"
                )

        # Underlying terrain constraints.
        if defn.required_underlying_bases:
            for tx, ty in area.tiles():
                try:
                    tag = terrain_at(tx, ty)
                except Exception:
                    issues.append(
                        f"Area '{area.id}' ({area.type}) references out-of-bounds tile ({tx},{ty})"
                    )
                    continue
                if tag.base_type not in defn.required_underlying_bases:
                    issues.append(
                        f"Area '{area.id}' ({area.type}) tile ({tx},{ty}) "
                        f"on base '{tag.base_type}', requires {sorted(defn.required_underlying_bases)}"
                    )
                    break  # no need to spam

        # Extra rules.
        for rule in defn.extra_rules:
            try:
                rule_issues = rule(level_data, area, terrain_at)
                if rule_issues:
                    issues.extend(rule_issues)
            except Exception as exc:  # defensive: rule bugs shouldn't crash validation
                issues.append(
                    f"Area '{area.id}' ({area.type}) rule '{rule.__name__}' error: {exc}"
                )

        return issues

    def validate_level_areas(
        self,
        area_map: AreaMap,
        level_data: Dict[str, Any],
        terrain_grid: List[List[str]],
    ) -> List[str]:
        """
        Validate all areas for a level.

        Expects:
            terrain_grid[y][x] as terrain_id; resolved through TerrainTypeRegistry.get_terrain.
        """
        if not terrain_grid:
            return []  # Nothing to validate against; assume higher layers handle.

        height = len(terrain_grid)
        width = len(terrain_grid[0]) if height > 0 else 0

        def terrain_at(tx: int, ty: int) -> TerrainTag:
            if not (0 <= ty < height and 0 <= tx < width):
                raise IndexError("tile out of bounds")
            tid = terrain_grid[ty][tx]
            return TerrainTypeRegistry.get_terrain(tid)

        issues: List[str] = []
        for area in area_map.areas:
            issues.extend(self.validate_area(area, level_data, terrain_at))
        return issues

    # --- Built-in types ---

    def init_defaults(self) -> None:
        """
        Register default AreaTypeDefinitions matching design spec.
        """

        # PLAYER_SPAWN:
        # - Must be on PLATFORM/FLOOR.
        # - Allowed spawns: player, portal, ground/flying enemies.
        self.register_area_type(
            AreaTypeDefinition(
                name=AreaType.PLAYER_SPAWN,
                min_size=(1, 1),
                required_underlying_bases={TerrainBaseType.FLOOR, TerrainBaseType.PLATFORM},
                allowed_spawns={"player", "portal", "enemy_ground", "enemy_flying"},
                forbidden_spawns=set(),
            )
        )

        # PORTAL_ZONE:
        # - >= 3x3
        # - On PLATFORM/FLOOR
        # - Only portals, no enemies or merchants.
        self.register_area_type(
            AreaTypeDefinition(
                name=AreaType.PORTAL_ZONE,
                min_size=(3, 3),
                required_underlying_bases={TerrainBaseType.FLOOR, TerrainBaseType.PLATFORM},
                allowed_spawns={"portal"},
                forbidden_spawns={"enemy_ground", "enemy_flying", "merchant"},
                extra_rules=[_rule_portal_zone_no_enemies],
            )
        )

        # GROUND_ENEMY_SPAWN:
        # - On PLATFORM/FLOOR; only ground enemies.
        self.register_area_type(
            AreaTypeDefinition(
                name=AreaType.GROUND_ENEMY_SPAWN,
                min_size=(2, 2),
                required_underlying_bases={TerrainBaseType.FLOOR, TerrainBaseType.PLATFORM},
                allowed_spawns={"enemy_ground"},
                forbidden_spawns={"portal", "merchant"},
            )
        )

        # FLYING_ENEMY_SPAWN:
        # - More relaxed underlying terrain, by default unconstrained (None).
        # - Only flying enemies.
        self.register_area_type(
            AreaTypeDefinition(
                name=AreaType.FLYING_ENEMY_SPAWN,
                min_size=(2, 2),
                required_underlying_bases=None,
                allowed_spawns={"enemy_flying"},
                forbidden_spawns={"merchant"},
            )
        )

        # WATER_AREA:
        # - All tiles must be WATER base.
        self.register_area_type(
            AreaTypeDefinition(
                name=AreaType.WATER_AREA,
                min_size=(1, 1),
                required_underlying_bases={TerrainBaseType.WATER},
                allowed_spawns={"enemy_water", "enemy_amphibious"},
                forbidden_spawns={"player"},  # player spawn excluded here
            )
        )

        # MERCHANT_AREA:
        # - On PLATFORM/FLOOR.
        # - Only merchant, no enemies or portal.
        self.register_area_type(
            AreaTypeDefinition(
                name=AreaType.MERCHANT_AREA,
                min_size=(3, 2),
                required_underlying_bases={TerrainBaseType.FLOOR, TerrainBaseType.PLATFORM},
                allowed_spawns={"merchant"},
                forbidden_spawns={"enemy_ground", "enemy_flying", "portal"},
                extra_rules=[_rule_merchant_single_and_no_enemies],
            )
        )


# Singleton registry instance.
AreaRegistry = _AreaRegistry()


# --- Built-in extra rules (used by default AreaTypeDefinitions) ---


def _rule_portal_zone_no_enemies(
    level_data: Dict[str, Any],
    area: Area,
    terrain_at: Callable[[int, int], TerrainTag],
) -> List[str]:
    """
    Ensure no enemy spawns inside PORTAL_ZONE based on level_data['enemy_spawns']
    if present. This is soft; if the structure is missing, rule is effectively NOP.
    """
    issues: List[str] = []
    enemy_spawns = level_data.get("enemy_spawns") or []
    if not enemy_spawns:
        return issues

    for sp in enemy_spawns:
        tx = getattr(sp, "x", None)
        ty = getattr(sp, "y", None)
        if tx is None or ty is None:
            continue
        if area.contains(int(tx), int(ty)):
            issues.append(
                f"PORTAL_ZONE '{area.id}' contains enemy spawn at ({tx},{ty})"
            )
            break
    return issues


def _rule_merchant_single_and_no_enemies(
    level_data: Dict[str, Any],
    area: Area,
    terrain_at: Callable[[int, int], TerrainTag],
) -> List[str]:
    """
    Example rule for MERCHANT_AREA:
    - Enforce at most one merchant spawn inside area, if level_data exposes such info.
    - Ensure no enemy spawns within this area.
    """
    issues: List[str] = []

    # Enemy spawns format is not strictly defined; we handle a generic object list.
    enemy_spawns = level_data.get("enemy_spawns") or []
    merchant_spawns = level_data.get("merchant_spawns") or []

    # Normalize positions as tile coords if present.
    def in_area(obj) -> bool:
        tx = getattr(obj, "x", None)
        ty = getattr(obj, "y", None)
        if tx is None or ty is None:
            return False
        return area.contains(int(tx), int(ty))

    enemy_inside = any(in_area(e) for e in enemy_spawns)
    merchant_inside_count = sum(1 for m in merchant_spawns if in_area(m))

    if enemy_inside:
        issues.append(f"MERCHANT_AREA '{area.id}' contains enemy spawns")
    if merchant_inside_count > 1:
        issues.append(
            f"MERCHANT_AREA '{area.id}' has {merchant_inside_count} merchants (max 1)"
        )
    return issues


# --- Helper utilities for generators / spawn systems ---


def build_default_areas(
    level_data: Dict[str, Any],
    terrain_grid: List[List[str]],
) -> AreaMap:
    """
    Construct a minimal AreaMap based on generated data.

    This is intentionally simple and can be replaced or extended by more advanced
    algorithms. It provides:
        - a PLAYER_SPAWN area around the primary spawn
        - a PORTAL_ZONE around portal_pos if present and valid size
        - WATER_AREA rectangles inferred from WATER tiles
    Enemy spawn and merchant areas are expected to be added by dedicated logic,
    potentially using this helper as a starting point.
    """
    if not terrain_grid:
        return AreaMap()

    height = len(terrain_grid)
    width = len(terrain_grid[0]) if height > 0 else 0

    def terrain_at(tx: int, ty: int) -> TerrainTag:
        tid = terrain_grid[ty][tx]
        return TerrainTypeRegistry.get_terrain(tid)

    area_map = AreaMap()
    area_id_counter = 1

    # 1) PLAYER_SPAWN area around first spawn point, if any.
    spawn_points = level_data.get("spawn_points") or []
    if spawn_points:
        sx, sy = spawn_points[0]
        # Clamp to grid
        sx = max(0, min(width - 1, int(sx)))
        sy = max(0, min(height - 1, int(sy)))
        # Simple 3x3 area centered on spawn (clamped inside bounds).
        half = 1
        ax = max(0, sx - half)
        ay = max(0, sy - half)
        aw = min(width - ax, 2 * half + 1)
        ah = min(height - ay, 2 * half + 1)
        area_map.add_area(
            Area(
                id=f"player_spawn_{area_id_counter}",
                type=AreaType.PLAYER_SPAWN,
                x=ax,
                y=ay,
                width=aw,
                height=ah,
                attributes={},
            )
        )
        area_id_counter += 1

    # 2) PORTAL_ZONE around portal_pos tile, if available (3x3 min).
    portal_pos = level_data.get("portal_pos")
    if portal_pos is not None:
        # level_data portal_pos assumed pixel coords; convert using TILE if present.
        tile_size = level_data.get("tile_size")  # optional
        if not tile_size:
            # Try config import lazily to avoid cycle if available.
            try:
                from config import TILE as _T
                tile_size = _T
            except Exception:
                tile_size = 16  # fallback
        px, py = portal_pos
        pt_x = int(px // tile_size)
        pt_y = int(py // tile_size)
        if 0 <= pt_x < width and 0 <= pt_y < height:
            # Build 3x3 around portal, clamped.
            half = 1
            ax = max(0, pt_x - half)
            ay = max(0, pt_y - half)
            aw = min(width - ax, 2 * half + 1)
            ah = min(height - ay, 2 * half + 1)
            if aw >= 3 and ah >= 3:
                area_map.add_area(
                    Area(
                        id=f"portal_zone_{area_id_counter}",
                        type=AreaType.PORTAL_ZONE,
                        x=ax,
                        y=ay,
                        width=aw,
                        height=ah,
                        attributes={},
                    )
                )
                area_id_counter += 1

    # 3) WATER_AREA: group contiguous WATER tiles into coarse rectangles.
    visited = [[False] * width for _ in range(height)]

    def is_water(tx: int, ty: int) -> bool:
        tag = terrain_at(tx, ty)
        return tag.base_type == TerrainBaseType.WATER

    for y in range(height):
        for x in range(width):
            if visited[y][x] or not is_water(x, y):
                continue
            # Grow simple rectangle from (x, y).
            max_x = x
            while max_x + 1 < width and is_water(max_x + 1, y):
                max_x += 1
            max_y = y
            done = False
            while not done and max_y + 1 < height:
                for tx in range(x, max_x + 1):
                    if visited[max_y + 1][tx] or not is_water(tx, max_y + 1):
                        done = True
                        break
                if not done:
                    max_y += 1
            # Mark visited and add area.
            for ty in range(y, max_y + 1):
                for tx in range(x, max_x + 1):
                    visited[ty][tx] = True
            area_map.add_area(
                Area(
                    id=f"water_area_{area_id_counter}",
                    type=AreaType.WATER_AREA,
                    x=x,
                    y=y,
                    width=max_x - x + 1,
                    height=max_y - y + 1,
                    attributes={},
                )
            )
            area_id_counter += 1

    return area_map


def find_spawn_positions(
    area_map: AreaMap,
    area_type: str,
    terrain_grid: List[List[str]],
    movement_tag: str,
) -> List[Tuple[int, int]]:
    """
    Utility for enemy/portal/merchant placement:

    Returns candidate (tx, ty) tile positions inside all areas of given type
    where TerrainTypeRegistry.is_walkable(tag, movement_tag) is True.

    movement_tag:
        - "ground" for ground enemies/merchant/player.
        - "flying" for flying enemies.
        - etc.
    """
    if not terrain_grid:
        return []

    height = len(terrain_grid)
    width = len(terrain_grid[0]) if height > 0 else 0

    def terrain_at(tx: int, ty: int) -> TerrainTag:
        tid = terrain_grid[ty][tx]
        return TerrainTypeRegistry.get_terrain(tid)

    candidates: List[Tuple[int, int]] = []
    for area in area_map.find_areas_by_type(area_type):
        for tx, ty in area.tiles():
            if 0 <= tx < width and 0 <= ty < height:
                tag = terrain_at(tx, ty)
                if TerrainTypeRegistry.is_walkable(tag, movement_tag):
                    candidates.append((tx, ty))
    return candidates


def init_defaults() -> None:
    """
    Public entry point for initializing default area type definitions.

    Should be called once during startup together with terrain_system.init_defaults().
    """
    AreaRegistry.init_defaults()