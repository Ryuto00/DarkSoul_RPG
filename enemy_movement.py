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
from utils import los_clear


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
        else:
            # Random wandering
            if random.random() < 0.02:  # 2% chance to change direction
                enemy.vx = random.choice([-1.2, 0, 1.2])
    
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
            # print(f"[DEBUG] GroundPatrol: {enemy.__class__.__name__} hit top boundary")
        if enemy.rect.left < 0:
            enemy.rect.left = 0
            enemy.vx = abs(enemy.vx)
            # print(f"[DEBUG] GroundPatrol: {enemy.__class__.__name__} hit left boundary")
        elif enemy.rect.right > level.w * TILE:
            enemy.rect.right = level.w * TILE
            enemy.vx = -abs(enemy.vx)
            # print(f"[DEBUG] GroundPatrol: {enemy.__class__.__name__} hit right boundary")
        
        # Log position changes only when significant
        if old_pos != (enemy.rect.x, enemy.rect.y) and (abs(old_pos[0] - enemy.rect.x) > 5 or abs(old_pos[1] - enemy.rect.y) > 5):
            print(f"[DEBUG] GroundPatrol: {enemy.__class__.__name__} moved from {old_pos} to ({enemy.rect.x}, {enemy.rect.y})")


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
    
    def _random_hop(self, enemy):
        """Random hop in a direction"""
        angle = random.uniform(0, 2 * math.pi)
        hop_power = 6
        
        enemy.vx = math.cos(angle) * hop_power
        enemy.vy = -8  # Upward jump
        enemy.on_ground = False
    
    def _handle_jump_physics(self, enemy, level):
        """Handle physics for jumping enemies"""
        # Apply gravity
        enemy.vy = min(enemy.vy + GRAVITY * 0.6, 15)
        
        # Store old position for debugging
        old_pos = (enemy.rect.x, enemy.rect.y)
        
        # Update position
        enemy.rect.x += int(enemy.vx)
        enemy.rect.y += int(enemy.vy)
        
        # DEBUG: Log position changes
        if old_pos != (enemy.rect.x, enemy.rect.y):
            print(f"[DEBUG] Jumping: {enemy.__class__.__name__} moved from {old_pos} to ({enemy.rect.x}, {enemy.rect.y})")
        
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
                    print(f"[DEBUG] Jumping: {enemy.__class__.__name__} horizontal collision, vx={enemy.vx}")
                
                # Vertical collision
                if enemy.vy > 0:
                    if enemy.rect.bottom > solid.top and enemy.rect.centery < solid.centery:
                        enemy.rect.bottom = solid.top
                        enemy.vy = 0
                        enemy.on_ground = True
                        print(f"[DEBUG] Jumping: {enemy.__class__.__name__} landed on ground")
        
        # Keep enemy in bounds
        if enemy.rect.top < 0:
            enemy.rect.top = 0
            enemy.vy = 0
            print(f"[DEBUG] Jumping: {enemy.__class__.__name__} hit top boundary")
        
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
        """Tactical movement to maintain optimal distance"""
        epos = (enemy.rect.centerx, enemy.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        distance = context.get('distance_to_player', 0)
        has_los = context.get('has_los', False)
        
        print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} distance={distance}, has_los={has_los}")
        
        if has_los:
            # Maintain optimal distance
            if distance < self.optimal_distance * 0.7:
                # Too close, back away
                print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} too close, backing away")
                self._strafe_away(enemy, ppos, level)
            elif distance > self.optimal_distance * 1.3:
                # Too far, get closer
                print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} too far, approaching")
                self._approach_cautiously(enemy, ppos, level)
            else:
                # Good distance, strafe
                print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} good distance, strafing")
                self._strafe_sideways(enemy, ppos, level)
        else:
            # No line of sight, find better position
            print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} no LOS, finding vantage point")
            self._find_vantage_point(enemy, ppos, level)
        
        # Apply basic physics
        self._handle_basic_physics(enemy, level)
    
    def _strafe_away(self, enemy, player_pos, level):
        """Move away from player while maintaining facing"""
        dx = enemy.rect.centerx - player_pos[0]
        dy = enemy.rect.centery - player_pos[1]
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance > 0:
            # Move directly away
            enemy.vx = (dx / distance) * 1.5
            enemy.vy = (dy / distance) * 0.5  # Less vertical movement
    
    def _approach_cautiously(self, enemy, player_pos, level):
        """Approach player cautiously"""
        dx = player_pos[0] - enemy.rect.centerx
        dy = player_pos[1] - enemy.rect.centery
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance > 0:
            enemy.vx = (dx / distance) * 1.0
            enemy.vy = 0  # Don't approach vertically
    
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
            enemy.vx = (perp_x / length) * 1.2 * direction
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
                    enemy.vx = (dx / distance) * 1.0
                    enemy.vy = (dy / distance) * 0.5
                    print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} moving to vantage point, vx={enemy.vx}, vy={enemy.vy}")
                return
        
        # No good position found, stay put
        enemy.vx = 0
        enemy.vy = 0
        print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} no vantage point found, staying put")
    
    def _handle_basic_physics(self, enemy, level):
        """Basic physics for ranged enemies"""
        old_pos = (enemy.rect.x, enemy.rect.y)
        
        # Apply gravity
        enemy.vy = min(enemy.vy + GRAVITY * 0.5, 15)
        
        # Update position
        enemy.rect.x += int(enemy.vx)
        enemy.rect.y += int(enemy.vy)
        
        # DEBUG: Log position changes
        if old_pos != (enemy.rect.x, enemy.rect.y):
            print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} moved from {old_pos} to ({enemy.rect.x}, {enemy.rect.y})")
        
        # Handle collisions
        for solid in level.solids:
            if enemy.rect.colliderect(solid):
                # Horizontal collision
                if enemy.vx != 0:
                    if enemy.vx > 0:
                        enemy.rect.right = solid.left
                    else:
                        enemy.rect.left = solid.right
                    enemy.vx = 0
                    print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} horizontal collision")
                
                # Vertical collision
                if enemy.vy > 0:
                    if enemy.rect.bottom > solid.top and enemy.rect.centery < solid.centery:
                        enemy.rect.bottom = solid.top
                        enemy.vy = 0
                        print(f"[DEBUG] RangedTactical: {enemy.__class__.__name__} ground collision")
        
        # Friction
        enemy.vx *= 0.85


class FloatingStrategy(MovementStrategy):
    """Floating movement for magical enemies - WizardCaster"""
    
    def __init__(self):
        super().__init__("floating")
    
    def move(self, enemy, level, player, context: Dict[str, Any]) -> None:
        """Floating movement with smooth drifts"""
        epos = (enemy.rect.centerx, enemy.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        distance = context.get('distance_to_player', 0)
        has_los = context.get('has_los', False)
        
        # Floating enemies hover above ground
        target_height = self._get_optimal_height(enemy, level)
        current_height = enemy.rect.centery
        
        # Adjust height
        if abs(current_height - target_height) > 5:
            enemy.vy = 1.0 if current_height < target_height else -1.0
        else:
            enemy.vy = 0
        
        # Horizontal movement
        if has_los and distance < enemy.vision_range:
            # Maintain distance but face player
            if distance < 150:
                # Too close, drift back
                dx = epos[0] - ppos[0]
                enemy.vx = 0.8 if dx > 0 else -0.8
            elif distance > 250:
                # Too far, drift closer
                dx = ppos[0] - epos[0]
                enemy.vx = 0.6 if dx > 0 else -0.6
            else:
                # Good distance, slight drift
                enemy.vx = math.sin(pygame.time.get_ticks() * 0.001) * 0.5
        else:
            # Gentle floating drift
            enemy.vx = math.sin(pygame.time.get_ticks() * 0.0008) * 0.8
        
        # Apply movement
        enemy.rect.x += int(enemy.vx)
        enemy.rect.y += int(enemy.vy)
        
        # Keep in bounds
        self._keep_in_bounds(enemy, level)
    
    def _get_optimal_height(self, enemy, level):
        """Get optimal floating height for enemy"""
        # Find ground level below enemy
        ground_y = enemy.rect.bottom
        
        for solid in level.solids:
            if (solid.left <= enemy.rect.centerx <= solid.right and 
                solid.top > ground_y):
                ground_y = solid.top
        
        # Float 50 pixels above ground
        return ground_y - 50
    
    def _keep_in_bounds(self, enemy, level):
        """Keep enemy within level bounds"""
        # Simple boundary check
        if enemy.rect.left < 0:
            enemy.rect.left = 0
            enemy.vx = abs(enemy.vx)
        elif enemy.rect.right > level.w * TILE:
            enemy.rect.right = level.w * TILE
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