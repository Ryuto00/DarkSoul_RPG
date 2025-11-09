import math
import pygame

from config import (
    FPS, GRAVITY, TERMINAL_VY, PLAYER_SPEED, PLAYER_AIR_SPEED, PLAYER_JUMP_V,
    PLAYER_SMALL_JUMP_CUT, COYOTE_FRAMES, JUMP_BUFFER_FRAMES,
    DASH_SPEED, DASH_TIME, DASH_COOLDOWN, MOBILITY_COOLDOWN_FRAMES, INVINCIBLE_FRAMES,
    DOUBLE_JUMPS,
    ATTACK_COOLDOWN, ATTACK_LIFETIME, COMBO_RESET, SWORD_DAMAGE,
    POGO_BOUNCE_VY, ACCENT, GREEN, CYAN, RED, WHITE, IFRAME_BLINK_INTERVAL,
    # NEW: Physics-based wall jump parameters
    WALL_SLIDE_SPEED, WALL_SLIDE_GRAVITY_SCALE, WALL_JUMP_H_ACCEL, WALL_JUMP_H_MAX_SPEED,
    WALL_JUMP_V_SPEED, WALL_JUMP_GRAVITY_SCALE, WALL_JUMP_COYOTE_TIME, WALL_JUMP_BUFFER_TIME,
    WALL_JUMP_COOLDOWN, WALL_REATTACH_TIME, WALL_LEAVE_H_BOOST, WALL_CONTROL_MULTIPLIER,
    WALL_STICK_FRAMES,
    # Air control parameters
    AIR_ACCEL, AIR_FRICTION, MAX_AIR_SPEED
)
from .entity_common import Hitbox, DamageNumber, hitboxes, floating

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
        # NEW Wall jump system - cleaner physics-based approach
        self.on_left_wall = False
        self.on_right_wall = False
        self.wall_sliding = False
        self.wall_jump_cooldown = 0
        self.wall_jump_coyote_timer = 0  # Frames after leaving wall you can still jump
        self.wall_jump_buffer_timer = 0  # Remember jump input when touching wall
        self.wall_jump_state = None  # None, 'jumping', 'sliding', 'falling'
        self.wall_jump_direction = 0  # 1 for right, -1 for left
        self.wall_reattach_timer = 0  # Prevent immediate reattachment
        self.double_jumps = DOUBLE_JUMPS
        self.can_dash = True
        self.dashing = 0
        self.dash_cd = 0
        # Shared mobility cooldown: any jump/double/wall/dash triggers this,
        # and while > 0 all those actions are locked.
        self.mobility_cd = 0
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
        elif cls == 'Assassin': # Assuming Assassin is a player class
            self.max_hp = 6
            self.hp = 6
            self.player_speed = 5.0
            self.player_air_speed = 4.5
            self.attack_damage = 5
            self.max_stamina = 10.0
            self.stamina = 10.0
            self.max_mana = 60.0
            self.mana = 60.0
            self._stamina_regen = 0.15
            self._mana_regen = 6.0 / FPS
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
        # no-clip mode (for debugging)
        self.no_clip = False
        # floating mode variables
        self.floating_mode = False
        self.last_space_time = 0
        self.space_double_tap_window = 20  # frames for double-tap detection
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
        self.jump_boost_timer = 0
        self.jump_force_multiplier = 1.0
        self.extra_jump_charges = 0
        self.stamina_boost_timer = 0
        self.stamina_buff_mult = 1.0
        self._base_stats = {
            'max_hp': float(self.max_hp),
            'attack_damage': float(self.attack_damage),
            'player_speed': float(self.player_speed),
            'player_air_speed': float(self.player_air_speed),
            'max_mana': float(getattr(self, 'max_mana', 0.0)),
            'max_stamina': float(getattr(self, 'max_stamina', 0.0)),
            'stamina_regen': float(getattr(self, '_stamina_regen', 0.0)),
            'mana_regen': float(getattr(self, '_mana_regen', 0.0)),
        }
        # Money/currency system
        self.money = 0

    def _find_safe_landing_spot(self, level):
        """Find a safe landing spot when exiting floating mode. Places player on top of nearest platform with at least 2 tiles of headroom."""
        from config import TILE

        # Get level bounds
        level_width = getattr(level, 'w', 10000)
        level_height = getattr(level, 'h', 10000)

        # Search for nearby ground/platform
        best_spot = None
        min_distance = float('inf')

        # Check solids (platforms, walls, floors)
        for solid in level.solids:
            # Check if there's at least 2 tiles (64 pixels) of space above this solid
            test_rect = pygame.Rect(solid.left, solid.top - 64, solid.width, 64)

            # Check if this space is free from collisions
            can_stand_here = True
            for other_solid in level.solids:
                if other_solid != solid and test_rect.colliderect(other_solid):
                    can_stand_here = False
                    break

            if can_stand_here:
                # Check if this spot is within level bounds
                landing_x = self.rect.centerx
                landing_y = solid.top - self.rect.height

                # Ensure landing position is within bounds
                if landing_x < 0:
                    landing_x = self.rect.width // 2
                elif landing_x > level_width - self.rect.width:
                    landing_x = level_width - self.rect.width // 2

                if landing_y < 0:
                    landing_y = 0
                elif landing_y > level_height - self.rect.height:
                    landing_y = level_height - self.rect.height

                # Calculate distance from current position
                distance = abs(landing_x - self.rect.centerx) + abs(landing_y - self.rect.centery)

                # Prefer closer spots
                if distance < min_distance:
                    min_distance = distance
                    best_spot = (landing_x, landing_y)

        # If we found a good spot, move the player there
        if best_spot:
            self.rect.centerx = best_spot[0]
            self.rect.y = best_spot[1]
            self.vx = 0
            self.vy = 0

            # Show notification
            from entity_common import floating, DamageNumber
            floating.append(DamageNumber(
                self.rect.centerx,
                self.rect.top - 12,
                "Landed!",
                (100, 255, 100)
            ))
        else:
            # If no safe spot found, try to find any valid position within bounds
            # Place player at bottom center of level as fallback
            fallback_x = max(self.rect.width, min(level_width - self.rect.width, level_width // 2))
            fallback_y = max(0, level_height - self.rect.height - 100)  # 100 pixels from bottom

            self.rect.centerx = fallback_x
            self.rect.y = fallback_y
            self.vx = 0
            self.vy = 0

            # Show notification
            from entity_common import floating, DamageNumber
            floating.append(DamageNumber(
                self.rect.centerx,
                self.rect.top - 12,
                "Safe spot created!",
                (255, 255, 100)
            ))
    def input(self, level, camera):
        if self.dead:
            return
        keys = pygame.key.get_pressed()
        stunned = self.stunned > 0
        if stunned:
            self.stunned -= 1
        move = 0
        if not stunned:
            if keys[pygame.K_a]:
                move -= 1
            if keys[pygame.K_d]:
                move += 1

        # Track if we just exited floating mode
        just_exited_floating = getattr(self, '_was_floating_mode', False) and not getattr(self, 'floating_mode', False)
        # Update floating mode tracking
        self._was_floating_mode = getattr(self, 'floating_mode', False)

        # Reset momentum when exiting floating mode
        if just_exited_floating:
            self.vx = 0
            self.vy = 0

        # Horizontal movement with momentum-preserving air control
        if not self.dashing:
            # In no-clip mode, use enhanced speed for easier movement
            if getattr(self, 'no_clip', False):
                if getattr(self, 'floating_mode', False):
                    # In floating mode: no momentum, direct control with instant stop
                    speed = self.player_speed * 2.0  # Even faster in floating mode
                    self.vx = move * speed
                    # No momentum - instant stop when no input
                    if move == 0:
                        self.vx = 0
                else:
                    # Normal no-clip mode with some momentum
                    speed = self.player_speed * 1.5  # 50% faster movement in no-clip
                    # Direct control for no-clip mode
                    self.vx = move * speed
                    # Apply damping when no input for smooth floating
                    if move == 0:
                        self.vx *= 0.9
            else:
                base_speed = self.player_speed if self.on_ground else self.player_air_speed
                bonus = 1.0 if (self.cls == 'Ranger' and getattr(self, 'speed_timer', 0) > 0) else 0.0
                speed = base_speed + bonus

                if self.on_ground:
                    # Instant, grounded control
                    self.vx = move * speed
                else:
                    # NEW: Simplified air control with wall jump enhancements
                    if self.wall_jump_state == 'jumping':
                        # Enhanced control during wall jump ascent
                        effective_air_accel = AIR_ACCEL * WALL_CONTROL_MULTIPLIER
                    else:
                        effective_air_accel = AIR_ACCEL

                    if move != 0:
                        target_vx = move * MAX_AIR_SPEED
                        if self.vx < target_vx:
                            self.vx = min(self.vx + effective_air_accel, target_vx)
                        elif self.vx > target_vx:
                            self.vx = max(self.vx - effective_air_accel, target_vx)
                    else:
                        # No input: air friction is handled in _apply_physics()
                        pass

            # Update facing only when there is horizontal input
            if move != 0:
                self.facing = move

      
        # Jump input buffering - allow jumping when in god mode with floating mode OFF
        in_no_clip_but_not_floating = getattr(self, 'no_clip', False) and not getattr(self, 'floating_mode', False)
        if not getattr(self, 'no_clip', False) or in_no_clip_but_not_floating:
            if not stunned and self.mobility_cd == 0 and (keys[pygame.K_SPACE] or keys[pygame.K_k]):
                self.jump_buffer = JUMP_BUFFER_FRAMES
            else:
                if self.vy < 0:
                    if not (keys[pygame.K_SPACE] or keys[pygame.K_k]):
                        self.vy *= PLAYER_SMALL_JUMP_CUT

        # NEW: Simplified dash - only if mobility cooldown is free
        free_dash_available = False
        if (
            not stunned
            and (self.mobility_cd == 0 or free_dash_available)
            and (keys[pygame.K_LSHIFT] or keys[pygame.K_j])
            and (self.can_dash or free_dash_available)
            and (self.dash_cd == 0 or free_dash_available)
            and not self.dashing
        ):
            self.start_dash(free_action=free_dash_available)

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

    def start_dash(self, free_action=False):
        # require some stamina to dash (unless it's a free action)
        if not free_action:
            dash_cost = 2.0
            if getattr(self, 'stamina', 0) <= 0:
                return
            # consume stamina if available
            if hasattr(self, 'stamina'):
                self.stamina = max(0.0, self.stamina - dash_cost)
            # start stamina regen cooldown (1 second)
            self._stamina_cooldown = int(FPS)
            self.can_dash = False
            self.dash_cd = DASH_COOLDOWN
            # trigger shared mobility cooldown
            self.mobility_cd = MOBILITY_COOLDOWN_FRAMES
        else:
            # Dash cancels wall jump state
            self.wall_jump_state = None
        
        # grant short invincibility when dash starts (0.25s)
        self.inv = int(0.25 * FPS)
        self.dashing = DASH_TIME
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

        # Tick shared mobility cooldown
        if self.mobility_cd > 0:
            self.mobility_cd -= 1

        if self.on_ground:
            self.coyote = COYOTE_FRAMES
            self.double_jumps = DOUBLE_JUMPS + int(getattr(self, 'extra_jump_charges', 0))
            self.can_dash = True if self.dash_cd == 0 else self.can_dash
            # Reset wall jump state when touching ground
            if self.wall_jump_state is not None:
                self.wall_jump_state = None
                self.wall_jump_direction = 0
        else:
            self.coyote = max(0, self.coyote-1)

        if self.jump_buffer > 0:
            self.jump_buffer -= 1

        # NEW: Update wall jump system timers
        if self.wall_jump_cooldown > 0:
            self.wall_jump_cooldown -= 1

        if self.wall_jump_coyote_timer > 0:
            self.wall_jump_coyote_timer -= 1

        if self.wall_jump_buffer_timer > 0:
            self.wall_jump_buffer_timer -= 1

        if self.wall_reattach_timer > 0:
            self.wall_reattach_timer -= 1

        # NEW: Simplified wall sliding detection
        self.wall_sliding = False
        if not self.on_ground and self.wall_jump_cooldown == 0:
            if self.on_left_wall or self.on_right_wall:
                # Start sliding if touching wall
                self.wall_sliding = True
                self.wall_jump_coyote_timer = WALL_JUMP_COYOTE_TIME
                # Reset jump buffer when touching wall
                if self.jump_buffer > 0 and self.wall_jump_buffer_timer == 0:
                    self.wall_jump_buffer_timer = WALL_JUMP_BUFFER_TIME

        # Only allow resolving buffered jump if mobility cooldown is free
        want_jump = self.jump_buffer > 0 and self.mobility_cd == 0
        jump_mult = getattr(self, 'jump_force_multiplier', 1.0)
        if want_jump:
            did = False

            # NEW: Physics-based wall jump system
            if self.wall_sliding or self.wall_jump_coyote_timer > 0:
                # Wall jump with acceleration-based physics
                if self.wall_jump_cooldown == 0:
                    # Determine jump direction based on wall
                    if self.on_left_wall:
                        self.wall_jump_direction = 1  # Jump right
                        # Gentle nudge away from wall
                        self.rect.x += 1
                    elif self.on_right_wall:
                        self.wall_jump_direction = -1  # Jump left
                        # Gentle nudge away from wall
                        self.rect.x -= 1
                    else:
                        # Use coyote direction if just left wall
                        self.wall_jump_direction = self.wall_jump_direction if self.wall_jump_direction != 0 else (-1 if self.facing > 0 else 1)

                    # Apply gentle initial horizontal boost
                    self.vx = WALL_LEAVE_H_BOOST * self.wall_jump_direction
                    # Set vertical velocity
                    self.vy = WALL_JUMP_V_SPEED * jump_mult

                    # Set state for physics update
                    self.wall_jump_state = 'jumping'
                    self.wall_jump_cooldown = WALL_JUMP_COOLDOWN
                    self.wall_reattach_timer = WALL_REATTACH_TIME
                    self.wall_sliding = False
                    self.on_left_wall = False
                    self.on_right_wall = False
                    did = True
                elif self.double_jumps > 0:
                    # Normal double jump if wall jump on cooldown
                    self.vy = PLAYER_JUMP_V * jump_mult
                    self.double_jumps -= 1
                    did = True
            elif self.on_ground or self.coyote > 0:
                # Normal ground jump
                self.vy = PLAYER_JUMP_V * jump_mult
                did = True
            elif self.double_jumps > 0:
                # Air double jump
                self.vy = PLAYER_JUMP_V * jump_mult
                self.double_jumps -= 1
                did = True

            if did:
                self.jump_buffer = 0
                self.on_ground = False
                # Any successful jump triggers shared mobility cooldown
                self.mobility_cd = MOBILITY_COOLDOWN_FRAMES

        # Apply gravity or wall slide physics
        # NEW: Simplified physics system
        if getattr(self, 'no_clip', False):
            keys = pygame.key.get_pressed()
            if getattr(self, 'floating_mode', False):
                # Floating mode with direct control
                if self.stunned <= 0:
                    if keys[pygame.K_w]:
                        self.vy = -8
                    elif keys[pygame.K_s]:
                        self.vy = 8
                    else:
                        self.vy = 0
            else:
                # No-clip mode with physics
                if not self.dashing:
                    self._apply_physics()
                else:
                    self.dashing -= 1
        elif not self.dashing:
            self._apply_physics()
        else:
            self.dashing -= 1
            if self.dashing == 0 and not self.on_ground:
                self.vy = GRAVITY

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
        if self.jump_boost_timer > 0:
            self.jump_boost_timer -= 1
            if self.jump_boost_timer <= 0:
                self.jump_boost_timer = 0
                self.jump_force_multiplier = 1.0
                self.extra_jump_charges = 0
        if self.stamina_boost_timer > 0:
            self.stamina_boost_timer -= 1
            if self.stamina_boost_timer <= 0:
                self.stamina_boost_timer = 0
                self.stamina_buff_mult = 1.0
        
        # Lucky charm timer
        if getattr(self, 'lucky_charm_timer', 0) > 0:
            self.lucky_charm_timer -= 1
            if self.lucky_charm_timer <= 0:
                self.lucky_charm_timer = 0
        
        # Phoenix feather revival check
        if getattr(self, 'phoenix_feather_active', False) and getattr(self, 'dead', False):
            # Revive player with 50% HP
            self.dead = False
            self.hp = max(1, self.max_hp // 2)
            self.phoenix_feather_active = False
            floating.append(DamageNumber(self.rect.centerx, self.rect.top - 12, "PHOENIX REVIVE!", (255, 150, 50)))

        self.move_and_collide(level)

    def move_and_collide(self, level):
        # Reset wall detection
        prev_left_wall = self.on_left_wall
        prev_right_wall = self.on_right_wall
        self.on_left_wall = False
        self.on_right_wall = False

        # Special handling for no-clip mode
        if getattr(self, 'no_clip', False):
            # If floating mode is ON, just move without any collision
            if getattr(self, 'floating_mode', False):
                self.rect.x += int(self.vx)
                self.rect.y += int(self.vy)
                # In floating mode, always treat as if in air
                self.on_ground = False
                self.was_on_ground = False
                return
            else:
                # In normal no-clip mode (floating OFF), move without collision but still detect walls for wall jumps
                self.rect.x += int(self.vx)
                self.rect.y += int(self.vy)

                # Reset wall detection
                prev_left_wall = self.on_left_wall
                prev_right_wall = self.on_right_wall
                self.on_left_wall = False
                self.on_right_wall = False

                # Check for wall proximity even in no-clip mode (for wall jumps)
                expanded_rect = self.rect.inflate(2, 0)  # Expand horizontally by 1 pixel each side
                for s in level.solids:
                    if expanded_rect.colliderect(s):
                        # Determine which side the wall is on
                        if self.rect.centerx < s.centerx:  # Wall is to the right
                            if abs(self.rect.right - s.left) <= 2:  # Within 2 pixels
                                self.on_right_wall = True
                        else:  # Wall is to the left
                            if abs(self.rect.left - s.right) <= 2:  # Within 2 pixels
                                self.on_left_wall = True

                # Simulate ground detection for jumping purposes
                # Check if there's ground below the player
                ground_check = self.rect.copy()
                ground_check.y += 2
                self.was_on_ground = self.on_ground
                self.on_ground = any(ground_check.colliderect(s) for s in level.solids)

                return

        # Check if we just exited no-clip mode
        if getattr(self, '_was_no_clip', False) and not getattr(self, 'no_clip', False):
            # Reset horizontal momentum when exiting no-clip to prevent slow movement
            self.vx = 0
            # Apply slight downward momentum when exiting no-clip
            self.vy = max(self.vy, 1)  # Reduced downward momentum for better feel

            # Check if player is stuck in a wall
            player_stuck = False
            for s in level.solids:
                if self.rect.colliderect(s):
                    player_stuck = True
                    break

            if player_stuck:
                # Find nearest safe position
                safe_pos = self._find_safe_position(level)
                if safe_pos:
                    self.rect.x, self.rect.y = safe_pos
                    # Reset velocity to ensure clean movement
                    self.vx = 0
                    self.vy = 1  # Gentle downward momentum

        # Update tracking for no-clip state changes
        self._was_no_clip = getattr(self, 'no_clip', False)

        # Horizontal movement and collision
        self.rect.x += int(self.vx)
        for s in level.solids:
            if self.rect.colliderect(s):
                # NEW: Prevent wall reattachment if timer is active
                can_attach = self.wall_reattach_timer == 0
                if self.vx > 0:
                    self.rect.right = s.left
                    if can_attach:
                        self.on_right_wall = True
                elif self.vx < 0:
                    self.rect.left = s.right
                    if can_attach:
                        self.on_left_wall = True
                self.vx = 0

        # Additional wall check - check if player is touching wall even without horizontal movement
        # This helps maintain wall contact during sliding
        if not self.on_left_wall and not self.on_right_wall and self.wall_reattach_timer == 0:
            # Check a slightly expanded rect to detect wall proximity
            expanded_rect = self.rect.inflate(2, 0)  # Expand horizontally by 1 pixel each side
            for s in level.solids:
                if expanded_rect.colliderect(s):
                    # Determine which side the wall is on
                    if self.rect.centerx < s.centerx:  # Wall is to the right
                        if abs(self.rect.right - s.left) <= 2:  # Within 2 pixels
                            self.on_right_wall = True
                    else:  # Wall is to the left
                        if abs(self.rect.left - s.right) <= 2:  # Within 2 pixels
                            self.on_left_wall = True


        # Vertical movement and collision
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
                    # Check if hitting ceiling while moving up into a wall
                    if self.on_left_wall or self.on_right_wall:
                        # Maintain wall contact when hitting ceiling
                        pass
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
        # Change color for visual feedback
        if getattr(self, 'no_clip', False):
            if getattr(self, 'floating_mode', False):
                # Cyan color for floating mode
                col = (100, 255, 200) if not self.iframes_flash else (100, 255, 80)
            else:
                # Purple/magenta color for regular no-clip mode
                col = (200, 100, 255) if not self.iframes_flash else (200, 100, 80)
        elif self.wall_sliding:
            col = (100, 150, 255) if not self.iframes_flash else (100, 150, 80)  # Blue tint when sliding
        else:
            col = ACCENT if not self.iframes_flash else (ACCENT[0], ACCENT[1], 80)

        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=4)

    def _find_safe_position(self, level):
        """Find the nearest safe position where the player won't be stuck in a wall"""
        from config import TILE

        # Start searching from current position, expanding outward
        search_radius = 1
        max_radius = 10

        while search_radius <= max_radius:
            # Check positions in a square pattern around the player
            for dx in range(-search_radius, search_radius + 1):
                for dy in range(-search_radius, search_radius + 1):
                    if dx == 0 and dy == 0:
                        continue

                    test_rect = self.rect.copy()
                    test_rect.x += dx * TILE // 4
                    test_rect.y += dy * TILE // 4

                    # Check if this position is safe (not inside any solid)
                    is_safe = True
                    for solid in level.solids:
                        if test_rect.colliderect(solid):
                            is_safe = False
                            break

                    if is_safe:
                        # Also check if we're within level bounds
                        if hasattr(level, 'w') and hasattr(level, 'h'):
                            level_w = level.w * TILE if isinstance(level.w, int) else level.w
                            level_h = level.h * TILE if isinstance(level.h, int) else level.h
                            if (test_rect.left >= 0 and test_rect.right <= level_w and
                                test_rect.top >= 0 and test_rect.bottom <= level_h):
                                return (test_rect.x, test_rect.y)
                        else:
                            return (test_rect.x, test_rect.y)

            search_radius += 1

        # If no safe position found, return None
        return None

    def _apply_physics(self):
        """NEW: Physics-based wall jump and gravity system"""

        # NEW: Handle wall jump acceleration and state
        if self.wall_jump_state == 'jumping':
            # Apply horizontal acceleration away from wall
            if self.wall_jump_direction != 0:
                # Accelerate in the jump direction
                self.vx += WALL_JUMP_H_ACCEL * self.wall_jump_direction
                # Clamp to maximum horizontal speed
                self.vx = max(-WALL_JUMP_H_MAX_SPEED, min(WALL_JUMP_H_MAX_SPEED, self.vx))

            # Apply reduced gravity during ascent phase
            if self.vy < 0:
                self.vy += GRAVITY * WALL_JUMP_GRAVITY_SCALE
                # Check if we should transition to falling
                if self.vy >= 0:
                    self.wall_jump_state = 'falling'
            else:
                self.wall_jump_state = 'falling'

        # Apply wall sliding physics
        elif self.wall_sliding:
            # Heavy gravity but with speed cap for controlled descent
            self.vy = min(WALL_SLIDE_SPEED, self.vy + GRAVITY * WALL_SLIDE_GRAVITY_SCALE)
            # Reset wall jump state when sliding
            self.wall_jump_state = None

        # Normal gravity
        else:
            self.vy = min(TERMINAL_VY, self.vy + GRAVITY)

        # Apply air friction for better control
        if not self.on_ground:
            friction = AIR_FRICTION
            # Enhanced control during wall jump
            if self.wall_jump_state in ['jumping', 'falling']:
                if self.wall_reattach_timer <= 0:
                    friction *= (1.0 - (WALL_CONTROL_MULTIPLIER - 1.0) * 0.1)  # Slightly better air control

            self.vx *= friction
