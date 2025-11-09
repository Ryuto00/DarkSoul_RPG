"""
Vision Component - Shared vision and detection logic for entities
Eliminates code duplication in vision cone updates and player detection
"""

import math
import pygame
from ..entity_common import in_vision_cone
from ...core.utils import los_clear


class VisionComponent:
    """Handles vision and detection for entities"""
    
    def __init__(self, entity, vision_range=200, cone_half_angle=math.pi/6, turn_rate=0.05):
        self.entity = entity
        self.vision_range = vision_range
        self.cone_half_angle = cone_half_angle
        self.turn_rate = turn_rate
        self.facing = 1  # 1 for right, -1 for left
        self.facing_angle = 0 if self.facing > 0 else math.pi
        
        # Debug information
        self._has_los = False
        self._los_point = None
        self._in_cone = False
    
    def update_vision_cone(self, player_pos):
        """Update facing direction based on player position"""
        entity_pos = (self.entity.rect.centerx, self.entity.rect.centery)
        
        # Calculate distance to player
        dx = player_pos[0] - entity_pos[0]
        dy = player_pos[1] - entity_pos[1]
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
        """Check if player is in vision cone and has line of sight"""
        entity_pos = (self.entity.rect.centerx, self.entity.rect.centery)
        
        # Check if player is in vision cone
        in_cone = in_vision_cone(
            entity_pos, player_pos, self.facing_angle, 
            self.cone_half_angle, self.vision_range
        )
        has_los = in_cone and los_clear(level, entity_pos, player_pos)
        
        # Store for debug drawing
        self._has_los = has_los
        self._los_point = player_pos
        self._in_cone = in_cone
        
        return has_los, in_cone
    
    def get_distance_to_player(self, player_pos):
        """Calculate distance to player"""
        dx = player_pos[0] - self.entity.rect.centerx
        dy = player_pos[1] - self.entity.rect.centery
        return (dx*dx + dy*dy) ** 0.5
    
    def is_player_in_range(self, player_pos, range_multiplier=1.0):
        """Check if player is within vision range (with optional multiplier)"""
        distance = self.get_distance_to_player(player_pos)
        return distance < (self.vision_range * range_multiplier)
    
    def is_player_detected(self, level, player_pos):
        """Check if player is both in vision cone and has line of sight"""
        has_los, in_cone = self.check_vision_cone(level, player_pos)
        return has_los and in_cone
    
    def get_debug_info(self):
        """Get debug information for drawing"""
        return {
            'has_los': self._has_los,
            'los_point': self._los_point,
            'in_cone': self._in_cone,
            'facing_angle': self.facing_angle,
            'vision_range': self.vision_range,
            'cone_half_angle': self.cone_half_angle
        }
    
    def draw_debug_vision(self, surf, camera, show_los=False):
        """Draw debug vision cone and LOS line"""
        if not show_los:
            return
            
        # Draw LOS line to last-checked player point if available
        if self._los_point is not None:
            from config import GREEN, RED
            col = GREEN if self._has_los else RED
            pygame.draw.line(
                surf, col, 
                camera.to_screen(self.entity.rect.center), 
                camera.to_screen(self._los_point), 
                2
            )
            
            # Draw vision cone
            center = camera.to_screen(self.entity.rect.center)
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