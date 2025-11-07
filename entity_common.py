import math
import pygame

from config import ACCENT, WHITE

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
    def __init__(self, rect, lifetime, damage, owner, dir_vec=(1,0), pogo=False, vx=0, vy=0, aoe_radius=0, visual_only=False, pierce=False, bypass_ifr=False, tag=None):
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

    def tick(self):
        # move if velocity set
        if getattr(self, 'vx', 0) != 0:
            self.rect.x += int(self.vx)
        if getattr(self, 'vy', 0) != 0:
            self.rect.y += int(self.vy)
        self.lifetime -= 1
        if self.lifetime <= 0:
            self.alive = False

    def draw(self, surf, camera):
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

