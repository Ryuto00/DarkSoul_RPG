from typing import Dict, Optional
from .tile_types import TileType
from .tile_data import (
    TileData,
    CollisionProperties,
    VisualProperties,
    PhysicalProperties,
    InteractionProperties,
    AudioProperties,
    LightingProperties
)


class TileRegistry:
    """Registry for storing and managing tile definitions."""

    def __init__(self):
        self._tiles: Dict[TileType, TileData] = {}
        self._initialize_default_tiles()

    def _initialize_default_tiles(self):
        """Initialize default tile types with their properties."""

        # Air tile
        self.register_tile(TileData(
            tile_type=TileType.AIR,
            name="Air",
            collision=CollisionProperties(
                collision_type="none",
                can_pass_through=True
            ),
            visual=VisualProperties(
                base_color=(0, 0, 0)  # Transparent
            ),
            physics=PhysicalProperties(
                friction=0.0
            ),
            lighting=LightingProperties(
                transparency=1.0,
                blocks_light=False,
                casts_shadows=False
            )
        ))



        # Wall tile
        self.register_tile(TileData(
            tile_type=TileType.WALL,
            name="Wall",
            collision=CollisionProperties(
                collision_type="full",
                collision_box_size=(24, 24),
                can_walk_on=True
            ),
            visual=VisualProperties(
                base_color=(54, 60, 78),
                border_radius=4,
                sprite_path="assets/tiles/Wall.png"
            ),
            physics=PhysicalProperties(
                friction=0.8
            ),
            lighting=LightingProperties(
                blocks_light=True,
                casts_shadows=True
            ),
            audio=AudioProperties(
                contact_sound="hit_wall"
            )
        ))

        # Door Entrance tile (spawn marker)
        self.register_tile(TileData(
            tile_type=TileType.DOOR_ENTRANCE,
            name="Door Entrance",
            collision=CollisionProperties(
                collision_type="none",
                can_pass_through=True
            ),
            visual=VisualProperties(
                base_color=(40, 160, 220),
                border_radius=4,
                render_border=True,
                border_color=(255, 255, 255),
                sprite_path="assets/tiles/portal.png"
            ),
            interaction=InteractionProperties(
                is_trigger=True,
                is_spawn_point=True
            )
        ))

        # Door Exit tile (proximity + E to interact)
        self.register_tile(TileData(
            tile_type=TileType.DOOR_EXIT,
            name="Door Exit",
            collision=CollisionProperties(
                collision_type="none",
                can_pass_through=True
            ),
            visual=VisualProperties(
                base_color=(180, 120, 40),
                border_radius=4,
                render_border=True,
                border_color=(255, 255, 255),
                sprite_path="assets/tiles/portal.png"
            ),
            interaction=InteractionProperties(
                interactable=True,
                is_trigger=True,
                requires_proximity=True,
                proximity_radius=24.0,
                prompt="Press E to enter",
                on_interact_id="door_exit_default"
            )
        ))

        # Door Exit 1 tile (first exit slot)
        self.register_tile(TileData(
            tile_type=TileType.DOOR_EXIT_1,
            name="Door Exit 1",
            collision=CollisionProperties(
                collision_type="none",
                can_pass_through=True
            ),
            visual=VisualProperties(
                base_color=(200, 100, 50),
                border_radius=4,
                render_border=True,
                border_color=(255, 200, 100),
                sprite_path="assets/tiles/portal.png"
            ),
            interaction=InteractionProperties(
                interactable=True,
                is_trigger=True,
                requires_proximity=True,
                proximity_radius=24.0,
                prompt="Press E to enter (Exit 1)",
                on_interact_id="door_exit_1"
            )
        ))

        # Door Exit 2 tile (second exit slot)
        self.register_tile(TileData(
            tile_type=TileType.DOOR_EXIT_2,
            name="Door Exit 2",
            collision=CollisionProperties(
                collision_type="none",
                can_pass_through=True
            ),
            visual=VisualProperties(
                base_color=(150, 80, 120),
                border_radius=4,
                render_border=True,
                border_color=(200, 150, 255),
                sprite_path="assets/tiles/portal.png"
            ),
            interaction=InteractionProperties(
                interactable=True,
                is_trigger=True,
                requires_proximity=True,
                proximity_radius=24.0,
                prompt="Press E to enter (Exit 2)",
                on_interact_id="door_exit_2"
            )
        ))




    def register_tile(self, tile_data: TileData):
        """Register a new tile type."""
        self._tiles[tile_data.tile_type] = tile_data

    def get_tile(self, tile_type: TileType) -> Optional[TileData]:
        """Get tile data by type."""
        return self._tiles.get(tile_type)

    def get_all_tiles(self) -> Dict[TileType, TileData]:
        """Get all registered tiles."""
        return self._tiles.copy()

    def tiles_with_property(self, property_name: str, value=True):
        """Get all tiles that have a specific property value."""
        matching_tiles = []
        for tile_data in self._tiles.values():
            if hasattr(tile_data, property_name):
                if getattr(tile_data, property_name) == value:
                    matching_tiles.append(tile_data)
        return matching_tiles

    def register_custom_tile(self, tile_data: TileData):
        """Register a custom tile type (for user-defined tiles)."""
        if tile_data.tile_type in self._tiles:
            raise ValueError(f"Tile type {tile_data.tile_type} already registered")
        self.register_tile(tile_data)


# Global tile registry instance
tile_registry = TileRegistry()