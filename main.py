import sys
import random

import pygame
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reduce verbosity of PCG modules (only show warnings/errors)
logging.getLogger('src.level.pcg_postprocess').setLevel(logging.WARNING)
logging.getLogger('src.level.pcg_generator_simple').setLevel(logging.WARNING)

# Reduce verbosity of PCG modules (only show warnings/errors)
logging.getLogger('src.level.pcg_postprocess').setLevel(logging.WARNING)
logging.getLogger('src.level.pcg_generator_simple').setLevel(logging.WARNING)
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
    BACKGROUND_IMAGE_PATH,
)

from src.core.utils import draw_text, get_font
from src.core.interaction import handle_proximity_interactions, find_spawn_point, parse_door_target
from src.systems.camera import Camera
from src.level.legacy_level import LegacyLevel, ROOM_COUNT
from src.level.config_loader import load_pcg_runtime_config
from src.level.pcg_generator_simple import generate_simple_pcg_level_set
from src.level.level_loader import level_loader
from src.entities.entities import Player, hitboxes, floating, DamageNumber
from src.entities.entity_common import alert_system
from src.systems.inventory import Inventory
from src.systems.menu import Menu
from src.systems.shop import Shop
from typing import Optional
from src.debug import DebugOverlays
from src.ui.hud import draw_hud
from src.core.input import InputHandler




class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Haridd")
        self.clock = pygame.time.Clock()
        self.font_small = get_font(18)
        self.font_big = get_font(32, bold=True)
        self.camera = Camera()

        # Track current level
        self.current_level_number = 1
        
        # Level configuration: static layout only (procedural disabled)
        self.level_type = "static"
        self.difficulty = 1
        
        # PCG configuration
        runtime = load_pcg_runtime_config()
        self.use_pcg = runtime.use_pcg
        
        # Resolve seed
        if runtime.seed_mode == "random":
            import random as py_random
            seed = py_random.randrange(0, 2**31 - 1)
        else:
            seed = runtime.seed
        
        self.pcg_seed = seed
        
        # Only generate levels if PCG is enabled AND we actually need them
        # Skip generation entirely - will only generate when "Start Game" is selected
        # This saves resources when PCG is disabled or when game hasn't started yet
        
        # Door interaction state
        self.interaction_prompt = None
        self.interaction_position = None

        # Initialize menu system
        self.menu = Menu(self)

        # Load selected class from config
        runtime = load_pcg_runtime_config()
        self.selected_class = runtime.selected_class

        # Developer cheat toggles
        self.cheat_infinite_mana = False
        self.cheat_zero_cooldown = False
        self.debug_enemy_rays = False
        self.debug_enemy_nametags = False # Default to False
        self.debug_show_hitboxes = False  # F3 will toggle this along with vision rays

        # Debug visualization toggles
        self.debug_tile_inspector = False
        self.debug_collision_boxes = False
        # Collision log overlay is now toggled via F9; default OFF
        self.debug_collision_log = False
        self.collision_events = []  # recent collision events for logger

        # Terrain/Area debug
        self.debug_show_area_overlay = False
        # Area overlay opacity (0.0 - 1.0)
        self.debug_area_overlay_opacity = 0.7
        # Whether we are currently in the dedicated terrain/area test level
        self.in_terrain_test_level = False

        # Grid position debug
        self.debug_grid_position = False
        self.mouse_grid_pos = None
        self.mouse_world_pos = None
        
        # Wall jump debug
        self.debug_wall_jump = False

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
            import traceback
            traceback.print_exc()
        
        # Initialize first level
        try:
            # Use appropriate level based on system
            if self.use_pcg:
                initial_level = 1  # PCG levels are 1-based
            else:
                initial_level = 0  # Legacy levels are 0-based
            self._load_level(level_number=initial_level, initial=True)
        except Exception as e:
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
        
        # Link inventory to player for on-hit effects
        self.player.inventory = self.inventory

        # Debug overlays helper
        try:
            self.debug_overlays = DebugOverlays(self)
        except Exception:
            self.debug_overlays = None
        
        # Load arrow sprite for Ranger projectiles
        try:
            self.arrow_sprite = pygame.image.load("assets/Player/Ranger/arrow.png").convert_alpha()
            # Scale arrow to be more visible (32x16 pixels)
            self.arrow_sprite = pygame.transform.scale(self.arrow_sprite, (32, 16))
        except Exception as e:
            logger.warning(f"Failed to load arrow sprite: {e}")
            self.arrow_sprite = None

        # Input handler
        try:
            self.input_handler = InputHandler()
        except Exception:
            self.input_handler = InputHandler()  # fallback to default
            
        # Shop delay callback for level transitions
        self._shop_delay_callback = None

        # Load dungeon background
        self.bg_tile = None
        try:
            self.bg_tile = pygame.image.load(BACKGROUND_IMAGE_PATH).convert()
            # Force size 64x64
            self.bg_tile = pygame.transform.scale(self.bg_tile, (64, 64))
            logger.info(f"Loaded background tile: {BACKGROUND_IMAGE_PATH}")
        except Exception as e:
            logger.warning(f"Failed to load background tile {BACKGROUND_IMAGE_PATH}: {e}")
            logger.info("Using solid color background instead")

    def reset_game_state(self):
        """
        Reset game state to initial state (similar to constructor logic).
        This is used when returning to main menu from death screen.
        """
        # Reload PCG configuration to get latest settings
        runtime = load_pcg_runtime_config()
        self.use_pcg = runtime.use_pcg
        
        # Reset level tracking
        self.level_index = 0
        self.current_level_number = 1
        self.current_level_data = None
        
        # Clear transient collections
        from src.entities.entities import hitboxes, floating
        hitboxes.clear()
        floating.clear()
        
        # Reinitialize first level
        try:
            # Use appropriate level based on system
            if self.use_pcg:
                initial_level = 1  # PCG levels are 1-based
                # Generate PCG levels if needed
                from src.level.pcg_generator_simple import generate_simple_pcg_level_set
                from src.level.level_loader import level_loader
                level_set = generate_simple_pcg_level_set(seed=self.pcg_seed)
                level_set.save_to_json("data/levels/generated_levels.json")
                level_loader._level_set = level_set
            else:
                initial_level = 0  # Legacy levels are 0-based
            self._load_level(level_number=initial_level, initial=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return

        # create player with chosen class
        sx, sy = self.level.spawn
        self.player = Player(sx, sy, cls=self.selected_class)
        self.enemies = self.level.enemies

        # Reset camera to player position immediately to prevent visual glitch
        self.camera.update(self.player.rect, 0)

        # Reset inventory & shop
        self.inventory = Inventory(self)
        self.inventory._refresh_inventory_defaults()
        self.shop = Shop(self)
        
        # Link inventory to player for on-hit effects
        self.player.inventory = self.inventory

        # Reload background tile to ensure consistency
        self.bg_tile = None
        try:
            self.bg_tile = pygame.image.load(BACKGROUND_IMAGE_PATH).convert()
            # Force size 64x64
            self.bg_tile = pygame.transform.scale(self.bg_tile, (64, 64))
            logger.info(f"Reloaded background tile: {BACKGROUND_IMAGE_PATH}")
        except Exception as e:
            logger.warning(f"Failed to reload background tile {BACKGROUND_IMAGE_PATH}: {e}")
            logger.info("Using solid color background instead")

    def restart_run(self):
        """
        Restart from the current level (preserving level progress).
        """
        # Determine current level to restart
        if self.use_pcg:
            level_to_restart = self.current_level_number
        else:
            level_to_restart = self.level_index

        # Load the current level
        self._load_level(level_number=level_to_restart, initial=True)

        # Recreate player at the new spawn
        sx, sy = self.level.spawn
        self.player = Player(sx, sy, cls=self.selected_class)

        # Sync enemies from the level
        self.enemies = getattr(self.level, "enemies", [])

        # Reset/refresh inventory if present
        if hasattr(self, "inventory") and self.inventory is not None:
            self.inventory._refresh_inventory_defaults()

        # Clear transient collections
        from src.entities.entities import hitboxes, floating
        hitboxes.clear()
        floating.clear()

        # Reset camera
        self.camera = Camera()

    def _toggle_pcg(self, enable: bool):
        """Toggle PCG mode and restart current level."""
        from src.level.config_loader import save_pcg_runtime_config, PCGRuntimeConfig
        
        # Update config
        self.use_pcg = enable
        runtime = PCGRuntimeConfig(
            use_pcg=enable,
            seed_mode="fixed",
            seed=self.pcg_seed,
            selected_class=self.selected_class
        )
        save_pcg_runtime_config(runtime)
        
        # Restart current level
        if enable:
            # Generate PCG levels if needed
            from src.level.pcg_generator_simple import generate_simple_pcg_level_set
            from src.level.level_loader import level_loader
            level_set = generate_simple_pcg_level_set(seed=self.pcg_seed)
            level_set.save_to_json("data/levels/generated_levels.json")
            level_loader._level_set = level_set
            self._load_pcg_level(1, None, initial=True)
        else:
            # Switch to legacy
            self._load_static_level(0, initial=True)
        
        # Recreate player at spawn
        sx, sy = self.level.spawn
        self.player = Player(sx, sy, cls=self.selected_class)
        self.enemies = self.level.enemies
        
        # Clear transient collections
        from src.entities.entities import hitboxes, floating
        hitboxes.clear()
        floating.clear()

    def _ensure_pcg_levels_generated(self):
        """Generate PCG levels only if needed and seed has changed."""
        if not self.use_pcg:
            print("PCG disabled - skipping generation")
            return False
            
        from src.level.level_loader import level_loader
        from src.level.config_loader import load_pcg_runtime_config
        import os
        import json
        
        # Check current runtime config
        runtime = load_pcg_runtime_config()
        current_seed = runtime.seed if runtime.seed_mode == "fixed" else self.pcg_seed
        
        # Check if we already have generated levels with this seed
        need_generation = True
        generated_file = "data/levels/generated_levels.json"
        
        if os.path.exists(generated_file):
            try:
                with open(generated_file, 'r') as f:
                    data = json.load(f)
                    saved_seed = data.get('seed')
                    if saved_seed == current_seed:
                        # Load existing levels instead of regenerating
                        from src.level.pcg_level_data import LevelSet
                        level_set = LevelSet.load_from_json(generated_file)
                        level_loader._level_set = level_set
                        need_generation = False
            except Exception:
                # If there's any error reading the file, we'll regenerate
                pass
        
        if need_generation:
            from src.level.pcg_generator_simple import generate_simple_pcg_level_set
            level_set = generate_simple_pcg_level_set(seed=current_seed)
            level_set.save_to_json(generated_file)
            level_loader._level_set = level_set
            return True
        
        return False

    def _load_level(self, level_number: Optional[int] = None, room_id: Optional[str] = None, initial: bool = False):
        """
        Load a level - load specific room from legacy or PCG system.
        
        Args:
            level_number: Which level to load
            room_id: Which room in current level to load (for room transitions)
            initial: Is this the first load?
        """
        
        if self.use_pcg:
            # Generate levels only when actually needed (when starting game)
            self._ensure_pcg_levels_generated()
            self._load_pcg_level(level_number, room_id, initial)
        else:
            self._load_static_level(level_number or 0, initial)

    def _load_static_level(self, index: int, initial: bool = False):
        """Legacy static room loading (for backwards compatibility)."""

        self.level_index = index
        room_index = index % ROOM_COUNT
        
        # Create LegacyLevel instance
        from src.level.legacy_level import LegacyLevel
        lvl = LegacyLevel(room_index)
        
        self.level = lvl
        self.enemies = lvl.enemies
        
        # Update camera boundaries
        self.camera.level_width = lvl.w
        self.camera.level_height = lvl.h
        
        if not initial:
            from src.entities.entities import hitboxes, floating
            hitboxes.clear()
            floating.clear()

    def _load_pcg_level(self, level_number: Optional[int], room_id: Optional[str], initial: bool = False):
        """Load a PCG-generated level."""
        from src.level.level_loader import level_loader
        
        # Default: start at Level 1
        level_id = level_number or 1
        
        if room_id:
            room = level_loader.get_room(level_id, room_id)
        else:
            room = level_loader.get_starting_room(level_id)
        
        if room is None:
            # Fallback: if PCG broken, drop back to legacy so game still runs
            logger.error("PCG room not found (level %s, room %s), falling back to legacy", level_id, room_id)
            self.use_pcg = False
            self._load_static_level(0, initial=True)
            return
        
        # Build a lightweight level wrapper expected by rest of game
        class PCGLevel:
            def __init__(self):
                self.level_id = 0
                self.room_code = ""
                self.tiles = []
                self.grid = []
                self.tile_grid = []
                self.enemies = []
                self.is_boss_room = False
                self.spawn = [100, 100]  # Will be overwritten
                self.solids = []
                self.doors = []
                self.w = 0  # Level width in tiles
                self.h = 0  # Level height in tiles
                
                # Initialize tile collision system
                from src.tiles.tile_collision import TileCollision
                from config import TILE
                self.tile_collision = TileCollision(TILE)
            
            def _update_solids_from_grid(self):
                """Update solids list from tile grid for enemy collision system."""
                from src.tiles.tile_registry import tile_registry
                from src.tiles.tile_types import TileType
                from config import TILE
                
                self.solids = []
                if not self.tile_grid:
                    return
                    
                for y, row in enumerate(self.tile_grid):
                    for x, tile_value in enumerate(row):
                        if tile_value >= 0:
                            tile_type = TileType(tile_value)
                            tile_data = tile_registry.get_tile(tile_type)
                            
                            # Add solids for tiles with full collision
                            if tile_data and tile_data.collision.collision_type == "full":
                                rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                                self.solids.append(rect)
                
            def draw(self, screen, camera, dt: float = 0.0):
                """Use the proper tile system for PCG levels."""
                from src.tiles.tile_renderer import TileRenderer
                from config import TILE
                
                renderer = TileRenderer(tile_size=TILE)
                
                # Use the canonical render_tile_grid method
                renderer.render_tile_grid(
                    surface=screen,
                    tile_grid=self.tile_grid,
                    camera_offset=(camera.x, camera.y),
                    visible_rect=screen.get_rect(),
                    time_delta=dt,
                    zoom=camera.zoom,
                )
        
        lvl = PCGLevel()
        lvl.level_id = room.level_id
        lvl.room_code = room.room_code
        lvl.tiles = room.tiles
        lvl.grid = room.tiles           # used by collision/debug
        lvl.tile_grid = room.tiles      # used by _handle_door_interactions
        lvl.enemies = []                # start empty for now
        lvl.is_boss_room = False
        # Set level dimensions for enemy movement system (in tiles and pixels)
        lvl.h = len(room.tiles) if room.tiles else 0
        lvl.w = len(room.tiles[0]) if lvl.h > 0 else 0
        
        # Convert to pixels for camera boundaries (matching legacy level behavior)
        from config import TILE
        lvl.w = lvl.w * TILE  # Width in pixels
        lvl.h = lvl.h * TILE  # Height in pixels
        
        # Generate collision solids from tile grid for enemy collision system
        lvl._update_solids_from_grid()
        lvl._update_solids_from_grid()

        # --- Spawn PCG enemies from room metadata 'spawn' areas ---
        try:
            from src.level.level_loader import level_loader
            from src.entities.entities import Bug, Bee, Frog, Archer, WizardCaster, Assassin, Golem
            from config import TILE
            import random as _rnd

            room_meta = level_loader.get_room(lvl.level_id, lvl.room_code)
            if room_meta:
                rng = _rnd.Random(self.pcg_seed or None)
                spawned = []
                areas = getattr(room_meta, 'areas', []) or []
                spawn_areas = [a for a in areas if isinstance(a, dict) and a.get('kind') == 'spawn']
                # Track used spawn positions to prevent crowding
                used_spawn_positions = []  # List of (tile_x, tile_y) tuples
                
                for a in spawn_areas:
                    props = a.get('properties', {}) or {}
                    surface = props.get('spawn_surface', 'both')
                    cap = int(props.get('spawn_cap', 1)) if props.get('spawn_cap') is not None else 1
                    # cap per region to avoid huge crowds
                    max_per_region = min(cap, 3)
                    for i in range(max_per_region):
                        allowed = None
                        if surface == 'ground':
                            allowed = ('ground', 'both')
                        elif surface == 'air':
                            allowed = ('air', 'both')
                        else:
                            allowed = ('ground', 'air', 'both')
                        try:
                            # Use minimum distance of 3 tiles between spawns to prevent crowding
                            tile_choice = level_loader.choose_spawn_tile(
                                lvl.level_id, lvl.room_code, 
                                kind='spawn', 
                                rng=rng, 
                                allowed_surfaces=allowed,
                                avoid_positions=used_spawn_positions,
                                min_distance=3  # Minimum 3 tiles between enemy spawns
                            )
                        except Exception:
                            tile_choice = None
                        if not tile_choice:
                            continue
                        tx, ty = tile_choice
                        # Add this position to used positions list
                        used_spawn_positions.append((tx, ty))
                        
                        cx = int(tx * TILE + TILE // 2)
                        ground_y = int((ty + 1) * TILE)
                        # pick enemy class based on surface
                        try:
                            if surface == 'air':
                                EnemyClass = _rnd.choice([Bee, WizardCaster])
                            elif surface == 'ground':
                                EnemyClass = _rnd.choice([Bug, Frog, Archer])
                            else:
                                EnemyClass = _rnd.choice([Bug, Bee, Archer])
                            spawned.append(EnemyClass(cx, ground_y))
                        except Exception:
                            try:
                                spawned.append(Bug(cx, ground_y))
                            except Exception:
                                pass
                # assign spawned enemies to level
                if spawned:
                    lvl.enemies = spawned
        except Exception:
            # don't let spawning break level load
            pass
        
        # Try to find door entrance spawn point first, fall back to center of room
        from src.core.interaction import find_spawn_point
        from config import TILE
        
        # Default spawn: center of room (fallback)
        h = len(room.tiles)
        w = len(room.tiles[0]) if h > 0 else 0
        default_spawn_x = w // 2 * TILE
        default_spawn_y = (h - 2) * TILE  # just above floor
        
        # Try to find proper door entrance spawn point
        try:
            # For initial room load, entrance_id should be None to find any entrance
            spawn_tile = find_spawn_point(room.tiles, entrance_id=None)
            if spawn_tile:
                # Use door entrance position if found
                lvl.spawn[0] = spawn_tile[0] * TILE
                lvl.spawn[1] = spawn_tile[1] * TILE
                logger.debug(f"Using door entrance spawn at tile ({spawn_tile[0]}, {spawn_tile[1]}) for room {room.room_code}")
            else:
                # Fall back to default center spawn
                lvl.spawn[0] = default_spawn_x
                lvl.spawn[1] = default_spawn_y
                logger.debug(f"No door entrance found in room {room.room_code}, using center spawn")
        except Exception as e:
            # If spawn point finding fails, use default
            lvl.spawn[0] = default_spawn_x
            lvl.spawn[1] = default_spawn_y
            logger.warning(f"Failed to find door entrance spawn for room {room.room_code}: {e}, using center spawn")
        


        self.level = lvl
        self.enemies = lvl.enemies
        
        # Update camera boundaries
        self.camera.level_width = lvl.w
        self.camera.level_height = lvl.h
        
        # Update current level tracking
        try:
            self.current_level_number = int(lvl.level_id)
        except Exception:
            pass

        # If door system exists, sync its internal tiles/state to the newly loaded room
        try:
            if hasattr(self, '_door_system') and getattr(self, '_door_system') is not None:
                try:
                    # Prefer DoorSystem.set_current_tiles when available
                    self._door_system.set_current_tiles(lvl.level_id, lvl.room_code, lvl.tile_grid)
                except Exception:
                    ds = self._door_system
                    ds.current_level_id = lvl.level_id
                    ds.current_room_code = lvl.room_code
                    # ensure door system sees the exact tile grid used for rendering
                    ds.current_tile_grid = lvl.tile_grid
        except Exception:
            logger.exception("Failed to sync DoorSystem after PCG level load")
        


        if not initial:
            hitboxes.clear()
            floating.clear()
            # Center camera on player to make new room visible immediately
            try:
                self.camera.update(getattr(self, 'player').rect, 0)
            except Exception:
                pass
        



    def switch_room(self, delta: Optional[int] = None, target_room_id: Optional[str] = None):
        """
        Switch to next room.
        
        Args:
            delta: +1 for next room
            target_room_id: Specific room to switch to (not used in legacy system)
        """
        # Legacy static room switching
        new_index = max(0, self.level_index + (delta or 1))
        self._load_level(new_index)
        sx, sy = self.level.spawn
        self.player.rect.topleft = (sx, sy)
        
        # Trigger shop for legacy levels after every room transition
        if not self.use_pcg:
            self._trigger_shop_after_level_transition()
        

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
        alert_system.reset()  # Clear alerts when changing rooms
        
        # Trigger shop for legacy levels after every room transition
        if not self.use_pcg:
            self._trigger_shop_after_level_transition()

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

 # Legacy door system for static rooms
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

        # Update alert system for enemy coordination
        alert_system.update()

        for e in self.enemies:
            e.tick(self.level, self.player)

        for hb in list(hitboxes):
            hb.tick()
            # Only projectiles (hitboxes with velocity) should be destroyed by solids
            # Melee attacks (no velocity) should pass through walls for enemy detection
            is_projectile = getattr(hb, 'vx', 0) != 0 or getattr(hb, 'vy', 0) != 0
            
            if is_projectile:
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
                    # remove projectiles that hit solids
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
                        
                        # Apply on-hit effects from player augmentations
                        try:
                            from src.systems.on_hit_effects import process_on_hit_effects
                            process_on_hit_effects(e, self.player, hb, self.inventory)
                        except Exception as ex:
                            import traceback
                            traceback.print_exc()
                            pass  # Fail silently if on-hit effects system has issues
                        
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
        
        # Handle door interactions
        self._handle_door_interactions()

    def _draw_area_overlay(self):
        # Delegated to debug overlays module
        try:
            self.debug_overlays.draw_area_overlay()
        except Exception:
            return

    def _get_player_area_labels(self):
        try:
            if self.debug_overlays:
                return self.debug_overlays.get_player_area_labels()
        except Exception:
            pass
        return ""

    def _get_grid_position(self, mouse_screen_pos):
        try:
            if self.debug_overlays:
                return self.debug_overlays.get_grid_position(mouse_screen_pos)
        except Exception:
            pass
        # Fallback minimal implementation
        world_x = (mouse_screen_pos[0] / self.camera.zoom) + self.camera.x
        world_y = (mouse_screen_pos[1] / self.camera.zoom) + self.camera.y
        grid_x = int(world_x // TILE)
        grid_y = int(world_y // TILE)
        return grid_x, grid_y, int(world_x), int(world_y), "Unknown", "Unknown", "Out of bounds", "N/A"

    def _draw_grid_position_overlay(self):
        try:
            if self.debug_overlays:
                self.debug_overlays.draw_grid_position_overlay()
        except Exception:
            return

    def _draw_tile_inspector(self):
        """Delegate tile inspector drawing to DebugOverlays."""
        try:
            if self.debug_overlays:
                self.debug_overlays.draw_tile_inspector()
        except Exception:
            return

    def _draw_collision_boxes(self):
        """Delegate collision box drawing to DebugOverlays."""
        try:
            if self.debug_overlays:
                self.debug_overlays.draw_collision_boxes()
        except Exception:
            return

    def _draw_collision_log_overlay(self):
        """Delegate collision log drawing to DebugOverlays."""
        try:
            if self.debug_overlays:
                self.debug_overlays.draw_collision_log_overlay()
        except Exception:
            return

    def _draw_arrow_sprite(self, hitbox):
        """Draw arrow sprite for Ranger projectiles with proper rotation."""
        if not self.arrow_sprite:
            return
        
        import math
        
        # Get arrow direction from hitbox
        dir_vec = getattr(hitbox, 'dir_vec', (1, 0))
        angle = math.atan2(dir_vec[1], dir_vec[0])
        
        # Rotate arrow sprite to match direction
        # Convert radians to degrees (pygame uses degrees)
        angle_degrees = -math.degrees(angle)  # Negative because pygame y-axis is flipped
        rotated_sprite = pygame.transform.rotate(self.arrow_sprite, angle_degrees)
        
        # Get hitbox center in world coordinates
        world_center = hitbox.rect.center
        
        # Convert to screen coordinates
        screen_pos = self.camera.to_screen(world_center)
        
        # Apply camera zoom
        scaled_width = int(rotated_sprite.get_width() * self.camera.zoom)
        scaled_height = int(rotated_sprite.get_height() * self.camera.zoom)
        scaled_sprite = pygame.transform.scale(rotated_sprite, (scaled_width, scaled_height))
        
        # Center the sprite on the hitbox position
        sprite_rect = scaled_sprite.get_rect(center=screen_pos)
        
        # Draw the sprite
        self.screen.blit(scaled_sprite, sprite_rect.topleft)

    def draw(self):
        # Draw dungeon background image
        if self.bg_tile:
            tile_w = self.bg_tile.get_width()
            tile_h = self.bg_tile.get_height()
            for x in range(0, WIDTH, tile_w):
                for y in range(0, HEIGHT, tile_h):
                    self.screen.blit(self.bg_tile, (x, y))
        else:
            self.screen.fill(BG)
        self.level.draw(self.screen, self.camera)
        for e in self.enemies:
            e.draw(self.screen, self.camera, show_los=self.debug_enemy_rays, show_nametags=self.debug_enemy_nametags, debug_hitboxes=self.debug_show_hitboxes)
        
        # Draw arrow sprites for Ranger projectiles
        if self.arrow_sprite:
            for hb in hitboxes:
                if getattr(hb, 'arrow_sprite', False) and hb.alive:
                    self._draw_arrow_sprite(hb)
        
        # Draw hitboxes: force draw all hitboxes if debug mode is on
        for hb in hitboxes:
            hb.draw(self.screen, self.camera, force_draw=self.debug_show_hitboxes)
        self.player.draw(self.screen, self.camera, debug_hitboxes=self.debug_show_hitboxes)
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

        # Draw interaction prompt if active
        if self.interaction_prompt and self.interaction_position:
            prompt_x, prompt_y = self.interaction_position
            # Convert world coordinates to screen coordinates
            screen_x = int((prompt_x - self.camera.x) * self.camera.zoom)
            screen_y = int((prompt_y - self.camera.y) * self.camera.zoom)
            
            # Draw prompt background
            font = self.font_small
            text_surf = font.render(self.interaction_prompt, True, (255, 255, 200))
            text_rect = text_surf.get_rect(center=(screen_x, screen_y))
            padding = 8
            bg_rect = text_rect.inflate(padding * 2, padding)
            pygame.draw.rect(self.screen, (40, 40, 60, 200), bg_rect, border_radius=4)
            pygame.draw.rect(self.screen, (255, 255, 200), bg_rect, width=1, border_radius=4)
            self.screen.blit(text_surf, text_rect)

        # HUD
        try:
            draw_hud(self, self.screen)
        except Exception:
            logger.exception('HUD draw failed')

        if self.inventory.inventory_open:
            try:
                self.inventory.draw_inventory_overlay()
            except Exception:
                logger.exception("Inventory draw failed; closing inventory to avoid crash")
                try:
                    self.inventory.inventory_open = False
                    self.inventory._clear_inventory_selection()
                except Exception:
                    pass
        
        # Draw shop if open
        if self.shop.shop_open:
            self.shop.draw(self.screen)
            # Draw tooltip overlay last so it's always on top
            try:
                self.shop.draw_tooltip_overlay(self.screen)
            except Exception:
                pass



    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0  # Convert milliseconds to seconds
            try:
                self.input_handler.process_events(self, dt)
            except Exception:
                logger.exception('Input processing failed')

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
        """
        Open the main Developer Tools menu as a tiled grid (PCG-style).
        Uses arrow/WASD navigation; Enter to toggle/action; Esc/F5 to close.
        """
        self.inventory.inventory_open = False
        self.inventory._clear_inventory_selection()

        options = [
            # Cheats
            {'label': 'God Mode', 'type': 'toggle',
             'getter': lambda: getattr(self.player, 'god', False),
             'setter': lambda v: setattr(self.player, 'god', v)},
            {'label': 'No-clip', 'type': 'toggle',
             'getter': lambda: getattr(self.player, 'no_clip', False),
             'setter': lambda v: setattr(self.player, 'no_clip', v)},
            {'label': 'Infinite Mana', 'type': 'toggle',
             'getter': lambda: self.cheat_infinite_mana,
             'setter': lambda v: setattr(self, 'cheat_infinite_mana', v)},
            {'label': 'Zero Cooldown', 'type': 'toggle',
             'getter': lambda: self.cheat_zero_cooldown,
             'setter': lambda v: setattr(self, 'cheat_zero_cooldown', v)},

            # Visuals
            {'label': 'Enemy Vision Rays', 'type': 'toggle',
             'getter': lambda: self.debug_enemy_rays,
             'setter': lambda v: setattr(self, 'debug_enemy_rays', v)},
            {'label': 'Show Hitboxes', 'type': 'toggle',
             'getter': lambda: self.debug_show_hitboxes,
             'setter': lambda v: setattr(self, 'debug_show_hitboxes', v)},
            {'label': 'Enemy Nametags', 'type': 'toggle',
             'getter': lambda: self.debug_enemy_nametags,
             'setter': lambda v: setattr(self, 'debug_enemy_nametags', v)},
            {'label': 'Area Overlay', 'type': 'toggle',
             'getter': lambda: self.debug_show_area_overlay,
             'setter': lambda v: setattr(self, 'debug_show_area_overlay', v)},
            {'label': 'Overlay Opacity', 'type': 'info', 'getter': lambda: f"{self.debug_area_overlay_opacity:.2f}"},
            {'label': 'Increase Overlay Opacity', 'type': 'action', 'action': lambda: self._adjust_overlay_opacity(0.05)},
            {'label': 'Decrease Overlay Opacity', 'type': 'action', 'action': lambda: self._adjust_overlay_opacity(-0.05)},

            # Tools
            {'label': 'Refill Consumables', 'type': 'action', 'action': self.inventory.add_all_consumables},
            {'label': 'Give Items', 'type': 'action', 'action': self.debug_item_menu},

            # PCG & Navigation
            {'label': 'PCG Mode', 'type': 'toggle',
             'getter': lambda: getattr(self, 'use_pcg', False),
             'setter': lambda v: self._toggle_pcg(v)},
            {'label': 'Teleport to Level/Room', 'type': 'action', 'action': self.debug_teleport_menu},

            # Close
            {'label': 'Close', 'type': 'action', 'action': None, 'close': True},
        ]

        # Grid rendering helper for options (now uses fixed rows and dark palette)
        def _draw_option_grid_overlay(options, selected_idx, rows=3, cols=None, title="Developer Tools", offset=0):
            import math
            total = len(options)
            # If caller specified 'cols', honor it; otherwise compute cols from rows.
            if cols is None:
                cols = max(1, math.ceil(total / max(1, rows)))
            else:
                # Ensure rows is consistent with cols (rows = how many vertical cells we attempt per page)
                rows = max(1, rows)

            # derive alpha and draw overlay+panel on SRCALPHA surfaces to respect alpha properly
            alpha = int(max(0.05, min(1.0, getattr(self, 'debug_area_overlay_opacity', 0.7))) * 220)
            backdrop = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            backdrop.fill((12, 14, 20, alpha))
            self.screen.blit(backdrop, (0, 0))

            # cap panel size so it never overflows the screen
            max_panel_w = min(780, WIDTH - 80)
            max_panel_h = min(HEIGHT - 120, 520)
            panel_w = min(640, max_panel_w)
            panel_h = min(420, max_panel_h)
            panel_x = (WIDTH - panel_w) // 2
            panel_y = (HEIGHT - panel_h) // 2

            # Panel shadow + body (dark theme)
            shadow_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            shadow_surf.fill((0, 0, 0, 180))
            self.screen.blit(shadow_surf, (panel_x + 6, panel_y + 8))

            panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel_surf.fill((22, 24, 30, max(80, alpha)))
            pygame.draw.rect(panel_surf, (80, 80, 90), pygame.Rect(0, 0, panel_w, panel_h), width=1, border_radius=14)
            self.screen.blit(panel_surf, (panel_x, panel_y))

            # header band with subtle accent (similar to PCG palette)
            header = pygame.Rect(panel_x, panel_y, panel_w, 64)
            pygame.draw.rect(self.screen, (44, 46, 72), header, border_radius=14)
            draw_text(self.screen, title, (panel_x + 22, panel_y + 14), (230, 230, 240), size=22, bold=True)
            draw_text(self.screen, f"Options: {total}", (panel_x + panel_w - 160, panel_y + 18), (190,190,200), size=16)

            # Grid area inside panel
            grid_x = panel_x + 24
            grid_y = panel_y + 86
            grid_w = panel_w - 48
            grid_h = panel_h - 120
            spacing = 12

            # compute cell sizes for columns/rows (use provided rows as vertical count per page)
            cell_w = max(120, (grid_w - (cols - 1) * spacing) // cols)
            cell_h = max(64, (grid_h - (rows - 1) * spacing) // max(1, rows))
            cell_h = min(120, cell_h)

            # page sizing
            page_size = rows * cols
            # subset of options to render for current page
            subset = options[offset:offset + page_size]

            # center grid vertically if there's extra space
            used_h = rows * cell_h + (rows - 1) * spacing
            start_y = grid_y + max(0, (grid_h - used_h) // 2)

            # small helpers
            def _ellipsize(text, font, max_w):
                try:
                    if font.render(text, True, (0,0,0)).get_width() <= max_w:
                        return text
                except Exception:
                    return text
                base = text
                while base and font.render(base + '...', True, (0,0,0)).get_width() > max_w:
                    base = base[:-1]
                return base + '...'

            def _text_for_bg(rgb):
                r,g,b = rgb
                lum = 0.299*r + 0.587*g + 0.114*b
                return (0,0,0) if lum > 160 else (255,255,255)

            # Draw cells in row-major order for the subset
            for i, opt in enumerate(subset):
                global_idx = offset + i
                r = i // cols
                c = i % cols
                cx = grid_x + c * (cell_w + spacing)
                cy = start_y + r * (cell_h + spacing)
                cell = pygame.Rect(cx, cy, cell_w, cell_h)

                # Use darker, higher-contrast cell colors for readability
                default_pastel = (44, 48, 56)
                selected_pastel = (70, 110, 150)
                is_selected = (global_idx == selected_idx)
                cell_fill = selected_pastel if is_selected else default_pastel
                pygame.draw.rect(self.screen, cell_fill, cell, border_radius=8)

                # determine text color for contrast
                def text_for_bg(rgb):
                    r,g,b = rgb
                    lum = 0.299*r + 0.587*g + 0.114*b
                    return (0,0,0) if lum > 160 else (255,255,255)
                text_color = text_for_bg(cell_fill)

                # Label (ellipsize to avoid clipping) — larger and moved slightly down
                label = _ellipsize(opt.get('label', ''), self.font_small, cell_w - 28)
                draw_text(self.screen, label, (cell.x + 12, cell.y + 14), text_color, size=18)

                # Right status for toggles/info: draw a prominent pill for toggles centered vertically
                if opt.get('type') == 'toggle':
                    try:
                        state_on = bool(opt['getter']())
                    except Exception:
                        state_on = False
                    pill_w, pill_h = 64, 26
                    pill_x = cell.right - pill_w - 12
                    pill_y = cell.y + (cell_h - pill_h)//2
                    pill_rect = pygame.Rect(pill_x, pill_y, pill_w, pill_h)
                    if state_on:
                        pygame.draw.rect(self.screen, (80,200,120), pill_rect, border_radius=14)
                        draw_text(self.screen, 'ON', (pill_x + 18, pill_y + 4), (8,12,10), size=16, bold=True)
                    else:
                        pygame.draw.rect(self.screen, (80,80,90), pill_rect, border_radius=14)
                        draw_text(self.screen, 'OFF', (pill_x + 16, pill_y + 4), (200,200,210), size=16, bold=True)
                elif opt.get('type') == 'info':
                    try:
                        right_text = str(opt['getter']())
                    except Exception:
                        right_text = 'ERR'
                    if right_text:
                        rt_w = self.font_small.render(right_text, True, text_color).get_width()
                        draw_text(self.screen, right_text, (cell.right - rt_w - 12, cell.y + 14), text_color, size=14)

                # Kind tag (muted for dark background)
                kt = opt.get('type', '')
                if kt == 'toggle':
                    ktcol = (54, 70, 60)
                elif kt == 'action':
                    ktcol = (60, 64, 88)
                else:
                    ktcol = (64,64,64)
                kind_rect = pygame.Rect(cell.right - 96, cell.y + cell_h - 32, 86, 22)
                pygame.draw.rect(self.screen, ktcol, kind_rect, border_radius=6)
                kcol = (240,240,240)
                draw_text(self.screen, kt.upper(), (kind_rect.x + 10, kind_rect.y + 2), kcol, size=12)

            # Page indicator
            page_num = (offset // page_size) + 1
            total_pages = max(1, (total + page_size - 1) // page_size)
            draw_text(self.screen, f"Page {page_num}/{total_pages}", (panel_x + panel_w - 160, panel_y + 46), (180,180,200), size=14)

            draw_text(self.screen, "Use Arrows/WASD to navigate • Enter = Toggle/Run • Esc = Close", (panel_x + 22, panel_y + panel_h - 38), (220,220,230), size=15)



        # Interactive loop for grid with paging (scrollable)
        cols = 3
        rows = 3
        idx = 0
        offset = 0
        total = len(options)
        page_size = rows * cols
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            total = len(options)
            idx = max(0, min(idx, total - 1))
            # ensure offset keeps selected in current page
            offset = (idx // page_size) * page_size

            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_F5):
                        return
                    elif ev.key in (pygame.K_LEFT, pygame.K_a):
                        idx = (idx - 1) % total
                    elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                        idx = (idx + 1) % total
                    elif ev.key in (pygame.K_UP, pygame.K_w):
                        # move up by one row
                        idx = (idx - cols) % total
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        # move down by one row
                        idx = (idx + cols) % total
                    elif ev.key == pygame.K_PAGEUP:
                        # previous page
                        offset = max(0, offset - page_size)
                        idx = offset
                    elif ev.key == pygame.K_PAGEDOWN:
                        # next page
                        offset = min(max(0, total - page_size), offset + page_size)
                        idx = offset
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        opt = options[idx]
                        if opt.get('type') == 'toggle':
                            try:
                                opt['setter'](not opt['getter']())
                            except Exception:
                                pass
                        elif opt.get('type') == 'action' and opt.get('action'):
                            try:
                                opt['action']()
                            except Exception:
                                pass
                        if opt.get('close'):
                            return

            self.draw()
            _draw_option_grid_overlay(options, idx, rows=rows, cols=cols, title="Developer Tools", offset=offset)
            pygame.display.flip()

    def debug_item_menu(self):
        """
        Give Items debug submenu (grid view).

        Presents available gear and consumables in a tiled grid similar to the PCG
        teleport UI. Navigation: arrow keys (or WASD). Enter to give/equip. Esc/F5 to close.
        """
        self.inventory.inventory_open = False
        self.inventory._clear_inventory_selection()

        def _msg(text, color=(160,220,255)):
            try:
                floating.append(DamageNumber(self.player.rect.centerx, self.player.rect.top - 12, text, color))
            except Exception:
                pass

        def build_items_list():
            """Return a list of item dicts: {'key', 'name', 'action', 'obj', 'kind'}"""
            items = []
            try:
                gear_keys = sorted(list(self.inventory.armament_catalog.keys()))
            except Exception:
                gear_keys = []
            try:
                consumable_keys = sorted(list(self.inventory.consumable_catalog.keys()))
            except Exception:
                consumable_keys = []

            # Filter out owned gear
            try:
                owned = set(self.inventory.armament_order or [])
                gear_keys = [k for k in gear_keys if k not in owned]
            except Exception:
                pass

            # Filter consumables at cap
            try:
                cap = getattr(self.inventory, 'MAX_CONSUMABLE_SLOT_STACK', 20)
                consumable_keys = [k for k in consumable_keys if self.inventory._total_available_count(k) < cap]
            except Exception:
                pass

            # Add gear entries
            for k in gear_keys:
                obj = self.inventory.armament_catalog.get(k)
                def make_action(key, obj=obj):
                    def action():
                        try:
                            self.inventory._force_equip_armament(key)
                            _msg(f"Equipped: {getattr(obj, 'name', key)}", (200,220,160))
                        except Exception:
                            _msg("Failed to equip", (255,120,120))
                    return action
                items.append({'key': k, 'name': getattr(self.inventory.armament_catalog.get(k), 'name', k), 'action': make_action(k), 'obj': self.inventory.armament_catalog.get(k), 'kind': 'gear'})

            # Add consumable entries
            for k in consumable_keys:
                obj = self.inventory.consumable_catalog.get(k)
                def make_action(key, obj=obj):
                    def action():
                        try:
                            added = self.inventory.add_consumable(key, 1)
                            if added > 0:
                                _msg(f"Added x{added}: {getattr(obj, 'name', key)}", (160,255,180))
                            else:
                                stored = self.inventory.add_consumable_to_storage(key, 1)
                                if stored > 0:
                                    _msg(f"Stored x{stored}: {getattr(obj, 'name', key)}", (180,220,255))
                                else:
                                    _msg("Inventory Full", (255,180,120))
                        except Exception:
                            _msg("Failed to add", (255,120,120))
                    return action
                items.append({'key': k, 'name': getattr(obj, 'name', k), 'action': make_action(k), 'obj': obj, 'kind': 'consumable'})

            # Close entry as last
            items.append({'key': '__CLOSE__', 'name': 'Close', 'action': None, 'obj': None, 'kind': 'control'})
            return items

        # Grid drawing helper (supports paging)
        def _draw_item_grid_overlay(items, selected_idx, cols=3, title="Give Items", offset=0, rows=None):
            total = len(items)
            if rows is None:
                rows = max(1, (total + cols - 1) // cols)

            # Use overlay alpha from config so opacity controls have immediate effect
            alpha = int(max(0.05, min(1.0, getattr(self, 'debug_area_overlay_opacity', 0.7))) * 220)
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((12,14,20,alpha))
            self.screen.blit(overlay, (0,0))

            panel_w, panel_h = 700, 480
            panel_x = (WIDTH - panel_w) // 2
            panel_y = (HEIGHT - panel_h) // 2
            shadow = pygame.Rect(panel_x + 6, panel_y + 8, panel_w, panel_h)
            pygame.draw.rect(self.screen, (0,0,0, max(60, alpha-20)), shadow, border_radius=14)
            panel = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
            pygame.draw.rect(self.screen, (26,28,36, max(80, alpha)), panel, border_radius=14)
            pygame.draw.rect(self.screen, (140,140,150), panel, width=1, border_radius=14)

            # Header
            header = pygame.Rect(panel.x, panel.y, panel.width, 64)
            pygame.draw.rect(self.screen, (50,50,70, max(100, alpha)), header, border_radius=14)
            draw_text(self.screen, title, (panel.x + 22, panel.y + 14), (245,245,250), size=22, bold=True)
            draw_text(self.screen, f"Items: {total-1}", (panel.right - 180, panel.y + 18), (200,200,210), size=16)

            # Compute grid area
            grid_x = panel.x + 24
            grid_y = panel.y + 86
            grid_w = panel.width - 48
            grid_h = panel.height - 120

            spacing = 12
            # Larger default cells for better readability
            cell_w = max(140, (grid_w - (cols - 1) * spacing) // cols)
            cell_h = int(cell_w * 0.95)
            cell_h = min(cell_h, 180)

            # compute rows per page if not provided
            page_rows = rows
            page_size = page_rows * cols

            # subset for this page
            subset = items[offset:offset + page_size]

            # Ensure grid fits vertically: shrink if necessary to avoid clipping bottom
            used_h = page_rows * cell_h + (page_rows - 1) * spacing
            if used_h > grid_h:
                cell_h = max(56, (grid_h - (page_rows - 1) * spacing) // max(1, page_rows))
                used_h = page_rows * cell_h + (page_rows - 1) * spacing

            start_y = grid_y + max(0, (grid_h - used_h) // 2)

            # small helper to ellipsize long names to fit cell width
            def _ellipsize(text, font, max_w):
                if font.render(text, True, (0,0,0)).get_width() <= max_w:
                    return text
                base = text
                while base and font.render(base + '...', True, (0,0,0)).get_width() > max_w:
                    base = base[:-1]
                return base + '...'

            for i, it in enumerate(subset):
                r = i // cols
                c = i % cols
                cx = grid_x + c * (cell_w + spacing)
                cy = start_y + r * (cell_h + spacing)
                cell_rect = pygame.Rect(cx, cy, cell_w, cell_h)

                # Use darker, higher-contrast cell colors for readability
                default_pastel = (44, 48, 56)
                selected_pastel = (70, 110, 150)
                is_selected = ((offset + i) == selected_idx)
                cell_fill = selected_pastel if is_selected else default_pastel
                pygame.draw.rect(self.screen, cell_fill, cell_rect, border_radius=8)

                # Icon circle (use object's color if available)
                icon_r = min(36, max(20, cell_h // 4))
                icon_cx = cell_rect.x + 16 + icon_r
                icon_cy = cell_rect.y + 16 + icon_r
                color = (120,120,140)
                try:
                    obj = it.get('obj')
                    if obj and getattr(obj, 'color', None):
                        color = getattr(obj, 'color')
                except Exception:
                    pass
                pygame.draw.circle(self.screen, color, (icon_cx, icon_cy), icon_r)
                # Icon letter (light for dark bg)
                icon_letter = ''
                try:
                    icon_letter = getattr(it.get('obj'), 'icon_letter', '') or (it.get('key') or '')[:1].upper()
                except Exception:
                    icon_letter = (it.get('key') or '')[:1].upper()
                draw_text(self.screen, icon_letter, (icon_cx - 8, icon_cy - 12), (245,245,250), size=22, bold=True)

                # Name (ellipsize to avoid overflow) - light text for dark bg
                name = it.get('name') or it.get('key')
                name = _ellipsize(name, self.font_small, cell_w - 28)
                draw_text(self.screen, name, (cell_rect.x + 12, cell_rect.y + cell_h - 34), (235,235,240), size=16)

                # Kind tag (muted dark tag with light text)
                kind = it.get('kind', '')
                if kind == 'gear':
                    tag_col = (80,72,64)
                elif kind == 'consumable':
                    tag_col = (54,90,60)
                else:
                    tag_col = (64,64,64)
                tag_rect = pygame.Rect(cell_rect.right - 78, cell_rect.y + 8, 64, 20)
                pygame.draw.rect(self.screen, tag_col, tag_rect, border_radius=6)
                draw_text(self.screen, kind.upper(), (tag_rect.x + 6, tag_rect.y + 2), (240,240,240), size=12)

                # Selection outline
                if is_selected:
                    try:
                        pygame.draw.rect(self.screen, (80,150,220), cell_rect.inflate(6,6), width=3, border_radius=10)
                    except Exception:
                        pygame.draw.rect(self.screen, (80,150,220), cell_rect.inflate(6,6), width=3)

            # Page indicator
            page_num = (offset // page_size) + 1
            total_pages = max(1, (total + page_size - 1) // page_size)
            draw_text(self.screen, f"Page {page_num}/{total_pages}", (panel_x + panel_w - 160, panel_y + 46), (180,180,200), size=14)

            draw_text(self.screen, "Arrow keys / WASD = Move • Enter = Give/Equip • Esc = Close • PgUp/PgDn to scroll", (panel.x + 22, panel.bottom - 34), (180,190,200), size=14)

        # Interactive grid loop (paging)
        cols = 4
        rows = 3
        idx = 0
        offset = 0
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            items = build_items_list()
            total = len(items)
            if total == 0:
                return
            page_size = rows * cols
            idx = max(0, min(idx, total - 1))
            # ensure offset keeps selected in current page
            offset = (idx // page_size) * page_size

            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_F5):
                        return
                    elif ev.key in (pygame.K_LEFT, pygame.K_a):
                        idx = (idx - 1) % total
                    elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                        idx = (idx + 1) % total
                    elif ev.key in (pygame.K_UP, pygame.K_w):
                        idx = (idx - cols) % total
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        idx = (idx + cols) % total
                    elif ev.key == pygame.K_PAGEUP:
                        offset = max(0, offset - page_size)
                        idx = offset
                    elif ev.key == pygame.K_PAGEDOWN:
                        offset = min(max(0, total - page_size), offset + page_size)
                        idx = offset
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        it = items[idx]
                        if it.get('kind') == 'control' and it.get('key') == '__CLOSE__':
                            return
                        act = it.get('action')
                        if act:
                            try:
                                act()
                            except Exception:
                                pass

            self.draw()
            _draw_item_grid_overlay(items, idx, cols=cols, title="Give Items", offset=offset, rows=rows)
            pygame.display.flip()

    def _adjust_overlay_opacity(self, delta: float):
        """Adjust area overlay opacity by delta and clamp between 0.0 and 1.0."""
        self.debug_area_overlay_opacity = max(0.0, min(1.0, self.debug_area_overlay_opacity + delta))
        # Show floating message
        floating.append(DamageNumber(
            self.player.rect.centerx,
            self.player.rect.top - 12,
            f"Overlay opacity: {self.debug_area_overlay_opacity:.2f}",
            (200, 220, 255)
        ))

    def _draw_debug_overlay(self, options, selected, title="Debugger", offset=0, visible=9):
        """Draw the debug option overlay once (non-recursive).

        This overlay supports a new 'section' entry type which renders as a
        non-selectable header. Toggle/info/action entries render as rows.
        """
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(WIDTH//2 - 260, HEIGHT//2 - 220, 520, 440)
        pygame.draw.rect(self.screen, (28, 28, 36), panel, border_radius=12)
        pygame.draw.rect(self.screen, (140, 140, 150), panel, width=1, border_radius=12)

        # Title band
        title_band = pygame.Rect(panel.x, panel.y, panel.width, 64)
        pygame.draw.rect(self.screen, (40, 40, 48), title_band, border_radius=12)
        draw_text(self.screen, title, (panel.x + 24, panel.y + 16), (245,245,245), size=28, bold=True)
        info = "Arrows = Navigate | Enter = Activate | Esc/F5 = Close"
        draw_text(self.screen, info, (panel.x + 24, panel.bottom - 32), (190,190,200), size=14)

        line_h = 36
        visible = max(1, visible)
        subset = options[offset:offset+visible]

        for i, opt in enumerate(subset):
            global_idx = offset + i
            y = panel.y + 80 + i * line_h

            if opt.get('type') == 'section':
                # Section header (non-selectable)
                hdr_rect = pygame.Rect(panel.x + 20, y, panel.width - 40, line_h - 6)
                pygame.draw.rect(self.screen, (36,36,44), hdr_rect, border_radius=6)
                draw_text(self.screen, str(opt.get('label', '')).upper(), (hdr_rect.x + 10, hdr_rect.y + 6), (200,200,220), size=16, bold=True)
                # small separator line
                pygame.draw.line(self.screen, (60,60,70), (hdr_rect.x, hdr_rect.y + hdr_rect.height + 6), (hdr_rect.right, hdr_rect.y + hdr_rect.height + 6), 1)
                continue

            row = pygame.Rect(panel.x + 20, y, panel.width - 40, line_h - 6)
            is_selected = (global_idx == selected)
            bg_col = (70, 70, 90) if is_selected else (48, 48, 60)
            pygame.draw.rect(self.screen, bg_col, row, border_radius=8)

            text = opt.get('label', '')
            if opt.get('type') == 'toggle':
                try:
                    state = 'ON' if opt['getter']() else 'OFF'
                except Exception:
                    state = 'ERR'
                right_text = state
            elif opt.get('type') == 'info':
                try:
                    right_text = str(opt['getter']())
                except Exception:
                    right_text = 'ERR'
            else:
                right_text = ''

            # Left label and optional right-aligned status
            draw_text(self.screen, text, (row.x + 12, row.y + 6), (230,230,230), size=18)
            if right_text:
                # draw right-aligned status
                rt_w = self.font_small.render(right_text, True, (220,220,220)).get_width()
                draw_text(self.screen, right_text, (row.right - rt_w - 8, row.y + 6), (200,200,220), size=16)

            # Highlight selection with a rounded box outline
            if is_selected:
                try:
                    pygame.draw.rect(self.screen, (120,200,255), row, width=2, border_radius=8)
                except Exception:
                    # Fallback: draw simple rect if rounded rect unsupported
                    pygame.draw.rect(self.screen, (120,200,255), row, width=2)

        # Do not call self.draw() or recurse here — caller manages game draw and display flip.
        return

    def _run_debug_option_menu(self, options, title="Debugger"):
        """Run the debug menu input loop. Non-selectable 'section' entries are skipped."""
        # Helper to find nearest selectable index (direction: +1 or -1)
        def find_selectable(start_idx, direction):
            if not options:
                return 0
            n = len(options)
            idx = start_idx % n
            for _ in range(n):
                if options[idx].get('type') != 'section':
                    return idx
                idx = (idx + direction) % n
            return start_idx % n

        idx = find_selectable(0, 1)
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
                        # move to previous selectable
                        prev = (idx - 1) % len(options)
                        idx = find_selectable(prev, -1)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        nxt = (idx + 1) % len(options)
                        idx = find_selectable(nxt, 1)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        opt = options[idx]
                        if opt.get('type') == 'toggle':
                            try:
                                opt['setter'](not opt['getter']())
                            except Exception:
                                pass
                        elif opt.get('type') == 'action' and opt.get('action'):
                            try:
                                opt['action']()
                            except Exception:
                                pass
                        if opt.get('close'):
                            return

            # Ensure offset keeps selected in view
            if idx < offset:
                offset = idx
            elif idx >= offset + visible:
                offset = idx - visible + 1

            self.draw()
            self._draw_debug_overlay(options, idx, title=title, offset=offset, visible=visible)
            pygame.display.flip()

    def debug_teleport_menu(self):
        """
        Teleport debug menu.

        - For legacy/static levels: behaves as before and wraps using ROOM_COUNT.
        - For PCG levels: presents a flattened list of all PCG rooms (Level, RoomCode)
          and allows navigation and teleport to any PCG room.
        """
        # PCG-aware flow
        if getattr(self, 'use_pcg', False):
            try:
                from src.level.level_loader import list_all_levels, level_loader
                levels = list_all_levels()
                rooms = []
                for lid in levels:
                    rcodes = level_loader.list_rooms_in_level(lid)
                    for rc in rcodes:
                        rooms.append((lid, rc))
            except Exception:
                rooms = []

            if not rooms:
                # Fallback to legacy behaviour when no PCG rooms available
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
                return

            # Find starting index: prefer current room if available
            cur_level = getattr(self.level, 'level_id', None)
            cur_code = getattr(self.level, 'room_code', None)
            start_idx = 0
            for i, (lid, rcode) in enumerate(rooms):
                if lid == cur_level and rcode == cur_code:
                    start_idx = i
                    break
            idx = start_idx

            total = len(rooms)
            while True:
                dt = self.clock.tick(FPS) / 1000.0
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        pygame.quit(); sys.exit()
                    elif ev.type == pygame.KEYDOWN:
                        if ev.key in (pygame.K_ESCAPE, pygame.K_F5):
                            return
                        elif ev.key in (pygame.K_LEFT, pygame.K_a):
                            idx = (idx - 1) % total
                        elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                            idx = (idx + 1) % total
                        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                            level_id, room_code = rooms[idx]
                            try:
                                # Load the target PCG room and update all related state
                                self._load_pcg_level(level_id, room_code, initial=False)

                                # Clear transient visuals and hitboxes
                                from src.entities.entities import hitboxes, floating
                                hitboxes.clear()
                                floating.clear()

                                # Sync enemies from new level
                                self.enemies = getattr(self.level, 'enemies', []) or []

                                # Reset camera to player after placing player at spawn
                                # Prefer spawn_tile from level_loader if present
                                try:
                                    from src.level.level_loader import level_loader
                                    room_meta = level_loader.get_room(level_id, room_code)
                                    if room_meta and getattr(room_meta, 'spawn_tile', None):
                                        tx, ty = room_meta.spawn_tile
                                        self.player.rect.centerx = tx * TILE + TILE // 2
                                        self.player.rect.centery = ty * TILE + TILE // 2
                                    else:
                                        sx, sy = getattr(self.level, 'spawn', (100, 100))
                                        self.player.rect.topleft = (sx, sy)
                                except Exception:
                                    sx, sy = getattr(self.level, 'spawn', (100, 100))
                                    self.player.rect.topleft = (sx, sy)

                                # Reset camera to center on player immediately
                                self.camera = Camera()
                                self.camera.update(self.player.rect, 0)

                                # Update current level number for UI and state
                                try:
                                    self.current_level_number = int(level_id)
                                except Exception:
                                    self.current_level_number = getattr(self.level, 'level_id', self.current_level_number)

                                # Reinitialize door system for new room
                                try:
                                    from src.level.door_system import DoorSystem
                                    if hasattr(self, '_door_system') and self._door_system:
                                        self._door_system.load_room(self.level.level_id, self.level.room_code)
                                    else:
                                        self._door_system = DoorSystem()
                                        self._door_system.load_room(self.level.level_id, self.level.room_code)
                                except Exception:
                                    # ignore door system errors but log
                                    logger.exception("Door system reinit failed for %s/%s", getattr(self.level,'level_id', None), getattr(self.level,'room_code', None))

                                # Clear any interaction prompt
                                self.interaction_prompt = None
                                self.interaction_position = None

                                # Ensure player state is stable
                                try:
                                    self.player.stunned = 0
                                except Exception:
                                    pass

                                # Notify user visually and log
                                try:
                                    floating.append(DamageNumber(self.player.rect.centerx, self.player.rect.top - 12, f"Teleported to L{level_id} {room_code}", (160,220,255)))
                                except Exception:
                                    pass
                                logger.info("Teleported to PCG room %s/%s", level_id, room_code)

                            except Exception:
                                logger.exception("Failed to teleport to PCG room: %s/%s", level_id, room_code)
                            return

                self.draw()
                self._draw_pcg_level_select_overlay(rooms[idx], idx, total)
                pygame.display.flip()
            return

        # Legacy/static fallback
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

    def _draw_pcg_level_select_overlay(self, room_tuple, idx, total):
        """
        Draw a cleaner overlay for PCG room selection with header band and level badge.

        Args:
            room_tuple: (level_id, room_code)
            idx: flattened index
            total: total number of PCG rooms
        """
        from src.level.level_loader import level_loader
        # Backdrop
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((12, 14, 20, 200))
        self.screen.blit(overlay, (0, 0))

        # Panel shadow + body
        panel_w, panel_h = 540, 300
        panel_x = (WIDTH - panel_w) // 2
        panel_y = (HEIGHT - panel_h) // 2
        shadow = pygame.Rect(panel_x + 6, panel_y + 8, panel_w, panel_h)
        pygame.draw.rect(self.screen, (0, 0, 0, 220), shadow, border_radius=14)
        panel = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        pygame.draw.rect(self.screen, (26, 28, 36), panel, border_radius=14)
        pygame.draw.rect(self.screen, (140, 140, 150), panel, width=1, border_radius=14)

        # Header band
        level_id, room_code = room_tuple
        try:
            # level color derived deterministically from level id
            lc = (120 + (int(level_id) * 47) % 100, 110, 170)
        except Exception:
            lc = (120, 110, 170)
        header = pygame.Rect(panel.x, panel.y, panel.width, 64)
        pygame.draw.rect(self.screen, lc, header, border_radius=12)
        # Header title
        draw_text(self.screen, "Teleport to PCG Room", (panel.x + 20, panel.y + 14), (245, 245, 250), size=22, bold=True)

        # Level badge
        badge_w, badge_h = 88, 40
        badge = pygame.Rect(panel.x + 20, panel.y + 90 - 10, badge_w, badge_h)
        pygame.draw.rect(self.screen, lc, badge, border_radius=8)
        pygame.draw.rect(self.screen, (255,255,255,40), badge, width=1, border_radius=8)
        draw_text(self.screen, f"L{level_id}", (badge.x + 14, badge.y + 8), (245,245,245), size=20, bold=True)

        # Main room label
        room_name = f"Room {room_code}"
        draw_text(self.screen, room_name, (badge.right + 16, panel.y + 78), (230,230,235), size=28, bold=True)

        # Local index info (try fetch)
        local_idx = None
        rcount = None
        try:
            rlist = level_loader.list_rooms_in_level(int(level_id))
            rcount = len(rlist)
            if room_code in rlist:
                local_idx = rlist.index(room_code) + 1
        except Exception:
            rlist = None

        # Subtext: position in level and overall count
        sub_x = badge.right + 16
        sub_y = panel.y + 118
        if local_idx is not None and rcount is not None:
            draw_text(self.screen, f"{local_idx}/{rcount} in Level {level_id}", (sub_x, sub_y), (200,200,210), size=16)
        draw_text(self.screen, f"PCG: {idx+1}/{total}", (panel.right - 140, panel.y + 78), (200,200,210), size=18)

        # Help text
        draw_text(self.screen, "← / → to choose  •  Enter to teleport  •  Esc to cancel", (panel.x + 20, panel.bottom - 42), (170,180,200), size=14)

        # Decorative separators
        pygame.draw.line(self.screen, (60,60,70), (panel.x + 20, panel.y + 64), (panel.right - 20, panel.y + 64), 1)

        # Optionally show a tiny preview: show tile coords under spawn if available
        try:
            room = level_loader.get_room(int(level_id), str(room_code))
            if room and getattr(room, 'spawn_tile', None):
                sx, sy = room.spawn_tile
                draw_text(self.screen, f"Spawn tile: ({sx}, {sy})", (panel.x + 20, panel.y + 148), (200,200,210), size=14)
        except Exception:
            pass

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

    def _handle_door_interactions(self):
        """Handle proximity-based door interactions."""
        # Get current tile grid from level (if available)
        tile_grid = getattr(self.level, "tile_grid", None)
        if not tile_grid:
            return
        
        # Check if E key was pressed this frame
        keys = pygame.key.get_pressed()
        is_e_pressed = keys[pygame.K_e]
        
        # Use PCG door system if available
        if self.use_pcg and hasattr(self.level, 'level_id') and hasattr(self.level, 'room_code'):
            from src.level.door_system import DoorSystem
            # Ensure door system exists and is synced to current room each frame
            if not hasattr(self, '_door_system') or self._door_system is None:
                self._door_system = DoorSystem()
            try:
                # Only sync DoorSystem when the room actually changed to avoid
                # redundant per-frame reloads. Prefer `set_current_tiles` when
                # available; fall back to `load_room` for compatibility.
                if (getattr(self._door_system, 'current_level_id', None) != getattr(self.level, 'level_id', None)
                    or getattr(self._door_system, 'current_room_code', None) != getattr(self.level, 'room_code', None)):
                    try:
                        self._door_system.set_current_tiles(self.level.level_id, self.level.room_code, getattr(self.level, 'tile_grid', None))
                    except Exception:
                        try:
                            self._door_system.load_room(self.level.level_id, self.level.room_code)
                        except Exception:
                            logger.exception("Failed to sync DoorSystem to current room %s/%s", getattr(self.level,'level_id', None), getattr(self.level,'room_code', None))
            except Exception:
                logger.exception("Failed to sync DoorSystem to current room %s/%s", getattr(self.level,'level_id', None), getattr(self.level,'room_code', None))

            except Exception:
                logger.exception("Failed to sync DoorSystem to current room %s/%s", getattr(self.level,'level_id', None), getattr(self.level,'room_code', None))

            # Handle door interaction using PCG system
            result = self._door_system.handle_door_interaction(
                player_rect=self.player.rect,
                tile_size=TILE,
                is_e_pressed=is_e_pressed
            )
            
            if result:
                self.interaction_prompt, interaction_x, interaction_y = result
                self.interaction_position = (interaction_x, interaction_y)

                # Show prompt; validate at the moment of E-press before transitioning.
                if is_e_pressed:
                    try:
                        from src.tiles.tile_types import TileType
                        grid = getattr(self.level, 'tile_grid', None)
                        valid = False
                        if grid is not None:
                            # Check a small neighborhood around the prompt position to tolerate offsets
                            tx_center = int(interaction_x // TILE)
                            ty_center = int(interaction_y // TILE)
                            for dx in (-1, 0, 1):
                                for dy in (-1, 0, 1):
                                    tx = tx_center + dx
                                    ty = ty_center + dy
                                    if 0 <= ty < len(grid) and 0 <= tx < len(grid[0]):
                                        val = grid[ty][tx]
                                        if val in (TileType.DOOR_ENTRANCE.value, TileType.DOOR_EXIT_1.value, TileType.DOOR_EXIT_2.value):
                                            valid = True
                                            break
                                if valid:
                                    break
                        if not valid:
                            logger.debug("Door E-press ignored: no door tile near prompt coords %s,%s", interaction_x, interaction_y)
                            # clear prompt to avoid confusing stale prompts
                            self.interaction_prompt = None
                            self.interaction_position = None
                            return
                    except Exception:
                        logger.exception("Door validation failed; proceeding permissively")

                    # Proceed with transition using DoorSystem's recorded planned transition
                    transition = None
                    try:
                        transition = self._door_system.pop_last_transition()
                    except Exception:
                        # Fallback: try to use get_current_room_info if pop not available
                        try:
                            room_info = self._door_system.get_current_room_info()
                            if room_info:
                                transition = {
                                    'level_id': room_info.get('level_id'),
                                    'room_code': room_info.get('room_code'),
                                    'spawn': None,
                                }
                        except Exception:
                            transition = None

                    if transition:
                        cur_code = getattr(self.level, 'room_code', None)
                        cur_level_id = getattr(self.level, 'level_id', None)
                        target_level = transition.get('level_id')
                        target_room = transition.get('room_code')

                        if cur_code == target_room and cur_level_id == target_level:
                            logger.info("Door interaction target equals current room (%s/%s); ignoring reload", cur_level_id, cur_code)
                        else:
                            logger.info("Attempting PCG room load: %s/%s -> target %s/%s", cur_level_id, cur_code, target_level, target_room)
                            try:
                                self._load_pcg_level(target_level, target_room, initial=False)
                            except Exception:
                                logger.exception("_load_pcg_level raised an exception for %s/%s", target_level, target_room)

                            # Verify load succeeded
                            loaded_code = getattr(self.level, 'room_code', None)
                            loaded_level = getattr(self.level, 'level_id', None)
                            if loaded_code != target_room or loaded_level != target_level:
                                logger.error("PCG load mismatch: expected %s/%s but level is %s/%s", target_level, target_room, loaded_level, loaded_code)
                            else:
                                logger.info("Loaded PCG room successfully: %s/%s", loaded_level, loaded_code)

                            # Sync transient state: enemies, hitboxes, floating, camera, door system
                            try:
                                from src.entities.entities import hitboxes, floating
                                hitboxes.clear()
                                floating.clear()
                            except Exception:
                                logger.debug("Failed to clear hitboxes/floating after PCG load")

                            try:
                                self.enemies = getattr(self.level, 'enemies', []) or []
                            except Exception:
                                logger.debug("Failed to sync enemies after PCG load")

                            # Position player at spawn (prefer transition.spawn, then door system, then level.spawn)
                            try:
                                spawn_point = transition.get('spawn') if isinstance(transition, dict) else None
                                if not spawn_point and hasattr(self, '_door_system') and self._door_system:
                                    try:
                                        spawn_point = self._door_system.get_spawn_point()
                                    except Exception:
                                        spawn_point = None
                                if not spawn_point:
                                    spawn_point = getattr(self.level, 'spawn', None)
                                if spawn_point:
                                    if isinstance(spawn_point, (tuple, list)):
                                        self.player.rect.topleft = (spawn_point[0], spawn_point[1])
                            except Exception:
                                logger.exception("Failed to position player after PCG load")

                            # Reset camera immediately
                            try:
                                self.camera = Camera()
                                self.camera.update(self.player.rect, 0)
                            except Exception:
                                logger.exception("Failed to reset camera after PCG load")

                            # Update door system to match new room
                            try:
                                if hasattr(self, '_door_system') and self._door_system:
                                    self._door_system.load_room(target_level, target_room)
                            except Exception:
                                logger.exception("DoorSystem.load_room after main load failed")

                            # Clear any interaction prompt/state
                            self.interaction_prompt = None
                            self.interaction_position = None

                            # Check if this is a level transition (different level_id) or specific room transitions and trigger shop
                            try:
                                should_trigger_shop = False
                                
                                # Trigger shop when moving between levels
                                if cur_level_id != target_level:
                                    should_trigger_shop = True
                                # OR trigger shop based on room pattern within same level
                                else:
                                    # Get the actual room_index from the target room data
                                    target_room_code = transition.get('room_code', '')
                                    target_level_id = transition.get('level_id')
                                    
                                    # Try to get the room data to access the room_index field
                                    try:
                                        from src.level.level_loader import level_loader
                                        target_room_data = level_loader.get_room(target_level_id, target_room_code)
                                        if target_room_data and hasattr(target_room_data, 'room_index'):
                                            room_index = target_room_data.room_index
                                            
                                            # Shop pattern: trigger shop for specific room number indices
                                            # This means: Room 1(index 0)=shop, Room 2(index 1)=shop, Room 3(index 2)=no shop, 
                                            # Room 4(index 3)=shop, Room 5(index 4)=no shop, Room 6(index 5)=shop
                                            # Note: Rooms 2A and 2B both have index 1, so both get shop or no shop together
                                            shop_room_indices = [0, 1, 3, 5]  # Room number indices that should have shops
                                            if room_index in shop_room_indices:
                                                should_trigger_shop = True
                                                logger.info(f"Shop triggered for room {target_room_code} (room number index {room_index})")
                                        else:
                                            # Fallback to room code parsing if room data not available
                                            logger.warning(f"Could not get room_index for {target_room_code}, using fallback logic")
                                            # Extract room number from room code (e.g., "2A" -> 2, then subtract 1 for 0-based index)
                                            import re
                                            match = re.match(r'(\d+)[A-Za-z]+', target_room_code)
                                            if match:
                                                room_number = int(match.group(1)) - 1  # Convert to 0-based room number index
                                                shop_room_indices = [0, 1, 3, 5]
                                                if room_number in shop_room_indices:
                                                    should_trigger_shop = True
                                                    logger.info(f"Shop triggered via fallback for room {target_room_code} (room number index {room_number})")
                                    except Exception as e:
                                        logger.exception(f"Error getting room data for {target_room_code}: {e}")
                                        # Fallback to room number parsing
                                        import re
                                        match = re.match(r'(\d+)[A-Za-z]+', target_room_code)
                                        if match:
                                            room_number = int(match.group(1)) - 1  # Convert to 0-based room number index
                                            shop_room_indices = [0, 1, 3, 5]
                                            if room_number in shop_room_indices:
                                                should_trigger_shop = True
                                                logger.info(f"Shop triggered via exception fallback for room {target_room_code} (room number index {room_number})")
                                
                                if should_trigger_shop:
                                    self._trigger_shop_after_level_transition()
                            except Exception:
                                logger.exception("Failed to trigger shop after level transition")
                    else:
                        self.interaction_prompt = None
                        self.interaction_position = None
                    return
        
        # Legacy door system for non-PCG levels
        def on_door_interact(tile_data, tile_pos):
            target = parse_door_target(tile_data.interaction.on_interact_id)
            if target:
                level_name, entrance_id = target
                self._transition_to_level(level_name, entrance_id)
        
        # Check for proximity interactions
        result = handle_proximity_interactions(
            player_rect=self.player.rect,
            tile_grid=tile_grid,
            tile_size=TILE,
            is_e_pressed=is_e_pressed,
            on_interact=on_door_interact
        )
        
        if result:
            self.interaction_prompt, interaction_x, interaction_y = result
            self.interaction_position = (interaction_x, interaction_y)
        else:
            self.interaction_prompt = None
            self.interaction_position = None
    
    def _get_room_index_from_code(self, room_code: str) -> int:
        """
        Convert room code (like '1A', '2B', etc.) to a zero-based room index.
        
        Args:
            room_code: Room code like '1A', '2B', etc.
            
        Returns:
            int: Zero-based room index (0 for first room, 1 for second, etc.)
        """
        try:
            if not room_code:
                return 0
            
            # Extract the numeric part (level number) and letter part (room letter)
            import re
            match = re.match(r'(\d+)([A-Za-z]+)', room_code)
            if match:
                level_num = int(match.group(1)) - 1  # Convert to 0-based level
                room_letter = match.group(2).upper()
                room_letter_index = ord(room_letter) - ord('A')  # A=0, B=1, C=2, etc.
                
                # Ensure room_letter_index is within valid range (0-25 for A-Z)
                room_letter_index = max(0, min(25, room_letter_index))
                
                # For simplicity, assume sequential rooms across levels
                # This gives us: 1A=0, 1B=1, 1C=2, 2A=3, 2B=4, etc.
                return level_num * 26 + room_letter_index
            else:
                # Fallback: try to extract any digits
                digits = ''.join(filter(str.isdigit, room_code))
                return int(digits) - 1 if digits else 0
        except Exception:
            # Fallback to 0 if anything goes wrong
            return 0

    def _trigger_shop_after_level_transition(self):
        """Trigger shop after completing a level transition."""
        try:
            # Check if player has enough health to shop (optional)
            if hasattr(self.player, 'max_hp') and hasattr(self.player, 'hp'):
                if self.player.hp <= 0:
                    return  # Don't show shop if player is dead
            
            # Open shop immediately
            if hasattr(self, 'shop') and self.shop:
                logger.info("Opening shop after level transition")
                self.shop.open_shop()
                # Show a notification
                try:
                    from src.entities.entities import floating, DamageNumber
                    floating.append(DamageNumber(
                        self.player.rect.centerx,
                        self.player.rect.top - 20,
                        "Shop Available!",
                        (100, 255, 150)
                    ))
                except Exception:
                    pass
            else:
                logger.warning("Shop not available for triggering")
            
        except Exception as e:
            logger.exception("Failed to trigger shop after level transition")

    def _transition_to_level(self, level_name: str, entrance_id: str):
        """Transition to a new level and spawn at specific entrance."""
        # For now, treat level_name as room index for legacy system
        # In future, this could load actual level files
        try:
            room_index = int(level_name.replace("Level", "")) - 1
            room_index = max(0, min(room_index, ROOM_COUNT - 1))
        except (ValueError, AttributeError):
            # Fallback to next room if parsing fails
            room_index = (self.level_index + 1) % ROOM_COUNT
        
        # Load target level
        self._load_level(room_index)
        
        # Find spawn point for specified entrance
        spawn_pos = find_spawn_point(
            getattr(self.level, "tile_grid", []),
            entrance_id
        )
        
        if spawn_pos:
            tx, ty = spawn_pos
            self.player.rect.centerx = tx * TILE + TILE // 2
            self.player.rect.centery = ty * TILE + TILE // 2
        else:
            # Fallback to default spawn
            sx, sy = getattr(self.level, "spawn", (100, 100))
            self.player.rect.topleft = (sx, sy)


if __name__ == '__main__':
    Game().run()