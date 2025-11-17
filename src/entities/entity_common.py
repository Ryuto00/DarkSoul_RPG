import math
import pygame

from config import ACCENT, WHITE

# ============================================================================
# Shared Vision / Alert System
# ============================================================================

class AlertSystem:
    """
    Global alert system for enemy coordination.
    When one enemy spots the player, nearby allies are alerted.
    """
    def __init__(self):
        self.alerts = {}  # {enemy_id: {'position': (x, y), 'timestamp': int, 'level': int}}
        self.alert_radius = 400  # Radius in pixels for alert propagation
        self.alert_duration = 180  # Frames an alert stays active (3 seconds at 60fps)
        self.current_frame = 0
    
    def broadcast_alert(self, enemy, player_position, alert_level=2):
        """
        Broadcast an alert from an enemy who spotted the player.
        
        Args:
            enemy: Enemy instance broadcasting the alert
            player_position: (x, y) tuple of player's current position
            alert_level: 1=investigating, 2=combat
        """
        enemy_id = id(enemy)
        self.alerts[enemy_id] = {
            'position': player_position,
            'enemy_pos': (enemy.rect.centerx, enemy.rect.centery),
            'timestamp': self.current_frame,
            'level': alert_level
        }
    
    def check_nearby_alerts(self, enemy):
        """
        Check if there are any active alerts near this enemy.
        Returns (has_alert, player_last_seen_pos, alert_level) or (False, None, 0)
        
        Args:
            enemy: Enemy instance checking for alerts
            
        Returns:
            tuple: (has_alert: bool, position: tuple or None, level: int)
        """
        enemy_pos = (enemy.rect.centerx, enemy.rect.centery)
        enemy_id = id(enemy)
        
        # Find closest alert within radius
        closest_alert = None
        closest_dist = float('inf')
        
        for aid, alert_data in self.alerts.items():
            if aid == enemy_id:
                continue  # Don't alert yourself
            
            # Check if alert is still valid
            age = self.current_frame - alert_data['timestamp']
            if age > self.alert_duration:
                continue
            
            # Check distance to alerting enemy
            alert_enemy_pos = alert_data['enemy_pos']
            dx = alert_enemy_pos[0] - enemy_pos[0]
            dy = alert_enemy_pos[1] - enemy_pos[1]
            dist = (dx*dx + dy*dy) ** 0.5
            
            if dist <= self.alert_radius and dist < closest_dist:
                closest_dist = dist
                closest_alert = alert_data
        
        if closest_alert:
            return (True, closest_alert['position'], closest_alert['level'])
        return (False, None, 0)
    
    def clear_old_alerts(self):
        """Remove alerts that have expired."""
        expired = []
        for enemy_id, alert_data in self.alerts.items():
            age = self.current_frame - alert_data['timestamp']
            if age > self.alert_duration:
                expired.append(enemy_id)
        
        for enemy_id in expired:
            del self.alerts[enemy_id]
    
    def update(self):
        """Update alert system each frame."""
        self.current_frame += 1
        self.clear_old_alerts()
    
    def reset(self):
        """Clear all alerts (e.g., when changing levels)."""
        self.alerts.clear()
        self.current_frame = 0

# Global alert system instance
alert_system = AlertSystem()

# ============================================================================
# Vision Cone Helper
# ============================================================================

# ADDED: Vision cone helper function
def in_vision_cone(enemy_pos, player_pos, facing_angle, cone_half_angle, max_range):
    """
    Check if player is within enemy's vision cone.
    Returns True if player is within the cone and range.
    """
    ex, ey = enemy_pos
    px, py = player_pos
    
    # Calculate distance to player
    dx = px - ex
    dy = py - ey
    dist = (dx*dx + dy*dy) ** 0.5
    
    # Check if player is within range
    if dist > max_range or dist == 0:
        return False
    
    # Calculate angle to player
    angle_to_player = math.atan2(dy, dx)
    
    # Normalize angle difference to handle wrap-around
    angle_diff = (angle_to_player - facing_angle) % (2 * math.pi)
    if angle_diff > math.pi:
        angle_diff -= 2 * math.pi
    
    # Check if player is within cone angle
    return abs(angle_diff) <= cone_half_angle

# Shared containers (imported by main)
hitboxes = []
floating = []

class Hitbox:
    def __init__(self, rect, lifetime, damage, owner, dir_vec=(1,0), pogo=False, vx=0.0, vy=0.0, aoe_radius=0, visual_only=False, pierce=False, bypass_ifr=False, tag=None, has_sprite=False, arrow_sprite=False):
        self.rect = rect.copy()
        self.lifetime = lifetime
        self.damage = damage
        self.owner = owner
        self.dir_vec = dir_vec
        self.pogo = pogo
        self.vx = vx
        self.vy = vy
        self.aoe_radius = aoe_radius  # if >0, triggers area damage on hit
        self.visual_only = visual_only
        self.pierce = pierce
        # When True, this hit ignores enemy i-frames and does not set i-frames
        self.bypass_ifr = bypass_ifr
        # Optional tag for custom effects (e.g., 'stun')
        self.tag = tag
        self.alive = True
        # When True, suppresses fallback rectangle drawing (sprite will be drawn separately)
        self.has_sprite = has_sprite
        # When True, this hitbox should be rendered as an arrow sprite
        self.arrow_sprite = arrow_sprite

    def tick(self):
        # move if velocity set (keep as float for precision, convert only when applying)
        vx = getattr(self, 'vx', 0)
        vy = getattr(self, 'vy', 0)
        if vx != 0:
            self.rect.x += int(vx)
        if vy != 0:
            self.rect.y += int(vy)
        self.lifetime -= 1
        if self.lifetime <= 0:
            self.alive = False

    def draw(self, surf, camera, force_draw=False):
        # Skip drawing if this hitbox has a sprite (sprite is drawn separately by enemy's draw_projectile_sprites)
        # UNLESS force_draw is True (for debug mode)
        if getattr(self, 'has_sprite', False) and not force_draw:
            return
        
        # Only draw hitbox debug visualization when force_draw is enabled (F3 debug mode)
        if not force_draw:
            return
        
        # if this hitbox represents an AOE, draw a circle
        if getattr(self, 'aoe_radius', 0) > 0:
            cx, cy = camera.to_screen(self.rect.center)
            pygame.draw.circle(surf, (220,140,80), (int(cx), int(cy)), int(self.aoe_radius), width=2)
        else:
            pygame.draw.rect(surf, ACCENT, camera.to_screen_rect(self.rect), width=1)

class DamageNumber:
    def __init__(self, x, y, text, col=WHITE):
        self.x, self.y = x, y
        self.vy = -0.6
        self.life = 30
        self.text = text
        self.col = col

    def tick(self):
        self.y += self.vy
        self.life -= 1

    def draw(self, surf, camera, font):
        surf.blit(font.render(self.text, True, self.col), camera.to_screen((self.x, self.y)))

