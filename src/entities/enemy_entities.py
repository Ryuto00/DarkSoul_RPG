from __future__ import annotations

import math
import random
import pygame
from typing import Optional

from config import (
    FPS, GRAVITY, TERMINAL_VY, PLAYER_SPEED, PLAYER_AIR_SPEED, PLAYER_JUMP_V,
    PLAYER_SMALL_JUMP_CUT, COYOTE_FRAMES, JUMP_BUFFER_FRAMES,
    DASH_SPEED, DASH_TIME, DASH_COOLDOWN, INVINCIBLE_FRAMES,
    DOUBLE_JUMPS,
    ATTACK_COOLDOWN, ATTACK_LIFETIME, COMBO_RESET, SWORD_DAMAGE,
    POGO_BOUNCE_VY, ACCENT, GREEN, CYAN, RED, WHITE, IFRAME_BLINK_INTERVAL
)
from src.core.utils import los_clear, find_intermediate_visible_point, find_idle_patrol_target
from src.entities.entity_common import Hitbox, DamageNumber, hitboxes, floating, in_vision_cone
from src.entities.player_entity import Player
from src.ai.enemy_movement import MovementStrategyFactory
from src.entities.components.combat_component import CombatComponent


class Enemy:
    """Base class for all enemy types with shared functionality."""
    
    def __init__(self, x, ground_y, width, height, combat_config, vision_range=200, cone_half_angle=math.pi/6, turn_rate=0.05):
        # Basic properties
        self.rect = pygame.Rect(x - width//2, ground_y - height, width, height)
        self.vx = 0
        self.vy = 0
        
        # Unified combat state via component
        self.combat = CombatComponent(self, combat_config)
        self.alive = self.combat.alive
        
        # Vision cone properties
        self.vision_range = vision_range
        self.cone_half_angle = cone_half_angle
        self.turn_rate = turn_rate
        self.facing = 1  # 1 for right, -1 for left
        self.facing_angle = 0 if self.facing > 0 else math.pi
        
        # Status effects
        self.slow_mult = 1.0
        self.slow_remaining = 0
        self.stunned = 0
        
        # AI state (for enemies that need it)
        self.state = 'idle'
        self.home = (self.rect.centerx, self.rect.centery)
        self.target = None
        self.last_seen = None
        self.repath_t = 0
        
        # New movement system properties
        self.movement_strategy = None
        self.speed_multiplier = 1.0
        self.terrain_traits = self._get_terrain_traits()
        self.on_ground = False
        self.base_speed = 1.0
        self.iframes_flash = False
        self.draw_border_radius = 4
        
        # Physics properties
        self.friction = 0.8
        self.gravity_affected = True
        self.sliding = False
        self.stuck = False
        self.stuck_timer = 0
        
        # Set movement strategy based on enemy type
        self._set_movement_strategy()
    
    def _get_terrain_traits(self):
        """Define terrain access traits for each enemy type"""
        return ['ground']  # Default
    
    def _initialize_movement_strategy(self):
        """Initialize movement strategy - to be overridden by subclasses"""
        # Default to ground patrol
        self.movement_strategy = MovementStrategyFactory.create_strategy('ground_patrol')
    
    def _set_movement_strategy(self):
        """Set movement strategy based on enemy type"""
        # This will be overridden by specific enemy classes
        # Initialize movement strategy as fallback
        self._initialize_movement_strategy()
    
    def update_vision_cone(self, player_pos):
        """Update facing direction based on player position."""
        epos = (self.rect.centerx, self.rect.centery)
        ppos = player_pos
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # Update facing direction
        if dist_to_player > 0:
            # Calculate angle to player
            angle_to_player = math.atan2(dy, dx)
            
            # Update facing if player is within 1.2-1.5x vision_range
            if dist_to_player < self.vision_range * 1.5:
                # Smoothly turn toward player
                angle_diff = (angle_to_player - self.facing_angle) % (2 * math.pi)
                if angle_diff > math.pi:
                    angle_diff -= 2 * math.pi
                self.facing_angle += angle_diff * self.turn_rate
                
                # Update facing direction based on angle
                self.facing = 1 if math.cos(self.facing_angle) > 0 else -1
            else:
                # Idle/patrol: subtle oscillation
                self.facing_angle += 0.02 * self.facing
                # Flip at bounds
                if self.facing_angle > math.pi:
                    self.facing_angle = math.pi
                    self.facing = -1
                elif self.facing_angle < 0:
                    self.facing_angle = 0
                    self.facing = 1
        
        return dist_to_player
    
    def check_vision_cone(self, level, player_pos):
        """Check if player is in vision cone and has line of sight."""
        epos = (self.rect.centerx, self.rect.centery)
        ppos = player_pos
        
        # Check if player is in vision cone
        in_cone = in_vision_cone(epos, ppos, self.facing_angle, self.cone_half_angle, self.vision_range)
        has_los = in_cone and los_clear(level, epos, ppos)
        
        # Store for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        
        return has_los, in_cone
    
    def handle_status_effects(self):
        """Handle DOT and slow effects including poison, burn, bleed."""
        # Initialize status effect attributes if not present
        if not hasattr(self, 'poison_stacks'):
            self.poison_stacks = 0
            self.poison_dps = 0.0
            self.poison_remaining = 0
        if not hasattr(self, 'burn_dps'):
            self.burn_dps = 0.0
            self.burn_remaining = 0
        if not hasattr(self, 'bleed_dps'):
            self.bleed_dps = 0.0
            self.bleed_remaining = 0
        if not hasattr(self, 'frozen'):
            self.frozen = False
        
        # Original DOT handling (cold feet)
        if getattr(self, 'dot_remaining', 0) > 0:
            per_frame = getattr(self, 'dot_dps', 0) / FPS
            self.dot_accum = getattr(self, 'dot_accum', 0.0) + per_frame
            if self.dot_accum >= 1.0:
                dmg = int(self.dot_accum)
                self.dot_accum -= dmg
                # Use the combat component to take DOT damage
                self.combat.take_damage(dmg)
            self.dot_remaining -= 1
        
        # Poison damage
        if getattr(self, 'poison_remaining', 0) > 0:
            per_frame = getattr(self, 'poison_dps', 0) / FPS
            self.dot_accum = getattr(self, 'dot_accum', 0.0) + per_frame
            if self.dot_accum >= 1.0:
                dmg = int(self.dot_accum)
                self.dot_accum -= dmg
                self.combat.take_damage(dmg)
            self.poison_remaining -= 1
            if self.poison_remaining <= 0:
                self.poison_stacks = 0
                self.poison_dps = 0.0
        
        # Burn damage
        if getattr(self, 'burn_remaining', 0) > 0:
            per_frame = getattr(self, 'burn_dps', 0) / FPS
            self.dot_accum = getattr(self, 'dot_accum', 0.0) + per_frame
            if self.dot_accum >= 1.0:
                dmg = int(self.dot_accum)
                self.dot_accum -= dmg
                self.combat.take_damage(dmg)
            self.burn_remaining -= 1
        
        # Bleed damage
        if getattr(self, 'bleed_remaining', 0) > 0:
            per_frame = getattr(self, 'bleed_dps', 0) / FPS
            self.dot_accum = getattr(self, 'dot_accum', 0.0) + per_frame
            if self.dot_accum >= 1.0:
                dmg = int(self.dot_accum)
                self.dot_accum -= dmg
                self.combat.take_damage(dmg)
            self.bleed_remaining -= 1
        
        # Slow timer
        if getattr(self, 'slow_remaining', 0) > 0:
            self.slow_remaining -= 1
            if self.slow_remaining <= 0:
                self.slow_mult = 1.0
        
        # Clear frozen state if stun expires
        if getattr(self, 'frozen', False) and getattr(self, 'stunned', 0) <= 0:
            self.frozen = False
    
    def hit(self, hb: Hitbox, player: Player):
        """Handle being hit by a player attack."""
        self.combat.handle_hit_by_player_hitbox(hb)
    
    def handle_movement(self, level, player=None, speed_multiplier=1.0):
        """Handle movement using enemy-specific hardcoded behaviors."""
        # Apply all speed modifiers (no terrain effects)
        actual_speed = speed_multiplier * self.speed_multiplier * getattr(self, 'slow_mult', 1.0)
        
        # Use movement strategy if available
        if self.movement_strategy:
            context = self._create_movement_context(level, player)
            self.movement_strategy.move(self, level, player, context)
        else:
            # Fallback to original movement
            self._fallback_movement(level, actual_speed)
    
    def _create_movement_context(self, level, player=None):
        """Create context dictionary for movement strategy"""
        # Calculate distance to player if available
        distance_to_player = 0
        if player:
            dx = player.rect.centerx - self.rect.centerx
            dy = player.rect.centery - self.rect.centery
            distance_to_player = (dx*dx + dy*dy) ** 0.5
        
        context = {
            'player': player,
            'has_los': getattr(self, '_has_los', False),
            'distance_to_player': distance_to_player,
            'level': level
        }
        return context
    
    def _handle_inaccessible_terrain(self, level):
        """Handle when enemy encounters inaccessible terrain"""
        self.vx = 0
        self.vy = 0
        
        # Try to find alternative path (no terrain system)
        if hasattr(self, 'target') and self.target:
            # Ensure target is a tuple
            if isinstance(self.target, tuple):
                target_pos = self.target
            else:
                # Convert to tuple if needed
                target_pos = (self.target[0] if hasattr(self.target, '__getitem__') else self.target.rect.centerx,
                             self.target[1] if hasattr(self.target, '__getitem__') else self.target.rect.centery)
            
            # Simple pathfinding without terrain system
            alt_path = self._find_simple_alternative_path(
                (self.rect.centerx, self.rect.centery),
                target_pos, level
            )
            if alt_path:
                self.target = alt_path[0] if alt_path else None
    
    def _fallback_movement(self, level, actual_speed):
        """Fallback movement for enemies without strategy"""
        # Move horizontally
        self.rect.x += int(self.vx * actual_speed)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx > 0:
                    self.rect.right = s.left
                else:
                    self.rect.left = s.right
                self.vx *= -1  # Bounce off walls
    
    def _find_simple_alternative_path(self, start_pos: tuple, goal_pos, level) -> Optional[list]:
        """Simple alternative pathfinding without terrain system"""
        # Simple implementation - try to find path around obstacles
        # Convert goal_pos to tuple if it's not already
        if hasattr(goal_pos, 'rect'):
            # It's an enemy or player object
            goal_tuple = (goal_pos.rect.centerx, goal_pos.rect.centery)
        elif isinstance(goal_pos, (list, tuple)) and len(goal_pos) >= 2:
            # It's already a coordinate
            goal_tuple = (int(goal_pos[0]), int(goal_pos[1]))
        else:
            # Fallback
            goal_tuple = start_pos
        
        # Try direct path first
        if self._is_path_clear(start_pos, goal_tuple, level):
            return [goal_tuple]
        
        # Simple waypoint-based pathfinding
        current = start_pos
        path = []
        
        # Try going around from perpendicular directions
        dx = goal_tuple[0] - current[0]
        dy = goal_tuple[1] - current[1]
        
        if abs(dx) > abs(dy):
            # Try going up or down first
            for offset in [-100, 100]:
                waypoint = (current[0], current[1] + offset)
                if self._is_valid_waypoint(waypoint, level):
                    path.append(waypoint)
                    break
        else:
            # Try going left or right first
            for offset in [-100, 100]:
                waypoint = (current[0] + offset, current[1])
                if self._is_valid_waypoint(waypoint, level):
                    path.append(waypoint)
                    break
        
        path.append(goal_tuple)
        return path if len(path) > 1 else None
    
    def _is_path_clear(self, start: tuple, end: tuple, level) -> bool:
        """Check if path is clear for enemy"""
        steps = 20
        for i in range(steps + 1):
            t = i / steps
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            
            # Check collision with solids
            temp_rect = pygame.Rect(int(x) - self.rect.width//2, int(y) - self.rect.height//2,
                                  self.rect.width, self.rect.height)
            for s in level.solids:
                if temp_rect.colliderect(s):
                    return False
        
        return True
    
    def _is_valid_waypoint(self, position: tuple, level) -> bool:
        """Check if waypoint is valid for enemy"""
        # Simple validation - no collision with solids
        temp_rect = pygame.Rect(position[0] - self.rect.width//2, position[1] - self.rect.height//2,
                              self.rect.width, self.rect.height)
        for s in level.solids:
            if temp_rect.colliderect(s):
                return False
        return True
    
    def handle_gravity(self, level, gravity_multiplier=2.0):
        """Apply gravity and handle ground collision."""
        # Apply gravity to velocity first, then position
        self.vy = getattr(self, 'vy', 0) + min(GRAVITY * gravity_multiplier, 10)
        
        # Apply gravity to position
        old_y = self.rect.y
        self.rect.y += int(min(10, self.vy))
        
        was_on_ground = getattr(self, 'on_ground', False)
        self.on_ground = False  # Reset ground detection
        
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
                    self.vy = 0  # Reset velocity when landing
                    self.on_ground = True
    
    def draw_debug_vision(self, surf, camera, show_los=False):
        """Draw debug vision cone and LOS line."""
        if not show_los:
            return
            
        # Draw LOS line to last-checked player point if available
        if getattr(self, '_los_point', None) is not None:
            col = GREEN if getattr(self, '_has_los', False) else RED
            pygame.draw.line(surf, col, camera.to_screen(self.rect.center), camera.to_screen(self._los_point), 2)
            
            # Draw vision cone
            center = camera.to_screen(self.rect.center)
            # Calculate cone edges
            left_angle = self.facing_angle - self.cone_half_angle
            right_angle = self.facing_angle + self.cone_half_angle
            
            # Calculate end points of cone lines
            left_x = center[0] + math.cos(left_angle) * self.vision_range
            left_y = center[1] + math.sin(left_angle) * self.vision_range
            right_x = center[0] + math.cos(right_angle) * self.vision_range
            right_y = center[1] + math.sin(right_angle) * self.vision_range
            
            # Draw cone lines
            pygame.draw.line(surf, (255, 255, 0), center, (left_x, left_y), 1)
            pygame.draw.line(surf, (255, 255, 0), center, (right_x, right_y), 1)

    def draw_telegraph(self, surf, camera, text, color=(255, 80, 80)):
        from src.core.utils import draw_text
        if text:
            draw_text(surf, text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), color, size=18, bold=True)
    
    def get_status_effect_color(self, base_color):
        """Returns a color modified by current status effects.
        Priority: frozen/stunned -> blueish, burn -> orange, poison -> green, bleed -> red.
        Blends multiple effects if present. Also brightens if iframes_flash is set.
        """
        def blend(a, b, t):
            return (int(a[0] * (1.0 - t) + b[0] * t), int(a[1] * (1.0 - t) + b[1] * t), int(a[2] * (1.0 - t) + b[2] * t))
        col = base_color
        # Stunned or frozen: apply bluish tint
        if getattr(self, 'stunned', 0) > 0 or getattr(self, 'frozen', False):
            col = blend(col, (120, 180, 255), 0.5)
        # Burn
        if getattr(self, 'burn_remaining', 0) > 0:
            col = blend(col, (255, 140, 40), 0.5)
        # Poison
        if getattr(self, 'poison_remaining', 0) > 0:
            blended = blend(col, (80, 200, 80), 0.45)
            # If base color equals poison tint, brighten green channel to ensure visible change
            if blended == col:
                r, g, b = col
                blended = (r, min(255, g + 40), b)
            col = blended
        # Bleed
        if getattr(self, 'bleed_remaining', 0) > 0:
            col = blend(col, (200, 80, 80), 0.35)
        # Invincibility flash
        if getattr(self, 'iframes_flash', False):
            # simple brighten
            col = tuple(min(255, int(c * 1.25)) for c in col)
        return col

    def draw_status_effects(self, surf, camera):
        """Draw icons/text indicating active status effects above the enemy."""
        effects = []
        if getattr(self, 'stunned', 0) > 0:
            effects.append(('!', (255, 200, 80)))
        if getattr(self, 'burn_remaining', 0) > 0:
            effects.append(('F', (255, 140, 40)))
        if getattr(self, 'poison_remaining', 0) > 0:
            effects.append(('P', (120, 220, 120)))
        if getattr(self, 'bleed_remaining', 0) > 0:
            effects.append(('B', (200, 80, 80)))
        if getattr(self, 'slow_remaining', 0) > 0 and getattr(self, 'slow_mult', 1.0) < 1.0:
            effects.append(('S', (180, 200, 255)))
        if not effects:
            return
        from src.core.utils import draw_text
        # Draw them left-to-right above enemy
        x_off = -len(effects) * 8
        for (txt, col) in effects:
            pos = camera.to_screen((self.rect.centerx + x_off, self.rect.top - 14))
            draw_text(surf, txt, pos, col, size=14, bold=True)
            x_off += 16

    def draw_nametag(self, surf, camera, show_nametags=False):
        if not show_nametags:
            return
        from src.core.utils import draw_text
        # Name
        name = getattr(self, 'type', self.__class__.__name__)
        pos = camera.to_screen((self.rect.centerx-4, self.rect.top - 24))
        draw_text(surf, name, pos, (220, 240, 255), size=14, bold=True)
        # HP bar
        if hasattr(self, 'combat') and hasattr(self.combat, 'hp'):
            hp = max(0, int(getattr(self.combat, 'hp', 0)))
            max_hp = max(1, int(getattr(self.combat, 'max_hp', 1)))
            frac = float(hp) / float(max_hp) if max_hp > 0 else 0.0
            width = int(36 * frac)
            from src.core.utils import draw_text
            left_x = int((self.rect.centerx - 18) - camera.x)
            top_y = int((self.rect.top - 16) - camera.y)
            # we need to respect zoom; use to_screen for coordinates then draw rects relative to screen
            top_left = camera.to_screen((self.rect.centerx - 18, self.rect.top - 16))
            bg_rect = pygame.Rect(top_left[0], top_left[1], 36, 6)
            fg_rect = pygame.Rect(top_left[0], top_left[1], width, 6)
            pygame.draw.rect(surf, (60, 60, 60), bg_rect)
            pygame.draw.rect(surf, (240, 60, 60), fg_rect)

    def draw(self, surf, camera, show_los=False, show_nametags=False):
        if not getattr(self, 'combat', None) or not getattr(self.combat, 'alive', True):
            return
        # Optional debug: vision cone/LOS
        self.draw_debug_vision(surf, camera, show_los)
        # Apply base color and status effect tint
        base_color = self.get_base_color()
        status_color = self.get_status_effect_color(base_color)
        pygame.draw.rect(surf, status_color, camera.to_screen_rect(self.rect), border_radius=getattr(self, 'draw_border_radius', 4))
        # Draw status effect indicators and telegraph if any
        self.draw_status_effects(surf, camera)
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text', ''):
            from src.core.utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), (255,200,80), size=18, bold=True)
        # Name and HP
        self.draw_nametag(surf, camera, show_nametags)

    # Methods to be implemented by subclasses
    def tick(self, level, player):
        raise NotImplementedError("Subclasses must implement tick method")
    
    def get_base_color(self) -> tuple[int, int, int]:
        return (180, 70, 160) if not self.combat.is_invincible() else (120, 40, 100)


class Bug(Enemy):
    """Basic ground enemy with simple patrol behavior."""
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 30,
            'money_drop': (5, 15)
        }
        super().__init__(x, ground_y, width=28, height=22, combat_config=combat_config,
                         vision_range=200, cone_half_angle=math.pi/6, turn_rate=0.05)
        # Bug-specific initialization
        self.vx = random.choice([-1,1]) * 1.6
        self.facing = 1 if self.vx > 0 else -1
        self.facing_angle = 0 if self.facing > 0 else math.pi
        self.base_speed = 1.8
        self.can_jump = False
        # Expose attributes expected by validation/tests.
        self.type = "Bug"
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)
    
    def _get_terrain_traits(self):
        """Bug can navigate through narrow spaces"""
        return ['ground', 'small', 'narrow']
    
    def _set_movement_strategy(self):
        """Set movement strategy for Bug"""
        self.movement_strategy = MovementStrategyFactory.create_strategy('ground_patrol')

    def tick(self, level, player):
        if not self.combat.alive: return
        
        # Update combat timers (invincibility, etc.)
        self.combat.update()
        self.handle_status_effects()
        
        # Simple patrol movement
        if abs(self.vx) < 0.1:
            self.vx = random.choice([-1.6, 1.6])
        
        # Move horizontally
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx > 0:
                    self.rect.right = s.left
                else:
                    self.rect.left = s.right
                self.vx *= -1
        
        # Update facing direction
        self.facing = 1 if self.vx > 0 else -1
        self.facing_angle = 0 if self.facing > 0 else math.pi
        
        # Update position tracking
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)
    
    def get_base_color(self):
        """Get the base color for Bug enemy."""
        return (180, 70, 160) if not self.combat.is_invincible() else (120, 40, 100)


class Boss(Enemy):
    """Simple boss: large HP, slow movement, collides with player like Bug.
    This is intentionally simple — acts as a strong enemy for the boss room.
    """
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 70,
            'default_ifr': 12,  # Boss has longer IFR
            'money_drop': (50, 100)
        }
        # Make boss wider and taller
        super().__init__(x, ground_y, width=64, height=48, combat_config=combat_config,
                        vision_range=300, cone_half_angle=math.pi/3, turn_rate=0.03)
        self.base_speed = 1.2
        self.can_jump = False
        self.draw_border_radius = 8
    
    def _get_terrain_traits(self):
        """Boss can break through destructible terrain"""
        return ['ground', 'strong', 'destructible']
    
    def _set_movement_strategy(self):
        """Set movement strategy for Boss"""
        self.movement_strategy = MovementStrategyFactory.create_strategy('ground_patrol')
    
    def get_base_color(self):
        """Get the base color for Boss enemy."""
        return (200, 100, 40) if not self.combat.is_invincible() else (140, 80, 30)

    def tick(self, level, player):
        if not self.combat.alive: return
        
        self.combat.update()
        self.handle_status_effects()
        
        ppos = (player.rect.centerx, player.rect.centery)
        dist_to_player = self.update_vision_cone(ppos)
        
        epos = (self.rect.centerx, self.rect.centery)
        has_los, in_cone = self.check_vision_cone(level, ppos)
        
        if has_los and dist_to_player < self.vision_range:
            dx = ppos[0] - epos[0]
            self.vx = (1 if dx>0 else -1) * 1.2
        else:
            self.vx = 0

        self.handle_movement(level, player)
        self.handle_gravity(level)

        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)

        # The component now handles collision with custom damage/knockback
        # Note: The custom damage(2) and knockback values from the original code
        # would need to be passed into the component's config to be fully replicated.
        # For now, we use the component's default collision handling.
        self.combat.handle_collision_with_player(player)


# --- New Enemy Types ---

class Frog(Enemy):
    """Dashing enemy with a telegraphed lunge toward the player."""
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 18,
            'money_drop': (10, 20) # Example money drop
        }
        super().__init__(x, ground_y, width=28, height=22, combat_config=combat_config,
                        vision_range=220, cone_half_angle=math.pi/12, turn_rate=0.08)
        # Frog-specific properties
        self.state = 'idle'
        # Expose attributes expected by validation/tests.
        self.type = "Frog"
        self.tele_t = 0
        self.tele_text = ''
        self.cool = 0
        self.dash_t = 0
        self.base_speed = 1.5
        self.can_jump = True
    
    def _get_terrain_traits(self):
        """Frog can move through water and jump over obstacles"""
        return ['ground', 'amphibious']
    
    def _set_movement_strategy(self):
        """Set movement strategy for Frog"""
        self.movement_strategy = MovementStrategyFactory.create_strategy('jumping')

    def tick(self, level, player):
        if not self.combat.alive: return
        
        self.combat.update()
        self.handle_status_effects()
        
        ppos = (player.rect.centerx, player.rect.centery)
        dist_to_player = self.update_vision_cone(ppos)
        
        epos = (self.rect.centerx, self.rect.centery)
        has_los, in_cone = self.check_vision_cone(level, ppos)
        
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        
        if self.cool>0:
            self.cool -= 1
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0:
                spd = 8.0
                distv = max(1.0, (dx*dx + dy*dy) ** 0.5)
                nx, ny = dx/distv, dy/distv
                self.vx = nx * spd
                self.vy = ny * spd
                self.dash_t = 26
                self.state = 'dash'
                self.cool = 56
        elif self.state=='dash':
            if self.dash_t > 0:
                self.dash_t -= 1
            else:
                self.vx *= 0.9
                if abs(self.vx) < 1.0:
                    self.state='idle'
        else:
            self.vx = 0
            if has_los and dist_to_player < self.vision_range and self.cool==0:
                self.tele_t = 24
                self.tele_text = '!'

        self.handle_movement(level, player)
        
        self.vy = getattr(self, 'vy', 0) + min(GRAVITY, 10)
        self.rect.y += int(min(10, self.vy))
        
        self.on_ground = False
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
                    self.vy = 0
                    self.on_ground = True
        
        self.combat.handle_collision_with_player(player)

        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)




class Archer(Enemy):
    """Ranged enemy that shoots arrows with '!!' telegraph."""
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 16,
            'money_drop': (10, 25)
        }
        super().__init__(x, ground_y, width=28, height=22, combat_config=combat_config,
                        vision_range=350, cone_half_angle=math.pi/4, turn_rate=0.05)
        # Archer-specific properties
        self.cool = 0
        # Expose attributes expected by validation/tests.
        self.type = "Archer"
        self.tele_t = 0
        self.tele_text = ''
        self.base_speed = 1.2
        self.can_jump = False
    
    def _get_terrain_traits(self):
        """Archer prefers high ground and tactical positions"""
        return ['ground']
    
    def _set_movement_strategy(self):
        """Set movement strategy for Archer"""
        self.movement_strategy = MovementStrategyFactory.create_strategy('ranged_tactical')

    def tick(self, level, player):
        if not self.combat.alive: return
        
        self.combat.update()
        self.handle_status_effects()
        
        if self.cool>0: self.cool-=1
        
        ppos = (player.rect.centerx, player.rect.centery)
        dist_to_player = self.update_vision_cone(ppos)
        
        epos = (self.rect.centerx, self.rect.centery)
        has_los, in_cone = self.check_vision_cone(level, ppos)
        
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0 and has_los and dist_to_player < self.vision_range:
                dx = ppos[0] - epos[0]
                dy = ppos[1] - epos[1]
                dist = max(1.0, (dx*dx+dy*dy)**0.5)
                nx, ny = dx/dist, dy/dist
                hb = pygame.Rect(0,0,10,6); hb.center = self.rect.center
                hitboxes.append(Hitbox(hb, 120, 1, self, dir_vec=(nx,ny), vx=nx*10.0, vy=ny*10.0))
                self.cool = 60
        elif has_los and self.cool==0 and dist_to_player < self.vision_range:
            self.tele_t = 18
            self.tele_text = '!!'

        self.vx = 0
        if has_los and abs(ppos[0]-epos[0])<64:
            self.vx = -1.2 if ppos[0]>epos[0] else 1.2
        
        self.handle_movement(level, player)
        self.handle_gravity(level)

        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)

    def get_base_color(self):
        """Get the base color for Archer enemy."""
        return (200, 200, 80) if not self.combat.is_invincible() else (120, 120, 60)
    
    def draw(self, surf, camera, show_los=False, show_nametags=False):
        if not self.combat.alive: return
        
        self.draw_debug_vision(surf, camera, show_los)
        
        # Draw archer with status effect coloring
        base_color = self.get_base_color()
        status_color = self.get_status_effect_color(base_color)
        pygame.draw.rect(surf, status_color, camera.to_screen_rect(self.rect), border_radius=5)
        
        # Draw status effect indicators
        self.draw_status_effects(surf, camera)
        
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text',''):
            from src.core.utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), (255,200,80), size=18, bold=True)
        
        self.draw_nametag(surf, camera, show_nametags)
        
        # Draw debug vision cone and LOS line
        self.draw_debug_vision(surf, camera, show_los)


class WizardCaster(Enemy):
    """Casts fast magic bolts with '!!' telegraph."""
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 14,
            'money_drop': (15, 30)
        }
        super().__init__(x, ground_y, width=28, height=22, combat_config=combat_config,
                        vision_range=280, cone_half_angle=math.pi/3, turn_rate=0.05)
        # Wizard-specific properties
        self.cool = 0
        # Expose attributes expected by validation/tests.
        self.type = "WizardCaster"
        self.tele_t = 0
        self.tele_text = ''
        self.action = None  # 'bolt' | 'missile' | 'fireball'
        self.base_speed = 0.8
        self.can_jump = False
        self.gravity_affected = False  # Wizards float
    
    def _get_terrain_traits(self):
        """Wizard can float over most terrain"""
        return ['ground', 'floating']
    
    def _set_movement_strategy(self):
        """Set movement strategy for WizardCaster"""
        self.movement_strategy = MovementStrategyFactory.create_strategy('floating')

    def tick(self, level, player):
        if not self.combat.alive:
            return
        
        self.combat.update()
        self.handle_status_effects()
        
        if self.cool > 0:
            self.cool -= 1
        
        ppos = (player.rect.centerx, player.rect.centery)
        dist_to_player = self.update_vision_cone(ppos)
        
        epos = (self.rect.centerx, self.rect.centery)
        has_los, in_cone = self.check_vision_cone(level, ppos)
        
        if self.tele_t > 0:
            self.tele_t -= 1
            if self.tele_t == 0 and has_los and dist_to_player < self.vision_range:
                dx = ppos[0] - epos[0]
                dy = ppos[1] - epos[1]
                dist = max(1.0, (dx*dx+dy*dy)**0.5)
                nx, ny = dx/dist, dy/dist
                if self.action == 'missile':
                    hb = pygame.Rect(0,0,18,6); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 36, 12, self, dir_vec=(nx,ny), vx=nx*20.0, vy=ny*20.0))
                    self.cool = 70
                elif self.action == 'fireball':
                    hb = pygame.Rect(0,0,12,12); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 180, 6, self, dir_vec=(nx,ny), vx=nx*6.0, vy=ny*6.0, aoe_radius=48))
                    self.cool = 80
                else:
                    hb = pygame.Rect(0,0,8,8); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 90, 1, self, dir_vec=(nx,ny), vx=nx*9.0, vy=ny*9.0))
                    self.cool = 50
                self.action = None
        elif has_los and self.cool == 0 and dist_to_player < self.vision_range:
            import random
            self.action = random.choices(['bolt','missile','fireball'], weights=[0.5,0.3,0.2])[0]
            self.tele_t = 16
            self.tele_text = '!!'
        
        from ..ai.enemy_movement import clamp_enemy_to_level
        self.handle_movement(level, player)
        clamp_enemy_to_level(self, level, respect_solids=True)

        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)

    def get_base_color(self):
        """Get the base color for WizardCaster enemy."""
        return (180, 120, 220) if not self.combat.is_invincible() else (110, 80, 140)


class Assassin(Enemy):
    """Semi-invisible melee dash enemy."""
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 20,
            'money_drop': (20, 35)
        }
        super().__init__(x, ground_y, width=28, height=22, combat_config=combat_config,
                        vision_range=240, cone_half_angle=math.pi/4, turn_rate=0.06)  # Wider vision cone (45 degrees)
        # Assassin-specific properties
        self.state = 'idle'
        # Expose attributes expected by validation/tests.
        self.type = "Assassin"
        self.tele_t = 0
        self.cool = 0
        self.action = None  # 'dash' or 'slash'
        self.dash_t = 0
        self.base_speed = 2.0
        self.can_jump = True
        self.jump_cooldown = 0  # Prevent continuous jumping
    
    def _get_terrain_traits(self):
        """Assassin can move through narrow spaces and jump"""
        return ['ground', 'small', 'narrow', 'jumping']
    
    def _set_movement_strategy(self):
        """Set movement strategy for Assassin"""
        # Assassin uses custom movement logic, not standard strategies
        self.movement_strategy = None

    def tick(self, level, player):
        if not self.combat.alive:
            return
        
        self.combat.update()
        self.handle_status_effects()
         
        if self.cool > 0:
            self.cool -= 1
        if getattr(self, 'jump_cooldown', 0) > 0:
            self.jump_cooldown -= 1
         
        ppos = (player.rect.centerx, player.rect.centery)
        dist_to_player = self.update_vision_cone(ppos)
         
        epos = (self.rect.centerx, self.rect.centery)
        has_los, in_cone = self.check_vision_cone(level, ppos)
         
        self._in_cone = in_cone
         
        from ..ai.enemy_movement import clamp_enemy_to_level
         
        if self.tele_t > 0:
            self.tele_t -= 1
            if self.tele_t == 0:
                if self.action == 'dash':
                    dx = ppos[0] - epos[0]
                    dy = ppos[1] - epos[1]
                    dist = max(1.0, (dx*dx + dy*dy) ** 0.5)
                    nx, ny = dx / dist, dy / dist
                    self.vx = nx * 7.5
                    self.vy = ny * 7.5
                    self.dash_t = 18
                    self.state = 'dash'
                    self.facing = 1 if self.vx >= 0 else -1
                elif self.action == 'slash':
                    hb = pygame.Rect(0, 0, int(self.rect.w * 1.2), int(self.rect.h * 0.7))
                    if self.facing > 0:
                        hb.midleft = (self.rect.right, self.rect.centery)
                    else:
                        hb.midright = (self.rect.left, self.rect.centery)
                    hitboxes.append(Hitbox(hb, 10, 1, self, dir_vec=(self.facing, 0)))
                    self.cool = 48
                    self.action = None
        elif self.state == 'dash':
            hb = pygame.Rect(0, 0, int(self.rect.w * 1.1), int(self.rect.h * 0.6))
            if self.facing > 0:
                hb.midleft = (self.rect.right, self.rect.centery)
            else:
                hb.midright = (self.rect.left, self.rect.centery)
            hitboxes.append(Hitbox(hb, 6, 1, self, dir_vec=(self.facing, 0)))
             
            old_vy = getattr(self, 'vy', 0)
            self.vy = old_vy + min(GRAVITY, 10)
            
            old_rect = self.rect.copy()
            self.rect.x += int(self.vx)
            self.rect.y += int(min(10, self.vy))
             
            self.on_ground = False
            
            for s in level.solids:
                if self.rect.colliderect(s):
                    if self.rect.bottom > s.top and old_rect.bottom <= s.top and self.rect.centery < s.centery:
                        self.rect.bottom = s.top
                        self.vy = 0
                        self.on_ground = True
                    elif self.rect.top < s.bottom and old_rect.top >= s.bottom and self.rect.centery > s.centery:
                        self.rect.top = s.bottom
                        self.vy = 0
                    if self.vx > 0 and old_rect.right <= s.left and self.rect.right > s.left:
                        self.rect.right = s.left
                        self.vx = 0
                    elif self.vx < 0 and old_rect.left >= s.right and self.rect.left < s.right:
                        self.rect.left = s.right
                        self.vx = 0
             
            clamp_enemy_to_level(self, level, respect_solids=False)
             
            if self.dash_t > 0:
                self.dash_t -= 1
            else:
                self.state = 'idle'
                self.cool = 60
                self.action = None
                if getattr(self, 'on_ground', False):
                    self.vy = 0
                self.vx *= 0.6
                if abs(self.vx) < 0.8:
                    self.vx = 0
                return
        elif has_los and self.cool == 0 and dist_to_player < self.vision_range:
            import random
            self.action = 'dash' if random.random() < 0.5 else 'slash'
            if self.action == 'dash':
                self.tele_t = 14
                self.tele_text = '!'
            else:
                self.tele_t = 12
                self.tele_text = '!!'
        else:
            if has_los and dist_to_player < self.vision_range:
                dx = ppos[0] - epos[0]
                dy = ppos[1] - epos[1]
                
                if abs(dx) > 5:
                    self.vx = 2.0 if dx > 0 else -2.0
                else:
                    self.vx = 0
                    
                jump_cooldown = getattr(self, 'jump_cooldown', 0)
                if (hasattr(self, 'can_jump') and self.can_jump and dy < -50 and
                    getattr(self, 'on_ground', False) and jump_cooldown <= 0):
                    self.vy = -10
                    self.on_ground = False
                    self.jump_cooldown = 30
            else:
                import random as rnd
                if not hasattr(self, 'patrol_direction') or rnd.random() < 0.02:
                    self.patrol_direction = rnd.choice([-1.5, 0, 1.5])
                else:
                    if not hasattr(self, 'patrol_direction'):
                        self.patrol_direction = 0
                
                self.vx = self.patrol_direction
                if self.vx == 0:
                    self.vx = rnd.choice([-1.0, 1.0]) * 0.5
            
            if self.gravity_affected:
                self.handle_gravity(level)
            clamp_enemy_to_level(self, level, respect_solids=False)
         
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)

    def get_base_color(self):
        """Get the base color for Assassin enemy."""
        in_cone = getattr(self, '_in_cone', False)
        if in_cone:
            return (60,60,80) if not self.combat.is_invincible() else (40,40,60)
        else:
            return (30,30,40) if not self.combat.is_invincible() else (20,20,30)


class Bee(Enemy):
    """Hybrid shooter/dasher. Chooses randomly between actions."""
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 12,
            'money_drop': (10, 25)
        }
        super().__init__(x, ground_y, width=24, height=20, combat_config=combat_config,
                        vision_range=240, cone_half_angle=math.pi/4, turn_rate=0.05)
        # Bee-specific properties
        self.cool = 0
        # Expose attributes expected by validation/tests.
        self.type = "Bee"
        self.tele_t = 0
        self.tele_text = ''
        self.action = None
        self.base_speed = 1.8
        self.can_jump = False
        self.gravity_affected = False  # Bees float
    
    def _get_terrain_traits(self):
        """Bee can fly over most terrain"""
        return ['flying', 'air']
    
    def _set_movement_strategy(self):
        """Set movement strategy for Bee"""
        self.movement_strategy = MovementStrategyFactory.create_strategy('floating')

    def tick(self, level, player):
        if not self.combat.alive:
            return
        
        self.combat.update()
        if self.cool > 0:
            self.cool -= 1
        
        ppos = (player.rect.centerx, player.rect.centery)
        dist_to_player = self.update_vision_cone(ppos)
        
        epos = (self.rect.centerx, self.rect.centery)
        has_los, in_cone = self.check_vision_cone(level, ppos)
        
        import random
        if self.tele_t > 0:
            self.tele_t -= 1
            if self.tele_t == 0 and has_los and dist_to_player < self.vision_range:
                if self.action == 'dash':
                    self.vx = 7 if ppos[0] > epos[0] else -7
                elif self.action == 'shoot':
                    dx = ppos[0] - epos[0]
                    dy = ppos[1] - epos[1]
                    dist = max(1.0, (dx*dx+dy*dy)**0.5)
                    nx, ny = dx/dist, dy/dist
                    hb = pygame.Rect(0,0,10,6); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 120, 1, self, dir_vec=(nx,ny), vx=nx*7.5, vy=ny*7.5))
                self.cool = 50
        elif has_los and self.cool == 0 and dist_to_player < self.vision_range:
            self.action = 'dash' if random.random() < 0.5 else 'shoot'
            self.tele_t = 14 if self.action == 'dash' else 16
            self.tele_text = '!' if self.action == 'dash' else '!!'
        
        from ..ai.enemy_movement import clamp_enemy_to_level
        self.handle_movement(level, player)
        clamp_enemy_to_level(self, level, respect_solids=True)

        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)

    def get_base_color(self):
        """Get the base color for Frog enemy."""
        return (80, 200, 80) if not self.combat.is_invincible() else (60, 120, 60)


class Golem(Enemy):
    """Boss with random pattern: dash (!), shoot (!!), stun (!!)."""
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 120,
            'default_ifr': 12,
            'money_drop': (50, 100)
        }
        super().__init__(x, ground_y, width=56, height=44, combat_config=combat_config,
                        vision_range=500, cone_half_angle=math.pi/3, turn_rate=0.03)
        # Golem-specific properties
        self.cool = 0
        # Expose attributes expected by validation/tests.
        self.type = "Golem"
        self.tele_t = 0
        self.tele_text = ''
        self.action = None
        self.base_speed = 0.8
        self.can_jump = False
    
    def _get_terrain_traits(self):
        """Golem can move through earth and break obstacles"""
        return ['ground', 'strong', 'destructible', 'fire_resistant']
    
    def _set_movement_strategy(self):
        """Set movement strategy for Golem"""
        self.movement_strategy = MovementStrategyFactory.create_strategy('ground_patrol')

    def tick(self, level, player):
        if not self.combat.alive: return
        
        self.combat.update()
        self.handle_status_effects()
        
        if self.cool>0: self.cool-=1
        
        ppos = (player.rect.centerx, player.rect.centery)
        dist_to_player = self.update_vision_cone(ppos)
        
        epos = (self.rect.centerx, self.rect.centery)
        has_los = los_clear(level, epos, ppos)
        
        self._has_los = has_los
        self._los_point = ppos
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0:
                if self.action=='dash':
                    dx = ppos[0]-epos[0]; dy = ppos[1]-epos[1]
                    dist = max(1.0, (dx*dx+dy*dy)**0.5)
                    nx, ny = dx/dist, dy/dist
                    self.vx = nx * 8.0
                    self.vy = ny * 8.0
                elif self.action=='shoot' and has_los:
                    dx = ppos[0]-epos[0]; dy = ppos[1]-epos[1]
                    dist = max(1.0, (dx*dx+dy*dy)**0.5)
                    nx, ny = dx/dist, dy/dist
                    hb = pygame.Rect(0,0,14,10); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 120, 2, self, dir_vec=(nx,ny), vx=nx*8.0, vy=ny*8.0))
                elif self.action=='stun':
                    r = 72
                    hb = pygame.Rect(0,0,r*2, r*2)
                    hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 24, 0, self, aoe_radius=r, tag='stun'))
                self.cool = 70
        elif has_los and self.cool==0:
            self.action = random.choice(['dash','shoot','stun'])
            self.tele_text = '!' if self.action=='dash' else '!!'
            self.tele_t = 22 if self.action=='dash' else 18

        if abs(self.vx)>0:
            self.vx *= 0.9
            if abs(self.vx)<1.0: self.vx=0
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx>0: self.rect.right=s.left
                else: self.rect.left=s.right
                self.vx=0
        self.vy = getattr(self, 'vy', 0) + min(GRAVITY, 10)
        self.rect.y += int(min(10, self.vy))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
                    self.vy = 0

        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)

        self.combat.handle_collision_with_player(player)

    def get_base_color(self):
        """Get the base color for Bee enemy."""
        return (240, 180, 60) if not self.combat.is_invincible() else (140, 120, 50)
