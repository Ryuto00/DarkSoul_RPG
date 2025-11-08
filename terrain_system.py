"""
Modular terrain system with base types, modifiers, and concrete terrain IDs.

This module is intentionally data-driven:
- New base types and modifiers are registered via the registry API.
- Concrete terrain IDs (strings used in terrain_grid) map to TerrainTag instances.
- Helper predicates are used by generation, validation, and gameplay systems.

Core concepts:
- Base types: PLATFORM, FLOOR, WALL, WATER (extensible)
- Modifiers: STICKY, ICY, FIRE for PLATFORM/FLOOR (extensible, including for WALL later)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set, List, FrozenSet, Iterable, Optional


# Public string constants for base terrain categories.
class TerrainBaseType:
    PLATFORM: str = "platform"
    FLOOR: str = "floor"
    WALL: str = "wall"
    WATER: str = "water"
    # Additional base types can be added via TerrainTypeRegistry.register_base_type.


# Public string constants for terrain modifiers (effects).
class TerrainModifier:
    STICKY: str = "sticky"
    ICY: str = "icy"
    FIRE: str = "fire"
    # Additional modifiers can be added via TerrainTypeRegistry.register_terrain_modifier.


@dataclass(frozen=True)
class TerrainTag:
    """
    Resolved terrain properties for a single terrain ID.

    Attributes:
        id: canonical ID string used in terrain_grid (e.g. "floor_normal", "platform_fire")
        base_type: one of the registered base types
        modifiers: frozenset of modifier IDs affecting behavior/FX
    """
    id: str
    base_type: str
    modifiers: FrozenSet[str]


class _TerrainTypeRegistry:
    """
    Internal implementation of terrain registry.

    Responsibilities:
    - Track base types, modifiers, and allowed base types per modifier.
    - Map concrete terrain IDs to TerrainTag.
    - Provide helper predicates used by other systems.
    """

    def __init__(self) -> None:
        self._base_types: Set[str] = set()
        self._modifiers: Set[str] = set()
        self._modifier_allowed_bases: Dict[str, Set[str]] = {}
        self._terrains: Dict[str, TerrainTag] = {}

        # Behavior configuration (can be extended externally if needed).
        self._walkable_bases_for_movement: Dict[str, Set[str]] = {
            "ground": {TerrainBaseType.FLOOR, TerrainBaseType.PLATFORM},
            "flying": {
                TerrainBaseType.FLOOR,
                TerrainBaseType.PLATFORM,
                TerrainBaseType.WALL,
                TerrainBaseType.WATER,
            },
            "amphibious": {
                TerrainBaseType.FLOOR,
                TerrainBaseType.PLATFORM,
                TerrainBaseType.WATER,
            },
        }
        # Modifiers considered hazardous by default.
        self._hazardous_modifiers: Set[str] = {TerrainModifier.FIRE}
        # Base types considered hazardous regardless of modifier.
        self._hazardous_bases: Set[str] = set()
        # Base types considered platform-like for spawning, etc.
        self._platform_like_bases: Set[str] = {
            TerrainBaseType.FLOOR,
            TerrainBaseType.PLATFORM,
        }

    # --- Registration API ---

    def register_base_type(self, base_id: str) -> None:
        """
        Register a new base terrain type.

        Idempotent: re-registering same ID is allowed.
        """
        if not base_id:
            raise ValueError("base_id must be non-empty")
        self._base_types.add(base_id)

    def register_terrain_modifier(
        self,
        modifier_id: str,
        allowed_bases: Iterable[str],
    ) -> None:
        """
        Register a new terrain modifier and which base types it can apply to.

        Example:
            register_terrain_modifier("sticky", [TerrainBaseType.FLOOR, TerrainBaseType.PLATFORM])
        """
        if not modifier_id:
            raise ValueError("modifier_id must be non-empty")

        allowed_bases_set = set(allowed_bases)
        if not allowed_bases_set:
            raise ValueError("allowed_bases must not be empty")

        self._modifiers.add(modifier_id)
        self._modifier_allowed_bases[modifier_id] = allowed_bases_set

    def define_terrain(
        self,
        terrain_id: str,
        base: str,
        modifiers: Optional[Iterable[str]] = None,
    ) -> None:
        """
        Define a concrete terrain ID mapping to a TerrainTag.

        Args:
            terrain_id: ID used in terrain_grid (e.g. "floor_normal").
            base: registered base type.
            modifiers: optional modifiers that must be compatible with 'base'.
        """
        if not terrain_id:
            raise ValueError("terrain_id must be non-empty")
        if base not in self._base_types:
            raise ValueError(f"Unknown base type '{base}' for terrain '{terrain_id}'")

        mods: FrozenSet[str]
        if modifiers:
            norm_mods: Set[str] = set()
            for m in modifiers:
                if m not in self._modifiers:
                    raise ValueError(f"Unknown modifier '{m}' for terrain '{terrain_id}'")
                if not self.can_apply_modifier(base, m):
                    raise ValueError(
                        f"Modifier '{m}' cannot be applied to base '{base}' for terrain '{terrain_id}'"
                    )
                norm_mods.add(m)
            mods = frozenset(norm_mods)
        else:
            mods = frozenset()

        self._terrains[terrain_id] = TerrainTag(
            id=terrain_id,
            base_type=base,
            modifiers=mods,
        )

    # --- Lookup API ---

    def get_terrain(self, terrain_id: str) -> TerrainTag:
        """
        Resolve a terrain_id string into a TerrainTag.

        If the ID is unknown, falls back to a safe default 'floor_normal'-style tag
        if available, else raises KeyError. This keeps behavior predictable.
        """
        if terrain_id in self._terrains:
            return self._terrains[terrain_id]

        # Fallback: treat unknown as plain floor if defined.
        if "floor_normal" in self._terrains:
            return self._terrains["floor_normal"]

        raise KeyError(f"Unknown terrain id '{terrain_id}'")

    def can_apply_modifier(self, base: str, modifier: str) -> bool:
        """
        Check if a modifier is allowed on a given base type.
        """
        allowed = self._modifier_allowed_bases.get(modifier)
        return bool(allowed and base in allowed)

    # --- Behavior helpers ---

    def is_walkable(self, tag: TerrainTag, movement: str) -> bool:
        """
        Generic walkability check for different movement categories.
        movement: e.g. "ground", "flying", "amphibious".
        """
        if not movement:
            return False

        walkable_bases = self._walkable_bases_for_movement.get(movement)
        if not walkable_bases:
            # Unknown movement: default to floor/platform.
            walkable_bases = self._platform_like_bases

        return tag.base_type in walkable_bases

    def is_hazardous(self, tag: TerrainTag) -> bool:
        """
        Whether this terrain should be treated as dangerous for players/ground enemies.
        """
        if tag.base_type in self._hazardous_bases:
            return True
        if any(m in self._hazardous_modifiers for m in tag.modifiers):
            return True
        return False

    def is_platform_like(self, tag: TerrainTag) -> bool:
        """
        True if a tile behaves like ground/platform for spawning and standing.
        """
        return tag.base_type in self._platform_like_bases

    def supports_enemy(self, tag: TerrainTag, enemy_traits: List[str]) -> bool:
        """
        Check if a terrain tile supports an enemy with given traits.

        Conventions:
        - If 'flying' in traits: always allowed (independent of base type).
        - Else if 'amphibious' in traits: must be walkable for 'amphibious'.
        - Else: must be walkable for 'ground'.
        - If terrain is hazardous and enemy is not 'fire_resistant' or similar, we still
          return True here (combat tuning can further restrict).
        """
        traits = set(enemy_traits or [])
        if "flying" in traits or "air" in traits:
            return True

        if "amphibious" in traits:
            return self.is_walkable(tag, "amphibious")

        # Default: ground-based
        return self.is_walkable(tag, "ground")

    # --- Default configuration ---

    def init_defaults(self) -> None:
        """
        Initialize default base types, modifiers, and terrain IDs.

        This should be called once during startup (e.g., from level generation bootstrap).
        Safe to call multiple times; re-definitions of identical values are allowed.
        """
        # Base types
        self.register_base_type(TerrainBaseType.PLATFORM)
        self.register_base_type(TerrainBaseType.FLOOR)
        self.register_base_type(TerrainBaseType.WALL)
        self.register_base_type(TerrainBaseType.WATER)

        # Modifiers for PLATFORM/FLOOR; WALL intentionally has no modifiers yet.
        self.register_terrain_modifier(
            TerrainModifier.STICKY,
            [TerrainBaseType.FLOOR, TerrainBaseType.PLATFORM],
        )
        self.register_terrain_modifier(
            TerrainModifier.ICY,
            [TerrainBaseType.FLOOR, TerrainBaseType.PLATFORM],
        )
        self.register_terrain_modifier(
            TerrainModifier.FIRE,
            [TerrainBaseType.FLOOR, TerrainBaseType.PLATFORM],
        )

        # Concrete terrain IDs.
        # Floors
        self.define_terrain("floor_normal", TerrainBaseType.FLOOR, [])
        self.define_terrain("floor_sticky", TerrainBaseType.FLOOR, [TerrainModifier.STICKY])
        self.define_terrain("floor_icy", TerrainBaseType.FLOOR, [TerrainModifier.ICY])
        self.define_terrain("floor_fire", TerrainBaseType.FLOOR, [TerrainModifier.FIRE])

        # Platforms
        self.define_terrain("platform_normal", TerrainBaseType.PLATFORM, [])
        self.define_terrain("platform_sticky", TerrainBaseType.PLATFORM, [TerrainModifier.STICKY])
        self.define_terrain("platform_icy", TerrainBaseType.PLATFORM, [TerrainModifier.ICY])
        self.define_terrain("platform_fire", TerrainBaseType.PLATFORM, [TerrainModifier.FIRE])

        # Walls
        self.define_terrain("wall_solid", TerrainBaseType.WALL, [])

        # Water
        self.define_terrain("water", TerrainBaseType.WATER, [])

    # --- Utility for external code (optional overrides) ---

    def set_walkable_bases_for_movement(self, movement: str, bases: Iterable[str]) -> None:
        """
        Override or extend which base types are walkable for a given movement category.
        """
        self._walkable_bases_for_movement[movement] = set(bases)

    def add_hazardous_modifier(self, modifier: str) -> None:
        """
        Mark a modifier as hazardous globally.
        """
        self._hazardous_modifiers.add(modifier)

    def add_hazardous_base(self, base: str) -> None:
        """
        Mark a base type as hazardous globally.
        """
        self._hazardous_bases.add(base)

    def add_platform_like_base(self, base: str) -> None:
        """
        Mark a base type as platform-like (good for spawn, ground walk).
        """
        self._platform_like_bases.add(base)


# Singleton instance used across the project.
TerrainTypeRegistry = _TerrainTypeRegistry()


def init_defaults() -> None:
    """
    Public entry point for initializing default terrain configuration.
    Code should call this once during startup / before generation.
    """
    TerrainTypeRegistry.init_defaults()