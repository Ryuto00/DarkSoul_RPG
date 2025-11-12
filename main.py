import sys
import random

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
    TILE,
)
from src.core.utils import draw_text, get_font
from src.systems.camera import Camera
from src.level.level import Level, ROOM_COUNT
from src.entities.entities import Player, hitboxes, floating, DamageNumber
from src.systems.inventory import Inventory
from src.systems.menu import Menu
from src.systems.shop import Shop
from typing import Optional
from src.level.procedural_generator import GenerationConfig, MovementAttributes
from src.level.traversal_verification import verify_traversable
from src.level.room_data import RoomData
from src.level.level_data import LevelData, LevelGenerationConfig
from src.level.graph_generator import generate_complete_level




class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Haridd")
        self.clock = pygame.time.Clock()
        self.font_small = get_font(18)
        self.font_big = get_font(32, bold=True)
        self.camera = Camera()

        # NEW: Procedural generation config
        self.use_procedural = True  # Set to False to use static rooms
        
        self.movement_attrs = MovementAttributes(
            max_jump_height=4,  # Adjust based on your player jump
            max_jump_distance=6,
            player_width=1,
            player_height=2
        )
        
        self.room_gen_config = GenerationConfig(
            min_room_size=40,  # Adjust to match your tile size
            max_room_size=60,
            min_corridor_width=3,
            platform_placement_attempts=15,
            movement_attributes=self.movement_attrs, # CRITICAL: Pass here
            seed=None  # None = random, or set int for reproducible levels
        )
        
        self.level_gen_config = LevelGenerationConfig(
            num_rooms=5,  # 5 rooms per level
            layout_type="branching",  # or "linear", "looping"
            branch_probability=0.3
        )

        # Seed management for procedural generation
        self.user_seed: Optional[int] = None # Stores user-set seed, None for random
        self.current_active_seed: Optional[int] = None # The seed actually used for current level

        # Track current level
        self.current_level_data: Optional[LevelData] = None
        self.current_level_number = 1
        
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
        self.debug_enemy_nametags = False # Default to False

        # Debug visualization toggles
        self.debug_tile_inspector = False
        self.debug_collision_boxes = False
        # Collision log overlay is now toggled via F9; default OFF
        self.debug_collision_log = False
        self.collision_events = []  # recent collision events for logger

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

        # Level state for static rooms
        self.level_index = 0
        
        # Run title; legacy flow may still configure basic options
        try:
            self.menu.title_screen()
        except Exception as e:
            print(f"[ERROR] Exception in title_screen: {e}")
            import traceback
            traceback.print_exc()
        
        # Initialize first level
        try:
            # For static mode (PCG OFF), use 0-based index to start at Room 1 (ROOMS[0])
            # For procedural mode (PCG ON), use 1-based level_number
            initial_level = 0 if not self.use_procedural else 1
            self._load_level(level_number=initial_level, initial=True)
        except Exception as e:
            print(f"[ERROR] Exception in _load_level: {e}")
            import traceback
            traceback.print_exc()
            return

        # create player with chosen class
        sx, sy = self.level.spawn
        self.player = Player(sx, sy, cls=self.selected_class)
        self.enemies = self.level.enemies

        # Inventory & shop
        self.inventory = Inventory(self)
        self.inventory._refresh_inventory_defaults()
        self.shop = Shop(self)

    def toggle_procedural_generation(self):
        """Toggles procedural generation on/off."""
        print(f"[DEBUG] Toggling PCG: {self.use_procedural} -> {not self.use_procedural}")
        print(f"[DEBUG] Current state: level_index={self.level_index}, current_level_number={self.current_level_number}")
        self.use_procedural = not self.use_procedural
        print(f"[DEBUG] After toggle: use_procedural={self.use_procedural}")

    def set_custom_seed(self, seed: int):
        """Sets a custom seed for procedural generation."""
        self.user_seed = seed

    def generate_random_seed(self):
        """Clears the custom seed, allowing random generation."""
        self.user_seed = None

    def get_current_seed(self) -> Optional[int]:
        """Returns the currently active seed (user-set or the one used for current level)."""
        return self.user_seed if self.user_seed is not None else self.current_active_seed

    # === Level Management (static rooms only) ===

    def restart_run(self):
        """
        Restart from the current level (preserving level progress).
        """
        print(f"[DEBUG] restart_run called!")
        print(f"[DEBUG] Before restart: level_index={self.level_index}, current_level_number={self.current_level_number}, use_procedural={self.use_procedural}")
        
        # FIXED: Preserve current level instead of resetting to level 0
        if self.use_procedural:
            # PCG mode: restart from current level number (1-based)
            level_to_restart = self.current_level_number
        else:
            # Legacy mode: restart from current level index (0-based)
            level_to_restart = self.level_index
        
        print(f"[DEBUG] Restarting from level: {level_to_restart}")

        # Load the current level
        self._load_level(level_to_restart, initial=True)

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
        
        print(f"[DEBUG] After restart: level_index={self.level_index}, current_level_number={self.current_level_number}")

    def _load_level(self, level_number: Optional[int] = None, room_id: Optional[str] = None, initial: bool = False):
        """
        Load a level - either generate new procedural level or load specific room.
        
        Args:
            level_number: Which level to load (generates new if different from current)
            room_id: Which room in current level to load (for room transitions)
            initial: Is this the first load?
        """
        print(f"[DEBUG] _load_level called: level_number={level_number}, room_id={room_id}, initial={initial}, use_procedural={self.use_procedural}")
        print(f"[DEBUG] Current state: level_index={self.level_index}, current_level_number={self.current_level_number}")
        
        if not self.use_procedural:
            # LEGACY: Use old static room system
            self._load_static_level(level_number or 0, initial)
            return
        
        # PROCEDURAL SYSTEM
        
        # Generate new level if needed (first load or new level number requested)
        if self.current_level_data is None or (level_number is not None and level_number != self.current_level_number):
            
            # Determine seed for reproducible levels
            if self.user_seed is not None:
                level_seed = self.user_seed
            else:
                # If no user seed, generate a new random one for this level
                # or use a deterministic one based on level_number if that's desired behavior
                import random
                level_seed = random.randint(0, 1000000) # Generate a truly random seed
            
            self.current_active_seed = level_seed # Store the seed actually used
            
            # Generate complete multi-room level
            self.current_level_data = generate_complete_level(
                self.room_gen_config,
                self.level_gen_config,
                self.movement_attrs,
                seed=level_seed
            )
            
            self.current_level_number = level_number
            
            # Start at first room
            room_id = room_id or self.current_level_data.start_room_id
            
        
        # Load specific room
        if room_id is None:
            room_id = self.current_level_data.start_room_id if self.current_level_data else "room_0"
        
        room_data = self.current_level_data.get_room(room_id) if self.current_level_data else None
        
        if room_data is None:
            print(f"[ERROR] Room {room_id} not found in level!")
            return
        
        try:
            # Create Level from RoomData
            lvl = Level(
                room_data=room_data,
                level_data=self.current_level_data,
                room_id=room_id
            )
        except Exception as e:
            print(f"[CRITICAL ERROR] Failed to load room {room_id}: {e}")
            import traceback
            traceback.print_exc()
            return
        
        self.level = lvl
        self.enemies = lvl.enemies
        
        if not initial:
            hitboxes.clear()
            floating.clear()

    def _load_static_level(self, index: int, initial: bool = False):
        """Legacy static room loading (for backwards compatibility)."""
        print(f"[DEBUG] _load_static_level called: index={index}, initial={initial}")
        self.level_index = index
        room_index = index % ROOM_COUNT
        
        print(f"[DEBUG] Loading static room: room_index={room_index} ( ROOMS[{room_index}] = Room {room_index + 1} )")
        
        try:
            # Use room_index (not index) to pass the intended room number to Level constructor
            lvl = Level(room_index)
        except Exception as e:
            print(f"[CRITICAL ERROR] Failed to load static room {room_index}: {e}")
            return
        
        self.level = lvl
        self.enemies = lvl.enemies
        
        if not initial:
            hitboxes.clear()
            floating.clear()
            
        print(f"[DEBUG] Static level loaded: level_index={self.level_index}")

    def switch_room(self, delta: Optional[int] = None, target_room_id: Optional[str] = None):
        """
        Switch to next room in procedural level or next level.
        
        Args:
            delta: +1 for next room (legacy compatibility)
            target_room_id: Specific room to switch to
        """
        if not self.use_procedural:
            # Legacy static room switching
            new_index = max(0, self.level_index + (delta or 1))
            self._load_level(new_index)
            sx, sy = self.level.spawn
            self.player.rect.topleft = (sx, sy)
            self.enemies = getattr(self.level, "enemies", [])
            self.shop.open_shop()
            return
        
        # PROCEDURAL SYSTEM
        
        current_room_id = getattr(self.level, 'current_room_id', 'room_0')
        
        # Determine next room
        if target_room_id:
            next_room_id = target_room_id
        else:
            # Get next room from graph
            if self.current_level_data and self.current_level_data.internal_graph:
                neighbors = self.current_level_data.internal_graph.get(current_room_id, [])
                
                if not neighbors:
                    # No more rooms - reached goal!
                    
                    # Generate next level
                    self._load_level(level_number=self.current_level_number + 1)
                    
                    # Reset player position
                    sx, sy = self.level.spawn
                    self.player.rect.topleft = (sx, sy)
                    self.enemies = getattr(self.level, "enemies", [])
                    
                    # Open shop between levels
                    self.shop.open_shop()
                    return
                
                # If multiple neighbors, use first (later: let player choose)
                next_room_id = neighbors[0]
            else:
                next_room_id = current_room_id
        
        # Load next room
        self._load_level(room_id=next_room_id)
        
        # Reset player position
        sx, sy = self.level.spawn
        self.player.rect.topleft = (sx, sy)
        self.enemies = getattr(self.level, "enemies", [])

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

    def update(self, dt=1.0/FPS):
        self.player.input(self.level, self.camera)
        self.player.physics(self.level, dt)
        self.inventory.recalculate_player_stats()

        # If player died, show restart menu
        if not self.player.alive:
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
                            self.player.combat.take_damage(hb.damage, (int(kx*3), -6))
                        # consume the AOE
                        hb.alive = False
                # direct projectile/contact against player
                elif hb.rect.colliderect(self.player.rect) and not getattr(hb, 'visual_only', False):
                    if getattr(hb, 'tag', None) == 'stun':
                        self.player.stunned = max(self.player.stunned, int(0.8 * FPS))
                    if getattr(hb, 'damage', 0) > 0:
                        kx, ky = hb.dir_vec if getattr(hb, 'dir_vec', None) else (0, -1)
                        self.player.combat.take_damage(hb.damage, (int(kx*3), -6))
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

        self.camera.update(self.player.rect, dt)

    def _draw_area_overlay(self):
        """
        Debug: draw logical areas and terrain test info on top of current map.
        Uses self.level.areas if present.
        """
        # Disabled: area system not fully implemented, causes import errors
        pass

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
                grid_value = level_grid[grid_y][grid_x]
                # Get collision type from grid (0=air, 1=wall)
                from config import TILE_AIR, TILE_WALL
                if grid_value == TILE_AIR:
                    collision_type = "Air"
                elif grid_value == TILE_WALL:
                    collision_type = "Wall"
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
        highlight_rect = pygame.Rect(grid_screen_x, grid_screen_y, tile_screen_size, tile_screen_size)

        # Default colors if no specific conditions are met
        highlight_color = (255, 255, 255, 60)  # White with transparency
        border_color = (255, 255, 255, 180)    # White with transparency

        # Determine highlight color based on tile type and terrain
        level_grid = getattr(self.level, "grid", None)
        if level_grid:
            if 0 <= grid_y < len(level_grid) and 0 <= grid_x < len(level_grid[0]):
                from config import TILE_AIR, TILE_WALL
                tile_value = level_grid[grid_y][grid_x]

                # Set colors based on tile type
                if tile_value == TILE_AIR:
                    highlight_color = (200, 200, 200, 30)  # Light gray for air
                    border_color = (200, 200, 200, 100)
                elif tile_value == TILE_WALL:
                    highlight_color = (255, 100, 100, 60)  # Red for walls
                    border_color = (255, 100, 100, 180)
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

    def _draw_tile_inspector(self):
        """
        Live inspector for tile under mouse cursor.
        Safe-guarded, read-only; only active when explicitly enabled.
        """
        import pygame
        from config import TILE, WIDTH, HEIGHT
        from src.tiles.tile_types import TileType
        from src.tiles.tile_registry import tile_registry

        try:
            # Preconditions
            level = getattr(self, "level", None)
            if level is None:
                return
            grid = getattr(level, "grid", None)
            if not grid:
                # No grid present
                mx, my = pygame.mouse.get_pos()
                msg = "No tile grid"
                font = self.font_small
                surf = font.render(msg, True, (255, 180, 180))
                w, h = surf.get_size()
                bx = min(max(mx + 12, 0), max(0, WIDTH - w - 8))
                by = min(max(my - h - 12, 0), max(0, HEIGHT - h - 8))
                panel = pygame.Surface((w + 6, h + 6), pygame.SRCALPHA)
                panel.fill((20, 0, 0, 200))
                self.screen.blit(panel, (bx, by))
                self.screen.blit(surf, (bx + 3, by + 3))
                return

            # Block when shop/inventory overlays are open (no interaction)
            if getattr(self.shop, "shop_open", False):
                return
            if getattr(self.inventory, "inventory_open", False):
                return

            # Optional: require god mode for safety
            # If enforced, uncomment next two lines.
            # if not getattr(self.player, "god", False):
            #     return

            mx, my = pygame.mouse.get_pos()
            # Convert screen -> world
            world_x = (mx / self.camera.zoom) + self.camera.x
            world_y = (my / self.camera.zoom) + self.camera.y
            grid_x = int(world_x // TILE)
            grid_y = int(world_y // TILE)

            rows = len(grid)
            cols = len(grid[0]) if rows > 0 else 0

            # Helper: draw small info panel with clamping
            def draw_panel(lines, title_color=(255, 255, 255)):
                font = self.font_small
                pad_x = 8
                pad_y = 6
                line_h = font.get_linesize()
                max_w = 0
                for line in lines:
                    w, _ = font.render(line, True, (255, 255, 255)).get_size()
                    max_w = max(max_w, w)
                panel_w = max_w + pad_x * 2
                panel_h = line_h * len(lines) + pad_y * 2

                text_x = mx + 20
                text_y = my - 40
                # Clamp horizontally
                if text_x + panel_w > WIDTH:
                    text_x = mx - panel_w - 20
                if text_x < 0:
                    text_x = 4
                # Clamp vertically
                if text_y < 0:
                    text_y = my + 20
                if text_y + panel_h > HEIGHT:
                    text_y = max(4, HEIGHT - panel_h - 4)

                panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
                panel.fill((10, 10, 18, 210))
                pygame.draw.rect(panel, (200, 200, 240, 255), panel.get_rect(), 1)
                # Blit text
                y = pad_y
                for i, line in enumerate(lines):
                    col = (255, 255, 255)
                    surf = font.render(line, True, col)
                    panel.blit(surf, (pad_x, y))
                    y += line_h
                self.screen.blit(panel, (text_x, text_y))

            # Bounds check
            if grid_y < 0 or grid_y >= rows or grid_x < 0 or grid_x >= cols:
                draw_panel([
                    f"Grid: ({grid_x}, {grid_y})",
                    f"World: ({int(world_x)}, {int(world_y)})",
                    "Out of bounds",
                ])
                return

            tile_value = grid[grid_y][grid_x]

            # Highlight rect for in-bounds tile
            tile_screen_x = (grid_x * TILE - self.camera.x) * self.camera.zoom
            tile_screen_y = (grid_y * TILE - self.camera.y) * self.camera.zoom
            tile_screen_size = TILE * self.camera.zoom
            highlight = pygame.Surface((int(tile_screen_size), int(tile_screen_size)), pygame.SRCALPHA)
            highlight.fill((255, 255, 255, 40))
            self.screen.blit(highlight, (int(tile_screen_x), int(tile_screen_y)))
            pygame.draw.rect(
                self.screen,
                (255, 255, 255),
                pygame.Rect(
                    int(tile_screen_x),
                    int(tile_screen_y),
                    int(tile_screen_size),
                    int(tile_screen_size),
                ),
                1,
            )

            # Empty / no tile
            if tile_value < 0:
                draw_panel([
                    f"Grid: ({grid_x}, {grid_y})",
                    f"World: ({int(world_x)}, {int(world_y)})",
                    "Empty (no tile)",
                ])
                return

            # Resolve TileType & TileData
            try:
                tile_type = TileType(tile_value)
            except ValueError:
                draw_panel([
                    f"Grid: ({grid_x}, {grid_y})",
                    f"World: ({int(world_x)}, {int(world_y)})",
                    f"Unknown tile id={tile_value}",
                ])
                return

            tile_data = tile_registry.get_tile(tile_type)

            if tile_data is None:
                draw_panel([
                    f"Grid: ({grid_x}, {grid_y})",
                    f"World: ({int(world_x)}, {int(world_y)})",
                    f"Unknown tile: ID={tile_value}, type={tile_type.name}, no TileData",
                ])
                return

            # Collect info sections with defensive access
            c = getattr(tile_data, "collision", None)
            p = getattr(tile_data, "physics", None)
            inter = getattr(tile_data, "interaction", None)
            vis = getattr(tile_data, "visual", None)
            lit = getattr(tile_data, "lighting", None)
            aud = getattr(tile_data, "audio", None)

            lines = []
            # Position
            lines.append(f"Grid: ({grid_x}, {grid_y})")
            lines.append(f"World: ({int(world_x)}, {int(world_y)})")
            # Identity
            lines.append(f"Tile: {tile_data.name} ({tile_type.name}, id={tile_type.value})")

            # Collision
            if c:
                lines.append(f"collision_type={getattr(c, 'collision_type', 'unknown')}")
                lines.append(f"can_walk_on={getattr(c, 'can_walk_on', False)} pass_through={getattr(c, 'can_pass_through', False)} climb={getattr(c, 'can_climb', False)}")
                lines.append(f"damage={getattr(c, 'damage_on_contact', 0)} push={getattr(c, 'push_force', 0.0)}")
                lines.append(f"box_off={getattr(c, 'collision_box_offset', (0, 0))} box_size={getattr(c, 'collision_box_size', None)}")

            # Physical
            if p:
                lines.append(f"friction={getattr(p, 'friction', 1.0)} bounce={getattr(p, 'bounciness', 0.0)} move_speed_mul={getattr(p, 'movement_speed_modifier', 1.0)}")
                lines.append(f"sticky={getattr(p, 'is_sticky', False)} slippery={getattr(p, 'is_slippery', False)} density={getattr(p, 'density', 1.0)}")

            # Interaction
            if inter:
                lines.append(
                    f"breakable={getattr(inter, 'breakable', False)} hp={getattr(inter, 'health_points', 0)} "
                    f"climbable={getattr(inter, 'climbable', False)} interact={getattr(inter, 'interactable', False)} "
                    f"collectible={getattr(inter, 'collectible', False)} trigger={getattr(inter, 'is_trigger', False)}"
                )
                lines.append(f"resistance={getattr(inter, 'resistance', 1.0)}")

            # Visual
            if vis:
                base_color = getattr(vis, "base_color", None)
                sprite_path = getattr(vis, "sprite_path", None)
                anim_frames = getattr(vis, "animation_frames", []) or []
                anim_speed = getattr(vis, "animation_speed", 0.0)
                border_radius = getattr(vis, "border_radius", 0)
                render_border = getattr(vis, "render_border", False)
                border_color = getattr(vis, "border_color", None)
                lines.append(f"base_color={base_color}")
                lines.append(f"sprite={sprite_path or 'None'} anim_frames={len(anim_frames)} speed={anim_speed}")
                lines.append(f"border_radius={border_radius} border={render_border} border_color={border_color}")

            # Lighting
            if lit:
                lines.append(
                    f"emits_light={getattr(lit, 'emits_light', False)} "
                    f"color={getattr(lit, 'light_color', None)} radius={getattr(lit, 'light_radius', 0.0)}"
                )
                lines.append(
                    f"blocks_light={getattr(lit, 'blocks_light', False)} "
                    f"transparency={getattr(lit, 'transparency', 1.0)} casts_shadows={getattr(lit, 'casts_shadows', True)} "
                    f"reflection={getattr(lit, 'reflection_intensity', 0.0)}"
                )

            # Audio
            if aud:
                lines.append(
                    f"snd_foot={getattr(aud, 'footstep_sound', None)} "
                    f"snd_contact={getattr(aud, 'contact_sound', None)} "
                    f"snd_break={getattr(aud, 'break_sound', None)} "
                    f"snd_ambient={getattr(aud, 'ambient_sound', None)} "
                    f"vol={getattr(aud, 'sound_volume', 1.0)}"
                )

            # Derived
            try:
                lines.append(
                    f"is_walkable={getattr(tile_data, 'is_walkable', False)} "
                    f"has_collision={getattr(tile_data, 'has_collision', False)} "
                    f"is_destructible={getattr(tile_data, 'is_destructible', False)}"
                )
            except Exception:
                pass

            draw_panel(lines)
        except Exception:
            # Fail-safe: never let inspector crash the game.
            return

    def _draw_collision_boxes(self):
        """
        Debug: draw tile collision boxes for visible region.
        Uses Level.grid and TileRegistry; read-only and fail-safe.
        """
        import pygame
        from config import TILE
        from src.tiles.tile_types import TileType
        from src.tiles.tile_registry import tile_registry

        try:
            level = getattr(self, "level", None)
            if level is None:
                return
            grid = getattr(level, "grid", None)
            if not grid:
                return

            screen_w, screen_h = self.screen.get_size()
            zoom = getattr(self.camera, "zoom", 1.0) or 1.0

            world_left = self.camera.x
            world_top = self.camera.y
            world_right = self.camera.x + screen_w / zoom
            world_bottom = self.camera.y + screen_h / zoom

            rows = len(grid)
            cols = len(grid[0]) if rows > 0 else 0
            if rows == 0 or cols == 0:
                return

            start_tx = max(0, int(world_left // TILE) - 1)
            end_tx = min(cols, int(world_right // TILE) + 2)
            start_ty = max(0, int(world_top // TILE) - 1)
            end_ty = min(rows, int(world_bottom // TILE) + 2)

            for ty in range(start_ty, end_ty):
                row = grid[ty]
                for tx in range(start_tx, end_tx):
                    tile_value = row[tx]
                    if tile_value < 0:
                        continue
                    try:
                        tile_type = TileType(tile_value)
                    except ValueError:
                        continue
                    tile_data = tile_registry.get_tile(tile_type)
                    if not tile_data or not getattr(tile_data, "has_collision", False):
                        continue

                    c = getattr(tile_data, "collision", None)
                    if not c:
                        continue
                    off = getattr(c, "collision_box_offset", (0, 0))
                    size = getattr(c, "collision_box_size", None)
                    if not size:
                        continue
                    off_x, off_y = off
                    width, height = size

                    world_x = tx * TILE + off_x
                    world_y = ty * TILE + off_y

                    sx = int((world_x - self.camera.x) * zoom)
                    sy = int((world_y - self.camera.y) * zoom)
                    sw = int(width * zoom)
                    sh = int(height * zoom)
                    if sw <= 0 or sh <= 0:
                        continue

                    ct = getattr(c, "collision_type", "")
                    if ct == "full":
                        color = (255, 80, 80)
                    elif ct == "top_only":
                        color = (80, 255, 80)
                    elif ct == "one_way":
                        color = (80, 160, 255)
                    else:
                        color = (255, 255, 0)

                    pygame.draw.rect(self.screen, color, (sx, sy, sw, sh), width=1)
        except Exception:
            # Never allow debug overlay to crash the game.
            return

    def _draw_collision_log_overlay(self):
        """
        Debug: visualize recent player-vs-tile collisions.
        Uses self.collision_events populated from Player.last_tile_collisions.
        """
        import pygame
        from config import TILE, WIDTH, HEIGHT

        try:
            if not getattr(self, "collision_events", None):
                return

            now = pygame.time.get_ticks()
            RECENT_MS = 120

            # On-map markers for very recent collisions
            for ev in self.collision_events:
                if not isinstance(ev, dict):
                    continue
                t = ev.get("time")
                if t is None or now - t > RECENT_MS:
                    continue
                tx = ev.get("tile_x")
                ty = ev.get("tile_y")
                tile_data = ev.get("tile_data")
                if tx is None or ty is None:
                    continue

                # Base rect from tile
                wx = tx * TILE
                wy = ty * TILE
                ww = TILE
                wh = TILE

                # If detailed collision tile_rect is available, prefer that
                tile_rect = ev.get("tile_rect")
                if tile_rect is not None and hasattr(tile_rect, "x"):
                    wx, wy, ww, wh = tile_rect.x, tile_rect.y, tile_rect.w, tile_rect.h

                # Project to screen
                zoom = getattr(self.camera, "zoom", 1.0) or 1.0
                sx = int((wx - self.camera.x) * zoom)
                sy = int((wy - self.camera.y) * zoom)
                sw = int(ww * zoom)
                sh = int(wh * zoom)
                if sw <= 0 or sh <= 0:
                    continue

                side = ev.get("side")
                col = (0, 255, 0)
                if side == "top":
                    col = (0, 255, 255)
                elif side == "bottom":
                    col = (255, 0, 255)
                elif side == "left":
                    col = (255, 255, 0)
                elif side == "right":
                    col = (255, 165, 0)

                pygame.draw.rect(self.screen, col, (sx, sy, sw, sh), width=1)
                # Small marker at impact edge
                if side == "top":
                    pygame.draw.line(self.screen, col, (sx, sy), (sx + sw, sy), 2)
                elif side == "bottom":
                    pygame.draw.line(self.screen, col, (sx, sy + sh), (sx + sw, sy + sh), 2)
                elif side == "left":
                    pygame.draw.line(self.screen, col, (sx, sy), (sx, sy + sh), 2)
                elif side == "right":
                    pygame.draw.line(self.screen, col, (sx + sw, sy), (sx + sw, sy + sh), 2)

            # Text log panel: last N events (newest first)
            font = self.font_small
            lines = []
            max_events = 8
            for ev in reversed(self.collision_events[-40:]):
                if len(lines) >= max_events:
                    break
                if not isinstance(ev, dict):
                    continue
                tile_name = ev.get("tile_name", "Unknown")
                tx = ev.get("tile_x")
                ty = ev.get("tile_y")
                side = ev.get("side") or "-"
                pen = ev.get("penetration")
                if pen is None:
                    pen = "-"
                dmg = ev.get("damage")
                if dmg is None:
                    dmg = "-"
                line = f"P vs {tile_name} @({tx},{ty}) side={side} pen={pen} dmg={dmg}"
                lines.append(line)

            if not lines:
                return

            pad_x = 8
            pad_y = 6
            line_h = font.get_linesize()
            max_w = 0
            for s in lines:
                w, _ = font.render(s, True, (255, 255, 255)).get_size()
                max_w = max(max_w, w)
            panel_w = max_w + pad_x * 2
            panel_h = line_h * len(lines) + pad_y * 2

            x = 8
            y = HEIGHT - panel_h - 8

            panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel.fill((5, 5, 10, 200))
            pygame.draw.rect(panel, (120, 220, 255, 255), panel.get_rect(), 1)

            cy = pad_y
            for s in lines:
                surf = font.render(s, True, (220, 240, 255))
                panel.blit(surf, (pad_x, cy))
                cy += line_h

            self.screen.blit(panel, (x, y))
        except Exception:
            return

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

        # Optional tile inspector overlay (F8)
        if self.debug_tile_inspector:
            self._draw_tile_inspector()

        # Optional collision boxes overlay
        if self.debug_collision_boxes:
            self._draw_collision_boxes()

        # Optional collision log overlay
        if self.debug_collision_log:
            self._draw_collision_log_overlay()

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
            actives = [getattr(self.player.combat, 'shield_timer', 0) > 0, getattr(self.player.combat, 'power_timer', 0) > 0, False]
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
            dt = self.clock.tick(FPS) / 1000.0  # Convert milliseconds to seconds
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
                    # Toggle collision report debugger (overlay + capture) with F9
                    if ev.key == pygame.K_F9:
                        self.debug_collision_log = not self.debug_collision_log
                        continue
                    if ev.key == pygame.K_i:
                        if not self.shop.shop_open:
                            self.inventory.inventory_open = not self.inventory.inventory_open
                            if not self.inventory.inventory_open:
                                self.inventory._clear_inventory_selection()
                        continue
                    if ev.key == pygame.K_z:
                        # Toggle camera zoom
                        self.camera.toggle_zoom()
                        floating.append(DamageNumber(
                            self.player.rect.centerx,
                            self.player.rect.top - 12,
                            self.camera.get_zoom_label(),
                            (255, 255, 100)
                        ))
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
                    # Teleport / navigation / debug cheats:
                    elif ev.key == pygame.K_F8:
                        # Toggle tile inspector (safe: overlay-only)
                        self.debug_tile_inspector = not self.debug_tile_inspector
                        continue
                    elif ev.key == pygame.K_F11:
                        # Reserved: previously procedural regen; now no-op
                        continue
                    elif ev.key == pygame.K_F12:
                        # Teleport to room 6 (boss room) for debug
                        self.goto_room(5)

            if not self.inventory.inventory_open and not self.shop.shop_open:
                self.update(dt)

                # Capture tile collision events for debug logger (player vs tiles)
                if self.debug_collision_log:
                    collisions = getattr(self.player, "last_tile_collisions", []) or []
                    now = pygame.time.get_ticks()
                    for c in collisions:
                        if not isinstance(c, dict):
                            continue
                        tile_data = c.get("tile_data")
                        tile_type = c.get("tile_type")
                        # Build safe event snapshot
                        event = {
                            "time": now,
                            "entity": "player",
                            "tile_type": tile_type,
                            "tile_name": getattr(tile_data, "name", "Unknown") if tile_data else "Unknown",
                            "tile_x": c.get("tile_x"),
                            "tile_y": c.get("tile_y"),
                            "tile_rect": c.get("tile_rect"),
                            "tile_data": tile_data,
                            "collision_type": getattr(getattr(tile_data, "collision", None), "collision_type", "unknown") if tile_data else "unknown",
                            "side": c.get("side"),
                            "penetration": c.get("penetration"),
                        }
                        # Attach damage if available
                        if tile_data and getattr(tile_data, "collision", None):
                            event["damage"] = getattr(tile_data.collision, "damage_on_contact", 0)
                        else:
                            event["damage"] = 0
                        self.collision_events.append(event)

                    # Trim history
                    if len(self.collision_events) > 40:
                        self.collision_events = self.collision_events[-40:]

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
            {'label': "Tile Inspector", 'type': 'toggle',
             'getter': lambda: self.debug_tile_inspector,
             'setter': lambda v: setattr(self, 'debug_tile_inspector', v)},
            {'label': "Collision Boxes", 'type': 'toggle',
             'getter': lambda: self.debug_collision_boxes,
             'setter': lambda v: setattr(self, 'debug_collision_boxes', v)},
            {'label': "Collision Log", 'type': 'toggle',
             'getter': lambda: self.debug_collision_log,
             'setter': lambda v: setattr(self, 'debug_collision_log', v)},
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
        self.draw()
        self._draw_debug_overlay(options, selected, title=title, offset=offset, visible=visible)
        pygame.display.flip()

    def _run_debug_option_menu(self, options, title="Debugger"):
        idx = 0
        offset = 0
        visible = min(9, len(options)) or 1
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_F5):
                        return
                    elif ev.key in (pygame.K_UP, pygame.K_w):
                        idx = (idx - 1) % len(options)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
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
            dt = self.clock.tick(FPS) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_F5):
                        return
                    elif ev.key in (pygame.K_LEFT, pygame.K_a):
                        idx = (idx - 1) % ROOM_COUNT
                    elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                        idx = (idx + 1) % ROOM_COUNT
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
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