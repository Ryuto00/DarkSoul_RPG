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
from utils import sign, los_clear, find_intermediate_visible_point, find_idle_patrol_target

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

class Player:
    def __init__(self, x, y, cls='Knight'):
        self.rect = pygame.Rect(x, y, 18, 30)
        self.vx = 0
        self.vy = 0
        self.facing = 1
        self.on_ground = False
        self.was_on_ground = False
        self.coyote = 0
        self.jump_buffer = 0
        self.double_jumps = DOUBLE_JUMPS
        self.can_dash = True
        self.dashing = 0
        self.dash_cd = 0
        self.inv = 0
        # class selection
        self.cls = cls
        if cls == 'Knight':
            self.max_hp = 7
            self.hp = 7
            self.player_speed = 3.6
            self.player_air_speed = 3.0
            self.attack_damage = 4
            self.max_stamina = 8.0
            self.stamina = 8.0
            self.max_mana = 50.0
            self.mana = 50.0
            # Knight: moderate stamina regen, mana regen default 5 per second
            self._stamina_regen = 0.08
            self._mana_regen = 5.0 / FPS
        elif cls == 'Ranger':
            self.max_hp = 5
            self.hp = 5
            self.player_speed = 4.6
            self.player_air_speed = 4.0
            self.attack_damage = 3
            self.max_stamina = 12.0
            self.stamina = 12.0
            self.max_mana = 70.0
            self.mana = 70.0
            # Ranger: fast stamina regen, mana regen default 5 per second
            self._stamina_regen = 0.18
            self._mana_regen = 5.0 / FPS
        elif cls == 'Wizard':
            self.max_hp = 4
            self.hp = 4
            self.player_speed = 3.8
            self.player_air_speed = 3.2
            self.attack_damage = 1
            self.max_stamina = 4.0
            self.stamina = 4.0
            self.max_mana = 100.0
            self.mana = 100.0
            # Wizard: lower stamina regen, higher mana regen (8 per second)
            self._stamina_regen = 0.05
            self._mana_regen = 8.0 / FPS
        else:
            # fallback to defaults
            self.max_hp = 5
            self.hp = 5
            self.player_speed = PLAYER_SPEED
            self.player_air_speed = PLAYER_AIR_SPEED
            self.attack_damage = SWORD_DAMAGE
        self.combo = 0
        self.combo_t = 0
        self.attack_cd = 0
        self.sliding_wall = 0  # -1 left, +1 right, 0 none
        self.iframes_flash = False
        # developer cheat flag - when True player takes no damage
        self.god = False
        # parry state (frames left)
        self.parrying = 0
        # stamina regen cooldown (frames). When >0, stamina will not regen.
        self._stamina_cooldown = 0
        # teleport (wizard) cooldown
        self._teleport_cooldown = 0
        self._teleport_distance = 160
        self._teleport_mana_cost = 20.0
        # dead state
        self.dead = False
        # skill cooldown small buffer to avoid spam
        # Per-skill cooldowns (frames) and maxima for HUD
        self.skill_cd1 = 0
        self.skill_cd2 = 0
        self.skill_cd3 = 0
        self.skill_cd1_max = 1
        self.skill_cd2_max = 1
        self.skill_cd3_max = 1
        # ranger charge state
        self.charging = False
        self.charge_time = 0
        self.charge_threshold = int(0.5 * FPS)
        # track previous mouse button state to detect release
        self._prev_lmb = False
        # Knight buffs/skills
        self.shield_timer = 0
        self.shield_hits = 0
        self.power_timer = 0
        self.atk_bonus = 0
        self.lifesteal = 0
        # Ranger buffs/skills
        self.triple_timer = 0
        self.sniper_ready = False
        self.sniper_mult = 2.5
        self.speed_timer = 0
        self._blink_t = 0
        # crowd control
        self.stunned = 0
        # consumable buffs
        self.speed_potion_timer = 0
        self.speed_potion_bonus = 0.0
    def input(self, level, camera):
        if self.dead:
            return
        keys = pygame.key.get_pressed()
        stunned = self.stunned > 0
        if stunned:
            self.stunned -= 1
        move = 0
        if not stunned:
            if keys[pygame.K_a]: move -= 1
            if keys[pygame.K_d]: move += 1
        # use class-specific speeds (apply Ranger speed boost skill)
        base_speed = self.player_speed if self.on_ground else self.player_air_speed
        bonus = 1.0 if (self.cls == 'Ranger' and getattr(self, 'speed_timer', 0) > 0) else 0.0
        speed = base_speed + bonus
        if self.dashing:
            pass
        else:
            self.vx = move * speed
            if move:
                self.facing = move

        if not stunned and (keys[pygame.K_SPACE] or keys[pygame.K_k]):
            self.jump_buffer = JUMP_BUFFER_FRAMES
        else:
            if self.vy < 0:
                if not (keys[pygame.K_SPACE] or keys[pygame.K_k]):
                    self.vy *= PLAYER_SMALL_JUMP_CUT

        if not stunned and (keys[pygame.K_LSHIFT] or keys[pygame.K_j]) and self.can_dash and self.dash_cd == 0 and not self.dashing:
            self.start_dash()

        # Parry: Right mouse button or E (Knight only)
        rmb = pygame.mouse.get_pressed()[2]
        if not stunned and (rmb or keys[pygame.K_e]) and self.cls == 'Knight':
            self.parry_action()
        # Wizard teleport skill: R (teleport toward mouse)
        if not stunned and keys[pygame.K_r] and self.cls == 'Wizard':
            self.teleport_to_mouse(level, camera)

        # Skill keys per class (1/2/3)
        if not stunned and keys[pygame.K_1]:
            self.activate_skill(1, level, camera)
        elif not stunned and keys[pygame.K_2]:
            self.activate_skill(2, level, camera)
        elif not stunned and keys[pygame.K_3]:
            self.activate_skill(3, level, camera)

        # Attack / Ranger charge handling
        lmb = pygame.mouse.get_pressed()[0]
        if not stunned and self.attack_cd == 0:
            if self.cls == 'Ranger':
                # start charging on press
                if lmb and not self._prev_lmb:
                    self.charging = True
                    self.charge_time = 0
                if self.charging and lmb:
                    self.charge_time += 1
                # on release, fire arrow
                if self.charging and not lmb and self._prev_lmb:
                    charged = self.charge_time >= self.charge_threshold
                    # Triple-shot: force 3 arrows each dealing 7 dmg (example: 3*7=21)
                    if getattr(self, 'triple_timer', 0) > 0:
                        base = 7
                        dmg = base
                        # allow sniper multiplier to apply if charged
                        if charged and self.sniper_ready:
                            dmg = int(base * self.sniper_mult)
                            self.sniper_ready = False
                        speed = 14
                        self.fire_triple_arrows(dmg, speed, camera, pierce=charged)
                    else:
                        dmg = 7 if charged else 3
                        # Sniper buff multiplies next charged shot
                        if charged and self.sniper_ready:
                            dmg = int(dmg * self.sniper_mult)
                            self.sniper_ready = False
                        speed = 14 if charged else 10
                        self.fire_arrow(dmg, speed, camera, pierce=charged)
                    self.attack_cd = ATTACK_COOLDOWN
                    self.charging = False
            else:
                if keys[pygame.K_l] or lmb:
                    self.start_attack(keys, camera)
        # update prev mouse state
        self._prev_lmb = lmb

    def start_dash(self):
        # require some stamina to dash
        dash_cost = 2.0
        if getattr(self, 'stamina', 0) <= 0:
            return
        # consume stamina if available
        if hasattr(self, 'stamina'):
            self.stamina = max(0.0, self.stamina - dash_cost)
        # start stamina regen cooldown (1 second)
        self._stamina_cooldown = int(FPS)
        # grant short invincibility when dash starts (0.25s)
        self.inv = int(0.25 * FPS)
        self.dashing = DASH_TIME
        self.can_dash = False
        self.dash_cd = DASH_COOLDOWN
        self.vy = 0
        self.vx = self.facing * DASH_SPEED

    def start_attack(self, keys, camera):
        # Wizard: ranged normal attack toward mouse
        if self.cls == 'Wizard':
            self.attack_cd = ATTACK_COOLDOWN
            self.combo_t = COMBO_RESET
            self.combo = (self.combo + 1) % 3
            mx, my = pygame.mouse.get_pos()
            world_x = mx + camera.x
            world_y = my + camera.y
            dx = world_x - self.rect.centerx
            dy = world_y - self.rect.centery
            dist = (dx*dx + dy*dy) ** 0.5
            if dist == 0:
                nx, ny = (1, 0)
            else:
                nx, ny = dx / dist, dy / dist
            speed = 9.0
            hb = pygame.Rect(0, 0, 8, 8)
            hb.center = self.rect.center
            hitboxes.append(Hitbox(hb, 90, 1, self, dir_vec=(nx,ny), vx=nx*speed, vy=ny*speed))
            return

        up = keys[pygame.K_w] or keys[pygame.K_UP]
        down = keys[pygame.K_s] or keys[pygame.K_DOWN]
        dir_vec = (self.facing, 0)
        if up: dir_vec = (0, -1)
        elif down: dir_vec = (0, 1)
        self.attack_cd = ATTACK_COOLDOWN
        self.combo_t = COMBO_RESET
        self.combo = (self.combo + 1) % 3

        if dir_vec == (0, -1):
            # upward hitbox (unchanged width, tall)
            hb = pygame.Rect(0, 0, self.rect.w, int(self.rect.h * 0.9))
            hb.midbottom = self.rect.midtop
        elif dir_vec == (0, 1):
            # downward hitbox (unchanged)
            hb = pygame.Rect(0, 0, self.rect.w, int(self.rect.h * 1.2))
            hb.midtop = self.rect.midbottom
        else:
            # forward hitbox: increase horizontal reach (example change 1.2 -> 1.6)
            hb = pygame.Rect(0, 0, int(self.rect.w * 1.6), int(self.rect.h * 1.0))
            if self.facing > 0:
                hb.midleft = (self.rect.right, self.rect.centery)
            else:
                hb.midright = (self.rect.left, self.rect.centery)
        # use class attack damage (melee)
        dmg = self.attack_damage + getattr(self, 'atk_bonus', 0)
        hitboxes.append(Hitbox(hb, ATTACK_LIFETIME, dmg, self, dir_vec, pogo=(dir_vec==(0,1))))

    def fire_arrow(self, damage, speed, camera, pierce=False):
        # spawn a moving arrow hitbox toward mouse direction
        mx, my = pygame.mouse.get_pos()
        world_x = mx + camera.x
        world_y = my + camera.y
        dx = world_x - self.rect.centerx
        dy = world_y - self.rect.centery
        dist = (dx*dx + dy*dy) ** 0.5
        if dist == 0:
            nx, ny = (1, 0)
        else:
            nx, ny = dx / dist, dy / dist
        hb = pygame.Rect(0, 0, 10, 6)
        hb.center = self.rect.center
        vx = nx * speed
        vy = ny * speed
        hitboxes.append(Hitbox(hb, 120, damage, self, dir_vec=(nx,ny), vx=vx, vy=vy, pierce=pierce))

    def fire_triple_arrows(self, base_damage, speed, camera, pierce=False):
        # Fire three arrows with slight angle offsets
        import math
        mx, my = pygame.mouse.get_pos()
        world_x = mx + camera.x
        world_y = my + camera.y
        dx = world_x - self.rect.centerx
        dy = world_y - self.rect.centery
        base_ang = math.atan2(dy, dx)
        for ang in (base_ang - math.radians(8), base_ang, base_ang + math.radians(8)):
            nx, ny = math.cos(ang), math.sin(ang)
            hb = pygame.Rect(0, 0, 10, 6)
            hb.center = self.rect.center
            vx = nx * speed
            vy = ny * speed
            hitboxes.append(Hitbox(hb, 120, base_damage, self, dir_vec=(nx,ny), vx=vx, vy=vy, pierce=pierce, bypass_ifr=True))

    # --- Wizard skill casts ---
    def cast_fireball(self, level, camera):
        cost = 15
        if getattr(self, 'mana', 0) < cost or self.skill_cd1 > 0:
            return
        self.mana = max(0.0, self.mana - cost)
        self.skill_cd1 = self.skill_cd1_max = int(1 * FPS)  # 1s CD
        mx, my = pygame.mouse.get_pos()
        world_x = mx + camera.x
        world_y = my + camera.y
        dx = world_x - self.rect.centerx
        dy = world_y - self.rect.centery
        dist = (dx*dx + dy*dy) ** 0.5
        if dist == 0:
            return
        nx = dx / dist
        ny = dy / dist
        speed = 6.0
        hb = pygame.Rect(0, 0, 12, 12)
        hb.center = self.rect.center
        # small moving projectile that explodes on hit (AOE)
        hitboxes.append(Hitbox(hb, 180, 6, self, dir_vec=(nx, ny), vx=nx*speed, vy=ny*speed, aoe_radius=48))

    def cast_coldfeet(self, level, camera):
        cost = 25
        if getattr(self, 'mana', 0) < cost or self.skill_cd2 > 0:
            return
        self.mana = max(0.0, self.mana - cost)
        self.skill_cd2 = self.skill_cd2_max = int(8 * FPS)  # 8s CD
        mx, my = pygame.mouse.get_pos()
        world_x = mx + camera.x
        world_y = my + camera.y
        radius = 48
        # visual indicator for the cold feet area (no instant damage)
        hb = pygame.Rect(0,0,int(radius*2), int(radius*2))
        hb.center = (int(world_x), int(world_y))
        hitboxes.append(Hitbox(hb, 4*FPS, 0, self, aoe_radius=radius, visual_only=True))
        for e in level.enemies:
            if getattr(e, 'alive', False):
                dx = e.rect.centerx - world_x
                dy = e.rect.centery - world_y
                if (dx*dx + dy*dy) ** 0.5 <= radius:
                    # apply DOT state
                    e.dot_remaining = 4 * FPS
                    e.dot_dps = 5  # damage per second (buffed)
                    e.dot_accum = 0.0
                    # apply slow effect
                    e.slow_mult = 0.85
                    e.slow_remaining = 4 * FPS

    def cast_magic_missile(self, level, camera):
        cost = 30
        if getattr(self, 'mana', 0) < cost or self.skill_cd3 > 0:
            return
        self.mana = max(0.0, self.mana - cost)
        self.skill_cd3 = self.skill_cd3_max = int(2 * FPS)  # 2s CD
        mx, my = pygame.mouse.get_pos()
        world_x = mx + camera.x
        world_y = my + camera.y
        dx = world_x - self.rect.centerx
        dy = world_y - self.rect.centery
        dist = (dx*dx + dy*dy) ** 0.5
        if dist == 0:
            nx, ny = (1, 0)
        else:
            nx, ny = dx / dist, dy / dist
        speed = 20.0
    # a narrow fast projectile representing the magic missile
        hb = pygame.Rect(0, 0, 18, 6)
        hb.center = self.rect.center
        vx = nx * speed
        vy = ny * speed
        hitboxes.append(Hitbox(hb, 36, 12, self, dir_vec=(nx,ny), vx=vx, vy=vy))

    def parry_action(self):
        # Knight parry (consumes stamina), short duration
        if self.dead or getattr(self, 'parrying', 0) > 0 or self.cls != 'Knight':
            return
        parry_cost = 3.0
        parry_duration = 12
        if getattr(self, 'stamina', 0) >= parry_cost:
            self.stamina = max(0.0, self.stamina - parry_cost)
            self.parrying = parry_duration
            self._stamina_cooldown = int(FPS)

    def activate_skill(self, idx, level, camera):
        # Route skill casts by class and index
        if self.dead:
            return
        if self.cls == 'Wizard':
            if idx == 1:
                self.cast_fireball(level, camera)
            elif idx == 2:
                self.cast_coldfeet(level, camera)
            elif idx == 3:
                self.cast_magic_missile(level, camera)
        elif self.cls == 'Knight':
            # Knight skills: Shield, Power, Charge
            if idx == 1 and self.skill_cd1 == 0:
                self.shield_timer = 10 * FPS
                self.shield_hits = 2
                self.skill_cd1 = self.skill_cd1_max = 15 * FPS
            elif idx == 2 and self.skill_cd2 == 0:
                self.power_timer = 10 * FPS
                self.atk_bonus = 2
                self.lifesteal = 1
                self.skill_cd2 = self.skill_cd2_max = 25 * FPS
            elif idx == 3 and self.skill_cd3 == 0:
                # charge: a short fast moving hitbox that deals 4 dmg
                self.skill_cd3 = self.skill_cd3_max = 6 * FPS
                dash_speed = 10
                hb = pygame.Rect(0, 0, int(self.rect.w*1.2), self.rect.h)
                if self.facing > 0:
                    hb.midleft = (self.rect.right, self.rect.centery)
                else:
                    hb.midright = (self.rect.left, self.rect.centery)
                hitboxes.append(Hitbox(hb, 12, 4, self, dir_vec=(self.facing,0), vx=self.facing*dash_speed))
                # give the player a burst of speed
                self.vx = self.facing * dash_speed
                self.dashing = 8
        elif self.cls == 'Ranger':
            # Ranger skills: Triple shot, Sniper, Speed boost
            if idx == 1 and self.skill_cd1 == 0:
                self.triple_timer = 7 * FPS
                self.skill_cd1 = self.skill_cd1_max = 20 * FPS
            elif idx == 2 and self.skill_cd2 == 0:
                self.sniper_ready = True
                self.skill_cd2 = self.skill_cd2_max = 10 * FPS
            elif idx == 3 and self.skill_cd3 == 0:
                self.speed_timer = 7 * FPS
                self.skill_cd3 = self.skill_cd3_max = 15 * FPS

    def teleport_to_mouse(self, level, camera):
        """Teleport the player toward the mouse world position up to teleport_distance,
        stopping at the last safe position before solids. Consumes mana and sets a cooldown.
        """
        # check cooldown and mana
        if getattr(self, '_teleport_cooldown', 0) > 0:
            return
        if getattr(self, 'mana', 0) < getattr(self, '_teleport_mana_cost', 9999):
            return

        mx, my = pygame.mouse.get_pos()
        world_x = mx + camera.x
        world_y = my + camera.y
        dx = world_x - self.rect.centerx
        dy = world_y - self.rect.centery
        dist = (dx*dx + dy*dy) ** 0.5
        if dist == 0:
            return
        nx = dx / dist
        ny = dy / dist

        step = 8
        maxd = int(getattr(self, '_teleport_distance', 160))
        last_safe_x, last_safe_y = self.rect.x, self.rect.y
        for d in range(step, maxd+step, step):
            cx = int(self.rect.centerx + nx * d)
            cy = int(self.rect.centery + ny * d)
            cand = self.rect.copy()
            cand.center = (cx, cy)
            if any(cand.colliderect(s) for s in level.solids):
                break
            last_safe_x, last_safe_y = cand.x, cand.y

        # move to last safe position
        self.rect.x = last_safe_x
        self.rect.y = last_safe_y
        # consume mana and set cooldown
        self.mana = max(0.0, self.mana - getattr(self, '_teleport_mana_cost', 6.0))
        self._teleport_cooldown = int(FPS)  # 1 second cooldown
        # small mana use shouldn't block stamina regen, no cooldown

    def physics(self, level):
        if self.dead:
            return

        if self.on_ground:
            self.coyote = COYOTE_FRAMES
            self.double_jumps = DOUBLE_JUMPS
            self.can_dash = True if self.dash_cd == 0 else self.can_dash
        else:
            self.coyote = max(0, self.coyote-1)

        if self.jump_buffer > 0:
            self.jump_buffer -= 1

        self.sliding_wall = 0
        if not self.on_ground and not self.dashing:
            left_check = self.rect.move(-1, 0)
            right_check = self.rect.move(1, 0)
            if any(left_check.colliderect(s) for s in level.solids) and self.vx < 0:
                self.sliding_wall = -1
            elif any(right_check.colliderect(s) for s in level.solids) and self.vx > 0:
                self.sliding_wall = 1

        if self.sliding_wall != 0 and self.vy > WALL_SLIDE_MAX:
            self.vy = WALL_SLIDE_MAX

        want_jump = self.jump_buffer > 0
        if want_jump:
            did = False
            if self.on_ground or self.coyote > 0:
                self.vy = PLAYER_JUMP_V
                did = True
            elif self.sliding_wall != 0:
                self.vy = WALL_JUMP_VY
                self.vx = -self.sliding_wall * WALL_JUMP_VX
                self.facing = -self.sliding_wall
                did = True
            elif self.double_jumps > 0:
                self.vy = PLAYER_JUMP_V
                self.double_jumps -= 1
                did = True
            if did:
                self.jump_buffer = 0
                self.on_ground = False

        if not self.dashing:
            self.vy = min(TERMINAL_VY, self.vy + GRAVITY)
        else:
            self.dashing -= 1

        speed_bonus = self.speed_potion_bonus if self.speed_potion_timer > 0 else 0.0
        cd_step = 1.0 + speed_bonus
        if self.dash_cd > 0:
            self.dash_cd = max(0.0, self.dash_cd - cd_step)
        if self.attack_cd > 0:
            self.attack_cd = max(0.0, self.attack_cd - cd_step)
        # per-skill cooldowns
        if self.skill_cd1 > 0: self.skill_cd1 = max(0.0, self.skill_cd1 - cd_step)
        if self.skill_cd2 > 0: self.skill_cd2 = max(0.0, self.skill_cd2 - cd_step)
        if self.skill_cd3 > 0: self.skill_cd3 = max(0.0, self.skill_cd3 - cd_step)
        if self.combo_t > 0:
            self.combo_t -= 1
        else:
            self.combo = 0
        if self.inv > 0:
            self.inv -= 1
            self.iframes_flash = not self.iframes_flash
        else:
            self.iframes_flash = False

        # parry timer
        if self.parrying > 0:
            self.parrying -= 1
        # Knight shield/power timers
        if self.shield_timer > 0:
            self.shield_timer -= 1
            if self.shield_timer == 0:
                self.shield_hits = 0
        if self.power_timer > 0:
            self.power_timer -= 1
            if self.power_timer == 0:
                self.atk_bonus = 0
                self.lifesteal = 0
        # Ranger timers
        if self.triple_timer > 0:
            self.triple_timer -= 1
        if self.speed_timer > 0:
            self.speed_timer -= 1

        # stamina regen cooldown timer decrement
        if getattr(self, '_stamina_cooldown', 0) > 0:
            self._stamina_cooldown -= 1

        # teleport cooldown decrement
        if getattr(self, '_teleport_cooldown', 0) > 0:
            self._teleport_cooldown -= 1

        # regenerate stamina & mana when not dashing and cooldown expired
        if hasattr(self, 'stamina') and not self.dashing and self._stamina_cooldown == 0:
            self.stamina = min(self.max_stamina, self.stamina + self._stamina_regen)
        if hasattr(self, 'mana'):
            self.mana = min(self.max_mana, self.mana + self._mana_regen)

        if self.speed_potion_timer > 0:
            self.speed_potion_timer -= 1
            if self.speed_potion_timer <= 0:
                self.speed_potion_timer = 0
                self.speed_potion_bonus = 0.0

        self.move_and_collide(level)

    def move_and_collide(self, level):
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vx > 0:
                    self.rect.right = s.left
                elif self.vx < 0:
                    self.rect.left = s.right
                self.vx = 0

        self.was_on_ground = self.on_ground
        self.on_ground = False
        self.rect.y += int(self.vy)
        for s in level.solids:
            if self.rect.colliderect(s):
                if self.vy > 0:
                    self.rect.bottom = s.top
                    self.on_ground = True
                elif self.vy < 0:
                    self.rect.top = s.bottom
                self.vy = 0

    def damage(self, amount, knock=(0,0)):
        # respect god mode first
        if getattr(self, 'god', False):
            return
        # Knight shield absorbs up to 2 hits while active
        if getattr(self, 'shield_timer', 0) > 0 and getattr(self, 'shield_hits', 0) > 0:
            self.shield_hits -= 1
            floating.append(DamageNumber(self.rect.centerx, self.rect.top-8, "BLOCK", CYAN))
            return
        if self.inv > 0:
            return
        self.hp -= amount
        self.inv = INVINCIBLE_FRAMES
        # start blinking timer for visible feedback during i-frames
        self._blink_t = IFRAME_BLINK_INTERVAL
        self.iframes_flash = True
        self.vx += knock[0]
        self.vy += knock[1]
        floating.append(DamageNumber(self.rect.centerx, self.rect.top-8, f"-{amount}", RED))
        if self.hp <= 0:
            self.hp = 0
            self.dead = True
            floating.append(DamageNumber(self.rect.centerx, self.rect.centery, "KO", CYAN))

    def draw(self, surf, camera):
        col = ACCENT if not self.iframes_flash else (ACCENT[0], ACCENT[1], 80)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=4)

class Bug:
    def __init__(self, x, ground_y):
        self.rect = pygame.Rect(x-14, ground_y-22, 28, 22)
        self.vx = random.choice([-1,1]) * 1.6
        self.hp = 30
        self.alive = True
        self.aggro = 200
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
        # --- Smart AI ---
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        dist_x = abs(ppos[0] - epos[0])
        dist_y = abs(ppos[1] - epos[1])
        in_aggro = (dist_x + dist_y) < self.aggro
        has_los = los_clear(level, epos, ppos)
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        if in_aggro and has_los:
            self.state = 'pursue'
            self.last_seen = ppos
            self.target = ppos
        elif in_aggro:
            # lost LOS but aggroed -> search
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
        self.aggro = 400
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
        # Very simple AI: slowly move toward player when in range
        dx = player.rect.centerx - self.rect.centerx
        # compute LOS for drawing/debug
        epos = (self.rect.centerx, self.rect.centery)
        ppos = (player.rect.centerx, player.rect.centery)
        has_los = los_clear(level, epos, ppos)
        self._has_los = has_los
        self._los_point = ppos
        if abs(dx) < self.aggro:
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
        self.aggro = 220
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
        has_los = los_clear(level, epos, ppos)
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        dx = ppos[0] - epos[0]
        dist = abs(dx) + abs(ppos[1]-epos[1])
        if self.cool>0:
            self.cool -= 1
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0:
                # perform dash diagonally toward player
                spd = 8.0
                dy = ppos[1] - epos[1]
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
            if has_los and dist< self.aggro and self.cool==0:
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
        self.aggro = 260
        self.cool = 0
        self.tele_t = 0
        self.tele_text = ''

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
            if self.tele_t==0 and has_los:
                # fire arrow
                dx = ppos[0]-epos[0]; dy = ppos[1]-epos[1]
                dist = max(1.0, (dx*dx+dy*dy)**0.5)
                nx, ny = dx/dist, dy/dist
                hb = pygame.Rect(0,0,10,6); hb.center = self.rect.center
                # Match player ranger's normal arrow speed and lifetime
                hitboxes.append(Hitbox(hb, 120, 1, self, dir_vec=(nx,ny), vx=nx*10.0, vy=ny*10.0))
                self.cool = 60
        elif has_los and self.cool==0:
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
        self.aggro = 260
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
        has_los = los_clear(level, epos, ppos)
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0 and has_los:
                dx = ppos[0]-epos[0]; dy = ppos[1]-epos[1]
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
        elif has_los and self.cool==0:
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
        self.aggro = 240
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
        has_los = los_clear(level, epos, ppos)
        # store last LOS check / target for debug drawing
        self._has_los = has_los
        self._los_point = ppos
        facing = 1 if ppos[0] > epos[0] else -1
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
        elif has_los and self.cool==0:
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
        # semi-invisible look: darker color
        col = (60,60,80) if self.ifr==0 else (40,40,60)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=5)


class Bee:
    """Hybrid shooter/dasher. Chooses randomly between actions."""
    def __init__(self, x, ground_y):
        self.rect = pygame.Rect(x-12, ground_y-20, 24, 20)
        self.vx = 0
        self.hp = 12
        self.alive = True
        self.ifr = 0
        self.aggro = 240
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
        import random
        if self.tele_t>0:
            self.tele_t -= 1
            if self.tele_t==0 and has_los:
                if self.action=='dash':
                    self.vx = 7 if ppos[0]>epos[0] else -7
                elif self.action=='shoot':
                    dx = ppos[0]-epos[0]; dy = ppos[1]-epos[1]
                    dist = max(1.0, (dx*dx+dy*dy)**0.5)
                    nx, ny = dx/dist, dy/dist
                    hb = pygame.Rect(0,0,10,6); hb.center = self.rect.center
                    hitboxes.append(Hitbox(hb, 120, 1, self, dir_vec=(nx,ny), vx=nx*7.5, vy=ny*7.5))
                self.cool = 50
        elif has_los and self.cool==0:
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
        col = (140, 140, 160) if self.ifr==0 else (100, 100, 120)
        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=7)
        if getattr(self, 'tele_t', 0) > 0 and getattr(self, 'tele_text',''):
            from utils import draw_text
            draw_text(surf, self.tele_text, camera.to_screen((self.rect.centerx-6, self.rect.top-12)), (255,120,90), size=22, bold=True)
