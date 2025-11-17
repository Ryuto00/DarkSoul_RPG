import pygame
from typing import List, Optional, Dict, Tuple
from .tile_types import TileType
from .tile_registry import tile_registry


class TileRenderer:
    """Handles rendering of tiles."""

    def __init__(self, tile_size: Optional[int] = None):
        from config import TILE
        # Use provided tile_size or fall back to configured TILE constant
        self.tile_size = tile_size if tile_size is not None else TILE
        self.tile_cache: Dict[TileType, pygame.Surface] = {}
        self.zoom_cache: Dict[str, pygame.Surface] = {}  # For zoom-scaled surfaces
        self.base_cache: Dict[TileType, pygame.Surface] = {}  # For base surfaces
        self.animation_cache: Dict[str, List[pygame.Surface]] = {}
        self.animation_timers: Dict[str, float] = {}
        # Pre-rendered level cache for PCG levels
        self.level_surface_cache: Dict[str, pygame.Surface] = {}
        self.cached_camera_offset: Tuple[float, float] = (0, 0)
        self.cached_zoom: float = 1.0

    def render_tile(self, surface: pygame.Surface, tile_type: TileType,
                   x: int, y: int, camera_offset: Tuple[float, float] = (0, 0),
                   time_delta: float = 0, zoom: float = 1.0):
        """Render a single tile at given position."""
        tile_data = tile_registry.get_tile(tile_type)
        if not tile_data or tile_type == TileType.AIR:
            return

        # Get or create tile surface at the correct size
        tile_surface = self._get_tile_surface_for_zoom(tile_data, time_delta, zoom)
        if tile_surface:
            # Calculate screen position, applying zoom.
            screen_x = int((x - camera_offset[0]) * zoom)
            screen_y = int((y - camera_offset[1]) * zoom)
            
            # Blit the tile (surface is already scaled to correct size)
            surface.blit(tile_surface, (screen_x, screen_y))

    def _get_tile_surface_for_zoom(self, tile_data, time_delta: float, zoom: float) -> Optional[pygame.Surface]:
        """Get or create tile surface at the correct size for the given zoom."""
        tile_type = tile_data.tile_type
        
        # Create a cache key that includes the zoom level
        cache_key = f"{tile_type.value}_{zoom}"
        
        # Check if we have animation
        if tile_data.visual.animation_frames:
            return self._get_animated_surface_for_zoom(tile_data, time_delta, zoom, cache_key)

        # Use cached surface for this zoom level
        if cache_key in self.zoom_cache:
            return self.zoom_cache[cache_key]

        # Get the base surface and scale it to the correct size
        base_surface = self._get_base_tile_surface(tile_data, time_delta)
        if base_surface:
            # Scale to the correct size for this zoom
            screen_size = int(self.tile_size * zoom)
            scaled_surface = pygame.transform.scale(base_surface, (screen_size, screen_size))
            
            # Cache it
            self.zoom_cache[cache_key] = scaled_surface
            return scaled_surface
            
        return None

    def _get_animated_surface_for_zoom(self, tile_data, time_delta: float, zoom: float, cache_key: str) -> Optional[pygame.Surface]:
        """Get animated surface for tile at the correct zoom."""
        # Initialize animation if needed
        if cache_key not in self.animation_timers:
            self.animation_timers[cache_key] = 0
            self.animation_cache[cache_key] = []

        # Load animation frames if not cached
        if not self.animation_cache[cache_key]:
            for frame_path in tile_data.visual.animation_frames:
                try:
                    frame = pygame.image.load(frame_path).convert_alpha()
                    # Scale frame to the correct size for this zoom
                    screen_size = int(self.tile_size * zoom)
                    frame = pygame.transform.scale(frame, (screen_size, screen_size))
                    self.animation_cache[cache_key].append(frame)
                except:
                    # Fallback to static surface if frame loading fails
                    base_surface = self._get_base_tile_surface(tile_data, time_delta)
                    if base_surface:
                        screen_size = int(self.tile_size * zoom)
                        frame = pygame.transform.scale(base_surface, (screen_size, screen_size))
                        self.animation_cache[cache_key] = [frame]
                    else:
                        self.animation_cache[cache_key] = []

        # Update animation timer
        self.animation_timers[cache_key] += time_delta

        # Get current frame
        frames = self.animation_cache[cache_key]
        if frames:
            frame_index = int(self.animation_timers[cache_key] / tile_data.visual.animation_speed) % len(frames)
            return frames[frame_index]

        # Fallback
        base_surface = self._get_base_tile_surface(tile_data, time_delta)
        if base_surface:
            screen_size = int(self.tile_size * zoom)
            return pygame.transform.scale(base_surface, (screen_size, screen_size))
        return None

    def _get_base_tile_surface(self, tile_data, time_delta: float):
        """Get the base tile surface (without zoom scaling)."""
        tile_type = tile_data.tile_type

        # Use cached base surface
        if tile_type in self.base_cache:
            return self.base_cache[tile_type]

        # Create new base surface
        surface = self._create_tile_surface(tile_data)
        if surface:
            # Cache the base surface
            self.base_cache[tile_type] = surface
            return surface
            
        return None

    def _get_tile_surface(self, tile_data, time_delta: float) -> Optional[pygame.Surface]:
        """Get cached or create new surface for tile."""
        tile_type = tile_data.tile_type

        # Check if we have animation
        if tile_data.visual.animation_frames:
            return self._get_animated_surface(tile_data, time_delta)

        # Use cached static surface
        if tile_type in self.tile_cache:
            return self.tile_cache[tile_type]

        # Create new surface
        surface = self._create_tile_surface(tile_data)
        self.tile_cache[tile_type] = surface
        return surface

    def _get_animated_surface(self, tile_data, time_delta: float) -> pygame.Surface:
        """Get animated surface for tile."""
        tile_type = tile_data.tile_type
        cache_key = f"{tile_type}_anim"

        # Initialize animation
        if cache_key not in self.animation_timers:
            self.animation_timers[cache_key] = 0
            self.animation_cache[cache_key] = []

        # Load animation frames if not cached
        if not self.animation_cache[cache_key]:
            for frame_path in tile_data.visual.animation_frames:
                try:
                    frame = pygame.image.load(frame_path).convert_alpha()
                    frame = pygame.transform.scale(frame, (self.tile_size, self.tile_size))
                    self.animation_cache[cache_key].append(frame)
                except:
                    # Fallback to static surface if frame loading fails
                    surface = self._create_tile_surface(tile_data)
                    self.animation_cache[cache_key] = [surface]

        # Update animation timer
        self.animation_timers[cache_key] += time_delta

        # Get current frame
        frames = self.animation_cache[cache_key]
        if frames:
            frame_index = int(self.animation_timers[cache_key] / tile_data.visual.animation_speed) % len(frames)
            return frames[frame_index]

        # Fallback
        return self._create_tile_surface(tile_data)

    def _create_tile_surface(self, tile_data) -> pygame.Surface:
        """Create surface for tile based on its visual properties."""
        surface = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)

        # Try to load sprite (but don't replace the background surface immediately)
        sprite = None
        if getattr(tile_data.visual, 'sprite_path', None):
            try:
                sprite = pygame.image.load(tile_data.visual.sprite_path).convert_alpha()
            except Exception:
                sprite = None

        # Create colored rectangle with border if needed
        color = tile_data.visual.base_color
        if len(color) == 3:
            color = (*color, 255)  # Add alpha if not present

        # Draw main tile
        if tile_data.visual.border_radius > 0:
            pygame.draw.rect(surface, color, surface.get_rect(),
                           border_radius=tile_data.visual.border_radius)
        else:
            pygame.draw.rect(surface, color, surface.get_rect())

        # Draw border if specified
        if tile_data.visual.render_border and tile_data.visual.border_color:
            border_color = tile_data.visual.border_color
            if len(border_color) == 3:
                border_color = (*border_color, 255)
            pygame.draw.rect(surface, border_color, surface.get_rect(), 2,
                           border_radius=tile_data.visual.border_radius)

        # If we loaded a sprite, composite it over the rounded background so
        # sprite per-pixel alpha is preserved and rounded corners show through.
        if sprite:
            try:
                # Ensure tile_size is an int
                size = int(self.tile_size)
                scaled = pygame.transform.scale(sprite, (size, size))
                surface.blit(scaled, (0, 0))
            except Exception:
                # Don't let sprite issues crash tile rendering
                pass

        return surface

    def render_tile_grid(
        self,
        surface: pygame.Surface,
        tile_grid: List[List[int]],
        camera_offset: Tuple[float, float] = (0, 0),
        visible_rect: Optional[pygame.Rect] = None,
        time_delta: float = 0,
        zoom: float = 1.0,
    ):
        """
        Render all visible tiles in the grid for the given camera and zoom.
        Uses chunk-based caching to improve performance on large PCG levels.

        camera_offset: (camera_x, camera_y) in WORLD coordinates.
        zoom: current zoom factor.
        """
        if not tile_grid:
            return

        map_height = len(tile_grid)
        map_width = len(tile_grid[0])

        if visible_rect is None:
            visible_rect = surface.get_rect()

        screen_w = visible_rect.width
        screen_h = visible_rect.height

        cam_x, cam_y = camera_offset

        # Visible WORLD bounds based on camera + zoom
        world_left = cam_x
        world_top = cam_y
        world_right = cam_x + screen_w / zoom
        world_bottom = cam_y + screen_h / zoom

        # Convert world bounds to TILE indices with small buffer
        buffer_tiles = 2

        start_tx = max(0, int(world_left // self.tile_size) - buffer_tiles)
        end_tx = min(
            map_width,
            int(world_right // self.tile_size) + buffer_tiles,
        )

        start_ty = max(0, int(world_top // self.tile_size) - buffer_tiles)
        end_ty = min(
            map_height,
            int(world_bottom // self.tile_size) + buffer_tiles,
        )

        DEBUG_TILE_RENDERER = False
        if DEBUG_TILE_RENDERER:
            import logging
            logging.getLogger(__name__).debug(
                "[TileRenderer] zoom=%0.2f screen=(%dx%d) world=(%0.1f,%0.1f)-(%0.1f,%0.1f) tiles_x=[%d,%d) tiles_y=[%d,%d)",
                zoom, screen_w, screen_h, world_left, world_top, world_right, world_bottom, start_tx, end_tx, start_ty, end_ty
            )

        # Optimization: Only render non-air tiles to reduce draw calls
        for ty in range(start_ty, end_ty):
            row = tile_grid[ty]
            for tx in range(start_tx, end_tx):
                tile_value = row[tx]
                # Skip air tiles entirely
                if tile_value < 0 or tile_value == 0:
                    continue

                tile_type = TileType(tile_value)
                
                # Additional check to skip AIR tiles by enum
                if tile_type == TileType.AIR:
                    continue
                
                world_x = tx * self.tile_size
                world_y = ty * self.tile_size

                self.render_tile(
                    surface=surface,
                    tile_type=tile_type,
                    x=world_x,
                    y=world_y,
                    camera_offset=camera_offset,
                    time_delta=time_delta,
                    zoom=zoom,
                )

    def render_debug_grid(self, surface: pygame.Surface, tile_grid: List[List[int]],
                         camera_offset: Tuple[float, float] = (0, 0),
                         show_collision_boxes: bool = False, zoom: float = 1.0):
        """Render debug information about tiles."""
        if not tile_grid:
            return

        grid_color = (100, 100, 100, 100)
        font = pygame.font.Font(None, 12)

        # Get visible area
        start_x = max(0, int(camera_offset[0] // self.tile_size))
        end_x = min(len(tile_grid[0]),
                   int((camera_offset[0] + surface.get_width() / zoom) // self.tile_size) + 1)
        start_y = max(0, int(camera_offset[1] // self.tile_size))
        end_y = min(len(tile_grid),
                   int((camera_offset[1] + surface.get_height() / zoom) // self.tile_size) + 1)

        # Draw grid lines
        for x in range(start_x, end_x + 1):
            screen_x = (x * self.tile_size - camera_offset[0]) * zoom
            pygame.draw.line(surface, grid_color, (screen_x, 0),
                           (screen_x, surface.get_height()), 1)

        for y in range(start_y, end_y + 1):
            screen_y = (y * self.tile_size - camera_offset[1]) * zoom
            pygame.draw.line(surface, grid_color, (0, screen_y),
                           (surface.get_width(), screen_y), 1)

        # Show collision boxes if requested (disabled to avoid Pylance issues)
        # TODO: Re-enable once collision system is fully type-safe
        if show_collision_boxes:
            pass  # Collision debug rendering temporarily disabled

    def clear_cache(self):
        """Clear all cached surfaces."""
        self.tile_cache.clear()
        self.zoom_cache.clear()
        self.base_cache.clear()
        self.animation_cache.clear()
        self.animation_timers.clear()
        self.level_surface_cache.clear()

    def preload_tiles(self):
        """Preload all tile surfaces for different zoom levels."""
        for tile_type in TileType:
            tile_data = tile_registry.get_tile(tile_type)
            if tile_data and tile_type != TileType.AIR:
                # Preload for each zoom level (only non-air tiles)
                for zoom in [1.0, 1.2, 1.5]:
                    self._get_tile_surface_for_zoom(tile_data, 0, zoom)