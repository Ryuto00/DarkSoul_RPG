"""
Enemy Movement System - Core Movement Strategies
Provides modular movement behaviors for different enemy types
"""

import math
import random
import pygame
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict, Any

from config import TILE, GRAVITY
from ..core.utils import los_clear


class MovementStrategy(ABC):
    """Base class for enemy movement strategies"""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def move(self, enemy, level, player, context: Dict[str, Any]) -> None:
        """Execute movement strategy"""
        pass
    
    def can_use(self, enemy) -> bool:
        """Check if this strategy can be used by the enemy"""
        return True


def clamp_enemy_to_level(enemy, level, respect_solids: bool = False) -> None:
    """
    Global safety clamp for ALL enemies (Bee/Wizard/Assassin/etc).

    Goals:
    - Prevent enemies from leaving map boundaries.
    - Optionally prevent clipping through normal solids when respect_solids=True.
    - Keep attack-specific motion (dash/teleport) mostly intact, only fix illegal positions.

    Behavior:
    - Always enforces horizontal bounds [0, level.w * TILE].
    - Always enforces vertical top >= 0.
    - If respect_solids:
        - Nudge enemy out of overlapping solids on both axes.
    - Emits concise debug logs when correction is applied to help verify behavior.
    """
    level_width_px = getattr(level, "w", 0) * TILE if hasattr(level, "w") else 0
    solids = getattr(level, "solids", [])

    old = enemy.rect.copy()
    corrected = False

    # Horizontal map bounds
    if level_width_px > 0:
        if enemy.rect.left < 0:
            enemy.rect.left = 0
            enemy.vx = abs(getattr(enemy, "vx", 0))
            corrected = True
        elif enemy.rect.right > level_width_px:
            enemy.rect.right = level_width_px
            enemy.vx = -abs(getattr(enemy, "vx", 0))
            corrected = True

    # Vertical top bound
    if enemy.rect.top < 0:
        enemy.rect.top = 0
        vy = getattr(enemy, "vy", 0)
        enemy.vy = max(0, vy)
        corrected = True

    # Optional solid resolution
    if respect_solids and solids:
        for s in solids:
            if enemy.rect.colliderect(s):
                # Resolve vertical first
                if enemy.rect.bottom > s.top and old.bottom <= s.top:
                    enemy.rect.bottom = s.top
                    enemy.vy = min(0, getattr(enemy, "vy", 0))
                    corrected = True
                elif enemy.rect.top < s.bottom and old.top >= s.bottom:
                    enemy.rect.top = s.bottom
                    enemy.vy = max(0, getattr(enemy, "vy", 0))
                    corrected = True

                # Horizontal resolution
                if enemy.rect.right > s.left and old.right <= s.left:
                    enemy.rect.right = s.left
                    enemy.vx = min(0, getattr(enemy, "vx", 0))
                    corrected = True
                elif enemy.rect.left < s.right and old.left >= s.right:
                    enemy.rect.left = s.right
                    enemy.vx = max(0, getattr(enemy, "vx", 0))
                    corrected = True

    if corrected:
        # Position correction applied
        pass


class GroundPatrolStrategy(MovementStrategy):
    """Basic ground patrol with pursuit - for Bug, Boss"""
    
    def __init__(self):
        super().__init__("ground_patrol")
    
    def move(self, enemy, level, player, context: Dict[str, Any]) -> None:
        """Ground-based movement with patrol and pursuit"""
        epos = (enemy.rect.centerx, enemy.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        # Check if player is detected
        has_los = context.get('has_los', False)
        in_range = context.get('distance_to_player', 0) < enemy.vision_range
        
        if has_los and in_range:
            # Pursue player
            self._pursue_player(enemy, ppos, level)
        else:
            # Patrol behavior
            self._patrol_behavior(enemy, level)
        
        # Apply gravity and handle collisions
        self._handle_physics(enemy, level)
    
    def _pursue_player(self, enemy, player_pos, level):
        """Direct pursuit of player"""
        dx = player_pos[0] - enemy.rect.centerx
        dy = player_pos[1] - enemy.rect.centery
        
        # Simple pathfinding - move toward player
        if abs(dx) > 5:
            enemy.vx = 1.8 if dx > 0 else -1.8
            # Update facing direction
            enemy.facing = 1 if dx > 0 else -1
            enemy.facing_angle = 0 if enemy.facing > 0 else math.pi
        else:
            enemy.vx = 0
        
        # Handle vertical movement for jumping enemies
        if hasattr(enemy, 'can_jump') and enemy.can_jump:
            if dy < -50 and enemy.on_ground:  # Player is above
                enemy.vy = -12  # Jump
                enemy.on_ground = False
    
    def _patrol_behavior(self, enemy, level):
        """Random patrol movement"""
        if not hasattr(enemy, 'patrol_target') or enemy.patrol_target is None:
            # Find new patrol target
            enemy.patrol_target = self._find_patrol_target(enemy, level)
        
        if enemy.patrol_target:
            dx = enemy.patrol_target[0] - enemy.rect.centerx
            dy = enemy.patrol_target[1] - enemy.rect.centery
            
            if abs(dx) < 5 and abs(dy) < 5:
                # Reached target, find new one
                enemy.patrol_target = None
            else:
                # Move toward target
                enemy.vx = 1.2 if dx > 0 else -1.2
                # Update facing direction
                enemy.facing = 1 if dx > 0 else -1
                enemy.facing_angle = 0 if enemy.facing > 0 else math.pi
        else:
            # Random wandering
            if random.random() < 0.02:  # 2% chance to change direction
                enemy.vx = random.choice([-1.2, 0, 1.2])
                if enemy.vx != 0:
                    # Update facing when changing direction
                    enemy.facing = 1 if enemy.vx > 0 else -1
                    enemy.facing_angle = 0 if enemy.facing > 0 else math.pi
    
    def _find_patrol_target(self, enemy, level):
        """Find a suitable patrol target"""
        home = getattr(enemy, 'home', (enemy.rect.centerx, enemy.rect.centery))
        radius = TILE * 4
        
        for _ in range(10):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.randint(TILE, radius)
            x = int(home[0] + math.cos(angle) * distance)
            y = int(home[1] + math.sin(angle) * distance)
            
            # Check if position is valid
            test_rect = pygame.Rect(x - enemy.rect.width//2, y - enemy.rect.height, 
                                   enemy.rect.width, enemy.rect.height)
            
            if not any(test_rect.colliderect(solid) for solid in level.solids):
                return (x, y)
        
        return None
    
    def _handle_physics(self, enemy, level):
        """Apply gravity and handle collisions"""
        old_pos = (enemy.rect.x, enemy.rect.y)
        
        # Apply gravity
        if hasattr(enemy, 'vy'):
            enemy.vy = min(enemy.vy + GRAVITY * 0.5, 15)
            enemy.rect.y += int(enemy.vy)
            
            # Ground collision
            for solid in level.solids:
                if enemy.rect.colliderect(solid):
                    if enemy.rect.bottom > solid.top and enemy.rect.centery < solid.centery:
                        enemy.rect.bottom = solid.top
                        enemy.vy = 0
                        enemy.on_ground = True
        
        # Horizontal movement and collision
        if hasattr(enemy, 'vx') and enemy.vx != 0:
            enemy.rect.x += int(enemy.vx)
            
            for solid in level.solids:
                if enemy.rect.colliderect(solid):
                    if enemy.vx > 0:
                        enemy.rect.right = solid.left
                    else:
                        enemy.rect.left = solid.right
                    enemy.vx *= -0.5  # Bounce off walls
        
        # Keep enemy in bounds
        if enemy.rect.top < 0:
            enemy.rect.top = 0
            enemy.vy = 0
        if enemy.rect.left < 0:
            enemy.rect.left = 0
            enemy.vx = abs(enemy.vx)
        elif enemy.rect.right > level.w * TILE:
            enemy.rect.right = level.w * TILE
            enemy.vx = -abs(enemy.vx)
        
        # Position changes tracked silently
        if old_pos != (enemy.rect.x, enemy.rect.y) and (abs(old_pos[0] - enemy.rect.x) > 5 or abs(old_pos[1] - enemy.rect.y) > 5):
            pass


class JumpingStrategy(MovementStrategy):
    """Jumping movement for Frog"""
    
    def __init__(self):
        super().__init__("jumping")
    
    def move(self, enemy, level, player, context: Dict[str, Any]) -> None:
        """Jumping movement pattern"""
        epos = (enemy.rect.centerx, enemy.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        has_los = context.get('has_los', False)
        distance = context.get('distance_to_player', 0)
        
        if has_los and distance < enemy.vision_range:
            # Calculate jump toward player
            if enemy.on_ground and random.random() < 0.05:  # 5% chance per frame to jump
                self._jump_toward_player(enemy, ppos)
        else:
            # Random hopping
            if enemy.on_ground and random.random() < 0.02:  # 2% chance to hop
                self._random_hop(enemy)
        
        # Apply physics
        self._handle_jump_physics(enemy, level)
    
    def _jump_toward_player(self, enemy, player_pos):
        """Jump toward player position"""
        dx = player_pos[0] - enemy.rect.centerx
        dy = player_pos[1] - enemy.rect.centery
        
        # Calculate jump velocity
        jump_power = 10
        angle = math.atan2(dy, dx)
        
        enemy.vx = math.cos(angle) * jump_power * 0.7
        enemy.vy = math.sin(angle) * jump_power * 0.7 - 8  # Extra upward force
        enemy.on_ground = False
        
        # Update facing direction
        if abs(dx) > 5:
            enemy.facing = 1 if dx > 0 else -1
            enemy.facing_angle = 0 if enemy.facing > 0 else math.pi
    
    def _random_hop(self, enemy):
        """Random hop in a direction"""
        angle = random.uniform(0, 2 * math.pi)
        hop_power = 6
        
        enemy.vx = math.cos(angle) * hop_power
        enemy.vy = -8  # Upward jump
        enemy.on_ground = False
        
        # Update facing direction based on hop direction
        if abs(enemy.vx) > 1:
            enemy.facing = 1 if enemy.vx > 0 else -1
            enemy.facing_angle = 0 if enemy.facing > 0 else math.pi
    
    def _handle_jump_physics(self, enemy, level):
        """Handle physics for jumping enemies"""
        # Apply gravity
        enemy.vy = min(enemy.vy + GRAVITY * 0.6, 15)
        
        # Update position
        enemy.rect.x += int(enemy.vx)
        enemy.rect.y += int(enemy.vy)
        
        # Handle collisions
        for solid in level.solids:
            if enemy.rect.colliderect(solid):
                # Horizontal collision
                if enemy.vx != 0:
                    if enemy.vx > 0:
                        enemy.rect.right = solid.left
                    else:
                        enemy.rect.left = solid.right
                    enemy.vx *= -0.3
                
                # Vertical collision
                if enemy.vy > 0:
                    if enemy.rect.bottom > solid.top and enemy.rect.centery < solid.centery:
                        enemy.rect.bottom = solid.top
                        enemy.vy = 0
                        enemy.on_ground = True
                elif enemy.vy < 0:
                    # Hit ceiling
                    if enemy.rect.top < solid.bottom and enemy.rect.centery > solid.centery:
                        enemy.rect.top = solid.bottom
                        enemy.vy = 0
        
        # Keep enemy in bounds
        if enemy.rect.top < 0:
            enemy.rect.top = 0
            enemy.vy = 0
            enemy.on_ground = False  # Reset ground state when hitting boundary
            # Hit top boundary
        
        # Friction
        if enemy.on_ground:
            enemy.vx *= 0.9
            if abs(enemy.vx) < 0.1:
                enemy.vx = 0


class RangedTacticalStrategy(MovementStrategy):
    """Tactical positioning for ranged enemies - Archer"""
    
    def __init__(self):
        super().__init__("ranged_tactical")
        self.optimal_distance = 200  # Optimal distance from player
    
    def move(self, enemy, level, player, context: Dict[str, Any]) -> None:
        """Tactical movement to maintain optimal distance with safe, visible behavior.

        Reset: keep this strategy simple + robust so Archers don't vanish or clip.
        """
        if not player:
            return

        epos = (enemy.rect.centerx, enemy.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)

        distance = context.get('distance_to_player', 0.0)
        has_los = context.get('has_los', False)
        alert_level = getattr(enemy, 'alert_level', 0)

        # Base speeds — keep moderate so behavior is readable
        approach_speed = 1.0
        retreat_speed = 1.0
        strafe_speed = 0.6

        desired_vx = 0.0

        if has_los:
            # 1) Maintain distance band
            if distance < self.optimal_distance * 0.7:
                # Too close -> back away
                dx = epos[0] - ppos[0]
                if abs(dx) > 2:
                    desired_vx = (1 if dx > 0 else -1) * retreat_speed
            elif distance > self.optimal_distance * 1.3:
                # Too far -> approach
                dx = ppos[0] - epos[0]
                if abs(dx) > 2:
                    desired_vx = (1 if dx > 0 else -1) * approach_speed
            else:
                # In a good band -> mild random strafe
                side = random.choice([-1, 1])
                desired_vx = side * strafe_speed
        elif alert_level == 1:
            # Investigating - move toward investigation point if set
            inv_point = getattr(enemy, 'investigation_point', None)
            if inv_point:
                dx = inv_point[0] - epos[0]
                if abs(dx) > 20:
                    desired_vx = (1 if dx > 0 else -1) * 0.8
        elif alert_level == 0:
            # Idle patrol behavior with more standing still time
            # Initialize patrol state if needed
            if not hasattr(enemy, 'patrol_direction') or not hasattr(enemy, 'patrol_timer'):
                enemy.patrol_direction = random.choice([-1, 0, 0, 0, 1])  # 3/5 chance to start idle
                enemy.patrol_timer = random.randint(60, 150)  # Longer patrol cycles
                enemy.patrol_blocked = False
            
            # Check if we were blocked last frame (ledge detection)
            if getattr(enemy, 'patrol_blocked', False):
                # We hit a ledge, wait a bit then reverse or pick new direction
                if not hasattr(enemy, 'blocked_cooldown'):
                    enemy.blocked_cooldown = 20  # Wait 20 frames (~0.3s)
                    enemy.patrol_direction *= -1  # Reverse direction
                    # Update facing immediately when reversing
                    enemy.facing = enemy.patrol_direction
                    import math
                    enemy.facing_angle = 0 if enemy.facing > 0 else math.pi
                enemy.blocked_cooldown -= 1
                if enemy.blocked_cooldown <= 0:
                    enemy.patrol_blocked = False
                    del enemy.blocked_cooldown
                desired_vx = 0  # Stay still while blocked
            else:
                # Normal patrol
                enemy.patrol_timer -= 1
                if enemy.patrol_timer <= 0:
                    # 60% chance to stand still, 40% chance to move
                    enemy.patrol_direction = random.choice([-1, 0, 0, 0, 0, 0, 1])
                    enemy.patrol_timer = random.randint(60, 150)  # Longer intervals
                
                if enemy.patrol_direction != 0:
                    desired_vx = enemy.patrol_direction * 1.2  # Must be >= 1.0 for int() to work
                    # Update facing direction during patrol
                    enemy.facing = enemy.patrol_direction
                    enemy.facing_angle = 0 if enemy.facing > 0 else 3.14159
                else:
                    desired_vx = 0

        # Apply ledge-aware horizontal intent ONLY; physics handles the rest
        self._set_safe_horizontal_velocity(enemy, level, desired_vx)

        # Apply physics & collisions
        self._handle_basic_physics(enemy, level)

        # Safety clamps to prevent extreme speeds if something else tampers with vx/vy
        enemy.vx = max(-4.0, min(4.0, enemy.vx))
        enemy.vy = max(-16.0, min(16.0, enemy.vy))
    
    def _strafe_away(self, enemy, player_pos, level):
        """Move away from player while maintaining facing"""
        dx = enemy.rect.centerx - player_pos[0]
        dy = enemy.rect.centery - player_pos[1]
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance > 0:
            # Move directly away
            self._set_safe_horizontal_velocity(enemy, level, (dx / distance) * 1.5)
            if not self._is_gravity_bound(enemy):
                enemy.vy = (dy / distance) * 0.5  # Floaters can adjust vertically
    
    def _approach_cautiously(self, enemy, player_pos, level):
        """Approach player cautiously"""
        dx = player_pos[0] - enemy.rect.centerx
        dy = player_pos[1] - enemy.rect.centery
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance > 0:
            self._set_safe_horizontal_velocity(enemy, level, (dx / distance) * 1.0)
            if not self._is_gravity_bound(enemy):
                enemy.vy = 0  # Floating units can null vertical drift
    
    def _strafe_sideways(self, enemy, player_pos, level):
        """Strafe sideways to maintain distance"""
        # Calculate perpendicular direction
        dx = player_pos[0] - enemy.rect.centerx
        dy = player_pos[1] - enemy.rect.centery
        
        # Perpendicular vector (rotate 90 degrees)
        perp_x = -dy
        perp_y = dx
        length = math.sqrt(perp_x*perp_x + perp_y*perp_y)
        
        if length > 0:
            # Randomly choose left or right strafe
            direction = random.choice([-1, 1])
            self._set_safe_horizontal_velocity(enemy, level, (perp_x / length) * 1.2 * direction)
            if not self._is_gravity_bound(enemy):
                enemy.vy = 0
    
    def _find_vantage_point(self, enemy, player_pos, level):
        """Find a better position with line of sight"""
        # Try different positions around current location
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            test_x = enemy.rect.centerx + math.cos(rad) * 50
            test_y = enemy.rect.centery + math.sin(rad) * 50
            
            # Check if this position has line of sight
            if los_clear(level, (test_x, test_y), player_pos):
                # Move toward this position
                dx = test_x - enemy.rect.centerx
                dy = test_y - enemy.rect.centery
                distance = math.sqrt(dx*dx + dy*dy)
                
                if distance > 0:
                    self._set_safe_horizontal_velocity(enemy, level, (dx / distance) * 1.0)
                    if not self._is_gravity_bound(enemy):
                        enemy.vy = (dy / distance) * 0.5
                return
        
        # No good position found, stay put
        self._set_safe_horizontal_velocity(enemy, level, 0)
        if not self._is_gravity_bound(enemy):
            enemy.vy = 0
    
    def _handle_basic_physics(self, enemy, level):
        """Basic physics for ranged enemies.

        Simplified + clamped to prevent jitter and out-of-bounds for Archers.
        """
        old_pos = (enemy.rect.x, enemy.rect.y)

        # Apply gravity
        if getattr(enemy, 'gravity_affected', True):
            enemy.vy = min(enemy.vy + GRAVITY * 0.5, 12)
        enemy.on_ground = False

        # Integrate velocity
        enemy.rect.x += int(enemy.vx)
        enemy.rect.y += int(enemy.vy)

        # Collide with solids
        for solid in level.solids:
            if enemy.rect.colliderect(solid):
                # Horizontal resolution
                if enemy.vx > 0 and enemy.rect.right > solid.left and old_pos[0] + enemy.rect.width <= solid.left:
                    enemy.rect.right = solid.left
                    enemy.vx = 0
                elif enemy.vx < 0 and enemy.rect.left < solid.right and old_pos[0] >= solid.right:
                    enemy.rect.left = solid.right
                    enemy.vx = 0

                # Vertical resolution
                if enemy.vy > 0 and enemy.rect.bottom > solid.top and old_pos[1] + enemy.rect.height <= solid.top:
                    enemy.rect.bottom = solid.top
                    enemy.vy = 0
                    enemy.on_ground = True
                elif enemy.vy < 0 and enemy.rect.top < solid.bottom and old_pos[1] >= solid.bottom:
                    enemy.rect.top = solid.bottom
                    enemy.vy = 0

        # Soft friction when grounded
        if enemy.on_ground:
            # If we didn't actually move (vx too small), zero it out to prevent animation jitter
            if enemy.rect.x == old_pos[0] and abs(enemy.vx) > 0:
                enemy.vx = 0
            else:
                enemy.vx *= 0.8
                if abs(enemy.vx) < 0.05:
                    enemy.vx = 0

        # Keep inside level horizontal bounds (prevents disappearing off map)
        level_width_px = getattr(level, "w", 0) * TILE if hasattr(level, "w") else 0
        if level_width_px > 0:
            if enemy.rect.left < 0:
                enemy.rect.left = 0
                enemy.vx = abs(enemy.vx)
            elif enemy.rect.right > level_width_px:
                enemy.rect.right = level_width_px
                enemy.vx = -abs(enemy.vx)

        # Clamp velocities as final safety
        enemy.vx = max(-4.0, min(4.0, enemy.vx))
        enemy.vy = max(-16.0, min(16.0, enemy.vy))

    def _is_gravity_bound(self, enemy) -> bool:
        """Return True if enemy should obey gravity."""
        return getattr(enemy, 'gravity_affected', True)

    def _on_solid_ground(self, enemy, level) -> bool:
        """Check if enemy currently stands on solid ground."""
        if not level.solids:
            return False
        probe = pygame.Rect(enemy.rect.left, enemy.rect.bottom + 1, enemy.rect.width, 2)
        return any(probe.colliderect(solid) for solid in level.solids)
    
    def _has_support_in_direction(self, enemy, level, direction, distance=4) -> bool:
        """Check if ground exists ahead in the given direction.

        Uses a small probe just beyond the enemy's feet to see if there is a solid.
        """
        if not level.solids:
            return False

        # Look slightly ahead from the bottom center; this avoids overreacting to minor offsets.
        ahead = enemy.rect.centerx + direction * max(distance, 4)
        probe = pygame.Rect(ahead - 2, enemy.rect.bottom + 1, 4, 3)
        return any(probe.colliderect(solid) for solid in level.solids)

    def _set_safe_horizontal_velocity(self, enemy, level, desired_vx):
        """Apply horizontal velocity with ledge awareness for grounded Archers.

        Fix for:
        - Jittery 'always dashing' feel
        - Edge flipping that launches/clips Archer off platforms

        Behavior:
        - If not gravity-bound -> use desired_vx directly.
        - If airborne -> use desired_vx directly (no edge anchoring mid-air).
        - If grounded and stepping off would leave no support -> clamp vx to 0 (stop at edge).
        - No direction reversal here; we only prevent the unsafe step.
        """
        # Tiny velocities are treated as no movement
        if abs(desired_vx) < 1e-3:
            enemy.vx = 0
            return

        # Non-gravity units (floaters etc.) are free to move
        if not self._is_gravity_bound(enemy):
            enemy.vx = desired_vx
            return

        # If not currently on solid ground, don't apply ledge logic (avoid air jitter)
        if not self._on_solid_ground(enemy, level):
            enemy.vx = desired_vx
            return

        direction = 1 if desired_vx > 0 else -1

        # Check if there is still ground in the direction we intend to move.
        if not self._has_support_in_direction(enemy, level, direction, distance=max(6, enemy.rect.width // 4)):
            # Stop at edge instead of flipping; this gives proper "anchor" behavior.
            # Edge detected, blocking move
            enemy.vx = 0
            enemy.patrol_blocked = True  # Signal to patrol logic that we're blocked
        else:
            enemy.vx = desired_vx
            enemy.patrol_blocked = False  # Clear blocked flag when we can move


class FloatingStrategy(MovementStrategy):
    """Floating movement for magical enemies - WizardCaster, Bee, etc.
    
    Goals:
    - Smooth, readable hovering.
    - Respect level bounds so floaters (Bee/Wizard/Assassin variants) do NOT clip OOB.
    - Minimal interference with each enemy's attack logic.
    """
    
    def __init__(self):
        super().__init__("floating")
    
    def move(self, enemy, level, player, context: Dict[str, Any]) -> None:
        """Floating movement with bound-safe drifts."""
        # Defensive: ensure level dimensions exist
        level_width_px = getattr(level, "w", 0) * TILE if hasattr(level, "w") else 0
        
        epos = (enemy.rect.centerx, enemy.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        distance = context.get('distance_to_player', 0.0)
        has_los = context.get('has_los', False)
        
        # Choose a baseline target height; Bees might override via attributes later if needed.
        target_height = self._get_optimal_height(enemy, level)
        current_height = enemy.rect.centery
        
        # Vertical adjust (slow hover toward target height)
        if abs(current_height - target_height) > 5:
            enemy.vy = 1.0 if current_height < target_height else -1.0
        else:
            enemy.vy = 0.0
        
        # Horizontal drift logic (keep modest to avoid tunneling)
        if has_los and distance < getattr(enemy, "vision_range", 260):
            if distance < 150:
                # Too close, drift away horizontally from player
                dx = epos[0] - ppos[0]
                enemy.vx = 1.4 if dx > 0 else -1.4
                # Update facing direction
                if abs(dx) > 5:
                    enemy.facing = 1 if dx > 0 else -1
                    enemy.facing_angle = 0 if enemy.facing > 0 else 3.14159
            elif distance > 260:
                # Too far, drift toward player
                dx = ppos[0] - epos[0]
                enemy.vx = 1.0 if dx > 0 else -1.0
                # Update facing direction
                if abs(dx) > 5:
                    enemy.facing = 1 if dx > 0 else -1
                    enemy.facing_angle = 0 if enemy.facing > 0 else 3.14159
            else:
                # In a good band, mild oscillation
                enemy.vx = math.sin(pygame.time.get_ticks() * 0.001) * 0.9
                # Update facing based on oscillation direction
                if abs(enemy.vx) > 0.1:
                    enemy.facing = 1 if enemy.vx > 0 else -1
                    enemy.facing_angle = 0 if enemy.facing > 0 else 3.14159
        else:
            # Idle gentle hover
            enemy.vx = math.sin(pygame.time.get_ticks() * 0.0008) * 1.2
            # Update facing based on hover direction
            if abs(enemy.vx) > 0.1:
                enemy.facing = 1 if enemy.vx > 0 else -1
                enemy.facing_angle = 0 if enemy.facing > 0 else 3.14159
        
        # Integrate movement
        old_rect = enemy.rect.copy()
        enemy.rect.x += int(enemy.vx)
        enemy.rect.y += int(enemy.vy)
        
        # SOLID COLLISION DETECTION AND RESOLUTION for flying enemies
        solids = getattr(level, "solids", [])
        for solid in solids:
            if enemy.rect.colliderect(solid):
                # Resolve collision by pushing enemy out of solid
                # Check horizontal collision first
                if old_rect.right <= solid.left:
                    # Moving right, hit left side of solid
                    enemy.rect.right = solid.left
                    enemy.vx = -abs(enemy.vx) * 0.5  # Bounce back with damping
                elif old_rect.left >= solid.right:
                    # Moving left, hit right side of solid
                    enemy.rect.left = solid.right
                    enemy.vx = abs(enemy.vx) * 0.5  # Bounce back with damping
                
                # Check vertical collision
                if old_rect.bottom <= solid.top:
                    # Moving down, hit top of solid
                    enemy.rect.bottom = solid.top
                    enemy.vy = -abs(enemy.vy) * 0.3  # Small bounce up
                elif old_rect.top >= solid.bottom:
                    # Moving up, hit bottom of solid
                    enemy.rect.top = solid.bottom
                    enemy.vy = abs(enemy.vy) * 0.3  # Small bounce down
        
        # Soft clamp to level bounds to prevent clipping / disappearing
        if level_width_px > 0:
            if enemy.rect.left < 0:
                # Floaters clamped to left bound
                enemy.rect.left = 0
                enemy.vx = abs(enemy.vx)
            elif enemy.rect.right > level_width_px:
                # Floaters clamped to right bound
                enemy.rect.right = level_width_px
                enemy.vx = -abs(enemy.vx)
        
        # Prevent absurd vertical escape (failsafe; real ceiling/floor from level if needed)
        if enemy.rect.top < 0:
            # Floaters clamped to top bound
            enemy.rect.top = 0
            enemy.vy = max(0.0, enemy.vy)
        # Do not clamp bottom hard here; boss rooms / pits may want fall-through for specials.
    
    def _get_optimal_height(self, enemy, level):
        """Get optimal floating height: ~50px above nearest ground below, if any."""
        ground_y = None
        for solid in getattr(level, "solids", []):
            if solid.left <= enemy.rect.centerx <= solid.right and solid.top >= enemy.rect.bottom:
                if ground_y is None or solid.top < ground_y:
                    ground_y = solid.top
        if ground_y is None:
            # No ground below; use current height as baseline to avoid wild jumps.
            return enemy.rect.centery
        return ground_y - 50
    
    def _keep_in_bounds(self, enemy, level):
        """Deprecated helper kept for compatibility (no-op wrapper).
        
        Existing callers (if any) still get safe behavior via move() clamps.
        """
        level_width_px = getattr(level, "w", 0) * TILE if hasattr(level, "w") else 0
        if level_width_px <= 0:
            return
        if enemy.rect.left < 0:
            enemy.rect.left = 0
            enemy.vx = abs(enemy.vx)
        elif enemy.rect.right > level_width_px:
            enemy.rect.right = level_width_px
            enemy.vx = -abs(enemy.vx)


class MovementStrategyFactory:
    """Factory for creating movement strategies"""
    
    _strategies = {
        'ground_patrol': GroundPatrolStrategy,
        'jumping': JumpingStrategy,
        'ranged_tactical': RangedTacticalStrategy,
        'floating': FloatingStrategy
    }
    
    @classmethod
    def create_strategy(cls, strategy_name: str) -> MovementStrategy:
        """Create a movement strategy by name"""
        strategy_class = cls._strategies.get(strategy_name)
        if strategy_class:
            return strategy_class()
        else:
            # Default to ground patrol
            return GroundPatrolStrategy()
    
    @classmethod
    def register_strategy(cls, name: str, strategy_class: type):
        """Register a new movement strategy"""
        cls._strategies[name] = strategy_class
