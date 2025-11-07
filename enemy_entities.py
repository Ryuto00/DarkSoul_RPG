from __future__ import annotations

import math
import random
import pygame

from config import (
    FPS, GRAVITY, TERMINAL_VY, PLAYER_SPEED, PLAYER_AIR_SPEED, PLAYER_JUMP_V,
    PLAYER_SMALL_JUMP_CUT, COYOTE_FRAMES, JUMP_BUFFER_FRAMES,
    DASH_SPEED, DASH_TIME, DASH_COOLDOWN, INVINCIBLE_FRAMES,
    WALL_SLIDE_MAX, WALL_JUMP_VX, WALL_JUMP_VY, DOUBLE_JUMPS,
    ATTACK_COOLDOWN, ATTACK_LIFETIME, COMBO_RESET, SWORD_DAMAGE,
    POGO_BOUNCE_VY, ACCENT, GREEN, CYAN, RED, WHITE, IFRAME_BLINK_INTERVAL
)
from utils import los_clear, find_intermediate_visible_point, find_idle_patrol_target
from entity_common import Hitbox, DamageNumber, hitboxes, floating, in_vision_cone

class Bug:
    def __init__(self, x, ground_y):
        self.rect = pygame.Rect(x-14, ground_y-22, 28, 22)
        self.vx = random.choice([-1,1]) * 1.6
        self.hp = 30
        self.alive = True
        # ADDED: Vision cone properties (replacing aggro)
        self.vision_range = 200
        self.cone_half_angle = math.pi/6  # 60° total cone
        self.turn_rate = 0.05
        # ADDED: Facing direction and angle
        self.facing = 1 if self.vx > 0 else -1
        self.facing_angle = 0 if self.facing > 0 else math.pi
        self.ifr = 0
        # slow effect
        self.slow_mult = 1.0
        self.slow_remaining = 0
        # smart AI state
        self.state = 'idle'
        self.home = (self.rect.centerx, self.rect.centery)
        self.target = None
        self.last_seen = None
        self.repath_t = 0

    def tick(self, level, player):
        if not self.alive: return
        # DOT handling (cold feet)
        if getattr(self, 'dot_remaining', 0) > 0:
            per_frame = getattr(self, 'dot_dps', 0) / FPS
            self.dot_accum = getattr(self, 'dot_accum', 0.0) + per_frame
            if self.dot_accum >= 1.0:
                dmg = int(self.dot_accum)
                self.dot_accum -= dmg
                self.hp -= dmg
                floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{dmg}", WHITE))
                if self.hp <= 0:
                    self.alive = False
                    floating.append(DamageNumber(self.rect.centerx, self.rect.centery, "KO", CYAN))
            self.dot_remaining -= 1
        # slow timer
        if getattr(self, 'slow_remaining', 0) > 0:
            self.slow_remaining -= 1
            if self.slow_remaining <= 0:
                self.slow_mult = 1.0
        # --- Smart AI with Vision Cone ---
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # ADDED: Update facing direction
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
        
        # ADDED: Vision cone check
        in_cone = in_vision_cone(epos, ppos, self.facing_angle, self.cone_half_angle, self.vision_range)
        has_los = in_cone and los_clear(level, epos, ppos)
        
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        
        # AI state logic based on vision cone
        if has_los and dist_to_player < self.vision_range:
            self.state = 'pursue'
            self.last_seen = ppos
            self.target = ppos
        elif in_cone and dist_to_player < self.vision_range:
            # In cone but no LOS -> search
            if self.state != 'search' or self.repath_t <= 0:
                wp = find_intermediate_visible_point(level, epos, ppos)
                if wp:
                    self.state = 'search'
                    self.target = wp
                    self.repath_t = 15
                else:
                    # fallback toward last seen
                    self.state = 'search'
                    self.target = self.last_seen or ppos
                    self.repath_t = 15
            else:
                self.repath_t -= 1
        else:
            # idle and patrol
            if self.state != 'idle' or self.target is None:
                self.state = 'idle'
                self.target = find_idle_patrol_target(level, self.home)

        # movement toward target if any
        self.vx = 0
        spd = 1.8 * getattr(self, 'slow_mult', 1.0)
        if self.target:
            tx, ty = self.target
            dx = tx - self.rect.centerx
            dy = ty - self.rect.centery
            if abs(dx) < 2 and abs(dy) < 2:
                if self.state in ('search','idle'):
                    self.target = None
                # reached current target
            else:
                self.vx = spd if dx > 0 else -spd
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx > 0:
                    self.rect.right = s.left
                else:
                    self.rect.left = s.right
                self.vx *= -1
        self.rect.y += int(min(10, GRAVITY*2))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
        if self.ifr > 0:
            self.ifr -= 1
        if self.rect.colliderect(player.rect):
            # if player is parrying, reflect/hurt the bug instead of player
            if getattr(player, 'parrying', 0) > 0:
                self.hp -= 1
                self.ifr = 8
                floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, "PARRY", CYAN))
                # knockback away from player
                self.vx = -((1 if player.rect.centerx>self.rect.centerx else -1) * 3)
                player.vy = -6
            elif player.inv == 0:
                player.damage(1, ((1 if player.rect.centerx>self.rect.centerx else -1)*2, -6))
    def hit(self, hb: Hitbox, player: Player):
        if (self.ifr > 0 and not getattr(hb, 'bypass_ifr', False)) or not self.alive:
            return
        self.hp -= hb.damage
        if not getattr(hb, 'bypass_ifr', False):
            self.ifr = 8
        floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{hb.damage}", WHITE))
        # lifesteal: player heals 1 HP on hit when buff active
        if getattr(player, 'lifesteal', 0) > 0 and hb.damage > 0:
            old = player.hp
            player.hp = min(player.max_hp, player.hp + 1)
            if player.hp != old:
                floating.append(DamageNumber(player.rect.centerx, player.rect.top-10, "+1", GREEN))
        if hb.pogo:
            player.vy = POGO_BOUNCE_VY
            player.on_ground = False
        if self.hp <= 0:
            self.alive = False
            floating.append(DamageNumber(self.rect.centerx, self.rect.centery, "KO", CYAN))

    def draw(self, surf, camera, show_los=False):
        # draw LOS line to last-checked player point if available
        if show_los and getattr(self, '_los_point', None) is not None:
            col = GREEN if getattr(self, '_has_los', False) else RED
            pygame.draw.line(surf, col, camera.to_screen(self.rect.center), camera.to_screen(self._los_point), 2)
            
            # ADDED: Draw vision cone for debug
            if show_los:
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
        
        col = (180, 70, 160) if self.ifr==0 else (120, 40, 100)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=6)


class Boss:
    """Simple boss: large HP, slow movement, collides with player like Bug.
    This is intentionally simple — acts as a strong enemy for the boss room.
    """
    def __init__(self, x, ground_y):
        # Make boss wider and taller
        self.rect = pygame.Rect(x-32, ground_y-48, 64, 48)
        self.vx = 0
        self.hp = 70
        self.alive = True
        # ADDED: Vision cone properties (replacing aggro)
        self.vision_range = 300
        self.cone_half_angle = math.pi/3  # 120° total cone, wide
        self.turn_rate = 0.03  # slow turn rate
        # ADDED: Facing direction and angle
        self.facing = 1  # starts facing right
        self.facing_angle = 0  # 0 for right, math.pi for left
        self.ifr = 0
        # slow effect
        self.slow_mult = 1.0
        self.slow_remaining = 0

    def tick(self, level, player):
        if not self.alive: return
        # DOT handling (cold feet)
        if getattr(self, 'dot_remaining', 0) > 0:
            per_frame = getattr(self, 'dot_dps', 0) / FPS
            self.dot_accum = getattr(self, 'dot_accum', 0.0) + per_frame
            if self.dot_accum >= 1.0:
                dmg = int(self.dot_accum)
                self.dot_accum -= dmg
                self.hp -= dmg
                floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{dmg}", WHITE))
                if self.hp <= 0:
                    self.alive = False
                    floating.append(DamageNumber(self.rect.centerx, self.rect.centery, "KO", CYAN))
            self.dot_remaining -= 1
        # slow timer
        if getattr(self, 'slow_remaining', 0) > 0:
            self.slow_remaining -= 1
            if self.slow_remaining <= 0:
                self.slow_mult = 1.0
        
        # ADDED: Vision cone AI
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # ADDED: Update facing direction
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
        
        # ADDED: Vision cone check
        in_cone = in_vision_cone(epos, ppos, self.facing_angle, self.cone_half_angle, self.vision_range)
        has_los = in_cone and los_clear(level, epos, ppos)
        
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        
        # Simple AI: move toward player if in vision cone and has LOS
        if has_los and dist_to_player < self.vision_range:
            self.vx = (1 if dx>0 else -1) * 1.2
        else:
            self.vx = 0

        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx > 0:
                    self.rect.right = s.left
                else:
                    self.rect.left = s.right
                self.vx = 0

        # gravity
        self.rect.y += int(min(10, GRAVITY*2))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top

        if self.ifr > 0:
            self.ifr -= 1

        if self.rect.colliderect(player.rect):
            # if player parries, reflect to boss
            if getattr(player, 'parrying', 0) > 0:
                self.hp -= 2
                self.ifr = 12
                floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, "PARRY", CYAN))
                self.vx = -((1 if player.rect.centerx>self.rect.centerx else -1) * 4)
                player.vy = -8
            elif player.inv == 0:
                # bigger knockback
                player.damage(2, ((1 if player.rect.centerx>self.rect.centerx else -1)*3, -8))

    def hit(self, hb: Hitbox, player: Player):
        if (self.ifr > 0 and not getattr(hb, 'bypass_ifr', False)) or not self.alive:
            return
        self.hp -= hb.damage
        if not getattr(hb, 'bypass_ifr', False):
            self.ifr = 12
        floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{hb.damage}", WHITE))
        # lifesteal for player if buff active
        if getattr(player, 'lifesteal', 0) > 0 and hb.damage > 0:
            old = player.hp
            player.hp = min(player.max_hp, player.hp + 1)
            if player.hp != old:
                floating.append(DamageNumber(player.rect.centerx, player.rect.top-12, "+1", GREEN))
        if hb.pogo:
            player.vy = POGO_BOUNCE_VY
            player.on_ground = False
        if self.hp <= 0:
            self.alive = False
            floating.append(DamageNumber(self.rect.centerx, self.rect.centery, "KO", CYAN))

    def draw(self, surf, camera, show_los=False):
        # draw LOS line to last-checked player point if available
        if show_los and getattr(self, '_los_point', None) is not None:
            col = GREEN if getattr(self, '_has_los', False) else RED
            pygame.draw.line(surf, col, camera.to_screen(self.rect.center), camera.to_screen(self._los_point), 2)
            
            # ADDED: Draw vision cone for debug
            if show_los:
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
        
        col = (200, 100, 40) if self.ifr==0 else (140, 80, 30)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=8)


# --- New Enemy Types ---

class Frog:
    """Dashing enemy with a telegraphed lunge toward the player."""
    def __init__(self, x, ground_y):
        self.rect = pygame.Rect(x-14, ground_y-22, 28, 22)
        self.vx = 0
        self.hp = 18
        self.alive = True
        self.ifr = 0
        # ADDED: Vision cone properties (replacing aggro)
        self.vision_range = 220
        self.cone_half_angle = math.pi/12  # 30° total cone, precise
        self.turn_rate = 0.08  # quick turn rate
        # ADDED: Facing direction and angle
        self.facing = 1  # starts facing right
        self.facing_angle = 0  # 0 for right, math.pi for left
        self.state = 'idle'
        self.tele_t = 0
        self.tele_text = ''
        self.cool = 0
        self.dash_t = 0

    def tick(self, level, player):
        if not self.alive: return
        if self.ifr>0: self.ifr-=1
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # ADDED: Update facing direction
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
        
        # ADDED: Vision cone check
        in_cone = in_vision_cone(epos, ppos, self.facing_angle, self.cone_half_angle, self.vision_range)
        has_los = in_cone and los_clear(level, epos, ppos)
        
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        
        # Use Manhattan distance for frog's behavior (preserving original logic)
        dist = abs(dx) + abs(dy)
        
        if self.cool>0:
            self.cool -= 1
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0:
                # perform dash diagonally toward player
                spd = 8.0
                distv = max(1.0, (dx*dx + dy*dy) ** 0.5)
                nx, ny = dx/distv, dy/distv
                self.vx = nx * spd
                self.vy = ny * spd
                self.dash_t = 26
                self.state = 'dash'
                self.cool = 56
        elif self.state=='dash':
            # maintain dash for dash_t, then decay
            if self.dash_t > 0:
                self.dash_t -= 1
            else:
                self.vx *= 0.9
                if abs(self.vx) < 1.0:
                    self.state='idle'
        else:
            self.vx = 0
            if has_los and dist_to_player < self.vision_range and self.cool==0:
                # telegraph and delay
                self.tele_t = 24
                self.tele_text = '!'

        # move and collide
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx>0: self.rect.right = s.left
                else: self.rect.left = s.right
                self.vx = 0
        # gravity
        self.vy = getattr(self, 'vy', 0) + min(GRAVITY, 10)
        self.rect.y += int(min(10, self.vy))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
                    self.vy = 0
        # touch damage
        if self.rect.colliderect(player.rect) and player.inv==0:
            player.damage(1, ((1 if player.rect.centerx>self.rect.centerx else -1)*2, -6))

    def hit(self, hb: Hitbox, player: Player):
        if (self.ifr>0 and not getattr(hb,'bypass_ifr',False)) or not self.alive: return
        self.hp -= hb.damage
        if not getattr(hb,'bypass_ifr',False): self.ifr = 8
        floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{hb.damage}", WHITE))
        if self.hp<=0:
            self.alive=False
            floating.append(DamageNumber(self.rect.centery, self.rect.centery, "KO", CYAN))

    def draw(self, surf, camera, show_los=False):
        if not self.alive: return
        # draw LOS line to last-checked player point if available
        if show_los and getattr(self, '_los_point', None) is not None:
            col = GREEN if getattr(self, '_has_los', False) else RED
            pygame.draw.line(surf, col, camera.to_screen(self.rect.center), camera.to_screen(self._los_point), 2)
            
            # ADDED: Draw vision cone for debug
            if show_los:
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
        
        col = (80, 200, 80) if self.ifr==0 else (60, 120, 60)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=5)
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text',''):
            from utils import draw_text
            rx, ry = self.rect.centerx, self.rect.top - 10
            draw_text(surf, self.tele_text, camera.to_screen((rx-4, ry)), (255,80,80), size=18, bold=True)


class Archer:
    """Ranged enemy that shoots arrows with '!!' telegraph."""
    def __init__(self, x, ground_y):
        self.rect = pygame.Rect(x-14, ground_y-22, 28, 22)
        self.vx = 0
        self.hp = 16
        self.alive = True
        self.ifr = 0
        # ADDED: Vision cone properties (replacing aggro)
        self.vision_range = 350
        self.cone_half_angle = math.pi/4  # 90° total cone
        self.turn_rate = 0.05
        # ADDED: Facing direction and angle
        self.facing = 1  # starts facing right
        self.facing_angle = 0  # 0 for right, math.pi for left
        self.cool = 0
        self.tele_t = 0
        self.tele_text = ''

    def tick(self, level, player):
        if not self.alive: return
        if self.ifr>0: self.ifr-=1
        if self.cool>0: self.cool-=1
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # ADDED: Update facing direction
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
        
        # ADDED: Vision cone check
        in_cone = in_vision_cone(epos, ppos, self.facing_angle, self.cone_half_angle, self.vision_range)
        has_los = in_cone and los_clear(level, epos, ppos)
        
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0 and has_los and dist_to_player < self.vision_range:
                # fire arrow (limited to vision range)
                dist = max(1.0, (dx*dx+dy*dy)**0.5)
                nx, ny = dx/dist, dy/dist
                hb = pygame.Rect(0,0,10,6); hb.center = self.rect.center
                # Match player ranger's normal arrow speed and lifetime
                hitboxes.append(Hitbox(hb, 120, 1, self, dir_vec=(nx,ny), vx=nx*10.0, vy=ny*10.0))
                self.cool = 60
        elif has_los and self.cool==0 and dist_to_player < self.vision_range:
            self.tele_t = 18
            self.tele_text = '!!'

        # minimal reposition: sidestep a bit
        self.vx = 0
        if has_los and abs(ppos[0]-epos[0])<64:
            self.vx = -1.2 if ppos[0]>epos[0] else 1.2
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx>0: self.rect.right = s.left
                else: self.rect.left = s.right
                self.vx = 0
        # gravity
        self.rect.y += int(min(10, GRAVITY*2))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top

    def hit(self, hb: Hitbox, player: Player):
        if (self.ifr>0 and not getattr(hb,'bypass_ifr',False)) or not self.alive: return
        self.hp -= hb.damage
        if not getattr(hb,'bypass_ifr',False): self.ifr = 8
        floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{hb.damage}", WHITE))
        if self.hp<=0:
            self.alive=False
            floating.append(DamageNumber(self.rect.centery, self.rect.centery, "KO", CYAN))

    def draw(self, surf, camera, show_los=False):
        if not self.alive: return
        # draw LOS line to last-checked player point if available
        if show_los and getattr(self, '_los_point', None) is not None:
            col = GREEN if getattr(self, '_has_los', False) else RED
            pygame.draw.line(surf, col, camera.to_screen(self.rect.center), camera.to_screen(self._los_point), 2)
            
            # ADDED: Draw vision cone for debug
            if show_los:
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
        
        col = (200, 200, 80) if self.ifr==0 else (120, 120, 60)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=5)
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text',''):
            from utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), (255,200,80), size=18, bold=True)


class WizardCaster:
    """Casts fast magic bolts with '!!' telegraph."""
    def __init__(self, x, ground_y):
        self.rect = pygame.Rect(x-14, ground_y-22, 28, 22)
        self.vx = 0
        self.hp = 14
        self.alive = True
        self.ifr = 0
        # ADDED: Vision cone properties (replacing aggro)
        self.vision_range = 280
        self.cone_half_angle = math.pi/3  # 120° total cone
        self.turn_rate = 0.05
        # ADDED: Facing direction and angle
        self.facing = 1  # starts facing right
        self.facing_angle = 0  # 0 for right, math.pi for left
        self.cool = 0
        self.tele_t = 0
        self.tele_text = ''
        self.action = None  # 'bolt' | 'missile' | 'fireball'

    def tick(self, level, player):
        if not self.alive: return
        if self.ifr>0: self.ifr-=1
        if self.cool>0: self.cool-=1
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # ADDED: Update facing direction
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
        
        # ADDED: Vision cone check
        in_cone = in_vision_cone(epos, ppos, self.facing_angle, self.cone_half_angle, self.vision_range)
        has_los = in_cone and los_clear(level, epos, ppos)
        
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0 and has_los and dist_to_player < self.vision_range:
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
        elif has_los and self.cool==0 and dist_to_player < self.vision_range:
            import random
            self.action = random.choices(['bolt','missile','fireball'], weights=[0.5,0.3,0.2])[0]
            self.tele_t = 16
            self.tele_text = '!!'
        # gravity only (no movement)
        self.rect.y += int(min(10, GRAVITY*2))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top

    def hit(self, hb: Hitbox, player: Player):
        if (self.ifr>0 and not getattr(hb,'bypass_ifr',False)) or not self.alive: return
        self.hp -= hb.damage
        if not getattr(hb,'bypass_ifr',False): self.ifr = 8
        floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{hb.damage}", WHITE))
        if self.hp<=0:
            self.alive=False
            floating.append(DamageNumber(self.rect.centery, self.rect.centery, "KO", CYAN))

    def draw(self, surf, camera, show_los=False):
        if not self.alive: return
        # draw LOS line to last-checked player point if available
        if show_los and getattr(self, '_los_point', None) is not None:
            col = GREEN if getattr(self, '_has_los', False) else RED
            pygame.draw.line(surf, col, camera.to_screen(self.rect.center), camera.to_screen(self._los_point), 2)
        col = (180, 120, 220) if self.ifr==0 else (110, 80, 140)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=5)
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text',''):
            from utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), (255,200,80), size=18, bold=True)


class Assassin:
    """Semi-invisible melee dash enemy."""
    def __init__(self, x, ground_y):
        self.rect = pygame.Rect(x-14, ground_y-22, 28, 22)
        self.vx = 0
        self.hp = 20
        self.alive = True
        self.ifr = 0
        # ADDED: Vision cone properties (replacing aggro)
        self.vision_range = 240
        self.cone_half_angle = math.pi/8  # 45° total cone
        self.turn_rate = 0.06
        # ADDED: Facing direction and angle
        self.facing = 1  # starts facing right
        self.facing_angle = 0  # 0 for right, math.pi for left
        self.state = 'idle'
        self.tele_t = 0
        self.cool = 0
        self.action = None  # 'dash' or 'slash'
        self.dash_t = 0

    def tick(self, level, player):
        if not self.alive: return
        if self.ifr>0: self.ifr-=1
        if self.cool>0: self.cool-=1
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # ADDED: Update facing direction
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
        
        # ADDED: Vision cone check
        in_cone = in_vision_cone(epos, ppos, self.facing_angle, self.cone_half_angle, self.vision_range)
        has_los = in_cone and los_clear(level, epos, ppos)
        
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        self._in_cone = in_cone  # ADDED: Store for drawing
        
        facing = self.facing
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0:
                if self.action == 'dash':
                    # diagonal dash toward player
                    dx = ppos[0]-epos[0]; dy = ppos[1]-epos[1]
                    dist = max(1.0, (dx*dx+dy*dy)**0.5)
                    nx, ny = dx/dist, dy/dist
                    self.vx = nx * 7.5
                    self.vy = ny * 7.5
                    self.dash_t = 18
                    self.state = 'dash'
                elif self.action == 'slash':
                    # spawn a sword hitbox forward
                    hb = pygame.Rect(0, 0, int(self.rect.w*1.2), int(self.rect.h*0.7))
                    if facing > 0:
                        hb.midleft = (self.rect.right, self.rect.centery)
                    else:
                        hb.midright = (self.rect.left, self.rect.centery)
                    hitboxes.append(Hitbox(hb, 10, 1, self, dir_vec=(facing,0)))
                    self.cool = 48
                    self.action = None
        elif self.state=='dash':
            # while dashing, keep spawning short sword hitboxes forward
            hb = pygame.Rect(0, 0, int(self.rect.w*1.1), int(self.rect.h*0.6))
            if facing > 0:
                hb.midleft = (self.rect.right, self.rect.centery)
            else:
                hb.midright = (self.rect.left, self.rect.centery)
            hitboxes.append(Hitbox(hb, 6, 1, self, dir_vec=(facing,0)))
            if self.dash_t > 0:
                self.dash_t -= 1
            else:
                self.vx *= 0.9
                if abs(self.vx)<1.0:
                    self.state='idle'; self.cool=60
        elif has_los and self.cool==0 and dist_to_player < self.vision_range:
            import random
            self.action = 'dash' if random.random() < 0.5 else 'slash'
            if self.action == 'dash':
                self.tele_t = 14
                self.tele_text = '!'
            else:
                self.tele_t = 12
                self.tele_text = '!!'
        # move
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx>0: self.rect.right=s.left
                else: self.rect.left=s.right
                self.vx=0
        # vertical motion with gravity accumulation
        self.vy = getattr(self, 'vy', 0) + min(GRAVITY, 10)
        self.rect.y += int(min(10, self.vy))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
                    self.vy = 0
        # Melee damage is applied via explicit sword hitboxes during actions

    def hit(self, hb: Hitbox, player: Player):
        if (self.ifr>0 and not getattr(hb,'bypass_ifr',False)) or not self.alive: return
        self.hp -= hb.damage
        if not getattr(hb,'bypass_ifr',False): self.ifr = 8
        floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{hb.damage}", WHITE))
        if self.hp<=0:
            self.alive=False
            floating.append(DamageNumber(self.rect.centery, self.rect.centery, "KO", CYAN))

    def draw(self, surf, camera, show_los=False):
        if not self.alive: return
        # draw LOS line to last-checked player point if available
        if show_los and getattr(self, '_los_point', None) is not None:
            col = GREEN if getattr(self, '_has_los', False) else RED
            pygame.draw.line(surf, col, camera.to_screen(self.rect.center), camera.to_screen(self._los_point), 2)
            
            # ADDED: Draw vision cone for debug
            if show_los:
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
        
        # ADDED: Semi-invisible look: darker color when not in cone
        in_cone = getattr(self, '_in_cone', False)
        if in_cone:
            col = (60,60,80) if self.ifr==0 else (40,40,60)
        else:
            # Even darker when not in vision cone for "semi-invisible" effect
            col = (30,30,40) if self.ifr==0 else (20,20,30)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=5)


class Bee:
    """Hybrid shooter/dasher. Chooses randomly between actions."""
    def __init__(self, x, ground_y):
        self.rect = pygame.Rect(x-12, ground_y-20, 24, 20)
        self.vx = 0
        self.hp = 12
        self.alive = True
        self.ifr = 0
        # ADDED: Vision cone properties (replacing aggro)
        self.vision_range = 240
        self.cone_half_angle = math.pi/4  # 90° total cone
        self.turn_rate = 0.05
        # ADDED: Facing direction and angle
        self.facing = 1  # starts facing right
        self.facing_angle = 0  # 0 for right, math.pi for left
        self.cool = 0
        self.tele_t = 0
        self.tele_text = ''
        self.action = None

    def tick(self, level, player):
        if not self.alive: return
        if self.ifr>0: self.ifr-=1
        if self.cool>0: self.cool-=1
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        
        # Calculate distance to player
        dx = ppos[0] - epos[0]
        dy = ppos[1] - epos[1]
        dist_to_player = (dx*dx + dy*dy) ** 0.5
        
        # ADDED: Update facing direction
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
        
        # ADDED: Vision cone check
        in_cone = in_vision_cone(epos, ppos, self.facing_angle, self.cone_half_angle, self.vision_range)
        has_los = in_cone and los_clear(level, epos, ppos)
        
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        
        import random
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0 and has_los and dist_to_player < self.vision_range:
                if self.action=='dash':
                    self.vx = 7 if ppos[0]>epos[0] else -7
                elif self.action=='shoot':
                    dist = max(1.0, (dx*dx+dy*dy)**0.5)
                    nx, ny = dx/dist, dy/dist
                    hb = pygame.Rect(0,0,10,6); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 120, 1, self, dir_vec=(nx,ny), vx=nx*7.5, vy=ny*7.5))
                self.cool = 50
        elif has_los and self.cool==0 and dist_to_player < self.vision_range:
            self.action = 'dash' if random.random()<0.5 else 'shoot'
            self.tele_t = 14 if self.action=='dash' else 16
            self.tele_text = '!' if self.action=='dash' else '!!'

        # dash decay
        if abs(self.vx)>0:
            self.vx *= 0.9
            if abs(self.vx)<1.0: self.vx=0
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx>0: self.rect.right=s.left
                else: self.rect.left=s.right
                self.vx=0
        self.rect.y += int(min(10, GRAVITY*2))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top

    def hit(self, hb: Hitbox, player: Player):
        if (self.ifr>0 and not getattr(hb,'bypass_ifr',False)) or not self.alive: return
        self.hp -= hb.damage
        if not getattr(hb,'bypass_ifr',False): self.ifr = 8
        floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{hb.damage}", WHITE))
        if self.hp<=0:
            self.alive=False
            floating.append(DamageNumber(self.rect.centery, self.rect.centery, "KO", CYAN))

    def draw(self, surf, camera, show_los=False):
        if not self.alive: return
        # draw LOS line to last-checked player point if available
        if show_los and getattr(self, '_los_point', None) is not None:
            col = GREEN if getattr(self, '_has_los', False) else RED
            pygame.draw.line(surf, col, camera.to_screen(self.rect.center), camera.to_screen(self._los_point), 2)
            
            # ADDED: Draw vision cone for debug
            if show_los:
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
        
        col = (240, 180, 60) if self.ifr==0 else (140, 120, 50)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=5)
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text',''):
            from utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-4, self.rect.top-10)), (255,100,80), size=18, bold=True)


class Golem:
    """Boss with random pattern: dash (!), shoot (!!), stun (!!)."""
    def __init__(self, x, ground_y):
        self.rect = pygame.Rect(x-28, ground_y-44, 56, 44)
        self.vx = 0
        self.hp = 120
        self.alive = True
        self.ifr = 0
        self.aggro = 500
        self.cool = 0
        self.tele_t = 0
        self.tele_text = ''
        self.action = None

    def tick(self, level, player):
        if not self.alive: return
        if self.ifr>0: self.ifr-=1
        if self.cool>0: self.cool-=1
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        has_los = los_clear(level, epos, ppos)
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0:
                if self.action=='dash':
                    # diagonal dash toward player
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
                    # radial stun around golem
                    r = 72
                    hb = pygame.Rect(0,0,r*2, r*2)
                    hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 24, 0, self, aoe_radius=r, tag='stun'))
                self.cool = 70
        elif has_los and self.cool==0:
            self.action = random.choice(['dash','shoot','stun'])
            self.tele_text = '!' if self.action=='dash' else '!!'
            self.tele_t = 22 if self.action=='dash' else 18

        # dash decay
        if abs(self.vx)>0:
            self.vx *= 0.9
            if abs(self.vx)<1.0: self.vx=0
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx>0: self.rect.right=s.left
                else: self.rect.left=s.right
                self.vx=0
        # gravity with vertical velocity
        self.vy = getattr(self, 'vy', 0) + min(GRAVITY, 10)
        self.rect.y += int(min(10, self.vy))
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.rect.bottom > s.top and self.rect.centery < s.centery:
                    self.rect.bottom = s.top
                    self.vy = 0

        if self.rect.colliderect(player.rect) and player.inv==0:
            player.damage(2, ((1 if player.rect.centerx>self.rect.centerx else -1)*3, -8))

    def hit(self, hb: Hitbox, player: Player):
        if (self.ifr>0 and not getattr(hb,'bypass_ifr',False)) or not self.alive: return
        self.hp -= hb.damage
        if not getattr(hb,'bypass_ifr',False): self.ifr = 12
        floating.append(DamageNumber(self.rect.centerx, self.rect.top-6, f"{hb.damage}", WHITE))
        if self.hp<=0:
            self.alive=False
            floating.append(DamageNumber(self.rect.centery, self.rect.centery, "KO", CYAN))

    def draw(self, surf, camera, show_los=False):
        if not self.alive: return
        # draw LOS line to last-checked player point if available
        if show_los and getattr(self, '_los_point', None) is not None:
            col = GREEN if getattr(self,
            '_has_los', False) else RED
            pygame.draw.line(surf, col, camera.to_screen(self.rect.center), camera.to_screen(self._los_point), 2)
        # ADDED: Draw vision cone for debug
        if show_los:
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
        
        col = (140, 140, 160) if self.ifr==0 else (100, 100, 120)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=7)
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text',''):
            from utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-6, self.rect.top-12)), (255,120,90), size=22, bold=True)
