import sys

import pygame
from config import (
    WIDTH,
    HEIGHT,
    FPS,
    BG,
    WHITE,
    CYAN,
    GREEN,
    WALL_JUMP_COOLDOWN,
)
from src.core.utils import draw_text, get_font
from src.systems.camera import Camera
from src.level.level import Level, ROOM_COUNT
from src.entities.entities import Player, hitboxes, floating, DamageNumber
from src.systems.inventory import Inventory
from src.systems.menu import Menu
from src.systems.shop import Shop




class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Haridd")
        self.clock = pygame.time.Clock()
        self.font_small = get_font(18)
        self.font_big = get_font(32, bold=True)
        self.camera = Camera()

        # Level configuration: static layout only (procedural disabled)
        self.level_type = "static"
        self.difficulty = 1

        # Initialize menu system
        self.menu = Menu(self)

        # Title flow first
        self.selected_class = 'Knight'  # default if player skips class select

        # Developer cheat toggles
        self.cheat_infinite_mana = False
        self.cheat_zero_cooldown = False
        self.debug_enemy_rays = False
        self.debug_enemy_nametags = False

        # Terrain/Area debug
        self.debug_show_area_overlay = False
        # Whether we are currently in the dedicated terrain/area test level
        self.in_terrain_test_level = False

        # Grid position debug
        self.debug_grid_position = False
        self.mouse_grid_pos = None
        self.mouse_world_pos = None


        # Double spacebar detection for no-clip toggle
        self.last_space_time = 0
        self.space_double_tap_window = 20  # frames for double-tap detection
        self._prev_space_pressed = False

        # Run title; legacy flow may still configure basic options
        self.menu.title_screen()
        
        # Level state for static rooms
        self.level_index = 0
        
        # Initialize first static level
        self._load_level(self.level_index, initial=True)

        # create player with chosen class
        sx, sy = self.level.spawn
        self.player = Player(sx, sy, cls=self.selected_class)
        self.enemies = self.level.enemies

        # Inventory & shop
        self.inventory = Inventory(self)
        self.inventory._refresh_inventory_defaults()
        self.shop = Shop(self)

    # === Level Management (static rooms only) ===

    def restart_run(self):
        """
        Restart from the first static room.
        """
        # Reset to first level index
        self.level_index = 0

        # Load level 0
        self._load_level(self.level_index, initial=True)

        # Recreate player at the new spawn
        sx, sy = self.level.spawn
        self.player = Player(sx, sy, cls=self.selected_class)

        # Sync enemies from the level
        self.enemies = getattr(self.level, "enemies", [])

        # Reset/refresh inventory if present
        if hasattr(self, "inventory") and self.inventory is not None:
            self.inventory._refresh_inventory_defaults()

        # Clear transient collections
        hitboxes.clear()
        floating.clear()

        # Reset camera
        self.camera = Camera()

    def _load_level(self, index: int, initial: bool = False):
        """
        Load a static level by index using legacy hard-coded rooms.
        """
        self.level_index = index

        # Use modulo to cycle through available hardcoded rooms
        room_index = index % ROOM_COUNT

        try:
            lvl = Level(room_index)
            print(f"[INFO] Loaded hardcoded room {room_index} for level {index}")
        except Exception as e:
            print(f"[CRITICAL ERROR] Failed to load hardcoded room {room_index}: {e}")
            return

        # Ensure core attributes exist
        if not hasattr(lvl, "doors"):
            lvl.doors = []
        if not hasattr(lvl, "enemies"):
            lvl.enemies = []

        self.level = lvl
        self.enemies = lvl.enemies

        if not initial:
            # Clear transient combat visuals when switching rooms
            hitboxes.clear()
            floating.clear()

    def switch_room(self, delta: int):
        """
        Move to next/previous static room index (wraps within ROOM_COUNT).
        """
        new_index = max(0, self.level_index + delta)
        self._load_level(new_index)

        # Reposition player at new spawn
        sx, sy = self.level.spawn
        self.player.rect.topleft = (sx, sy)
        self.enemies = getattr(self.level, "enemies", [])

        # Open shop after completing level (preserve behavior)
        self.shop.open_shop()

    def goto_room(self, index: int):
        """
        Teleport to an absolute static room index (wraps within ROOM_COUNT).
        """
        target_index = max(0, index)
        self._load_level(target_index)
        sx, sy = self.level.spawn
        self.player.rect.topleft = (sx, sy)
        self.enemies = getattr(self.level, "enemies", [])
        hitboxes.clear()
        floating.clear()

    def update(self):
        self.player.input(self.level, self.camera)
        self.player.physics(self.level)
        self.inventory.recalculate_player_stats()

        # If player died, show restart menu
        if getattr(self.player, 'dead', False):
            self.menu.game_over_screen()
            return

        # Apply developer cheats each frame
        if self.cheat_infinite_mana and hasattr(self.player, 'max_mana'):
            self.player.mana = getattr(self.player, 'max_mana', self.player.mana)
        if self.cheat_zero_cooldown:
            # Force cooldowns to zero if present
            for attr in ('skill_cd1', 'skill_cd2', 'skill_cd3', 'dash_cd', 'mobility_cd'):
                if hasattr(self.player, attr):
                    setattr(self.player, attr, 0)

        # Handle double-space detection for no-clip + floating toggle (only in god mode)
        if getattr(self.player, 'god', False):
            keys = pygame.key.get_pressed()
            space_pressed = keys[pygame.K_SPACE] or keys[pygame.K_k]

            # Check for double-tap
            if space_pressed and not self._prev_space_pressed:
                # Space just pressed
                if pygame.time.get_ticks() - self.last_space_time < (self.space_double_tap_window * 1000 // FPS):
                    # Double-tap detected!
                    currently_active = getattr(self.player, 'no_clip', False)
                    if currently_active:
                        # Turn OFF both no-clip and floating
                        self.player.no_clip = False
                        self.player.floating_mode = False
                        floating.append(DamageNumber(
                            self.player.rect.centerx,
                            self.player.rect.top - 12,
                            "No-clip OFF!",
                            (200, 200, 200)
                        ))
                    else:
                        # Turn ON both no-clip and floating
                        self.player.no_clip = True
                        self.player.floating_mode = True
                        floating.append(DamageNumber(
                            self.player.rect.centerx,
                            self.player.rect.top - 12,
                            "No-clip ON (Floating)!",
                            (100, 255, 200)
                        ))
                self.last_space_time = pygame.time.get_ticks()
            self._prev_space_pressed = space_pressed

        for d in getattr(self.level, "doors", []):
            if self.player.rect.colliderect(d):
                # Boss gate logic preserved for legacy/boss-style levels
                if getattr(self.level, 'is_boss_room', False):
                    if any(getattr(e, 'alive', False) for e in self.enemies):
                        # door locked; stay in room
                        pass
                    else:
                        self.switch_room(+1)
                        break
                else:
                    self.switch_room(+1)
                    break

        for e in self.enemies:
            e.tick(self.level, self.player)

        for hb in list(hitboxes):
            hb.tick()
            # if projectile hits solids, explode or die
            collided_solid = False
            for s in self.level.solids:
                if hb.rect.colliderect(s):
                    collided_solid = True
                    break
            if collided_solid:
                if getattr(hb, 'aoe_radius', 0) > 0 and not getattr(hb, 'visual_only', False):
                    cx, cy = hb.rect.center
                    for e2 in self.enemies:
                        if getattr(e2, 'alive', False):
                            dx = e2.rect.centerx - cx
                            dy = e2.rect.centery - cy
                            if (dx*dx + dy*dy) ** 0.5 <= hb.aoe_radius:
                                e2.hit(hb, self.player)
                # remove visual-only hitboxes or projectiles
                if hb in hitboxes:
                    hitboxes.remove(hb)
                continue
            # enemy hitboxes can affect player (damage/stun). Ignore player's own.
            if getattr(hb, 'owner', None) is not self.player:
                # AOE against player
                if getattr(hb, 'aoe_radius', 0) > 0 and not getattr(hb, 'visual_only', False):
                    cx, cy = hb.rect.center
                    dx = self.player.rect.centerx - cx
                    dy = self.player.rect.centery - cy
                    if (dx*dx + dy*dy) ** 0.5 <= getattr(hb, 'aoe_radius', 0):
                        # apply stun tag if present
                        if getattr(hb, 'tag', None) == 'stun':
                            self.player.stunned = max(self.player.stunned, int(0.8 * FPS))
                        # apply damage if any
                        if getattr(hb, 'damage', 0) > 0:
                            kx, ky = hb.dir_vec if getattr(hb, 'dir_vec', None) else (0, -1)
                            self.player.damage(hb.damage, (int(kx*3), -6))
                        # consume the AOE
                        hb.alive = False
                # direct projectile/contact against player
                elif hb.rect.colliderect(self.player.rect) and not getattr(hb, 'visual_only', False):
                    if getattr(hb, 'tag', None) == 'stun':
                        self.player.stunned = max(self.player.stunned, int(0.8 * FPS))
                    if getattr(hb, 'damage', 0) > 0:
                        kx, ky = hb.dir_vec if getattr(hb, 'dir_vec', None) else (0, -1)
                        self.player.damage(hb.damage, (int(kx*3), -6))
                    # non-piercing projectiles disappear after hitting player
                    if (getattr(hb, 'vx', 0) or getattr(hb, 'vy', 0)) and not getattr(hb, 'pierce', False):
                        hb.alive = False
            # moving/projectile hitboxes may hit enemies; support AOE hitboxes
            # Only allow player-owned hitboxes to damage enemies (no enemy friendly-fire)
            if getattr(hb, 'aoe_radius', 0) > 0 and getattr(hb, 'owner', None) is self.player:
                # visual-only AOE (e.g., cold feet) should not apply instant damage
                if getattr(hb, 'visual_only', False):
                    if not hb.alive:
                        hitboxes.remove(hb)
                    continue
                # check collision with any enemy, explode on first hit
                exploded = False
                for e in self.enemies:
                    if getattr(e, 'alive', False) and hb.rect.colliderect(e.rect):
                        # explode: apply damage to all enemies within radius
                        cx, cy = hb.rect.center
                        for e2 in self.enemies:
                            if getattr(e2, 'alive', False):
                                dx = e2.rect.centerx - cx
                                dy = e2.rect.centery - cy
                                if (dx*dx + dy*dy) ** 0.5 <= hb.aoe_radius:
                                    e2.hit(hb, self.player)
                        exploded = True
                        hb.alive = False
                        break
                if not hb.alive:
                    hitboxes.remove(hb)
                continue

            # Only player-owned hitboxes damage enemies
            if getattr(hb, 'owner', None) is self.player:
                for e in self.enemies:
                    if getattr(e, 'alive', False) and hb.rect.colliderect(e.rect):
                        e.hit(hb, self.player)
                        # moving projectiles should disappear after first enemy hit unless they can pierce
                        if getattr(hb, 'vx', 0) or getattr(hb, 'vy', 0):
                            if not getattr(hb, 'pierce', False):
                                hb.alive = False
                                break
            if not hb.alive:
                hitboxes.remove(hb)

        for dn in list(floating):
            dn.tick()
            if dn.life <= 0:
                floating.remove(dn)

        self.camera.update(self.player.rect)

    def _draw_area_overlay(self):
        """
        Debug: draw logical areas and terrain test info on top of current map.
        Uses self.level.areas if present.
        """
        if not getattr(self, "debug_show_area_overlay", False):
            return

        areas = getattr(self.level, "areas", None)
        if not areas or not getattr(areas, "areas", None):
            return

        # Semi-transparent surface
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        # Draw grid lines first (very subtle) for levels that expose a grid.
        # Static Level does not define grid/terrain_grid; only run when attributes exist.
        level_grid = getattr(self.level, "grid", None)
        if level_grid:
            grid_height = len(level_grid)
            grid_width = len(level_grid[0]) if grid_height > 0 else 0

            # Vertical grid lines
            for x in range(grid_width + 1):
                world_x = x * TILE
                line_rect = pygame.Rect(world_x, 0, 1, grid_height * TILE)
                screen_rect = self.camera.to_screen_rect(line_rect)
                pygame.draw.rect(overlay, (100, 100, 100, 30), screen_rect)

            # Horizontal grid lines
            for y in range(grid_height + 1):
                world_y = y * TILE
                line_rect = pygame.Rect(0, world_y, grid_width * TILE, 1)
                screen_rect = self.camera.to_screen_rect(line_rect)
                pygame.draw.rect(overlay, (100, 100, 100, 30), screen_rect)

        # Simple color mapping per area type
        from src.level.area_system import AreaType
        color_map = {
            AreaType.PLAYER_SPAWN: (80, 200, 120, 80),
            AreaType.PORTAL_ZONE: (80, 160, 255, 80),
            AreaType.GROUND_ENEMY_SPAWN: (255, 120, 80, 80),
            AreaType.FLYING_ENEMY_SPAWN: (200, 200, 80, 80),
            AreaType.WATER_AREA: (80, 120, 255, 80),
            AreaType.MERCHANT_AREA: (255, 200, 120, 80),
        }

        for area in areas.areas:
            px = area.x * TILE
            py = area.y * TILE
            pw = area.width * TILE
            ph = area.height * TILE
            screen_rect = self.camera.to_screen_rect(pygame.Rect(px, py, pw, ph))

            base_col = color_map.get(area.type, (255, 255, 255, 40))
            pygame.draw.rect(overlay, base_col, screen_rect, border_radius=3)
            pygame.draw.rect(overlay, (base_col[0], base_col[1], base_col[2], 180), screen_rect, width=1, border_radius=3)

            # Label inside area with coordinates
            label = f"{area.type} ({area.x},{area.y})"
            draw_text(overlay, label, (screen_rect.x + 4, screen_rect.y + 2), (255, 255, 255), size=10)

            # Draw corner labels for tile coordinates
            if screen_rect.width > 40 and screen_rect.height > 20:
                # Top-left corner coordinate
                coord_label = f"({area.x},{area.y})"
                draw_text(overlay, coord_label, (screen_rect.x + 2, screen_rect.y + screen_rect.height - 15), (200, 200, 200), size=8)

        self.screen.blit(overlay, (0, 0))

    def _get_player_area_labels(self):
        """
        Return a comma-separated string of area types under the player's current tile,
        or empty string if none / unavailable.
        """
        areas = getattr(self.level, "areas", None)
        if not areas or not hasattr(areas, "areas_at"):
            return ""

        tx = self.player.rect.centerx // TILE
        ty = self.player.rect.centery // TILE
        here = areas.areas_at(tx, ty)
        if not here:
            return ""
        # Deduplicate while preserving order
        seen = set()
        types = []
        for a in here:
            if a.type not in seen:
                seen.add(a.type)
                types.append(a.type)
        return ", ".join(types)

    def _get_grid_position(self, mouse_screen_pos):
        """
        Convert mouse screen position to grid coordinates.
        Returns (grid_x, grid_y, world_x, world_y, collision_type, terrain_type, combined_info)
        """
        # Convert screen to world coordinates using camera inverse transform
        world_x = (mouse_screen_pos[0] / self.camera.zoom) + self.camera.x
        world_y = (mouse_screen_pos[1] / self.camera.zoom) + self.camera.y

        # Convert world to grid coordinates
        grid_x = int(world_x // TILE)
        grid_y = int(world_y // TILE)

        # Get tile type if grid exists
        collision_type = "Unknown"
        terrain_type = "Unknown"
        terrain_id = "N/A"

        level_grid = getattr(self.level, "grid", None)
        if level_grid:
            if 0 <= grid_y < len(level_grid) and 0 <= grid_x < len(level_grid[0]):
                # Get collision type from grid (0=air, 1=floor, 2=wall, 3=solid)
                grid_value = level_grid[grid_y][grid_x]
                from config import TILE_AIR, TILE_FLOOR, TILE_WALL, TILE_SOLID
                if grid_value == TILE_AIR:
                    collision_type = "Air"
                elif grid_value == TILE_FLOOR:
                    collision_type = "Floor"
                elif grid_value == TILE_WALL:
                    collision_type = "Wall"
                elif grid_value == TILE_SOLID:
                    collision_type = "Solid"
                else:
                    collision_type = f"Unknown({grid_value})"
        
                # Get terrain type if available (procedural/terrain test levels only)
                terrain_grid = getattr(self.level, "terrain_grid", None)
                if terrain_grid:
                    try:
                        terrain_id = terrain_grid[grid_y][grid_x]
        
                        # Simple terrain type mapping based on terrain_id string
                        if "platform" in terrain_id:
                            terrain_type = "Platform"
                        elif "wall" in terrain_id:
                            terrain_type = "Wall"
                        elif "floor" in terrain_id:
                            terrain_type = "Floor"
                        elif "water" in terrain_id:
                            terrain_type = "Water"
                        else:
                            # Use the terrain_id directly if we can't categorize it
                            terrain_type = terrain_id
        
                    except Exception as e:
                        # Fallback if terrain system fails
                        terrain_type = f"Error: {str(e)[:20]}"
                else:
                    terrain_type = "No terrain data"

        # Create combined info string showing both types
        if collision_type != "Unknown" and terrain_type != "Unknown":
            combined_info = f"Collision: {collision_type} | Terrain: {terrain_type}"
        elif collision_type != "Unknown":
            combined_info = f"Collision: {collision_type}"
        else:
            combined_info = "Out of bounds"

        return grid_x, grid_y, int(world_x), int(world_y), collision_type, terrain_type, combined_info, terrain_id

    def _draw_grid_position_overlay(self):
        """
        Draw grid position information at mouse cursor when debug_grid_position is enabled.
        Only works when god mode is active.
        """
        if not self.debug_grid_position:
            return

        # Only work in god mode
        if not getattr(self.player, 'god', False):
            return

        # Get current mouse position
        mouse_screen_pos = pygame.mouse.get_pos()

        # Calculate grid position
        grid_x, grid_y, world_x, world_y, collision_type, terrain_type, combined_info, terrain_id = self._get_grid_position(mouse_screen_pos)

        # Store positions for potential other uses
        self.mouse_grid_pos = (grid_x, grid_y)
        self.mouse_world_pos = (world_x, world_y)

        # Create overlay surface for text with transparency
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        # Draw highlight on the target grid tile
        grid_screen_x = (grid_x * TILE - self.camera.x) * self.camera.zoom
        grid_screen_y = (grid_y * TILE - self.camera.y) * self.camera.zoom
        tile_screen_size = TILE * self.camera.zoom

        # Draw semi-transparent highlight with terrain-specific colors
        highlight_rect = pygame.Rect(grid_screen_x, grid_screen_y, tile_screen_size, tile_screen_size)

        # Default colors if no specific conditions are met
        highlight_color = (255, 255, 255, 60)  # White with transparency
        border_color = (255, 255, 255, 180)    # White with transparency

        # Determine highlight color based on tile type and terrain
        level_grid = getattr(self.level, "grid", None)
        if level_grid:
            if 0 <= grid_y < len(level_grid) and 0 <= grid_x < len(level_grid[0]):
                from config import TILE_AIR, TILE_FLOOR, TILE_WALL, TILE_SOLID
                tile_value = level_grid[grid_y][grid_x]

                # Set colors based on tile type
                if tile_value == TILE_AIR:
                    highlight_color = (200, 200, 200, 30)  # Light gray for air
                    border_color = (200, 200, 200, 100)
                elif tile_value == TILE_FLOOR:
                    highlight_color = (100, 255, 100, 60)  # Green for floors
                    border_color = (100, 255, 100, 180)
                elif tile_value == TILE_WALL:
                    highlight_color = (255, 100, 100, 60)  # Red for walls
                    border_color = (255, 100, 100, 180)
                elif tile_value == TILE_SOLID:
                    highlight_color = (255, 200, 100, 60)  # Orange for solid tiles
                    border_color = (255, 200, 100, 180)
                else:
                    highlight_color = (255, 255, 255, 60)  # White for unknown
                    border_color = (255, 255, 255, 180)

                # Override with terrain-specific colors if terrain data exists
                terrain_grid = getattr(self.level, "terrain_grid", None)
                if terrain_grid:
                    if 0 <= grid_y < len(terrain_grid) and 0 <= grid_x < len(terrain_grid[0]):
                        terrain_id = terrain_grid[grid_y][grid_x]

                        # Set colors based on terrain type
                        if "water" in terrain_id:
                            highlight_color = (100, 100, 255, 60)  # Blue for water
                            border_color = (100, 100, 255, 180)
                        elif "floor" in terrain_id:
                            if "sticky" in terrain_id:
                                highlight_color = (255, 200, 100, 60)  # Orange for sticky floors
                                border_color = (255, 200, 100, 180)
                            elif "icy" in terrain_id:
                                highlight_color = (200, 200, 255, 60)  # Light blue for icy floors
                                border_color = (200, 200, 255, 180)
                            elif "fire" in terrain_id:
                                highlight_color = (255, 150, 50, 60)  # Orange-red for fire floors
                                border_color = (255, 150, 50, 180)
                            else:
                                highlight_color = (200, 200, 200, 60)  # Gray for normal floors
                                border_color = (200, 200, 200, 180)

        pygame.draw.rect(overlay, highlight_color, highlight_rect)
        pygame.draw.rect(overlay, border_color, highlight_rect, width=2)

        # Draw crosshair at center of tile
        crosshair_x = grid_screen_x + tile_screen_size // 2
        crosshair_y = grid_screen_y + tile_screen_size // 2
        crosshair_size = max(8, int(tile_screen_size * 0.3))
        pygame.draw.line(overlay, (255, 255, 100, 200),
                        (crosshair_x - crosshair_size, crosshair_y),
                        (crosshair_x + crosshair_size, crosshair_y), 2)
        pygame.draw.line(overlay, (255, 255, 100, 200),
                        (crosshair_x, crosshair_y - crosshair_size),
                        (crosshair_x, crosshair_y + crosshair_size), 2)

        # Prepare info text lines
        info_lines = [
            f"Grid: ({grid_x}, {grid_y})",
            f"World: ({world_x}, {world_y})",
            # Only show raw grid value when the current level exposes a debug grid
            "Grid Value: N/A",
            f"Collision: {collision_type}",
            f"Terrain: {terrain_type}",
            f"Terrain ID: {terrain_id}"
        ]

        # Add area information if available
        areas = getattr(self.level, "areas", None)
        if areas and hasattr(areas, "areas_at"):
            areas_here = areas.areas_at(grid_x, grid_y)
            if areas_here:
                area_names = [str(a.type) for a in areas_here]
                info_lines.append(f"Area: {', '.join(area_names)}")

        # Calculate distance from player
        player_grid_x = self.player.rect.centerx // TILE
        player_grid_y = self.player.rect.centery // TILE
        distance = ((grid_x - player_grid_x) ** 2 + (grid_y - player_grid_y) ** 2) ** 0.5
        info_lines.append(f"Distance: {distance:.1f}")

        # Draw info panel near cursor
        text_x = mouse_screen_pos[0] + 20
        text_y = mouse_screen_pos[1] - 40

        # Adjust position if panel would go off screen
        panel_width = 200
        panel_height = len(info_lines) * 18 + 10
        if text_x + panel_width > WIDTH:
            text_x = mouse_screen_pos[0] - panel_width - 20
        if text_y < 0:
            text_y = mouse_screen_pos[1] + 20
        if text_y + panel_height > HEIGHT:
            text_y = HEIGHT - panel_height - 10

        # Draw background panel
        panel_rect = pygame.Rect(text_x - 5, text_y - 5, panel_width, panel_height)
        pygame.draw.rect(overlay, (20, 20, 30, 220), panel_rect, border_radius=5)
        pygame.draw.rect(overlay, (255, 255, 100, 180), panel_rect, width=1, border_radius=5)

        # Draw text lines
        for i, line in enumerate(info_lines):
            color = (255, 255, 255) if i < 3 else (200, 200, 255)
            draw_text(overlay, line, (text_x, text_y + i * 18), color, size=14)

        # Apply overlay
        self.screen.blit(overlay, (0, 0))

    def draw(self):
        self.screen.fill(BG)
        self.level.draw(self.screen, self.camera)
        for e in self.enemies:
            e.draw(self.screen, self.camera, show_los=self.debug_enemy_rays, show_nametags=self.debug_enemy_nametags)
        for hb in hitboxes:
            hb.draw(self.screen, self.camera)
        self.player.draw(self.screen, self.camera)
        for dn in floating:
            dn.draw(self.screen, self.camera, self.font_small)

        # Optional debug overlay for areas
        self._draw_area_overlay()

        # Optional grid position overlay
        self._draw_grid_position_overlay()

        # HUD
        x, y = 16, 16
        for i in range(self.player.max_hp):
            c = (80,200,120) if i < self.player.hp else (60,80,60)
            pygame.draw.rect(self.screen, c, pygame.Rect(x+i*18, y, 16, 10), border_radius=3)
        y += 16
        # Dash cooldown bar (cyan)
        if self.player.dash_cd:
            pct = 1 - (self.player.dash_cd / 24)
            pygame.draw.rect(self.screen, (80,80,80), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(self.screen, CYAN, pygame.Rect(x, y, int(120*pct), 6), border_radius=3)
            y += 12  # Add space for next bar
        
        # Wall jump cooldown bar (orange) - positioned at bottom of other bars
        if self.player.wall_jump_cooldown > 0:
            pct = 1 - (self.player.wall_jump_cooldown / WALL_JUMP_COOLDOWN)  # Use config value
            pygame.draw.rect(self.screen, (80,80,80), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(self.screen, (255, 165, 0), pygame.Rect(x, y, int(120*pct), 6), border_radius=3)  # Orange color
        # stamina bar (if player has stamina)
        y += 12
        if hasattr(self.player, 'stamina') and hasattr(self.player, 'max_stamina'):
            spct = max(0.0, min(1.0, self.player.stamina / max(1e-6, self.player.max_stamina)))
            pygame.draw.rect(self.screen, (60,60,60), pygame.Rect(x, y, 120, 6), border_radius=3)
            stamina_col = (120, 230, 160) if getattr(self.player, 'stamina_boost_timer', 0) > 0 else (200,180,60)
            pygame.draw.rect(self.screen, stamina_col, pygame.Rect(x, y, int(120*spct), 6), border_radius=3)
            y += 12
        # mana bar
        if hasattr(self.player, 'mana') and hasattr(self.player, 'max_mana'):
            mpct = max(0.0, min(1.0, self.player.mana / max(1e-6, self.player.max_mana)))
            pygame.draw.rect(self.screen, (60,60,60), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(self.screen, CYAN, pygame.Rect(x, y, int(120*mpct), 6), border_radius=3)
            y += 12

        # show ranger charge bar when charging
        if getattr(self.player, 'cls', '') == 'Ranger' and getattr(self.player, 'charging', False):
            pct = max(0.0, min(1.0, self.player.charge_time / max(1, self.player.charge_threshold)))
            pygame.draw.rect(self.screen, (60,60,60), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(self.screen, (200,180,60), pygame.Rect(x, y, int(120*pct), 6), border_radius=3)
            # show '!' when fully charged
            if pct >= 1.0:
                draw_text(self.screen, "!", (x + 124, y-6), (255,80,80), size=18, bold=True)
            y += 12

        # show room info on HUD (static rooms only)
        draw_text(self.screen, f"Room {self.level_index+1}/{ROOM_COUNT}", (WIDTH-220, 8), WHITE, size=16)

        # selected class
        draw_text(self.screen, f"Class: {getattr(self.player, 'cls', 'Unknown')}", (WIDTH-220, 28), (200,200,200), size=16)

        # Static level label (no procedural progression metadata)
        draw_text(self.screen, f"Level {self.level_index + 1}", (16, 56), (220, 200, 160), size=16)

        # Skill bar (MOBA-style): show 1/2/3 cooldowns and active highlights
        sbx, sby = 16, HEIGHT - 80
        slot_w, slot_h = 46, 46
        # Names per class
        if self.player.cls == 'Knight':
            names = ['Shield', 'Power', 'Charge']
            actives = [self.player.shield_timer>0, self.player.power_timer>0, False]
        elif self.player.cls == 'Ranger':
            names = ['Triple', 'Sniper', 'Speed']
            actives = [self.player.triple_timer>0, self.player.sniper_ready, self.player.speed_timer>0]
        else:
            names = ['Fireball', 'Cold', 'Missile']
            actives = [False, False, False]
        cds = [self.player.skill_cd1, self.player.skill_cd2, self.player.skill_cd3]
        maxcds = [max(1,self.player.skill_cd1_max), max(1,self.player.skill_cd2_max), max(1,self.player.skill_cd3_max)]
        for i in range(3):
            rx = sbx + i*(slot_w+8)
            ry = sby
            # slot background
            pygame.draw.rect(self.screen, (40,40,50), pygame.Rect(rx, ry, slot_w, slot_h), border_radius=6)
            # active border glow
            if actives[i]:
                pygame.draw.rect(self.screen, (120,210,220), pygame.Rect(rx-2, ry-2, slot_w+4, slot_h+4), width=2, border_radius=8)
            # cooldown overlay
            if cds[i] > 0:
                pct = cds[i] / maxcds[i]
                h = int(slot_h * pct)
                overlay = pygame.Rect(rx, ry + (slot_h - h), slot_w, h)
                pygame.draw.rect(self.screen, (0,0,0,120), overlay)
                # remaining seconds text
                secs = max(0.0, cds[i]/FPS)
                draw_text(self.screen, f"{secs:.0f}", (rx + 12, ry + 12), (220,220,220), size=18, bold=True)
            # key label and name
            draw_text(self.screen, str(i+1), (rx+2, ry+2), (200,200,200), size=14)
            draw_text(self.screen, names[i], (rx+2, ry+slot_h-14), (180,180,200), size=12)

        self.inventory.draw_consumable_hotbar()

        if getattr(self.player, 'speed_potion_timer', 0) > 0:
            secs = max(0, int(self.player.speed_potion_timer / FPS))
            draw_text(self.screen, f"Haste {secs}s", (WIDTH-180, HEIGHT-120), (255,220,140), size=16, bold=True)
        if getattr(self.player, 'jump_boost_timer', 0) > 0:
            secs = max(0, int(self.player.jump_boost_timer / FPS))
            draw_text(self.screen, f"Skybound {secs}s", (WIDTH-180, HEIGHT-140), (200,220,255), size=16, bold=True)
        if getattr(self.player, 'stamina_boost_timer', 0) > 0:
            secs = max(0, int(self.player.stamina_boost_timer / FPS))
            draw_text(self.screen, f"Cavern Brew {secs}s", (WIDTH-180, HEIGHT-160), (150,255,180), size=16, bold=True)
        
        # Display special item status effects
        if getattr(self.player, 'lucky_charm_timer', 0) > 0:
            secs = max(0, int(self.player.lucky_charm_timer / FPS))
            draw_text(self.screen, f"Lucky! {secs}s", (WIDTH-180, HEIGHT-180), (255, 215, 0), size=16, bold=True)
        
        if getattr(self.player, 'phoenix_feather_active', False):
            draw_text(self.screen, "Phoenix Blessing", (WIDTH-180, HEIGHT-200), (255, 150, 50), size=16, bold=True)
        
        # Check for TimeCrystal effect on enemies
        time_crystal_active = any(getattr(e, 'slow_remaining', 0) > 0 for e in self.enemies if getattr(e, 'alive', False))
        if time_crystal_active:
            draw_text(self.screen, "Time Distorted", (WIDTH-180, HEIGHT-220), (150, 150, 255), size=16, bold=True)

        draw_text(self.screen,
                   "Move A/D | Jump Space/K | Dash Shift/J | Attack L/Mouse | Up/Down+Attack for Up/Down slash (Down=Pogo) | Shop F6 | God F1 | No-clip: Double-space in god mode (WASD to float)",
                   (12, HEIGHT-28), (180,180,200), size=16)
        # Money display moved to be under class
        draw_text(self.screen, f"Coins: {self.player.money}", (WIDTH-220, 48), (255, 215, 0), bold=True)

        # God + No-clip + Area labels
        hud_x = WIDTH - 64
        if getattr(self.player, 'no_clip', False):
            draw_text(self.screen, "NO-CLIP", (hud_x, 8), (200,100,255), bold=True)
            hud_x -= 8  # slight shift for area tag
            # Show floating mode if active
            if getattr(self.player, 'floating_mode', False):
                draw_text(self.screen, "FLOAT", (hud_x, 8), (100,255,200), bold=True)
                hud_x -= 8

        if getattr(self.player, 'god', False):
            draw_text(self.screen, "GOD", (hud_x, 8), (255,200,80), bold=True)
            hud_x -= 8  # slight shift for area tag

        if self.debug_show_area_overlay:
            area_label = self._get_player_area_labels()
            if area_label:
                draw_text(self.screen, f"AREA: {area_label}", (WIDTH-260, 8), (160, 220, 255), size=12)
            else:
                draw_text(self.screen, "AREA: NONE", (WIDTH-260, 8), (120, 160, 200), size=12)
        # Boss room hint: lock door until boss defeated
        if getattr(self.level, 'is_boss_room', False) and any(getattr(e, 'alive', False) for e in self.enemies):
            draw_text(self.screen, "Defeat the boss to open the door", (WIDTH//2 - 160, 8), (255,120,120), size=16)

        if self.inventory.inventory_open:
            self.inventory.draw_inventory_overlay()
        
        # Draw shop if open
        if self.shop.shop_open:
            self.shop.draw(self.screen)



    def run(self):
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    if ev.button == 1:  # Left click
                        if self.inventory.inventory_open:
                            self.inventory._handle_inventory_click(ev.pos)
                        elif self.shop.shop_open:
                            self.shop.handle_mouse_click(ev.pos)
                    continue
                elif ev.type == pygame.KEYDOWN:
                    # Handle shop input first when shop is open
                    if self.shop.shop_open:
                        self.shop.handle_event(ev)
                        continue
                    if ev.key == pygame.K_i:
                        if not self.shop.shop_open:
                            self.inventory.inventory_open = not self.inventory.inventory_open
                            if not self.inventory.inventory_open:
                                self.inventory._clear_inventory_selection()
                        continue
                    if ev.key == pygame.K_F5:
                        self.inventory.inventory_open = False
                        self.inventory._clear_inventory_selection()
                        self.debug_menu()
                        continue
                    if self.inventory.inventory_open:
                        if ev.key == pygame.K_ESCAPE:
                            self.inventory.inventory_open = False
                            self.inventory._clear_inventory_selection()
                        continue
                    used_consumable = False
                    for idx, keycode in enumerate(self.inventory.consumable_hotkeys):
                        if ev.key == keycode:
                            self.inventory.consume_slot(idx)
                            used_consumable = True
                            break
                    if used_consumable:
                        continue
                    if ev.key == pygame.K_ESCAPE:
                        # Check if shop is open first, then close it instead of opening pause menu
                        if self.shop.shop_open:
                            self.shop.close_shop()
                        else:
                            # open pause menu instead of quitting
                            self.menu.pause_menu()
                    # Developer cheats / debug tools
                    elif ev.key == pygame.K_F1:
                        # toggle god mode (invincibility only)
                        self.player.god = not getattr(self.player, 'god', False)
                        floating.append(DamageNumber(
                            self.player.rect.centerx,
                            self.player.rect.top - 12,
                            f"God Mode {'ON' if self.player.god else 'OFF'}!",
                            (255, 200, 80) if self.player.god else (200, 200, 200)
                        ))
                    elif ev.key == pygame.K_F2:
                        # refill consumables
                        self.inventory.add_all_consumables()
                    elif ev.key == pygame.K_F3:
                        # toggle enemy vision rays
                        self.debug_enemy_rays = not self.debug_enemy_rays
                    elif ev.key == pygame.K_F4:
                        # toggle enemy nametags
                        self.debug_enemy_nametags = not self.debug_enemy_nametags
                    elif ev.key == pygame.K_F5:
                        # open debugger menu
                        self.debug_menu()
                    elif ev.key == pygame.K_F6:
                        # Toggle shop
                        if not self.inventory.inventory_open:
                            if self.shop.shop_open:
                                self.shop.close_shop()
                            else:
                                self.shop.open_shop()
                        continue
                    elif ev.key == pygame.K_F7:
                        # Add 1000 money (keep original cheat; dedicated test map will be wired separately)
                        self.player.money += 1000
                        floating.append(DamageNumber(
                            self.player.rect.centerx,
                            self.player.rect.top - 12,
                            "+1000 coins!",
                            (255, 215, 0)
                        ))
                        continue
                    # Teleport / navigation cheats:
                    elif ev.key == pygame.K_F8:
                        # Reserved: previously procedural terrain test; now no-op
                        continue         
                    elif ev.key == pygame.K_F11:
                        # Reserved: previously procedural regen; now no-op
                        continue
                    elif ev.key == pygame.K_F12:
                        # Teleport to room 6 (boss room) for debug
                        self.goto_room(5)

            if not self.inventory.inventory_open and not self.shop.shop_open:
                self.update()
            
            self.draw()
            pygame.display.flip()


    def debug_menu(self):
        self.inventory.inventory_open = False
        self.inventory._clear_inventory_selection()
        options = [
            {'label': "God Mode (F1)", 'type': 'toggle',
             'getter': lambda: getattr(self.player, 'god', False),
             'setter': lambda v: setattr(self.player, 'god', v)},
            {'label': "No-clip Mode (F10)", 'type': 'toggle',
             'getter': lambda: getattr(self.player, 'no_clip', False),
             'setter': lambda v: setattr(self.player, 'no_clip', v)},
            {'label': "Refill Consumables (F2)", 'type': 'action',
             'action': self.inventory.add_all_consumables},
            {'label': "Enemy Vision Rays (F3)", 'type': 'toggle',
             'getter': lambda: self.debug_enemy_rays,
             'setter': lambda v: setattr(self, 'debug_enemy_rays', v)},
            {'label': "Enemy Nametags (F4)", 'type': 'toggle',
             'getter': lambda: self.debug_enemy_nametags,
             'setter': lambda v: setattr(self, 'debug_enemy_nametags', v)},
            {'label': "Infinite Mana", 'type': 'toggle',
             'getter': lambda: self.cheat_infinite_mana,
             'setter': lambda v: setattr(self, 'cheat_infinite_mana', v)},
            {'label': "Zero Cooldown", 'type': 'toggle',
             'getter': lambda: self.cheat_zero_cooldown,
             'setter': lambda v: setattr(self, 'cheat_zero_cooldown', v)},
            {'label': "Teleport to Level...", 'type': 'action',
             'action': self.debug_teleport_menu},
            {'label': "Refill Consumables", 'type': 'action',
             'action': self.inventory.add_all_consumables},
            {'label': "Give Items...", 'type': 'action',
             'action': self.debug_item_menu},
            {'label': "Close", 'type': 'action',
             'action': None, 'close': True},
        ]
        self._run_debug_option_menu(options, title="Debugger")

    def debug_item_menu(self):
        self.inventory.inventory_open = False
        self.inventory._clear_inventory_selection()
        options = []
        for key, item in self.inventory.consumable_catalog.items():
            options.append({
                'label': f"Add {item.name}",
                'type': 'action',
                'action': (lambda k=key: self.inventory.add_consumable(k, 1))
            })
        for key, item in self.inventory.armament_catalog.items():
            options.append({
                'label': f"Equip {item.name}",
                'type': 'action',
                'action': (lambda k=key: self.inventory._force_equip_armament(k))
            })
        options.append({'label': "Back", 'type': 'action', 'action': None, 'close': True})
        self._run_debug_option_menu(options, title="Item Spawner")

    def _draw_debug_overlay(self, options, selected, title="Debugger", offset=0, visible=9):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(WIDTH//2 - 220, HEIGHT//2 - 200, 440, 360)
        pygame.draw.rect(self.screen, (32, 30, 42), panel, border_radius=12)
        pygame.draw.rect(self.screen, (210, 200, 170), panel, width=2, border_radius=12)
        draw_text(self.screen, title, (panel.x + 24, panel.y + 16), (240,220,190), size=28, bold=True)
        info = "Arrows = Navigate | Enter = Toggle | Esc/F5 = Close"
        draw_text(self.screen, info, (panel.x + 24, panel.bottom - 32), (180,180,200), size=16)
        line_h = 34
        visible = max(1, visible)
        subset = options[offset:offset+visible]
        for i, opt in enumerate(subset):
            row = pygame.Rect(panel.x + 24, panel.y + 64 + i * line_h, panel.width - 48, 30)
            bg_col = (70, 70, 90) if (offset + i) == selected else (50, 50, 68)
            pygame.draw.rect(self.screen, bg_col, row, border_radius=8)
            text = opt['label']
            if opt['type'] == 'toggle':
                text = f"{text}: {'ON' if opt['getter']() else 'OFF'}"
            elif opt['type'] == 'info':
                text = f"{text}: {opt['getter']()}"
            elif opt['type'] == 'action' and not opt.get('close'):
                text = f"{text}"
            draw_text(self.screen, text, (row.x + 12, row.y + 8), (220,220,230), size=18)

    def _run_debug_option_menu(self, options, title="Debugger"):
        idx = 0
        offset = 0
        visible = min(9, len(options)) or 1
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_F5):
                        return
                    elif ev.key == pygame.K_UP:
                        idx = (idx - 1) % len(options)
                    elif ev.key == pygame.K_DOWN:
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        opt = options[idx]
                        if opt['type'] == 'toggle':
                            opt['setter'](not opt['getter']())
                        elif opt['type'] == 'action' and opt['action']:
                            opt['action']()
                        if opt.get('close'):
                            return
            if idx < offset:
                offset = idx
            elif idx >= offset + visible:
                offset = idx - visible + 1
            self.draw()
            self._draw_debug_overlay(options, idx, title=title, offset=offset, visible=visible)
            pygame.display.flip()

    def debug_teleport_menu(self):
        """
        Teleport debug menu for static rooms.
        Wraps using ROOM_COUNT.
        """
        idx = self.level_index
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_F5):
                        return
                    elif ev.key == pygame.K_LEFT:
                        idx = (idx - 1) % ROOM_COUNT
                    elif ev.key == pygame.K_RIGHT:
                        idx = (idx + 1) % ROOM_COUNT
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        self.goto_room(idx)
                        return
            self.draw()
            self._draw_level_select_overlay(idx)
            pygame.display.flip()

    def _draw_level_select_overlay(self, idx):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 200)
        pygame.draw.rect(self.screen, (30, 28, 42), panel, border_radius=12)
        pygame.draw.rect(self.screen, (210, 200, 170), panel, width=2, border_radius=12)
        draw_text(self.screen, "Teleport to Level", (panel.x + 24, panel.y + 16), (240,220,190), size=26, bold=True)
        info = "Left/Right choose, Enter confirm, Esc to cancel"
        draw_text(self.screen, info, (panel.x + 24, panel.bottom - 36), (180,180,200), size=16)

        draw_text(self.screen, f"Room {idx+1}/{ROOM_COUNT}", (panel.centerx - 80, panel.centery - 10),
                  (220,220,240), size=32, bold=True)


if __name__ == '__main__':
    Game().run()
