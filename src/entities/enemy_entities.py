from __future__ import annotations

import math
import random
import pygame
import logging
from typing import Optional

from config import (
    FPS, GRAVITY, TERMINAL_VY, PLAYER_SPEED, PLAYER_AIR_SPEED, PLAYER_JUMP_V,
    PLAYER_SMALL_JUMP_CUT, COYOTE_FRAMES, JUMP_BUFFER_FRAMES,
    DASH_SPEED, DASH_TIME, DASH_COOLDOWN, INVINCIBLE_FRAMES,
    DOUBLE_JUMPS,
    ATTACK_COOLDOWN, ATTACK_LIFETIME, COMBO_RESET, SWORD_DAMAGE,
    POGO_BOUNCE_VY, ACCENT, GREEN, CYAN, RED, WHITE, IFRAME_BLINK_INTERVAL,
    TILE
)
from src.core.utils import los_clear, find_intermediate_visible_point, find_idle_patrol_target
from src.entities.entity_common import Hitbox, DamageNumber, hitboxes, floating, in_vision_cone
from src.entities.player_entity import Player
from src.ai.enemy_movement import MovementStrategyFactory
from src.entities.components.combat_component import CombatComponent

logger = logging.getLogger(__name__)


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
        
        # Improved vision/memory system
        self.last_seen_pos = None  # Last known player position
        self.pursuit_timer = 0  # How long to pursue after losing sight
        self.pursuit_duration = 180  # 3 seconds at 60 FPS
        self.alert_level = 0  # 0=idle, 1=investigating, 2=combat
        self.investigation_point = None  # Where to investigate
        self.idle_look_direction = 0  # Direction enemy looks when idle
        
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
        
        # ----------------------------
        # SPRITE ANIMATION SYSTEM (Friend's Code - Universal)
        # ----------------------------
        # Sprite rendering (optional - enemies can have sprites or use colored rects)
        self.sprite_idle = None
        self.sprite = None
        self.sprite_offset_y = 0
        self.sprite_rect = None
        
        # Attack animation system (optional - for animated enemies)
        self.atk_frames = []
        self.play_attack_anim = False
        self.atk_index = 0
        self.atk_timer = 0
        self.atk_speed = 4  # Frames per animation step
        
        # Projectile sprite system (optional - for enemies with projectile attacks)
        self.projectile_sprite = None
        self.projectile_hitboxes = []
        
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
    
    def update_vision_cone_and_memory(self, player_pos, has_los=False):
        """Update facing direction based on player position and alert state with memory."""
        epos = (self.rect.centerx, self.rect.centery)
        ppos = player_pos
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # Update alert level and pursuit timer
        if has_los:
            self.alert_level = 2  # Combat
            self.pursuit_timer = self.pursuit_duration
            self.last_seen_pos = ppos
            self.investigation_point = None
        elif self.pursuit_timer > 0:
            self.pursuit_timer -= 1
            if self.pursuit_timer > self.pursuit_duration * 0.5:
                self.alert_level = 2  # Still in combat mode
            else:
                self.alert_level = 1  # Investigating
                if self.investigation_point is None and self.last_seen_pos:
                    self.investigation_point = self.last_seen_pos
        else:
            self.alert_level = 0  # Return to idle
            self.investigation_point = None
        
        # Update facing direction based on alert level
        if dist_to_player > 0:
            # Calculate angle to target (player or investigation point)
            target_pos = ppos
            if self.alert_level == 1 and self.investigation_point:
                target_pos = self.investigation_point
            
            dx_target = target_pos[0] - epos[0]
            dy_target = target_pos[1] - epos[1]
            angle_to_target = math.atan2(dy_target, dx_target)
            
            if self.alert_level >= 1:
                # Alert or investigating: turn toward target
                angle_diff = (angle_to_target - self.facing_angle) % (2 * math.pi)
                if angle_diff > math.pi:
                    angle_diff -= 2 * math.pi
                # Faster turn rate when alert
                turn_speed = self.turn_rate * (2.0 if self.alert_level == 2 else 1.5)
                self.facing_angle += angle_diff * turn_speed
                
                # Update facing direction based on angle
                self.facing = 1 if math.cos(self.facing_angle) > 0 else -1
            else:
                # Idle: slower patrol sweep
                if not hasattr(self, 'idle_look_direction'):
                    self.idle_look_direction = self.facing
                
                self.facing_angle += 0.015 * self.idle_look_direction
                
                # Flip at bounds (patrol sweep)
                if self.facing_angle > math.pi / 3:
                    self.idle_look_direction = -1
                elif self.facing_angle < -math.pi / 3:
                    self.idle_look_direction = 1
                
                # Update facing direction
                self.facing = 1 if self.facing_angle > -math.pi/2 and self.facing_angle < math.pi/2 else -1
        
        return dist_to_player
    
    def update_vision_cone(self, player_pos):
        """Simple vision cone update for backwards compatibility - just updates facing direction."""
        epos = (self.rect.centerx, self.rect.centery)
        ppos = player_pos
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # Just update facing direction (simple version for enemies that don't use advanced AI)
        if dist_to_player > 0 and dist_to_player < self.vision_range * 1.5:
            angle_to_player = math.atan2(dy, dx)
            angle_diff = (angle_to_player - self.facing_angle) % (2 * math.pi)
            if angle_diff > math.pi:
                angle_diff -= 2 * math.pi
            self.facing_angle += angle_diff * self.turn_rate
            self.facing = 1 if math.cos(self.facing_angle) > 0 else -1
        
        return dist_to_player

    def check_vision_cone(self, level, player_pos):
        """Check if player is in vision cone and has line of sight from eye level."""
        # Use eye-level position for more realistic vision
        eye_height_offset = -self.rect.height * 0.3  # Eyes are at upper 1/3 of body
        epos = (self.rect.centerx, self.rect.centery + eye_height_offset)
        
        # Check player's center mass (torso level) not feet
        player_target_height = -15 if hasattr(player_pos, '__len__') else 0
        ppos = (player_pos[0], player_pos[1] + player_target_height) if hasattr(player_pos, '__len__') else player_pos
        
        # Check if player is in vision cone
        in_cone = in_vision_cone(epos, ppos, self.facing_angle, self.cone_half_angle, self.vision_range)
        has_los = in_cone and los_clear(level, epos, ppos)
        
        # Store for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        self._eye_pos = epos
        
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
        
        # Become alert when hit - enemy notices the player!
        if self.combat.alive and hasattr(player, 'rect'):
            self.last_seen_pos = (player.rect.centerx, player.rect.centery)
            self.pursuit_timer = getattr(self, 'pursuit_duration', 180)
            self.alert_level = 2  # Go into combat mode
            # Turn to face attacker
            if player.rect.centerx > self.rect.centerx:
                self.facing = 1
                self.facing_angle = 0
            else:
                self.facing = -1
                self.facing_angle = math.pi
        
        # Become alert when hit - enemy notices the player!
        if self.combat.alive and hasattr(player, 'rect'):
            self.last_seen_pos = (player.rect.centerx, player.rect.centery)
            self.pursuit_timer = self.pursuit_duration if hasattr(self, 'pursuit_duration') else 180
            self.alert_level = 2  # Go into combat mode
            # Turn to face attacker
            if player.rect.centerx > self.rect.centerx:
                self.facing = 1
                self.facing_angle = 0
            else:
                self.facing = -1
                self.facing_angle = math.pi
    
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
        """Draw debug vision cone and LOS line from eye position with alert state visualization."""
        if not show_los:
            return
            
        # Use eye position if available, otherwise center
        eye_pos = getattr(self, '_eye_pos', self.rect.center)
        alert_level = getattr(self, 'alert_level', 0)
        pursuit_timer = getattr(self, 'pursuit_timer', 0)
        
        # Draw LOS line to last-checked player point if available
        if getattr(self, '_los_point', None) is not None:
            has_los = getattr(self, '_has_los', False)
            
            # Color based on alert state
            if has_los:
                col = GREEN  # Can see player
            elif alert_level == 2:
                col = (255, 150, 0)  # Pursuing (orange)
            elif alert_level == 1:
                col = (255, 200, 100)  # Investigating (yellow-orange)
            else:
                col = RED  # Lost player
            
            pygame.draw.line(surf, col, camera.to_screen(eye_pos), camera.to_screen(self._los_point), 2)
            
            # Draw eye position indicator (color changes with alert)
            if alert_level == 2:
                eye_color = (255, 100, 100)  # Red - combat alert
            elif alert_level == 1:
                eye_color = (255, 200, 0)  # Orange - investigating
            else:
                eye_color = (255, 255, 100)  # Yellow - idle
            pygame.draw.circle(surf, eye_color, camera.to_screen(eye_pos), 4, 2)
            
            # Draw vision cone from eye position
            center = camera.to_screen(eye_pos)
            # Calculate cone edges
            left_angle = self.facing_angle - self.cone_half_angle
            right_angle = self.facing_angle + self.cone_half_angle
            
            # Calculate end points of cone lines
            left_x = center[0] + math.cos(left_angle) * self.vision_range
            left_y = center[1] + math.sin(left_angle) * self.vision_range
            right_x = center[0] + math.cos(right_angle) * self.vision_range
            right_y = center[1] + math.sin(right_angle) * self.vision_range
            
            # Draw cone lines (color based on alert level)
            if alert_level == 2:
                cone_color = (255, 100, 100)  # Red - combat
                line_width = 2
            elif alert_level == 1:
                cone_color = (255, 180, 0)  # Orange - investigating
                line_width = 2
            else:
                cone_color = (255, 255, 0)  # Yellow - idle
                line_width = 1
            
            pygame.draw.line(surf, cone_color, center, (left_x, left_y), line_width)
            pygame.draw.line(surf, cone_color, center, (right_x, right_y), line_width)
            
            # Draw investigation point if investigating
            if getattr(self, 'investigation_point', None) and alert_level == 1:
                inv_point = camera.to_screen(self.investigation_point)
                pygame.draw.circle(surf, (255, 150, 0), inv_point, 8, 2)
                pygame.draw.line(surf, (255, 150, 0), center, inv_point, 1)
                # Draw "?" above investigation point
                from src.core.utils import draw_text
                draw_text(surf, "?", (inv_point[0] - 4, inv_point[1] - 15), (255, 200, 0), size=16, bold=True)
            
            # Draw pursuit timer bar if pursuing/investigating
            if pursuit_timer > 0:
                pursuit_duration = getattr(self, 'pursuit_duration', 180)
                bar_width = 30
                bar_height = 4
                bar_x = center[0] - bar_width // 2
                bar_y = center[1] - 20
                
                # Background
                pygame.draw.rect(surf, (60, 60, 60), (bar_x, bar_y, bar_width, bar_height))
                # Fill based on remaining time
                fill_width = int(bar_width * (pursuit_timer / pursuit_duration))
                fill_color = (255, 150, 0) if alert_level == 2 else (255, 200, 100)
                pygame.draw.rect(surf, fill_color, (bar_x, bar_y, fill_width, bar_height))
            
            # Draw alert state text
            if alert_level > 0:
                from src.core.utils import draw_text
                state_text = "COMBAT" if alert_level == 2 else "ALERT"
                state_color = (255, 100, 100) if alert_level == 2 else (255, 200, 0)
                draw_text(surf, state_text, (center[0] - 20, center[1] - 30), state_color, size=12, bold=True)

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
    
    # ========================================================================
    # SPRITE ANIMATION SYSTEM (Friend's Code - Made Universal for All Enemies)
    # ========================================================================
    
    def load_sprite_system(self, idle_path, sprite_size=(96, 128), offset_y=55):
        """
        Load sprite system for this enemy (Friend's sprite loading code).
        
        Args:
            idle_path: Path to idle sprite (e.g., "assets/monster/Dark_Knight.png")
            sprite_size: Tuple of (width, height) to scale sprite to
            offset_y: Vertical offset for sprite positioning
        """
        try:
            img = pygame.image.load(idle_path).convert_alpha()
            self.sprite_idle = pygame.transform.scale(img, sprite_size)
            self.sprite = self.sprite_idle
            self.sprite_offset_y = offset_y
            
            # Create sprite rect for positioning
            self.sprite_rect = self.sprite.get_rect()
            self.sprite_rect.midbottom = self.rect.midbottom
        except Exception as e:
            print(f"[ERROR] Cannot load sprite {idle_path}: {e}")
            self.sprite_idle = None
            self.sprite = None
            self.sprite_rect = self.rect.copy()
    
    def load_attack_animation(self, frame_paths, sprite_size=(96, 128), anim_speed=4):
        """
        Load attack animation frames (Friend's animation loading code).
        
        Args:
            frame_paths: List of paths to animation frames
            sprite_size: Tuple of (width, height) to scale frames to
            anim_speed: Frames per animation step
        """
        self.atk_frames = []
        for path in frame_paths:
            try:
                frame = pygame.image.load(path).convert_alpha()
                self.atk_frames.append(pygame.transform.scale(frame, sprite_size))
            except Exception as e:
                print(f"[ERROR] Cannot load animation frame {path}: {e}")
        
        self.atk_speed = anim_speed
    
    def load_projectile_sprite(self, sprite_path, sprite_size=(42, 42)):
        """
        Load projectile sprite (Friend's projectile sprite code).
        
        Args:
            sprite_path: Path to projectile sprite
            sprite_size: Tuple of (width, height) to scale sprite to
        """
        try:
            sprite_img = pygame.image.load(sprite_path).convert_alpha()
            self.projectile_sprite = pygame.transform.scale(sprite_img, sprite_size)
        except Exception as e:
            print(f"[ERROR] Cannot load projectile sprite {sprite_path}: {e}")
            self.projectile_sprite = None
    
    def update_facing_from_player(self, player):
        """
        Update facing direction based on player position (Friend's facing code).
        Integrates with your vision system.
        """
        if hasattr(player, 'rect'):
            self.facing = -1 if player.rect.centerx < self.rect.centerx else 1
    
    def update_attack_animation(self):
        """
        Update attack animation frame (Friend's animation update code).
        Call this every frame in tick() when animation is playing.
        """
        if self.play_attack_anim and self.atk_frames:
            self.atk_timer += 1
            if self.atk_timer >= self.atk_speed:
                self.atk_timer = 0
                self.atk_index += 1
                if self.atk_index >= len(self.atk_frames):
                    # Animation complete
                    self.play_attack_anim = False
                    self.sprite = self.sprite_idle
                    self.atk_index = 0
                else:
                    # Next frame
                    self.sprite = self.atk_frames[self.atk_index]
    
    def start_attack_animation(self):
        """Start playing attack animation (Friend's animation trigger code)."""
        if self.atk_frames:
            self.play_attack_anim = True
            self.atk_index = 0
            self.atk_timer = 0
    
    def sync_sprite_position(self):
        """Sync sprite rect with collision rect (Friend's positioning code)."""
        if hasattr(self, 'sprite_rect') and self.sprite_rect:
            self.sprite_rect.midbottom = (
                self.rect.midbottom[0],
                self.rect.midbottom[1] + self.sprite_offset_y
            )
    
    def clean_projectile_hitboxes(self):
        """Clean up dead projectile hitboxes (Friend's cleanup code)."""
        if hasattr(self, 'projectile_hitboxes'):
            self.projectile_hitboxes = [
                hb for hb in self.projectile_hitboxes 
                if hb.alive and hb in hitboxes
            ]
    
    def draw_sprite_with_animation(self, surf, camera):
        """
        Draw sprite with animation support (Friend's sprite draw code).
        Returns True if sprite was drawn, False if fallback needed.
        """
        if not self.sprite or not hasattr(self, 'sprite_rect') or not self.sprite_rect:
            return False
        
        # Flip sprite based on facing direction
        draw_sprite = pygame.transform.flip(self.sprite, True, False) if self.facing == -1 else self.sprite
        
        # Scale sprite to match camera zoom
        scaled_width = int(draw_sprite.get_width() * camera.zoom)
        scaled_height = int(draw_sprite.get_height() * camera.zoom)
        draw_sprite = pygame.transform.scale(draw_sprite, (scaled_width, scaled_height))
        
        # Create a rect for the scaled sprite and position it correctly
        scaled_sprite_rect = draw_sprite.get_rect()
        scaled_sprite_rect.midbottom = camera.to_screen(self.sprite_rect.midbottom)
        
        # Apply invincibility flicker effect
        if self.combat.is_invincible():
            temp = draw_sprite.copy()
            temp.set_alpha(150)
            surf.blit(temp, scaled_sprite_rect.topleft)
        else:
            surf.blit(draw_sprite, scaled_sprite_rect.topleft)
        
        return True
    
    def draw_projectile_sprites(self, surf, camera):
        """Draw projectile sprites scaled to match hitbox size for accurate visual feedback."""
        if self.projectile_sprite and hasattr(self, 'projectile_hitboxes'):
            for hb in self.projectile_hitboxes:
                # Scale sprite to match hitbox dimensions AND camera zoom for visual accuracy
                hitbox_w = int(hb.rect.width * camera.zoom)
                hitbox_h = int(hb.rect.height * camera.zoom)
                scaled_sprite = pygame.transform.scale(self.projectile_sprite, (hitbox_w, hitbox_h))
                
                # Center sprite on hitbox
                px = hb.rect.x
                py = hb.rect.y
                surf.blit(scaled_sprite, camera.to_screen((px, py)))
    
    # ========================================================================
    # END OF SPRITE ANIMATION SYSTEM
    # ========================================================================

    def draw(self, surf, camera, show_los=False, show_nametags=False, debug_hitboxes=False):
        if not getattr(self, 'combat', None) or not getattr(self.combat, 'alive', True):
            return
        # Optional debug: vision cone/LOS
        self.draw_debug_vision(surf, camera, show_los)
        # Apply base color and status effect tint
        base_color = self.get_base_color()
        status_color = self.get_status_effect_color(base_color)
        pygame.draw.rect(surf, status_color, camera.to_screen_rect(self.rect), border_radius=getattr(self, 'draw_border_radius', 4))
        # Draw collision box outline in debug mode (F3)
        if debug_hitboxes:
            pygame.draw.rect(surf, (255, 140, 0), camera.to_screen_rect(self.rect), width=2)
        # Draw status effect indicators and telegraph if any
        self.draw_status_effects(surf, camera)
        tele_text = getattr(self, 'tele_text', '')
        if getattr(self, 'tele_t', 0) > 0 and tele_text:
            from src.core.utils import draw_text
            draw_text(surf, tele_text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), (255,200,80), size=18, bold=True)
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
        has_los, in_cone = self.check_vision_cone(level, ppos)
        dist_to_player = self.update_vision_cone_and_memory(ppos, has_los)
        
        epos = (self.rect.centerx, self.rect.centery)
        
        if has_los and dist_to_player < self.vision_range:
            dx = ppos[0] - epos[0]
            self.vx = (1 if dx>0 else -1) * 1.2
        else:
            self.vx = 0

        self.handle_movement(level, player)
        self.handle_gravity(level)
        
        # Update facing direction based on movement
        if abs(self.vx) > 0.1:
            self.facing = 1 if self.vx > 0 else -1
            self.facing_angle = 0 if self.facing > 0 else math.pi

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
        
        # ----------------------------
        # Load Frog Sprite Animations
        # ----------------------------
        from src.entities.animation_system import AnimationManager, AnimationState
        
        # Initialize animation manager
        self.anim_manager = AnimationManager(self, default_state=AnimationState.IDLE)
        self.anim_manager.set_sprite_offset_y(-1)  # Adjust sprite positioning
        
        # Original frog sprite is roughly 32x32, scale to 40x40 to match hitbox better
        sprite_size = (32, 32)
        
        # Load idle animation (4 frames)
        idle_frames = [
            "assets/enemy/frog/frog-idle/Idle-1.png",
            "assets/enemy/frog/frog-idle/Idle-2.png",
            "assets/enemy/frog/frog-idle/Idle-3.png",
            "assets/enemy/frog/frog-idle/Idle-4.png"
        ]
        self.anim_manager.load_animation(
            AnimationState.IDLE,
            idle_frames,
            sprite_size=sprite_size,
            frame_duration=10,  # Slower idle animation
            loop=True,
            priority=0
        )
        
        # Load bounce/telegraph animation (2 frames) - plays when charging dash
        bounce_frames = [
            "assets/enemy/frog/frog-bounce/bounce-1.png",
            "assets/enemy/frog/frog-bounce/bounce-L.png"
        ]
        self.anim_manager.load_animation(
            AnimationState.TELEGRAPH,
            bounce_frames,
            sprite_size=sprite_size,
            frame_duration=6,
            loop=True,
            priority=5
        )
        
        # Load jump animation (single frame) - plays when launching dash
        self.anim_manager.load_animation(
            AnimationState.JUMP,
            ["assets/enemy/frog/frog-Jump.png"],
            sprite_size=sprite_size,
            frame_duration=1,
            loop=True,
            priority=10
        )
        
        # Load fall animation (single frame) - plays during dash/in air
        self.anim_manager.load_animation(
            AnimationState.DASH,
            ["assets/enemy/frog/frog-Fall.png"],
            sprite_size=sprite_size,
            frame_duration=1,
            loop=True,
            priority=10
        )
        
        # Load land animation (2 frames) - plays after dash completes
        land_frames = [
            "assets/enemy/frog/frog-land/frog-land-1.png",
            "assets/enemy/frog/frog-land/frog-land-2.png"
        ]
        self.anim_manager.load_animation(
            AnimationState.FALL,
            land_frames,
            sprite_size=sprite_size,
            frame_duration=4,
            loop=False,
            priority=8,
            next_state=AnimationState.IDLE  # Return to idle after landing
        )
    
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
        has_los, in_cone = self.check_vision_cone(level, ppos)
        dist_to_player = self.update_vision_cone_and_memory(ppos, has_los)
        
        epos = (self.rect.centerx, self.rect.centery)
        
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        
        # Update animation state machine
        from src.entities.animation_system import AnimationState
        
        if self.cool>0:
            self.cool -= 1
        if self.tele_t>0:
            self.tele_t -= 1
            # Play bounce/telegraph animation
            self.anim_manager.play(AnimationState.TELEGRAPH)
            if self.tele_t==0:
                spd = 8.0
                distv = max(1.0, (dx*dx + dy*dy) ** 0.5)
                nx, ny = dx/distv, dy/distv
                self.vx = nx * spd
                self.vy = ny * spd
                self.dash_t = 26
                self.state = 'dash'
                self.cool = 56
                # Play jump animation when launching
                self.anim_manager.play(AnimationState.JUMP, force=True)
        elif self.state=='dash':
            # Play dash/fall animation during dash
            if self.dash_t > 12:  # First half of dash
                self.anim_manager.play(AnimationState.JUMP)
            else:  # Second half - falling
                self.anim_manager.play(AnimationState.DASH)
            
            if self.dash_t > 0:
                self.dash_t -= 1
            else:
                self.vx *= 0.9
                if abs(self.vx) < 1.0:
                    self.state='idle'
                    # Play landing animation
                    if self.on_ground:
                        self.anim_manager.play(AnimationState.FALL, force=True)
        else:
            self.vx = 0
            # Play idle animation when not attacking
            if not self.anim_manager.is_playing or self.anim_manager.current_state not in [AnimationState.TELEGRAPH, AnimationState.JUMP, AnimationState.DASH, AnimationState.FALL]:
                self.anim_manager.play(AnimationState.IDLE)
            
            if has_los and dist_to_player < self.vision_range and self.cool==0:
                self.tele_t = 24
                self.tele_text = '!'

        self.handle_movement(level, player)
        
        self.vy = getattr(self, 'vy', 0) + min(GRAVITY, 10)
        self.rect.y += int(min(10, self.vy))
        
        was_on_ground = self.on_ground
        self.on_ground = False
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
                    self.vy = 0
                    self.on_ground = True
                    # Play landing animation when hitting ground during/after dash
                    if not was_on_ground and self.state == 'dash' and self.dash_t <= 0:
                        self.anim_manager.play(AnimationState.FALL, force=True)
        
        # Update animation system
        self.anim_manager.update()
        
        self.combat.handle_collision_with_player(player)

        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)
    
    def get_base_color(self):
        """Get the base color for Frog enemy."""
        return (80, 200, 80) if not self.combat.is_invincible() else (60, 120, 60)
    
    def draw(self, surf, camera, show_los=False, show_nametags=False, debug_hitboxes=False):
        """Custom draw with sprite animations"""
        if not self.combat.alive:
            return
        
        # Draw debug vision cone
        self.draw_debug_vision(surf, camera, show_los)
        
        # Draw sprite with animation
        sprite_drawn = self.anim_manager.draw(surf, camera, show_invincibility=True)
        
        # Fallback to colored rect if sprite failed
        if not sprite_drawn:
            base_color = self.get_base_color()
            status_color = self.get_status_effect_color(base_color)
            pygame.draw.rect(surf, status_color, camera.to_screen_rect(self.rect), border_radius=5)
        
        # Draw collision box outline in debug mode (F3)
        if debug_hitboxes:
            pygame.draw.rect(surf, (255, 140, 0), camera.to_screen_rect(self.rect), width=2)
        
        # Draw status effect indicators
        self.draw_status_effects(surf, camera)
        
        # Draw telegraph
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text', ''):
            from src.core.utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), (255,200,80), size=18, bold=True)
        
        # Draw nametag
        self.draw_nametag(surf, camera, show_nametags)




class Archer(Enemy):
    """Ranged enemy that shoots arrows with '!!' telegraph. Clean rewrite with proper animation."""
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 16,
            'money_drop': (10, 25)
        }
        super().__init__(x, ground_y, width=32, height=34, combat_config=combat_config,
                        vision_range=350, cone_half_angle=math.pi/4, turn_rate=0.05)
        
        # Combat state
        self.cool = 0
        self.type = "Archer"
        self.tele_t = 0
        self.tele_text = ''
        self.base_speed = 1.2
        self.can_jump = False
        
        # Animation state
        self.attacking = False
        self.arrow_spawned = False
        
        # Initialize animation system
        from src.entities.animation_system import AnimationManager, AnimationState
        self.anim_manager = AnimationManager(self, default_state=AnimationState.IDLE)
        self.anim_manager.set_sprite_offset_y(0)
        
        # Sprite size scaled to match hitbox (32×34 hitbox → 64×48 sprite)
        sprite_size = (64, 48)
        
        # Load idle animation (4 frames, slow breathing)
        self.anim_manager.load_animation(
            AnimationState.IDLE,
            [
                "assets/enemy/Archer-enemy/idle-archer-monster/idle-1.png",
                "assets/enemy/Archer-enemy/idle-archer-monster/idle-2.png",
                "assets/enemy/Archer-enemy/idle-archer-monster/idle-3.png",
                "assets/enemy/Archer-enemy/idle-archer-monster/idle-4.png"
            ],
            sprite_size=sprite_size,
            frame_duration=8,
            loop=True,
            priority=0
        )
        
        # Load run animation (5 frames, faster pace)
        self.anim_manager.load_animation(
            AnimationState.RUN,
            [
                "assets/enemy/Archer-enemy/run-archer-monster/run-1.png",
                "assets/enemy/Archer-enemy/run-archer-monster/run-2.png",
                "assets/enemy/Archer-enemy/run-archer-monster/run-3.png",
                "assets/enemy/Archer-enemy/run-archer-monster/run-4.png",
                "assets/enemy/Archer-enemy/run-archer-monster/run-5.png"
            ],
            sprite_size=sprite_size,
            frame_duration=5,
            loop=True,
            priority=5
        )
        
        # Load attack animation (7 frames, returns to idle)
        def on_attack_complete():
            """Called when attack animation finishes"""
            self.attacking = False
        
        self.anim_manager.load_animation(
            AnimationState.ATTACK,
            [
                "assets/enemy/Archer-enemy/attk-archer-monster/attk-1.png",
                "assets/enemy/Archer-enemy/attk-archer-monster/attk-2.png",
                "assets/enemy/Archer-enemy/attk-archer-monster/attk-3.png",
                "assets/enemy/Archer-enemy/attk-archer-monster/attk-4.png",
                "assets/enemy/Archer-enemy/attk-archer-monster/attk-5.png",
                "assets/enemy/Archer-enemy/attk-archer-monster/attk-6.png",
                "assets/enemy/Archer-enemy/attk-archer-monster/attk-7.png"
            ],
            sprite_size=sprite_size,
            frame_duration=4,
            loop=False,
            priority=10,
            next_state=AnimationState.IDLE,
            on_complete_callback=on_attack_complete
        )
        
        # Load projectile sprite (arrow)
        self.load_projectile_sprite(
            "assets/enemy/Archer-enemy/projectile.png",
            sprite_size=(16, 16)
        )
    
    def _get_terrain_traits(self):
        return ['ground']
    
    def _set_movement_strategy(self):
        self.movement_strategy = MovementStrategyFactory.create_strategy('ranged_tactical')
    
    def tick(self, level, player):
        if not self.combat.alive:
            return
        
        # Update combat and effects
        self.combat.update()
        self.handle_status_effects()
        
        if self.cool > 0:
            self.cool -= 1
        
        # Get player position and vision info
        ppos = (player.rect.centerx, player.rect.centery)
        epos = (self.rect.centerx, self.rect.centery)
        has_los, in_cone = self.check_vision_cone(level, ppos)
        dist_to_player = self.update_vision_cone_and_memory(ppos, has_los)
        
        # Attack state machine
        from src.entities.animation_system import AnimationState
        
        if self.tele_t > 0:
            # Telegraphing attack
            self.tele_t -= 1
            
            # Start attack animation at beginning of telegraph
            if self.tele_t == 17 and not self.attacking:
                self.attacking = True
                self.arrow_spawned = False
                self.anim_manager.play(AnimationState.ATTACK, force=True)
            
            # Spawn arrow at end of telegraph (frame 5 of attack animation)
            if self.tele_t == 0 and not self.arrow_spawned:
                self.arrow_spawned = True
                if has_los and dist_to_player < self.vision_range:
                    # Calculate arrow direction
                    dx = ppos[0] - epos[0]
                    dy = ppos[1] - epos[1]
                    dist = max(1.0, (dx*dx + dy*dy) ** 0.5)
                    nx, ny = dx/dist, dy/dist
                    
                    # Create arrow hitbox
                    hb = pygame.Rect(0, 0, 10, 6)
                    hb.center = self.rect.center
                    arrow = Hitbox(
                        hb, 120, 1, self,
                        dir_vec=(nx, ny),
                        vx=nx*10.0,
                        vy=ny*10.0,
                        has_sprite=True
                    )
                    hitboxes.append(arrow)
                    self.projectile_hitboxes.append(arrow)
                
                self.cool = 60
        elif has_los and self.cool == 0 and dist_to_player < self.vision_range:
            # Start new attack
            self.tele_t = 18
            self.tele_text = '!!'
            self.attacking = False
            self.arrow_spawned = False
        
        # Movement logic
        self.vx = 0
        
        # Retreat when player too close
        if has_los and abs(ppos[0] - epos[0]) < 64:
            self.vx = -1.2 if ppos[0] > epos[0] else 1.2
        
        # Let movement strategy handle patrol/tactical movement
        self.handle_movement(level, player)
        self.handle_gravity(level)
        
        # Update facing based on movement during idle patrol
        alert_level = getattr(self, 'alert_level', 0)
        if alert_level == 0 and abs(self.vx) > 0.1:
            self.facing = 1 if self.vx > 0 else -1
            self.facing_angle = 0 if self.facing > 0 else math.pi
        
        # Animation state logic
        # Only change animation if not attacking (let attack finish naturally)
        if not self.attacking:
            # Choose between idle and run based on movement
            # Use threshold of 0.8 to only show RUN for actual running, not slow strafing
            desired_state = AnimationState.RUN if abs(self.vx) > 0.8 else AnimationState.IDLE
            if self.anim_manager.current_state != desired_state:
                # Force idle animation to play to override priority system
                # IDLE has lower priority (0) than RUN (5), so it needs force=True to interrupt
                force_idle = (desired_state == AnimationState.IDLE)
                self.anim_manager.play(desired_state, force=force_idle)
        
        # Update animation system
        self.anim_manager.update()
        
        # Clean up old arrows
        self.clean_projectile_hitboxes()
        
        # Update position tracking
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)
    
    def get_base_color(self):
        return (200, 200, 80) if not self.combat.is_invincible() else (120, 120, 60)
    
    def draw(self, surf, camera, show_los=False, show_nametags=False, debug_hitboxes=False):
        if not self.combat.alive:
            return
        
        # Draw debug vision cone
        self.draw_debug_vision(surf, camera, show_los)
        
        # Draw sprite
        sprite_drawn = self.anim_manager.draw(surf, camera, show_invincibility=True)
        
        # Fallback to colored rect
        if not sprite_drawn:
            base_color = self.get_base_color()
            status_color = self.get_status_effect_color(base_color)
            pygame.draw.rect(surf, status_color, camera.to_screen_rect(self.rect), border_radius=5)
        
        # Debug hitbox
        if debug_hitboxes:
            pygame.draw.rect(surf, (255, 140, 0), camera.to_screen_rect(self.rect), width=2)
        
        # Draw arrows
        self.draw_projectile_sprites(surf, camera)
        
        # Draw status effects
        self.draw_status_effects(surf, camera)
        
        # Draw telegraph
        if self.tele_t > 0 and self.tele_text:
            from src.core.utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), (255,200,80), size=18, bold=True)
        
        # Draw nametag
        self.draw_nametag(surf, camera, show_nametags)


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
        # Check vision first
        has_los, in_cone = self.check_vision_cone(level, ppos)
        dist_to_player = self.update_vision_cone_and_memory(ppos, has_los)
        
        epos = (self.rect.centerx, self.rect.centery)
        
        epos = (self.rect.centerx, self.rect.centery)
        
        if self.tele_t > 0:
            self.tele_t -= 1
            if self.tele_t == 0 and has_los and dist_to_player < self.vision_range:
                dx = ppos[0] - epos[0]
                dy = ppos[1] - epos[1]
                dist = max(1.0, (dx*dx+dy*dy)**0.5)
                nx, ny = dx/dist, dy/dist
                if self.action == 'missile':
                    hb = pygame.Rect(0,0,18,6); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 36, 4, self, dir_vec=(nx,ny), vx=nx*14.0, vy=ny*14.0))
                    self.cool = 70
                elif self.action == 'fireball':
                    hb = pygame.Rect(0,0,12,12); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 180, 3, self, dir_vec=(nx,ny), vx=nx*6.0, vy=ny*6.0, aoe_radius=48))
                    self.cool = 80
                else:
                    hb = pygame.Rect(0,0,8,8); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 90, 1, self, dir_vec=(nx,ny), vx=nx*9.0, vy=ny*9.0))
                    self.cool = 50
                self.action = None
        elif has_los and self.cool == 0 and dist_to_player < self.vision_range:
            import random
            self.action = random.choices(['bolt','missile','fireball'], weights=[0.5,0.3,0.2])[0]
            if self.action == 'missile':
                self.tele_t = 24
                self.tele_text = '!!!'
            elif self.action == 'fireball':
                self.tele_t = 18
                self.tele_text = '!!'
            else:
                self.tele_t = 16
                self.tele_text = '!!'
        
        from ..ai.enemy_movement import clamp_enemy_to_level
        self.handle_movement(level, player)
        clamp_enemy_to_level(self, level, respect_solids=True)
        
        # Update facing direction based on player position
        if has_los and dist_to_player < self.vision_range:
            self.facing = 1 if ppos[0] > epos[0] else -1
            self.facing_angle = 0 if self.facing > 0 else math.pi

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
        super().__init__(x, ground_y, width=40, height=40, combat_config=combat_config,
                        vision_range=240, cone_half_angle=math.pi/4, turn_rate=0.06)  # Wider vision cone (45 degrees)
        # Assassin-specific properties
        self.state = 'idle'
        # Expose attributes expected by validation/tests.
        self.type = "Assassin"
        self.tele_t = 0
        self.tele_text = ''
        self.cool = 0
        self.action = None  # 'dash' or 'slash'
        self.dash_t = 0
        self.base_speed = 2.0
        self.can_jump = True
        self.jump_cooldown = 0  # Prevent continuous jumping
        self.attacking = False
        
        # Initialize animation system
        from src.entities.animation_system import AnimationManager, AnimationState
        self.anim_manager = AnimationManager(self, default_state=AnimationState.IDLE)
        self.anim_manager.set_sprite_offset_y(0)
        
        # Sprite size for assassin (32x32 for better hitbox match)
        sprite_size = (48, 48)
        
        # Load idle animation (4 frames)
        self.anim_manager.load_animation(
            AnimationState.IDLE,
            [
                "assets/enemy/assasin/idle-assasin/idle-1.png",
                "assets/enemy/assasin/idle-assasin/idle-2.png",
                "assets/enemy/assasin/idle-assasin/idle-3.png",
                "assets/enemy/assasin/idle-assasin/idle-4.png"
            ],
            sprite_size=sprite_size,
            frame_duration=8,
            loop=True,
            priority=0
        )
        
        # Load run animation (6 frames)
        self.anim_manager.load_animation(
            AnimationState.RUN,
            [
                "assets/enemy/assasin/run-assasin/run-1.png",
                "assets/enemy/assasin/run-assasin/run-2.png",
                "assets/enemy/assasin/run-assasin/run-3.png",
                "assets/enemy/assasin/run-assasin/run-4.png",
                "assets/enemy/assasin/run-assasin/run-5.png",
                "assets/enemy/assasin/run-assasin/run-6.png"
            ],
            sprite_size=sprite_size,
            frame_duration=4,
            loop=True,
            priority=5
        )
        
        # Load attack animation (5 frames)
        def on_attack_complete():
            self.attacking = False
            # Ensure we transition to appropriate animation after attack
            # This will be handled in the main animation update logic
        
        self.anim_manager.load_animation(
            AnimationState.ATTACK,
            [
                "assets/enemy/assasin/attk-assasin/attk-1.png",
                "assets/enemy/assasin/attk-assasin/attk-2.png",
                "assets/enemy/assasin/attk-assasin/attk-3.png",
                "assets/enemy/assasin/attk-assasin/attk-4.png",
                "assets/enemy/assasin/attk-assasin/attk-5.png"
            ],
            sprite_size=sprite_size,
            frame_duration=3,
            loop=False,
            priority=10,
            next_state=AnimationState.IDLE,
            on_complete_callback=on_attack_complete
        )
        
        # Load dash attack animation (5 frames)
        self.anim_manager.load_animation(
            AnimationState.DASH,
            [
                "assets/enemy/assasin/dash-attk-assasin/dash-attk-1.png",
                "assets/enemy/assasin/dash-attk-assasin/dash-attk-2.png",
                "assets/enemy/assasin/dash-attk-assasin/dash-attk-3.png",
                "assets/enemy/assasin/dash-attk-assasin/dash-attk-4.png",
                "assets/enemy/assasin/dash-attk-assasin/dash-attk-5.png"
            ],
            sprite_size=sprite_size,
            frame_duration=3,
            loop=True,  # Keep looping during dash duration
            priority=15
        )
    
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
        has_los, in_cone = self.check_vision_cone(level, ppos)
        dist_to_player = self.update_vision_cone_and_memory(ppos, has_los)
        
        epos = (self.rect.centerx, self.rect.centery)
         
        self._in_cone = in_cone
         
        from ..ai.enemy_movement import clamp_enemy_to_level
        from src.entities.animation_system import AnimationState
         
        if self.tele_t > 0:
            self.tele_t -= 1
            # Play telegraph animation (use idle but could add specific telegraph state)
            if self.tele_t > 0:
                self.anim_manager.play(AnimationState.IDLE, force=True)
            
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
                    # Start dash animation
                    self.anim_manager.play(AnimationState.DASH, force=True)
                elif self.action == 'slash':
                    # Start attack animation
                    self.attacking = True
                    self.anim_manager.play(AnimationState.ATTACK, force=True)
                    
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
                # Force transition back to idle animation when dash ends
                self.anim_manager.play(AnimationState.IDLE, force=True)
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
            # Movement behavior based on alert level
            alert_level = getattr(self, 'alert_level', 0)
            
            if has_los and dist_to_player < self.vision_range:
                # Can see player - move toward them
                dx = ppos[0] - epos[0]
                dy = ppos[1] - epos[1]
                
                if abs(dx) > 5:
                    self.vx = 2.0 if dx > 0 else -2.0
                    # Update facing while pursuing
                    self.facing = 1 if dx > 0 else -1
                    self.facing_angle = 0 if self.facing > 0 else math.pi
                else:
                    self.vx = 0
                    
                jump_cooldown = getattr(self, 'jump_cooldown', 0)
                if (hasattr(self, 'can_jump') and self.can_jump and dy < -50 and
                    getattr(self, 'on_ground', False) and jump_cooldown <= 0):
                    self.vy = -10
                    self.on_ground = False
                    self.jump_cooldown = 30
            elif alert_level == 1:
                # Investigating - move toward last known position
                inv_point = getattr(self, 'investigation_point', None)
                if inv_point is not None and isinstance(inv_point, tuple) and len(inv_point) == 2:
                    inv_x, inv_y = inv_point
                    dx_inv = inv_x - epos[0]
                    dy_inv = inv_y - epos[1]
                    if abs(dx_inv) > 20:
                        self.vx = 2.0 if dx_inv > 0 else -2.0
                        # Update facing while investigating
                        self.facing = 1 if dx_inv > 0 else -1
                        self.facing_angle = 0 if self.facing > 0 else math.pi
                    else:
                        self.vx = 0
                else:
                    self.vx = 0
            else:
                # Idle patrol with stable direction changes
                import random as rnd
                
                # Initialize patrol state if needed
                if not hasattr(self, 'patrol_direction'):
                    self.patrol_direction = rnd.choice([-1.5, 1.5])  # Start moving
                    self.patrol_timer = rnd.randint(45, 90)  # Hold direction for 0.75-1.5 seconds
                
                # Count down patrol timer
                if not hasattr(self, 'patrol_timer'):
                    self.patrol_timer = 60
                
                self.patrol_timer -= 1
                
                # Only change direction when timer expires
                if self.patrol_timer <= 0:
                    self.patrol_direction = rnd.choice([-1.5, 0, 1.5])  # Can stand still occasionally
                    self.patrol_timer = rnd.randint(45, 90)
                
                self.vx = self.patrol_direction
                
                # Update facing based on current movement direction (smooth updates)
                if abs(self.vx) > 0.1:
                    self.facing = 1 if self.vx > 0 else -1
                    self.facing_angle = 0 if self.facing > 0 else math.pi
            
            # Apply horizontal movement
            old_rect = self.rect.copy()
            self.rect.x += int(self.vx)
            
            # Handle horizontal collisions
            for s in level.solids:
                if self.rect.colliderect(s):
                    if self.vx > 0 and old_rect.right <= s.left:
                        self.rect.right = s.left
                        self.vx = 0
                        # Reverse patrol direction when hitting wall
                        if alert_level == 0:
                            self.patrol_direction *= -1
                    elif self.vx < 0 and old_rect.left >= s.right:
                        self.rect.left = s.right
                        self.vx = 0
                        # Reverse patrol direction when hitting wall
                        if alert_level == 0:
                            self.patrol_direction *= -1
            
            # Apply gravity and vertical movement
            if self.gravity_affected:
                self.handle_gravity(level)
            
            clamp_enemy_to_level(self, level, respect_solids=False)
        
        # Update animation state based on behavior
        # Improved animation state management with proper transitions
        if self.state == 'dash':
            # Keep dash animation playing during dash
            if self.anim_manager.current_state != AnimationState.DASH:
                self.anim_manager.play(AnimationState.DASH, force=True)
        elif self.attacking:
            # Let attack animation complete naturally - don't interrupt
            pass
        elif abs(self.vx) > 0.8:
            # Running
            if self.anim_manager.current_state != AnimationState.RUN:
                self.anim_manager.play(AnimationState.RUN)
        else:
            # Idle
            if self.anim_manager.current_state != AnimationState.IDLE:
                self.anim_manager.play(AnimationState.IDLE, force=True)
        
        # Update animation system
        self.anim_manager.update()
         
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)

    def get_base_color(self):
        """Get the base color for Assassin enemy."""
        in_cone = getattr(self, '_in_cone', False)
        if in_cone:
            return (60,60,80) if not self.combat.is_invincible() else (40,40,60)
        else:
            return (30,30,40) if not self.combat.is_invincible() else (20,20,30)
    
    def draw(self, surf, camera, show_los=False, show_nametags=False, debug_hitboxes=False):
        """Custom draw with sprite animations and semi-invisibility effect"""
        if not self.combat.alive:
            return
        
        # Draw debug vision cone
        self.draw_debug_vision(surf, camera, show_los)
        
        # Draw sprite with animation
        sprite_drawn = self.anim_manager.draw(surf, camera, show_invincibility=True)
        
        # Fallback to colored rect if sprite failed (with semi-invisibility)
        if not sprite_drawn:
            base_color = self.get_base_color()
            status_color = self.get_status_effect_color(base_color)
            pygame.draw.rect(surf, status_color, camera.to_screen_rect(self.rect), border_radius=5)
        
        # Draw collision box outline in debug mode (F3)
        if debug_hitboxes:
            pygame.draw.rect(surf, (255, 140, 0), camera.to_screen_rect(self.rect), width=2)
        
        # Draw status effect indicators
        self.draw_status_effects(surf, camera)
        
        # Draw telegraph
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text', ''):
            from src.core.utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), (255,200,80), size=18, bold=True)
        
        # Draw nametag
        self.draw_nametag(surf, camera, show_nametags)


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
        has_los, in_cone = self.check_vision_cone(level, ppos)
        dist_to_player = self.update_vision_cone_and_memory(ppos, has_los)
        
        epos = (self.rect.centerx, self.rect.centery)
        
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
        
        # Update facing direction based on movement
        if abs(self.vx) > 0.1:
            self.facing = 1 if self.vx > 0 else -1
            self.facing_angle = 0 if self.facing > 0 else math.pi

        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)

    def get_base_color(self):
        """Get the base color for Frog enemy."""
        return (80, 200, 80) if not self.combat.is_invincible() else (60, 120, 60)


class Golem(Enemy):
    """Boss with random pattern: dash (!), shoot (!!), stun (!!). Features sprite animations."""
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 120,
            'default_ifr': 12,
            'money_drop': (50, 100)
        }
        super().__init__(x, ground_y, width=60, height=90, combat_config=combat_config,
                        vision_range=500, cone_half_angle=math.pi/3, turn_rate=0.03)
        # ----------------------------
        # Basic properties
        # ----------------------------
        self.cool = 0
        self.type = "Golem"
        self.tele_t = 0
        self.tele_text = ""
        self.action = None
        self.base_speed = 0.8
        self.can_jump = False
        self.facing = 1
        
        # ----------------------------
        # Load Sprite System (Friend's Code - Using Universal System)
        # ----------------------------
        # Load idle sprite
        try:
            img = pygame.image.load("assets/monster/Dark_Knight.png").convert_alpha()
            self.sprite_idle = pygame.transform.scale(img, (96,128))
        except:
            print("[ERROR] Missing Dark_Knight.png")  # Friend's error handling
            self.sprite_idle = None
        
        self.sprite = self.sprite_idle
        self.sprite_offset_y = 18  # Align the sprite bottom with the new hitbox bottom
        
        # Sprite rect
        if self.sprite:
            self.sprite_rect = self.sprite.get_rect()
            self.sprite_rect.midbottom = self.rect.midbottom
        else:
            self.sprite_rect = self.rect.copy()
        
        # ----------------------------
        # Load Attack Animation (Friend's Code - Using Universal System)
        # ----------------------------
        self.atk_frames = []
        for i in range(1,5):
            path = f"assets/monster/atk/Dark_Knight_ATK{i}.png"
            try:
                frame = pygame.image.load(path).convert_alpha()
                self.atk_frames.append(pygame.transform.scale(frame,(96,128)))
            except:
                print(f"[ERROR] Cannot load {path}")  # Friend's error handling
        
        self.play_attack_anim = False
        self.atk_index = 0
        self.atk_timer = 0
        self.atk_speed = 4
        
        # ----------------------------
        # Load Aura Projectile Sprite (Friend's Code - Using Universal System)
        # ----------------------------
        try:
            aura_img = pygame.image.load("assets/monster/atk/Dark_Knight_Aura.png").convert_alpha()
            self.aura_sprite = pygame.transform.scale(aura_img, (42,42))
            # Note: Using aura_sprite instead of projectile_sprite for Golem's specific naming
            self.projectile_sprite = self.aura_sprite  # Map to universal system
        except:
            print("[ERROR] Missing Aura sprite")  # Friend's error handling
            self.aura_sprite = None
            self.projectile_sprite = None
        
        # Aura projectile hitboxes (Friend's code - using universal projectile_hitboxes)
        # NOTE: We use projectile_hitboxes directly (universal system)
        self.projectile_hitboxes = []
        # For Golem, aura_hitboxes is just an alias to projectile_hitboxes
        # Friend's original code used "aura_hitboxes" but universal system uses "projectile_hitboxes"
        # Both work, they point to the same list
    
    @property
    def aura_hitboxes(self):
        """Alias for projectile_hitboxes (Friend's original naming)"""
        return self.projectile_hitboxes
    
    @aura_hitboxes.setter
    def aura_hitboxes(self, value):
        """Setter to keep aura_hitboxes and projectile_hitboxes in sync"""
        self.projectile_hitboxes = value
    
    def _get_terrain_traits(self):
        """Golem can move through earth and break obstacles"""
        return ['ground', 'strong', 'destructible', 'fire_resistant']
    
    def _set_movement_strategy(self):
        """Set movement strategy for Golem"""
        self.movement_strategy = MovementStrategyFactory.create_strategy('ground_patrol')

    def tick(self, level, player):
        if not self.combat.alive:
            return
        
        self.combat.update()
        self.handle_status_effects()
        
        if self.cool > 0:
            self.cool -= 1
        
        # Player pos
        ppos = (player.rect.centerx, player.rect.centery)
        epos = (self.rect.centerx, self.rect.centery)
        
        # INTEGRATION: Friend's simple LOS + Your advanced vision system
        # Option 1: Friend's original simple LOS (current)
        has_los = los_clear(level, epos, ppos)
        
        # Option 2: Use your advanced vision cone system (uncomment to enable)
        # has_los, in_cone = self.check_vision_cone(level, ppos)
        # dist_to_player = self.update_vision_cone_and_memory(ppos, has_los)
        # This gives: alert levels, pursuit memory, investigation points
        
        # ----------------------------
        # Telegraph finish → perform action
        # ----------------------------
        if self.tele_t > 0:
            self.tele_t -= 1
            if self.tele_t == 0:
                dx = ppos[0] - epos[0]
                dy = ppos[1] - epos[1]
                dist = max(1.0, (dx*dx+dy*dy)**0.5)
                nx, ny = dx/dist, dy/dist
                
                # ----------- DASH -----------
                if self.action == "dash":
                    self.play_attack_anim = True
                    self.atk_index = 0
                    self.atk_timer = 0
                    self.vx = nx * 8
                    self.vy = ny * 8
                
                # ----------- SHOOT (Aura) -----------
                elif self.action == "shoot" and has_los:
                    self.play_attack_anim = True
                    self.atk_index = 0
                    self.atk_timer = 0
                    self.play_attack_anim = True
                    self.atk_index = 0
                    self.atk_timer = 0
                    hb = pygame.Rect(0,0,26,26)
                    hb.center = self.rect.center
                    new_hb = Hitbox(
                        hb,
                        120,
                        4,
                        self,
                        dir_vec=(nx,ny),
                        vx=nx*8,
                        vy=ny*8,
                        has_sprite=True  # Suppress fallback rectangle (sprite drawn via draw_projectile_sprites)
                    )
                    hitboxes.append(new_hb)
                    self.projectile_hitboxes.append(new_hb)  # Use universal system directly
                
                # ----------- STUN -----------
                elif self.action == "stun":
                    self.play_attack_anim = True
                    self.atk_index = 0
                    self.atk_timer = 0
                    r = 72
                    hb = pygame.Rect(0,0,r*2,r*2)
                    hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb,24,0,self,aoe_radius=r,tag='stun'))
                
                self.cool = 70
        
        # ----------------------------
        # Choose next attack
        # ----------------------------
        elif has_los and self.cool == 0:
            self.action = random.choice(['dash','shoot','stun'])
            self.tele_text = "!" if self.action=='dash' else "!!"
            self.tele_t = 22 if self.action=='dash' else 18
        
        # ----------------------------
        # Move X
        # ----------------------------
        if abs(self.vx) > 0:
            self.vx *= 0.9
            if abs(self.vx) < 1:
                self.vx = 0
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx > 0:
                    self.rect.right = s.left
                else:
                    self.rect.left = s.right
                self.vx = 0
        
        # Facing (Friend's code - now uses universal helper)
        self.update_facing_from_player(player)
        
        # ----------------------------
        # Attack Animation (Friend's code - using universal helper)
        # ----------------------------
        self.update_attack_animation()  # Universal helper does friend's exact logic
        
        # ----------------------------
        # Clean aura hitboxes (Friend's code - using universal helper)
        # ----------------------------
        self.clean_projectile_hitboxes()  # Universal helper cleans aura_hitboxes
        
        # Sync sprite position (Friend's code - using universal helper)
        self.sync_sprite_position()
        
        # ----------------------------
        # Move Y
        # ----------------------------
        self.vy = getattr(self,'vy',0) + min(GRAVITY,10)
        self.rect.y += int(min(10,self.vy))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
                    self.vy = 0
        
        # Sync sprite position again after vertical movement (Friend's code - universal helper)
        self.sync_sprite_position()
        
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)
        
        self.combat.handle_collision_with_player(player)

    def get_base_color(self):
        """Get the base color for Golem enemy."""
        return (240, 180, 60) if not self.combat.is_invincible() else (140, 120, 50)
    
    def draw(self, surf, camera, show_los=False, show_nametags=False, debug_hitboxes=False):
        """Custom draw with sprite animations (Friend's code - using universal helpers)"""
        if not self.combat.alive:
            return
        
        # Optional debug: vision cone/LOS
        self.draw_debug_vision(surf, camera, show_los)
        
        # Draw sprite with animation (Friend's exact code via universal helper)
        sprite_drawn = self.draw_sprite_with_animation(surf, camera)
        
        if not sprite_drawn:
            # Fallback to colored rect (Friend's fallback code)
            base_color = self.get_base_color()
            status_color = self.get_status_effect_color(base_color)
            pygame.draw.rect(surf, status_color, camera.to_screen_rect(self.rect), border_radius=getattr(self, 'draw_border_radius', 4))
        
        # Draw collision box outline in debug mode (F3)
        if debug_hitboxes:
            pygame.draw.rect(surf, (255, 140, 0), camera.to_screen_rect(self.rect), width=2)
        
        # Draw aura projectiles (Friend's code - using universal helper)
        self.draw_projectile_sprites(surf, camera)
        
        # Telegraph
        if self.tele_t > 0:
            from src.core.utils import draw_text
            tele_pos = (self.rect.centerx-6, self.rect.top-12)
            draw_text(
                surf, self.tele_text,
                camera.to_screen(tele_pos),
                (255,120,90), size=22, bold=True
            )
        
        # Draw status effect indicators
        self.draw_status_effects(surf, camera)
        
        # Name and HP
        self.draw_nametag(surf, camera, show_nametags)

class KnightMonster(Enemy):
    """Elite melee enemy with combo attacks, parry, evasive dodges, jumping, and double-dash abilities.
    
    Advanced AI features:
    - Explores entire map (not just back-and-forth patrol)
    - Pathfinding to reach different platforms
    - Responds immediately to allied alerts
    """
    def __init__(self, x, ground_y):
        combat_config = {
            'max_hp': 28,
            'default_ifr': 8,
            'money_drop': (20, 40)
        }
        super().__init__(x, ground_y, width=28, height=22, combat_config=combat_config,
                        vision_range=280, cone_half_angle=math.pi/4, turn_rate=0.06)
        
        # KnightMonster-specific properties
        self.type = "KnightMonster"
        self.state = 'idle'  # idle, windup, combo, dash_evade, parry, recover, exploring, pathfinding
        self.cool = 0
        self.windup_t = 0
        self.combo_len = 0
        self.combo_idx = 0
        self.combo_gap_t = 0
        self.evade_t = 0
        self.parry_window = 0
        self.parry_cool = 0
        self.tele_text = ''
        
        # Behavior tuning
        self.hit_windup = 12
        self.hit_gap = 10
        self.evade_speed = 8.0
        self.evade_time = 12
        self.dash_after_evade_slow = 0.86
        self.parry_len = 12
        self.parry_post_recover = 18
        self.min_combo_dist = 22
        self.max_combo_dist = 75
        self.evade_trigger_dist = 64
        
        # Edge-detect player attack start for 10% "immortal dodge"
        self._prev_player_attacking = False
        
        self.base_speed = 1.0
        self.can_jump = True  # Enable jumping
        
        # Jump mechanics (similar to player)
        self.jump_power = -10.0  # Negative = upward
        self.double_jumps_max = 1  # Can double jump once
        self.double_jumps_remaining = 1
        self.jump_cooldown = 0  # Frames before can jump again
        
        # Dash mechanics (double dash like player)
        self.dash_charges = 2  # Can dash twice
        self.dash_charges_max = 2
        self.dash_speed = 12.0  # Same as player
        self.dash_time = 10  # Frames dash lasts
        self.dashing_frames = 0  # Current dash timer
        self.dash_cooldown = 0  # Cooldown between dashes
        self.dash_direction = 0  # Direction of current dash
        
        # Exploration system - visit entire map
        self.exploration_mode = True  # Always exploring when not in combat
        self.exploration_targets = []  # List of positions to visit
        self.current_target = None  # Current exploration waypoint
        self.visited_positions = set()  # Track visited areas
        self.stuck_timer = 0  # Detect if stuck
        self.last_position = (x, ground_y)
        
        # Pathfinding for reaching platforms
        self.path_to_target = []  # List of waypoints to follow
        self.pathfinding_cooldown = 0  # Cooldown before recalculating path
        
        # ----------------------------
        # Load Knight-Monster Sprite Animations
        # ----------------------------
        from src.entities.animation_system import AnimationManager, AnimationState
        self.anim_manager = AnimationManager(self, default_state=AnimationState.IDLE)
        self.anim_manager.set_sprite_offset_y(-2)
        
        # Sprite size (knight-monster sprites)
        sprite_size = (56, 56)
        
        # Load idle animation (4 frames)
        self.anim_manager.load_animation(
            AnimationState.IDLE,
            [
                "assets/enemy/knight-monster/idle-knight-enemy/Idle-1.png",
                "assets/enemy/knight-monster/idle-knight-enemy/Idle-2.png",
                "assets/enemy/knight-monster/idle-knight-enemy/Idle-3.png",
                "assets/enemy/knight-monster/idle-knight-enemy/Idle-4.png"
            ],
            sprite_size=sprite_size,
            frame_duration=8,
            loop=True,
            priority=0
        )
        
        # Load run animation (8 frames)
        self.anim_manager.load_animation(
            AnimationState.RUN,
            [
                "assets/enemy/knight-monster/run/run-1.png",
                "assets/enemy/knight-monster/run/run-2.png",
                "assets/enemy/knight-monster/run/run-3.png",
                "assets/enemy/knight-monster/run/run-4.png",
                "assets/enemy/knight-monster/run/run-5.png",
                "assets/enemy/knight-monster/run/run-6.png",
                "assets/enemy/knight-monster/run/run-7.png",
                "assets/enemy/knight-monster/run/run-8.png"
            ],
            sprite_size=sprite_size,
            frame_duration=4,
            loop=True,
            priority=5
        )
        
        # Load normal attack animation (4 frames) - for combo strikes
        self.anim_manager.load_animation(
            AnimationState.ATTACK,
            [
                "assets/enemy/knight-monster/norm-atk/Attack1-pat1.png",
                "assets/enemy/knight-monster/norm-atk/Attack1-pat2.png",
                "assets/enemy/knight-monster/norm-atk/Attack1-pat3.png",
                "assets/enemy/knight-monster/norm-atk/Attack1-pat4.png"
            ],
            sprite_size=sprite_size,
            frame_duration=3,
            loop=False,
            priority=10,
            next_state=AnimationState.IDLE
        )
        
        # Load combo attack animation (7 frames) - for special combo finisher
        self.anim_manager.load_animation(
            AnimationState.SKILL_1,
            [
                "assets/enemy/knight-monster/combo-atk/Attack2-pat1.png",
                "assets/enemy/knight-monster/combo-atk/Attack2-pat2.png",
                "assets/enemy/knight-monster/combo-atk/Attack2-pat3.png",
                "assets/enemy/knight-monster/combo-atk/Attack2-pat4.png",
                "assets/enemy/knight-monster/combo-atk/Attack2-pat5.png",
                "assets/enemy/knight-monster/combo-atk/Attack2-pat6.png",
                "assets/enemy/knight-monster/combo-atk/Attack2-pat7.png"
            ],
            sprite_size=sprite_size,
            frame_duration=3,
            loop=False,
            priority=15,
            next_state=AnimationState.IDLE
        )
        
        # Load fall animation (3 frames) - for jumping/falling/dash
        self.anim_manager.load_animation(
            AnimationState.FALL,
            [
                "assets/enemy/knight-monster/fall/fall-1.png",
                "assets/enemy/knight-monster/fall/fall-2.png",
                "assets/enemy/knight-monster/fall/fall-3.png"
            ],
            sprite_size=sprite_size,
            frame_duration=4,
            loop=True,
            priority=6
        )
        
        # Use DASH state for evasive dash animation
        self.anim_manager.load_animation(
            AnimationState.DASH,
            [
                "assets/enemy/knight-monster/run/run-1.png",
                "assets/enemy/knight-monster/run/run-3.png",
                "assets/enemy/knight-monster/run/run-5.png",
                "assets/enemy/knight-monster/run/run-7.png"
            ],
            sprite_size=sprite_size,
            frame_duration=2,
            loop=True,
            priority=12
        )
    
    def _get_terrain_traits(self):
        """KnightMonster is a ground-based fighter"""
        return ['ground', 'strong']
    
    def _set_movement_strategy(self):
        """KnightMonster uses custom AI, no standard strategy"""
        self.movement_strategy = None
    
    def tick(self, level, player):
        if not self.combat.alive:
            return
        
        # Update combat timers
        self.combat.update()
        self.handle_status_effects()
        
        # Decrement stun timer
        if getattr(self, 'stunned', 0) > 0:
            self.stunned -= 1
        
        # Decrement stun timer
        if getattr(self, 'stunned', 0) > 0:
            self.stunned -= 1
        
        # Custom timers
        if self.cool > 0:
            self.cool -= 1
        if self.parry_cool > 0:
            self.parry_cool -= 1
        if self.parry_window > 0:
            self.parry_window -= 1
        if self.jump_cooldown > 0:
            self.jump_cooldown -= 1
        if self.dash_cooldown > 0:
            self.dash_cooldown -= 1
        
        # Update dash state
        if self.dashing_frames > 0:
            self.dashing_frames -= 1
            if self.dashing_frames == 0:
                self.vx = 0  # Stop dashing
        
        # Reset double jumps when on ground
        if self.on_ground:
            self.double_jumps_remaining = self.double_jumps_max
            # Recharge dash charges when on ground
            if self.dash_charges < self.dash_charges_max and self.dash_cooldown == 0:
                self.dash_charges = self.dash_charges_max
        
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        dx, dy = ppos[0] - epos[0], ppos[1] - epos[1]
        dist = (dx*dx + dy*dy) ** 0.5
        
        # Check vision first for advanced AI
        has_los, in_cone = self.check_vision_cone(level, ppos)
        # Turn smoothly toward player with memory
        dist_to_player = self.update_vision_cone_and_memory(ppos, has_los)
        has_los, in_cone = self.check_vision_cone(level, ppos)
        dist_to_player = self.update_vision_cone_and_memory(ppos, has_los)
        
        # Player attack status detection
        player_attacking_now = bool(
            getattr(player, 'attack_cd', 0) < ATTACK_COOLDOWN - 5 or
            getattr(player, 'charging', False)
        )
        
        # 10% "immortal" dodge on attack start
        if (not self._prev_player_attacking) and player_attacking_now:
            if has_los and dist < self.evade_trigger_dist and self.cool == 0 and random.random() < 0.10:
                self._start_evade_away_from(dx, dy, immortal=True)
        self._prev_player_attacking = player_attacking_now
        
        # CHECK FOR ALLIED ALERTS - Immediate response to combat
        from src.entities.entity_common import alert_system
        has_alert, alert_pos, alert_level = alert_system.check_nearby_alerts(self)
        if has_alert and alert_pos and not has_los:
            # Ally spotted player! Navigate there immediately
            self.current_target = alert_pos
            self.tele_text = '!!'
            # Override position to investigate alert
            ppos = alert_pos
            dx, dy = ppos[0] - epos[0], ppos[1] - epos[1]
            dist = (dx*dx + dy*dy) ** 0.5
        
        # ---- State machine ----
        # Skip AI decisions if stunned or frozen
        if getattr(self, 'stunned', 0) > 0 or getattr(self, 'frozen', False):
            # Still apply movement decay during stun
            self.vx *= 0.9
            # Apply slow movement and gravity, then return
            actual_vx = self.vx * getattr(self, 'slow_mult', 1.0)
            self.rect.x += int(actual_vx)
            for s in level.solids:
                if self.rect.colliderect(s):
                    if actual_vx > 0:
                        self.rect.right = s.left
                    else:
                        self.rect.left = s.right
                    self.vx = 0.0
            self.vy = min(self.vy + min(GRAVITY, 10), 10)
            self.rect.y += int(self.vy)
            for s in level.solids:
                if self.rect.colliderect(s):
                    if self.rect.bottom > s.top and self.rect.centery < s.centery:
                        self.rect.bottom = s.top
                        self.vy = 0.0
            self.x = float(self.rect.centerx)
            self.y = float(self.rect.bottom)
            return
        
        if self.state == 'idle':
            self.tele_text = ''
            player_threat = player_attacking_now
            
            if has_los and dist < self.evade_trigger_dist and self.cool == 0 and (player_threat or random.random() < 0.06):
                self._start_evade_away_from(dx, dy, immortal=False)
            elif has_los and self.cool == 0 and self.min_combo_dist <= dist <= self.max_combo_dist:
                self._start_combo()
            elif has_los and dist < self.min_combo_dist and self.parry_cool == 0 and random.random() < 0.03:
                self._start_parry()
            elif has_los and dist > self.max_combo_dist and dist < 400:
                # Player is far away but visible - use mobility to approach
                self._advanced_approach(dx, dy, dist, level)
            else:
                # EXPLORATION MODE - Navigate entire map
                self._explore_map(level, epos)
        
        elif self.state == 'windup':
            if self.windup_t == 0:
                if (has_los and self.min_combo_dist <= dist <= self.max_combo_dist and 
                    player_attacking_now and self.parry_cool == 0):
                    self._parry_clash(player)
                else:
                    self._do_strike(player)
                    if self.combo_idx < self.combo_len:
                        self.combo_idx += 1
                        self.combo_gap_t = self.hit_gap
                        self.windup_t = self.hit_windup
                        self.tele_text = '!' * min(3, self.combo_idx)
                    else:
                        self.state = 'recover'
                        self.cool = 36
                        self.tele_text = ''
            else:
                self.windup_t -= 1
        
        elif self.state == 'combo':
            if self.combo_gap_t > 0:
                self.combo_gap_t -= 1
            else:
                self.state = 'windup'
        
        elif self.state == 'dash_evade':
            if self.evade_t > 0:
                self.evade_t -= 1
                self.vx *= self.dash_after_evade_slow
            else:
                self.vx = 0.0
                self.state = 'recover'
                self.cool = 28
        
        elif self.state == 'parry':
            self.vx *= 0.8
            if self.parry_window == 0:
                self.state = 'recover'
                self.cool = self.parry_post_recover
        
        elif self.state == 'recover':
            self.vx *= 0.85
            if self.cool == 0:
                self.state = 'idle'
        
        # Movement and collisions (apply slow effect)
        actual_vx = self.vx * getattr(self, 'slow_mult', 1.0)
        self.rect.x += int(actual_vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if actual_vx > 0:
                    self.rect.right = s.left
                else:
                    self.rect.left = s.right
                self.vx = 0.0
        
        # Gravity
        self.vy = min(self.vy + min(GRAVITY, 10), 10)
        self.rect.y += int(self.vy)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
                    self.vy = 0.0
        
        # Update facing direction toward player when has LOS
        if has_los and abs(dx) > 5:
            self.facing = 1 if dx > 0 else -1
            self.facing_angle = 0 if self.facing > 0 else math.pi
        
        # ----------------------------
        # Update Animation State
        # ----------------------------
        from src.entities.animation_system import AnimationState
        
        # Determine which animation to play based on state
        if self.state in ['windup', 'combo']:
            # Attacking state
            if self.combo_idx >= self.combo_len - 1 and self.combo_len > 1:
                # Final strike in combo - use heavy attack animation
                if self.anim_manager.current_state != AnimationState.SKILL_1:
                    self.anim_manager.play(AnimationState.SKILL_1, force=True)
            else:
                # Regular combo strike
                if self.anim_manager.current_state != AnimationState.ATTACK:
                    self.anim_manager.play(AnimationState.ATTACK, force=True)
        elif self.state == 'dash_evade' or self.dashing_frames > 0:
            # Dashing/evading
            if self.anim_manager.current_state != AnimationState.DASH:
                self.anim_manager.play(AnimationState.DASH, force=True)
        elif self.state == 'parry':
            # Parrying - use idle with tension
            if self.anim_manager.current_state != AnimationState.IDLE:
                self.anim_manager.play(AnimationState.IDLE, force=True)
        elif not self.on_ground and abs(self.vy) > 2:
            # Falling/jumping
            if self.anim_manager.current_state != AnimationState.FALL:
                self.anim_manager.play(AnimationState.FALL)
        elif abs(self.vx) > 1.5:
            # Running
            if self.anim_manager.current_state != AnimationState.RUN:
                self.anim_manager.play(AnimationState.RUN)
        else:
            # Idle
            if self.anim_manager.current_state != AnimationState.IDLE:
                self.anim_manager.play(AnimationState.IDLE, force=True)
        
        # Update animation system
        self.anim_manager.update()
        
        # Update position tracking
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.bottom)
        
        # Handle collision with player
        self.combat.handle_collision_with_player(player)
    
    # -------------- Actions --------------
    
    def _start_combo(self):
        """Start a combo attack sequence"""
        self.combo_len = random.randint(1, 3)
        self.combo_idx = 1
        self.state = 'windup'
        self.windup_t = self.hit_windup
        self.combo_gap_t = 0
        self.tele_text = '!'
    
    def _do_strike(self, player):
        """Execute a single strike in the combo"""
        hb = pygame.Rect(0, 0, int(self.rect.w * 1.25), int(self.rect.h * 0.72))
        if self.facing > 0:
            hb.midleft = (self.rect.right, self.rect.centery)
        else:
            hb.midright = (self.rect.left, self.rect.centery)
        
        # Damage scales with combo: 4, 6, 8
        base = 4
        dmg = base + (self.combo_idx - 1) * 2
        kb = 1 if self.combo_idx < self.combo_len else 2
        
        hitboxes.append(Hitbox(hb, 10, dmg, self, dir_vec=(self.facing, 0)))
        self.vx = self.facing * 1.2
        self.state = 'combo'
    
    def _start_evade_away_from(self, dx, dy, immortal=False):
        """Dash away from player to evade"""
        away = -1 if dx > 0 else 1
        self.vx = away * self.evade_speed
        self.evade_t = self.evade_time
        self.state = 'dash_evade'
        self.cool = 22
        self.tele_text = ':P' if immortal else ('→' if away > 0 else '←')
        
        # Grant invincibility during evade
        ifr_duration = self.evade_time if immortal else (self.evade_time // 2)
        self.combat.invincible_frames = max(self.combat.invincible_frames, ifr_duration)
    
    def _start_parry(self):
        """Enter parry stance"""
        self.state = 'parry'
        self.parry_window = self.parry_len
        self.parry_cool = 90
        self.tele_text = '⛨'
        self.combat.invincible_frames = max(self.combat.invincible_frames, 6)
    
    def _parry_clash(self, player):
        """Parry and counter player attack"""
        self.state = 'parry'
        self.parry_window = max(6, self.parry_len // 2)
        self.parry_cool = 60
        self.tele_text = '!'
        self.combat.invincible_frames = max(self.combat.invincible_frames, 8)
        
        floating.append(DamageNumber(self.rect.centerx, self.rect.top - 10, "CLASH!", CYAN))
        
        # Knockback player
        if hasattr(player, 'combat'):
            knockback_x = (1 if player.rect.centerx > self.rect.centerx else -1) * 3
            knockback_y = -6
            player.combat.take_damage(0, (knockback_x, knockback_y), self)
    
    def _perform_jump(self):
        """Perform a jump (or double jump if in air)"""
        if self.on_ground and self.jump_cooldown == 0:
            # Ground jump
            self.vy = self.jump_power
            self.on_ground = False
            self.jump_cooldown = 10
            self.tele_text = '↑'
        elif not self.on_ground and self.double_jumps_remaining > 0:
            # Double jump
            self.vy = self.jump_power * 0.9  # Slightly weaker double jump
            self.double_jumps_remaining -= 1
            self.tele_text = '⇈'
    
    def _perform_dash(self, direction):
        """Perform a dash in the given direction (1=right, -1=left)"""
        if self.dash_charges > 0 and self.dash_cooldown == 0:
            self.vx = direction * self.dash_speed
            self.dashing_frames = self.dash_time
            self.dash_direction = direction
            self.dash_charges -= 1
            self.dash_cooldown = 30  # 0.5 second cooldown
            self.facing = direction
            self.facing_angle = 0 if direction > 0 else math.pi
            self.tele_text = '»' if direction > 0 else '«'
    
    def _advanced_approach(self, dx, dy, dist, level):
        """Use advanced mobility (jump/dash) to approach player"""
        # Move toward player
        move_dir = 1 if dx > 0 else -1
        self.vx = move_dir * 2.0
        
        # Jump over obstacles or to reach player at different height
        if dy < -40 and self.on_ground and self.jump_cooldown == 0:
            # Player is above, jump toward them
            self._perform_jump()
        
        # Use dash to close distance quickly (20% chance per frame when far)
        if dist > 150 and random.random() < 0.02 and self.dash_charges > 0 and self.dash_cooldown == 0:
            self._perform_dash(move_dir)
        
        # Update facing
        self.facing = move_dir
        self.facing_angle = 0 if move_dir > 0 else math.pi
    
    def _explore_map(self, level, epos):
        """Exploration AI - Wander entire map and find paths to different platforms"""
        # Check if stuck (not moving)
        current_pos = (self.rect.centerx, self.rect.centery)
        if abs(current_pos[0] - self.last_position[0]) < 2 and abs(current_pos[1] - self.last_position[1]) < 2:
            self.stuck_timer += 1
        else:
            self.stuck_timer = max(0, self.stuck_timer - 1)  # Gradually decrease when moving
        self.last_position = current_pos
        
        # If stuck for too long, try to unstuck with jump/dash
        if self.stuck_timer > 15:  # Reduced from 20 to 15 for even faster unstuck response
            if self.on_ground and self.jump_cooldown == 0:
                self._perform_jump()
                # Jump in opposite direction to get away from wall
                if self.vx != 0:
                    self.vx = -self.vx * 2
                else:
                    self.vx = random.choice([-3, 3])
                self.stuck_timer = 0
                self.current_target = None  # Force new target
            elif self.dash_charges > 0 and self.dash_cooldown == 0:
                # Dash in opposite direction or random if no vx
                dash_dir = -1 if self.vx > 0 else 1 if self.vx < 0 else random.choice([-1, 1])
                self._perform_dash(dash_dir)
                self.stuck_timer = 0
                self.current_target = None  # Force new target
            elif self.stuck_timer > 40:  # Reduced from 60
                # Really stuck - force new target and stop moving
                self.vx = 0
                self.current_target = None
                self.stuck_timer = 0
        
        # Find new exploration target if needed
        if self.current_target is None or self._reached_target(epos):
            self.current_target = self._find_exploration_target(level, epos)
            self.visited_positions.add((int(epos[0] // 48), int(epos[1] // 48)))  # Mark 48px grid as visited
        
        if self.current_target:
            # Navigate to target using pathfinding
            self._navigate_to_target(level, epos, self.current_target)
    
    def _find_exploration_target(self, level, current_pos):
        """Find next unvisited area to explore"""
        # Generate potential targets across the map
        candidates = []
        level_width = level.w * TILE
        level_height = level.h * TILE if hasattr(level, 'h') else 600
        
        # Sample points across the level
        for _ in range(20):
            tx = random.randint(48, level_width - 48)
            ty = random.randint(48, level_height - 48)
            grid_pos = (int(tx // 48), int(ty // 48))
            
            # Check if target is inside a wall - skip if so
            test_rect = pygame.Rect(tx - 10, ty - 10, 20, 20)
            inside_wall = any(test_rect.colliderect(s) for s in level.solids)
            
            # Prefer unvisited locations that aren't inside walls
            if grid_pos not in self.visited_positions and not inside_wall:
                candidates.append((tx, ty))
        
        # If all explored or all inside walls, pick random valid location
        if not candidates:
            # Try to find any valid non-wall location
            for _ in range(10):
                tx = random.randint(48, level_width - 48)
                ty = random.randint(48, level_height - 48)
                test_rect = pygame.Rect(tx - 10, ty - 10, 20, 20)
                inside_wall = any(test_rect.colliderect(s) for s in level.solids)
                if not inside_wall:
                    return (tx, ty)
            # Fallback to current position if can't find valid target
            return current_pos
        
        # Pick farthest unvisited location
        best_target = max(candidates, key=lambda p: abs(p[0] - current_pos[0]) + abs(p[1] - current_pos[1]))
        return best_target
    
    def _reached_target(self, pos):
        """Check if reached current target"""
        if not self.current_target:
            return True
        dx = self.current_target[0] - pos[0]
        dy = self.current_target[1] - pos[1]
        dist = (dx*dx + dy*dy) ** 0.5
        return dist < 32  # Within 32 pixels = reached
    
    def _navigate_to_target(self, level, current_pos, target_pos):
        """Navigate to target using jumps and dashes to overcome obstacles"""
        dx = target_pos[0] - current_pos[0]
        dy = target_pos[1] - current_pos[1]
        
        # Move horizontally toward target
        move_dir = 1 if dx > 0 else -1
        
        # Check for obstacles ahead with better detection
        check_dist = 32  # Increased detection distance
        ahead_x = self.rect.centerx + (move_dir * check_dist)
        probe_wall = pygame.Rect(ahead_x - 2, self.rect.centery - 10, 4, 20)
        probe_floor = pygame.Rect(ahead_x - 2, self.rect.bottom + 1, 4, 3)
        
        # Also check if we're currently touching a wall
        touching_wall_rect = pygame.Rect(
            self.rect.right if move_dir > 0 else self.rect.left - 2,
            self.rect.centery - 10,
            2,
            20
        )
        currently_touching_wall = any(touching_wall_rect.colliderect(s) for s in level.solids)
        
        wall_ahead = any(probe_wall.colliderect(s) for s in level.solids) or currently_touching_wall
        floor_ahead = any(probe_floor.colliderect(s) for s in level.solids)
        
        # Pathfinding logic
        if wall_ahead:
            # Wall blocking ahead - stop immediately and try to overcome
            if self.on_ground and self.jump_cooldown == 0:
                # Try to jump over it
                self._perform_jump()
                self.vx = move_dir * 3.0
            elif self.on_ground and self.dash_charges > 0 and self.dash_cooldown == 0:
                # Can't jump but can dash - try dashing
                self._perform_dash(move_dir)
            else:
                # Can't jump or dash - STOP and pick new target
                self.vx = 0
                # Increment stuck timer to trigger unstuck logic sooner
                self.stuck_timer += 1
                # If stuck for a bit, give up on this target
                if self.stuck_timer > 10:
                    self.current_target = None
        elif not floor_ahead and abs(dx) > 48:
            # Gap ahead
            if self.on_ground and self.jump_cooldown == 0:
                # Jump across the gap
                self._perform_jump()
                self.vx = move_dir * 4.0
                # Use dash mid-air if gap is large
                if abs(dx) > 96 and self.dash_charges > 0 and self.dash_cooldown == 0:
                    self._perform_dash(move_dir)
            else:
                # Can't jump - stop at edge
                self.vx = 0
        elif dy < -48 and self.on_ground and abs(dx) < 32 and self.jump_cooldown == 0:
            # Target is above - jump up
            self._perform_jump()
            self.vx = move_dir * 1.5
        elif abs(dx) > 96 and self.dash_charges > 0 and self.dash_cooldown == 0 and self.on_ground:
            # Far away - dash to close distance faster
            self._perform_dash(move_dir)
        else:
            # Normal movement - only if no wall blocking and not dashing
            if self.dashing_frames == 0 and not wall_ahead:  # Don't override dash or move into walls
                self.vx = move_dir * 2.5
            elif wall_ahead:
                # Safety: if wall detected, stop
                self.vx = 0
        
        # Update facing
        self.facing = move_dir
        self.facing_angle = 0 if move_dir > 0 else math.pi
    
    # -------------- Combat Overrides --------------
    
    def hit(self, hb, player):
        """Override hit to handle parry mechanics"""
        if not self.combat.alive:
            return
        
        is_player_hit = getattr(hb, 'owner', None) is player
        
        # Parry player attacks
        if self.parry_window > 0 and is_player_hit:
            floating.append(DamageNumber(self.rect.centerx, self.rect.top - 8, "PARRY!", CYAN))
            
            # Knockback player
            if hasattr(player, 'combat'):
                knockback_x = (1 if player.rect.centerx > self.rect.centerx else -1) * 3
                knockback_y = -6
                player.combat.take_damage(0, (knockback_x, knockback_y), self)
            
            self.state = 'recover'
            self.cool = 16
            self.vx = -self.facing * 1.0
            return
        
        # Use combat component for normal damage handling
        self.combat.handle_hit_by_player_hitbox(hb)
        
        # 18% chance to parry after being hit
        if self.combat.alive and self.parry_cool == 0 and random.random() < 0.18:
            self._start_parry()
    
    def get_base_color(self):
        """Get the base color for KnightMonster"""
        return (60, 120, 255) if not self.combat.is_invincible() else (35, 80, 200)
    
    def draw(self, surf, camera, show_los=False, show_nametags=False, debug_hitboxes=False):
        """Draw the KnightMonster with sprite animations"""
        if not self.combat.alive:
            return
        
        # Draw debug vision cone
        self.draw_debug_vision(surf, camera, show_los)
        
        # Draw sprite with animation
        sprite_drawn = self.anim_manager.draw(surf, camera, show_invincibility=True)
        
        # Fallback to colored rect if sprite fails to load
        if not sprite_drawn:
            base_color = self.get_base_color()
            status_color = self.get_status_effect_color(base_color)
            pygame.draw.rect(surf, status_color, camera.to_screen_rect(self.rect), border_radius=5)
        
        # Draw collision box outline in debug mode (F3)
        if debug_hitboxes:
            pygame.draw.rect(surf, (255, 140, 0), camera.to_screen_rect(self.rect), width=2)
        
        # Draw status effect indicators
        self.draw_status_effects(surf, camera)
        
        # Draw telegraph text
        if getattr(self, 'tele_text', ''):
            from src.core.utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx - 5, self.rect.top - 12)),
                     (255, 210, 120), size=18, bold=True)
        
        # Draw nametag
        self.draw_nametag(surf, camera, show_nametags)
