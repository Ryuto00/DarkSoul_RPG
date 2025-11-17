import math
import pygame
import logging

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
from .components.combat_component import CombatComponent
from .animation_system import AnimationManager, AnimationState

logger = logging.getLogger(__name__)

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
        self.jump_key_pressed = False
        self.on_left_wall = False
        self.on_right_wall = False
        self.wall_sliding = False
        self._left_wall_contact_frames = 0
        self._right_wall_contact_frames = 0
        self.wall_jump_cooldown = 0
        self.wall_jump_coyote_timer = 0
        self.wall_jump_buffer_timer = 0
        self.wall_jump_state = None
        self.wall_jump_direction = 0
        self.wall_reattach_timer = 0
        self.double_jumps = DOUBLE_JUMPS
        self.can_dash = True
        self.dash_charges = 1  # Base dash charges
        self.dash_charges_max = 1  # Maximum dash charges
        self.dashing = 0
        self.dash_cd = 0
        self.mobility_cd = 0
        self.dash_key_pressed = False  # Track dash key state to prevent holding

        self.cls = cls
        combat_config = {}

        if cls == 'Knight':
            self.player_speed = 3.6
            self.player_air_speed = 3.0
            self.attack_damage = 4
            self.max_stamina = 8.0
            self.stamina = 8.0
            self.max_mana = 50.0
            self.mana = 50.0
            self._stamina_regen = 0.08
            self._mana_regen = 5.0 / FPS
            combat_config = {
                'max_hp': 7,
                'default_ifr': INVINCIBLE_FRAMES,
                'god_mode': False,
                'shield_hits_max': 2,
                'shield_duration': 10 * FPS,
                'parry_duration': 12,
                'power_buff_lifesteal': 1,
                'power_buff_duration': 10 * FPS,
                'power_buff_atk_bonus': 2,
            }
        elif cls == 'Ranger':
            self.player_speed = 4.6
            self.player_air_speed = 4.0
            self.attack_damage = 3
            self.max_stamina = 12.0
            self.stamina = 12.0
            self.max_mana = 70.0
            self.mana = 70.0
            self._stamina_regen = 0.18
            self._mana_regen = 5.0 / FPS
            combat_config = {
                'max_hp': 5,
                'default_ifr': INVINCIBLE_FRAMES,
            }
        elif cls == 'Wizard':
            self.player_speed = 3.8
            self.player_air_speed = 3.2
            self.attack_damage = 1
            self.max_stamina = 4.0
            self.stamina = 4.0
            self.max_mana = 100.0
            self.mana = 100.0
            self._stamina_regen = 0.05
            self._mana_regen = 8.0 / FPS
            combat_config = {
                'max_hp': 4,
                'default_ifr': INVINCIBLE_FRAMES,
            }
        elif cls == 'Assassin':
            self.player_speed = 5.0
            self.player_air_speed = 4.5
            self.attack_damage = 5
            self.max_stamina = 10.0
            self.stamina = 10.0
            self.max_mana = 60.0
            self.mana = 60.0
            self._stamina_regen = 0.15
            self._mana_regen = 6.0 / FPS
            combat_config = {
                'max_hp': 6,
                'default_ifr': INVINCIBLE_FRAMES,
            }
        else: # Fallback
            self.player_speed = PLAYER_SPEED
            self.player_air_speed = PLAYER_AIR_SPEED
            self.attack_damage = SWORD_DAMAGE
            combat_config = {
                'max_hp': 5,
                'default_ifr': INVINCIBLE_FRAMES,
            }

        self.combat = CombatComponent(self, combat_config)
        self.alive = True # Unified death state

        self.combo = 0
        self.combo_t = 0
        self.attack_cd = 0
        self.iframes_flash = False
        self._stamina_cooldown = 0
        self._teleport_cooldown = 0
        self._teleport_distance = 160
        self._teleport_mana_cost = 20.0
        self.no_clip = False
        self.floating_mode = False
        self.last_space_time = 0
        self.space_double_tap_window = 20
        self.skill_cd1 = 0
        self.skill_cd2 = 0
        self.skill_cd3 = 0
        self.skill_cd1_max = 1
        self.skill_cd2_max = 1
        self.skill_cd3_max = 1
        self.charging = False
        self.charge_time = 0
        self.charge_threshold = int(0.5 * FPS)
        self._prev_lmb = False
        # Wizard skill selection system (for select-then-cast)
        self.selected_skill = None  # None, 'fireball', 'coldfeet', or 'magic_missile'
        # Animation smoothing
        self._anim_grounded_buffer = 0
        self.triple_timer = 0
        self.sniper_ready = False
        self.sniper_mult = 2.5
        self.speed_timer = 0
        self._blink_t = 0
        self.stunned = 0
        self.speed_potion_timer = 0
        self.speed_potion_bonus = 0.0
        self.jump_boost_timer = 0
        self.jump_force_multiplier = 1.0
        self.extra_jump_charges = 0
        self.stamina_boost_timer = 0
        self.stamina_buff_mult = 1.0
        self._base_stats = {
            'max_hp': float(self.combat.max_hp),
            'attack_damage': float(self.attack_damage),
            'player_speed': float(self.player_speed),
            'player_air_speed': float(self.player_air_speed),
            'max_mana': float(getattr(self, 'max_mana', 0.0)),
            'max_stamina': float(getattr(self, 'max_stamina', 0.0)),
            'stamina_regen': float(getattr(self, '_stamina_regen', 0.0)),
            'mana_regen': float(getattr(self, '_mana_regen', 0.0)),
            # Lifesteal base values (percentages)
            'lifesteal_pct': float(getattr(self.combat, 'lifesteal_pct', 0.0)),
            'spell_lifesteal': float(getattr(self.combat, 'spell_lifesteal_pct', getattr(self.combat, 'spell_lifesteal', 0.0))),
        }
        self.money = 0

        # Initialize animation system (call after all properties set)
        self.anim_manager = None
        self._setup_animations(cls)

    @property
    def visual_center(self):
        """Return the visual center point for arrow spawning (chest height for Ranger)"""
        if self.cls == 'Ranger':
            # For Ranger, offset upward to chest/bow height (approx 40% up from collision center)
            # Sprite is 64px tall, collision is 30px tall, so offset by ~12 pixels upward
            return (self.rect.centerx, self.rect.centery - 20)
        return self.rect.center
    
    def _setup_animations(self, cls):
        """Setup animation system for any player class using universal AnimationManager"""
        if cls not in ('Knight', 'Ranger', 'Wizard'):
            return  # No animations for other classes yet
        
        try:
            self.anim_manager = AnimationManager(self, default_state=AnimationState.IDLE)
            
            if cls == 'Knight':
                self._load_knight_animations()
                # Knight sprite offset: shift right 8px to center the visible character on collision box
                # (93px sprite width vs 18px collision box = ~37px overhang per side,
                #  but sprite has left padding, so shift right to align better)
                self.anim_manager.set_sprite_offset(0, 0)
            elif cls == 'Ranger':
                self._load_ranger_animations()
                self.anim_manager.set_sprite_offset(0, 0)
            elif cls == 'Wizard':
                self._load_wizard_animations()
                self.anim_manager.set_sprite_offset(0, 0)
                # Wizard wall slide sprite faces wrong direction, reverse it
                self.anim_manager.reverse_facing_states.add(AnimationState.WALL_SLIDE)
            logger.info(f"[Player] {cls} animations loaded successfully")
        except Exception as e:
            logger.exception(f"[Player] Failed to load {cls} animations: {e}")
            self.anim_manager = None
    
    def _load_knight_animations(self):
        """Load Knight animation frames into AnimationManager"""
        # Knight sprite size: 93x64 (preserves 64x44 original aspect ratio, matches Ranger height)
        sprite_size = (93, 64)
        
        # IDLE - Lowest priority, always available
        self.anim_manager.load_animation(
            AnimationState.IDLE,
            [f"assets/Player/Knight/idle/Warrior_Idle_{i}.png" for i in range(1, 7)],
            sprite_size=sprite_size,
            frame_duration=8,
            loop=True,
            priority=0
        )
        
        # RUN - Basic movement
        self.anim_manager.load_animation(
            AnimationState.RUN,
            [f"assets/Player/Knight/Run/Warrior_Run_{i}.png" for i in range(1, 9)],
            sprite_size=sprite_size,
            frame_duration=6,
            loop=True,
            priority=1
        )
        
        # JUMP - Moving upward
        self.anim_manager.load_animation(
            AnimationState.JUMP,
            [f"assets/Player/Knight/Jump/Warrior_Jump_{i}.png" for i in range(1, 4)],
            sprite_size=sprite_size,
            frame_duration=4,
            loop=False,
            priority=2
        )
        
        # FALL - Moving downward
        self.anim_manager.load_animation(
            AnimationState.FALL,
            [f"assets/Player/Knight/Fall/Warrior_Fall_{i}.png" for i in range(1, 4)],
            sprite_size=sprite_size,
            frame_duration=4,
            loop=False,
            priority=2
        )
        
        # WALL_SLIDE - On wall
        self.anim_manager.load_animation(
            AnimationState.WALL_SLIDE,
            [f"assets/Player/Knight/WallSlide/Warrior_WallSlide_{i}.png" for i in range(1, 4)],
            sprite_size=sprite_size,
            frame_duration=6,
            loop=True,
            priority=3
        )
        
        # DASH - High priority action
        self.anim_manager.load_animation(
            AnimationState.DASH,
            [f"assets/Player/Knight/Dash/Warrior_Dash_{i}.png" for i in range(1, 8)],
            sprite_size=sprite_size,
            frame_duration=2,
            loop=False,
            priority=4,
            next_state=AnimationState.IDLE
        )
        
        # ATTACK - Main attack animation (9 frames)
        self.anim_manager.load_animation(
            AnimationState.ATTACK,
            [f"assets/Player/Knight/Attack/Warrior_Attack_{i}.png" for i in range(4, 13)],
            sprite_size=sprite_size,
            frame_duration=2,
            loop=False,
            priority=5,
            next_state=AnimationState.IDLE
        )
        
        # Setup frame event: Spawn hitbox on frame 4 (mid-swing of 9-frame animation)
        self.anim_manager.set_attack_frame(AnimationState.ATTACK, 4, self._spawn_knight_attack_hitbox)
        
        # SKILL_1 - Dash Attack animation (10 frames) for Knight charge skill
        self.anim_manager.load_animation(
            AnimationState.SKILL_1,
            [f"assets/Player/Knight/Dash Attack/Warrior_Dash-Attack_{i}.png" for i in range(1, 11)],
            sprite_size=sprite_size,
            frame_duration=2,
            loop=False,
            priority=6,
            next_state=AnimationState.IDLE
        )
        
        # Setup frame event: Spawn dash attack hitbox on frame 3 (early in dash)
        self.anim_manager.set_attack_frame(AnimationState.SKILL_1, 3, self._spawn_knight_dash_attack_hitbox)

    def _load_ranger_animations(self):
        """
        Load Ranger animation frames into AnimationManager.
        
        Ranger Attack System (3-State Bow Animation):
        1. CHARGE: Progressive draw animation (4 frames) - plays while holding attack
        2. CHARGED: Hold at full draw (1 looping frame) - plays when charge_time >= threshold
        3. SHOOT: Release animation (2 frames) - plays on attack release, auto-transitions to IDLE
        
        The attack system uses self.charging flag and self.charge_time counter to track state.
        Animation priority ensures attack animations override movement during combat.
        """
        sprite_size = (42, 40)
        
        # IDLE - Lowest priority, always available
        self.anim_manager.load_animation(
            AnimationState.IDLE,
            [f"assets/Player/Ranger/idle/Idle-{i}.png" for i in range(1, 3)],
            sprite_size=sprite_size,
            frame_duration=12,
            loop=True,
            priority=0
        )
        
        # RUN - Basic movement
        self.anim_manager.load_animation(
            AnimationState.RUN,
            [f"assets/Player/Ranger/run/run-{i}.png" for i in range(1, 9)],
            sprite_size=sprite_size,
            frame_duration=5,
            loop=True,
            priority=1
        )
        
        # JUMP - Moving upward
        self.anim_manager.load_animation(
            AnimationState.JUMP,
            ["assets/Player/Ranger/jump.png"],
            sprite_size=sprite_size,
            frame_duration=1,
            loop=True,
            priority=2
        )
        
        # FALL - Moving downward
        self.anim_manager.load_animation(
            AnimationState.FALL,
            ["assets/Player/Ranger/fall.png"],
            sprite_size=sprite_size,
            frame_duration=1,
            loop=True,
            priority=2
        )
        
        # WALL_SLIDE - On wall
        self.anim_manager.load_animation(
            AnimationState.WALL_SLIDE,
            ["assets/Player/Ranger/climb.png"],
            sprite_size=sprite_size,
            frame_duration=1,
            loop=True,
            priority=3
        )
        
        # DASH - High priority action (but lower than shoot/charge so they can override)
        self.anim_manager.load_animation(
            AnimationState.DASH,
            [f"assets/Player/Ranger/dash/dash-{i}.png" for i in range(1, 4)],
            sprite_size=sprite_size,
            frame_duration=3,
            loop=False,
            priority=3,  # Same as wall slide
            next_state=AnimationState.IDLE
        )
        
        # === REUSABLE 3-STATE RANGER BOW ATTACK SYSTEM ===
        
        # CHARGE - Drawing bow (progressive 4-frame animation)
        # This animation plays while holding attack button, showing bow being drawn back
        # Auto-transitions to CHARGED when animation completes
        self.anim_manager.load_animation(
            AnimationState.CHARGE,
            [f"assets/Player/Ranger/attk-adjust/charge/na-{i}.png" for i in range(1, 5)],
            sprite_size=sprite_size,
            frame_duration=5,  # 5 frames per sprite = 20 frames total for full charge
            loop=False,  # Don't loop - transition to CHARGED
            priority=4,  # High priority to override movement
            next_state=AnimationState.CHARGED  # Auto-transition when complete
        )
        
        # CHARGED - Holding at full draw (looping hold pose)
        # This single frame loops while player holds attack at full charge
        # Stays active until player releases attack button
        self.anim_manager.load_animation(
            AnimationState.CHARGED,
            ["assets/Player/Ranger/attk-adjust/charged/na-5.png"],
            sprite_size=sprite_size,
            frame_duration=1,
            loop=True,  # Loop to hold this pose indefinitely
            priority=4  # Same priority as CHARGE
        )
        
        # SHOOT - Releasing arrow (2-frame release animation)
        # Plays when attack button is released, fires arrow projectile
        # Auto-transitions back to IDLE when complete
        self.anim_manager.load_animation(
            AnimationState.SHOOT,
            ["assets/Player/Ranger/attk-adjust/shoot/na-5.png", 
             "assets/Player/Ranger/attk-adjust/shoot/na-6.png"],
            sprite_size=sprite_size,
            frame_duration=4,  # 4 frames per sprite = 8 frames total
            loop=False,  # Don't loop - transition to IDLE
            priority=4,  # Same priority as charge states
            next_state=AnimationState.IDLE  # Return to idle after shooting
        )

    def _load_wizard_animations(self):
        """
        Load Wizard animation frames into AnimationManager.
        
        Wizard sprites have inconsistent canvas sizes with varying transparent padding:
        - Small sprites (80×95, 74×105): IDLE, JUMP, FALL - less padding
        - Large sprites (222×144, 231×142): RUN, ATTACK, SKILLS - lots of padding
        
        Solution: Scale large sprites 2.8× bigger to compensate for extra padding,
        ensuring the actual wizard character appears the same visual size across all animations.
        """
        # Small sprites with minimal padding (IDLE, JUMP, FALL)
        # Native: 80×95 - scale to match Knight visual size
        sprite_size_small = (42, 40)  # Match Knight size
        
        # Large sprites with heavy padding (RUN, ATTACK, SKILLS)
        # Native: 222×144 / 231×142 - character is tiny inside, needs 2.8× scale compensation
        # 222/80 ≈ 2.78, so we scale proportionally larger to match visual wizard size
        sprite_size_large = (117, 112)  # 2.8× bigger than small sprites
        
        # IDLE - Lowest priority, always available (6 frames)
        # Native: 80×95 (minimal padding)
        self.anim_manager.load_animation(
            AnimationState.IDLE,
            [f"assets/Player/wizard/idle-wizard/idle{i}.png" for i in range(1, 7)],
            sprite_size=sprite_size_small,
            frame_duration=8,
            loop=True,
            priority=0
        )
        
        # RUN - Basic movement (8 frames)
        # Native: 222×144 (HEAVY padding - character is small inside canvas)
        self.anim_manager.load_animation(
            AnimationState.RUN,
            [f"assets/Player/wizard/run-wizard/run{i}.png" for i in range(1, 9)],
            sprite_size=(80,70),  # 2.8× bigger to compensate for padding
            frame_duration=5,
            loop=True,
            priority=1
        )
        
        # JUMP - Moving upward (2 frames)
        # Native: 74×105 (minimal padding)
        self.anim_manager.load_animation(
            AnimationState.JUMP,
            [f"assets/Player/wizard/jump-wizard/Jump-{i}.png" for i in range(1, 3)],
            sprite_size=sprite_size_small,
            frame_duration=6,
            loop=False,
            priority=2
        )
        
        # FALL - Moving downward (2 frames from wizard-fall folder)
        # Native: 80×108 (minimal padding)
        self.anim_manager.load_animation(
            AnimationState.FALL,
            [f"assets/Player/wizard/wizard-fall/jump{i}.png" for i in range(1, 3)],
            sprite_size=sprite_size_small,
            frame_duration=6,
            loop=False,
            priority=2
        )
        
        # ATTACK - Basic attack animation (4 frames from wizard-atk)
        # Native: 231×142 (HEAVY padding)
        # Frame duration: 2 frames per sprite = 8 total frames, fits in ATTACK_COOLDOWN (10 frames)
        self.anim_manager.load_animation(
            AnimationState.ATTACK,
            [f"assets/Player/wizard/wizard-atk/attk{i:03d}.png" for i in range(1, 5)],
            sprite_size=(80,70),  # 2.8× bigger to compensate for padding
            frame_duration=2,  # Synced to ATTACK_COOLDOWN
            loop=False,
            priority=4,
            next_state=AnimationState.IDLE
        )
        
        # SKILL_1 - Fireball skill (uses basic wizard-atk since it's a fire projectile)
        # Native: 231×142 (HEAVY padding)
        # Frame duration: 2 frames per sprite = 8 total frames (~0.13s fast cast)
        self.anim_manager.load_animation(
            AnimationState.SKILL_1,
            [f"assets/Player/wizard/wizard-atk/attk{i:03d}.png" for i in range(1, 5)],
            sprite_size=(80,70),  # 2.8× bigger to compensate for padding
            frame_duration=2,  # Quick fireball cast
            loop=False,
            priority=5,
            next_state=AnimationState.IDLE
        )
        
        # SKILL_2 - Cold Feet skill (8 frames from wizard-skill folder)
        # Native: 231×142 (HEAVY padding)
        # Frame duration: 4 frames per sprite = 32 total frames (~0.5s cast time)
        self.anim_manager.load_animation(
            AnimationState.SKILL_2,
            [f"assets/Player/wizard/wizard-skill/skill{i}.png" for i in range(1, 9)],
            sprite_size=(80,70),  # 2.8× bigger to compensate for padding
            frame_duration=4,  # Slower AOE spell cast
            loop=False,
            priority=5,
            next_state=AnimationState.IDLE
        )
        
        # SKILL_3 - Magic Missile (5 frames from wizard-lazer-skill-atk)
        # Native: 231×142 (HEAVY padding)
        # Frame duration: 5 frames per sprite = 25 total frames (~0.4s fast cast)
        self.anim_manager.load_animation(
            AnimationState.SKILL_3,
            [f"assets/Player/wizard/wizard-lazer-skill-atk/attk{i:03d}.png" for i in range(1, 6)],
            sprite_size=(80,70),  # 2.8× bigger to compensate for padding
            frame_duration=5,  # Fast aggressive laser cast
            loop=False,
            priority=5,
            next_state=AnimationState.IDLE
        )

    def _update_knight_animations(self):
        """Update Knight animation state - clean state machine with smoothing"""
        if not self.anim_manager:
            return
        
        # Smooth ground detection to prevent flicker (use coyote time concept)
        if self.on_ground or self.coyote > 0:
            self._anim_grounded_buffer = 5  # Stay "grounded" for animation for 5 frames
        elif self._anim_grounded_buffer > 0:
            self._anim_grounded_buffer -= 1
        
        anim_grounded = self._anim_grounded_buffer > 0
        
        current = self.anim_manager.current_state
        
        # Priority 1: SKILL_1 (Dash Attack) - don't interrupt while playing
        if current == AnimationState.SKILL_1 and self.anim_manager.is_playing:
            return
        
        # Priority 2: ATTACK (don't interrupt while playing)
        if self.attack_cd > 0 and current == AnimationState.ATTACK and self.anim_manager.is_playing:
            return
        
        # Priority 3: Start attack animation when attack begins
        if self.attack_cd > 0 and self.attack_cd > (ATTACK_COOLDOWN - ATTACK_LIFETIME):
            if current != AnimationState.ATTACK:
                self.anim_manager.play(AnimationState.ATTACK, force=True)
            return
        
        # Priority 4: DASH (only while actively dashing, and NOT during dash attack animation)
        if self.dashing > 0 and current != AnimationState.SKILL_1:
            if current != AnimationState.DASH:
                self.anim_manager.play(AnimationState.DASH, force=True)
            return
        
        # Priority 4: RUN (on ground + moving) - CHECK BEFORE WALL_SLIDE
        # This prevents flicker when pushing into wall on ground
        if anim_grounded and abs(self.vx) > 0.3:
            if current != AnimationState.RUN:
                self.anim_manager.play(AnimationState.RUN, force=True)
            return
        
        # Priority 5: IDLE when grounded and not moving - CHECK BEFORE WALL_SLIDE
        if anim_grounded:
            if current != AnimationState.IDLE:
                self.anim_manager.play(AnimationState.IDLE, force=True)
            return
        
        # Priority 6: WALL_SLIDE (only when airborne)
        # CRITICAL: Must be truly airborne (no ground contact at all) AND on wall AND falling
        is_truly_airborne = not self.on_ground and self.coyote == 0 and self._anim_grounded_buffer == 0
        is_on_wall = self.on_left_wall or self.on_right_wall
        is_falling_on_wall = self.vy > 0  # Moving downward
        
        if is_truly_airborne and is_on_wall and is_falling_on_wall:
            if current != AnimationState.WALL_SLIDE:
                self.anim_manager.play(AnimationState.WALL_SLIDE, force=True)
            return
        
        # Priority 7: AIR STATES (jump/fall) - only if clearly in air
        if self.vy < -1.0:  # Rising with clear upward velocity
            if current != AnimationState.JUMP:
                self.anim_manager.play(AnimationState.JUMP, force=True)
            return
        elif self.vy > 1.0:  # Falling with clear downward velocity
            if current != AnimationState.FALL:
                self.anim_manager.play(AnimationState.FALL, force=True)
            return
        
        # Priority 8: Final fallback to IDLE
        if current != AnimationState.IDLE:
            self.anim_manager.play(AnimationState.IDLE, force=True)

    def _update_ranger_animations(self):
        """
        Update Ranger animation state - clean state machine with 3-state bow attack system.
        
        Animation Priority (highest to lowest):
        1. DASH - Active dash movement (overrides everything)
        2. SHOOT - Arrow release animation (must complete, no interrupt)
        3. CHARGE/CHARGED - Bow drawing states (based on charge_time)
        4. RUN - Ground movement
        5. IDLE - Grounded, stationary
        6. WALL_SLIDE - Airborne wall contact with downward velocity
        7. JUMP/FALL - Airborne states based on vertical velocity
        
        The 3-state bow attack system:
        - self.charging = True: Start CHARGE animation
        - charge_time >= threshold: Transition to CHARGED (looping hold)
        - Release attack: Play SHOOT animation → auto-transition to IDLE
        """
        if not self.anim_manager:
            return
        
        # Smooth ground detection to prevent flicker (use coyote time concept)
        if self.on_ground or self.coyote > 0:
            self._anim_grounded_buffer = 5  # Stay "grounded" for animation for 5 frames
        elif self._anim_grounded_buffer > 0:
            self._anim_grounded_buffer -= 1
        
        anim_grounded = self._anim_grounded_buffer > 0
        current = self.anim_manager.current_state
        
        # Priority 1: DASH (only while actively dashing)
        if self.dashing > 0:
            if current != AnimationState.DASH:
                self.anim_manager.play(AnimationState.DASH, force=True)
            return
        
        # Priority 2: SHOOT (don't interrupt while playing)
        # This ensures the arrow release animation completes before returning to idle
        if current == AnimationState.SHOOT and self.anim_manager.is_playing:
            return
        
        # Priority 3: CHARGE/CHARGED (3-state bow attack system)
        # This handles the progressive bow draw → hold → release sequence
        if self.charging:
            # Check if we've reached full charge
            if self.charge_time >= self.charge_threshold:
                # Transition to CHARGED (holding at full draw)
                if current != AnimationState.CHARGED:
                    self.anim_manager.play(AnimationState.CHARGED, force=True)
            else:
                # Still drawing the bow
                if current != AnimationState.CHARGE:
                    self.anim_manager.play(AnimationState.CHARGE, force=True)
            return
        
        # Priority 4: RUN (on ground + moving) - CHECK BEFORE WALL_SLIDE
        # This prevents flicker when pushing into wall on ground
        if anim_grounded and abs(self.vx) > 0.3:
            if current != AnimationState.RUN:
                self.anim_manager.play(AnimationState.RUN, force=True)
            return
        
        # Priority 5: IDLE when grounded and not moving - CHECK BEFORE WALL_SLIDE
        if anim_grounded:
            if current != AnimationState.IDLE:
                self.anim_manager.play(AnimationState.IDLE, force=True)
            return
        
        # Priority 6: WALL_SLIDE (only when airborne)
        # CRITICAL: Must be truly airborne (no ground contact at all) AND on wall AND falling
        is_truly_airborne = not self.on_ground and self.coyote == 0 and self._anim_grounded_buffer == 0
        is_on_wall = self.on_left_wall or self.on_right_wall
        is_falling_on_wall = self.vy > 0  # Moving downward
        
        if is_truly_airborne and is_on_wall and is_falling_on_wall:
            if current != AnimationState.WALL_SLIDE:
                self.anim_manager.play(AnimationState.WALL_SLIDE, force=True)
            return
        
        # Priority 7: AIR STATES (jump/fall) - only if clearly in air
        if self.vy < -1.0:  # Rising with clear upward velocity
            if current != AnimationState.JUMP:
                self.anim_manager.play(AnimationState.JUMP, force=True)
            return
        elif self.vy > 1.0:  # Falling with clear downward velocity
            if current != AnimationState.FALL:
                self.anim_manager.play(AnimationState.FALL, force=True)
            return
        
        # Priority 8: Final fallback to IDLE
        if current != AnimationState.IDLE:
            self.anim_manager.play(AnimationState.IDLE, force=True)

    def _update_wizard_animations(self):
        """
        Update Wizard animation state - clean state machine with skill casting animations.
        
        Animation Priority (highest to lowest):
        1. SKILL_1/SKILL_2/SKILL_3 - Skill casting animations (must complete, no interrupt)
        2. ATTACK - Basic attack animation (must complete, no interrupt)
        3. RUN - Ground movement
        4. IDLE - Grounded, stationary
        5. WALL_SLIDE - Airborne wall contact with downward velocity
        6. JUMP/FALL - Airborne states based on vertical velocity
        """
        if not self.anim_manager:
            return
        
        # Smooth ground detection to prevent flicker (use coyote time concept)
        if self.on_ground or self.coyote > 0:
            self._anim_grounded_buffer = 5  # Stay "grounded" for animation for 5 frames
        elif self._anim_grounded_buffer > 0:
            self._anim_grounded_buffer -= 1
        
        anim_grounded = self._anim_grounded_buffer > 0
        current = self.anim_manager.current_state
        
        # Priority 1: SKILL_1 (Fireball) - don't interrupt while playing
        if current == AnimationState.SKILL_1 and self.anim_manager.is_playing:
            return
        
        # Priority 2: SKILL_2 (Cold Feet/Lazer) - don't interrupt while playing
        if current == AnimationState.SKILL_2 and self.anim_manager.is_playing:
            return
        
        # Priority 3: SKILL_3 (Magic Missile) - don't interrupt while playing
        if current == AnimationState.SKILL_3 and self.anim_manager.is_playing:
            return
        
        # Priority 4: ATTACK (don't interrupt while playing)
        if self.attack_cd > 0 and current == AnimationState.ATTACK and self.anim_manager.is_playing:
            return
        
        # Priority 5: Start attack animation when attack begins
        if self.attack_cd > 0 and self.attack_cd > (ATTACK_COOLDOWN - ATTACK_LIFETIME):
            if current != AnimationState.ATTACK:
                self.anim_manager.play(AnimationState.ATTACK, force=True)
            return
        
        # Priority 6: RUN (on ground + moving) - CHECK BEFORE WALL_SLIDE
        # Use lower threshold (0.1) to catch any movement and prevent flicker
        if anim_grounded and abs(self.vx) > 0.1:
            if current != AnimationState.RUN:
                self.anim_manager.play(AnimationState.RUN, force=True)
            return
        
        # Priority 7: IDLE when grounded and not moving - CHECK BEFORE WALL_SLIDE
        if anim_grounded:
            if current != AnimationState.IDLE:
                self.anim_manager.play(AnimationState.IDLE, force=True)
            return
        
        # Priority 8: WALL_SLIDE (only when airborne)
        is_truly_airborne = not self.on_ground and self.coyote == 0 and self._anim_grounded_buffer == 0
        is_on_wall = self.on_left_wall or self.on_right_wall
        is_falling_on_wall = self.vy > 0  # Moving downward
        
        if is_truly_airborne and is_on_wall and is_falling_on_wall:
            if current != AnimationState.WALL_SLIDE:
                self.anim_manager.play(AnimationState.WALL_SLIDE, force=True)
            return
        
        # Priority 9: AIR STATES (jump/fall) - only if clearly in air
        if self.vy < -1.0:  # Rising with clear upward velocity
            if current != AnimationState.JUMP:
                self.anim_manager.play(AnimationState.JUMP, force=True)
            return
        elif self.vy > 1.0:  # Falling with clear downward velocity
            if current != AnimationState.FALL:
                self.anim_manager.play(AnimationState.FALL, force=True)
            return
        
        # Priority 10: Final fallback to IDLE
        if current != AnimationState.IDLE:
            self.anim_manager.play(AnimationState.IDLE, force=True)

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
        if not self.alive:
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
        
        # Store current movement input for dash direction
        self._current_move_input = move

        # Track if we just exited floating mode
        just_exited_floating = getattr(self, '_was_floating_mode', False) and not getattr(self, 'floating_mode', False)
        # Update floating mode tracking
        self._was_floating_mode = getattr(self, 'floating_mode', False)

        # Reset momentum when exiting floating mode
        if just_exited_floating:
            self.vx = 0
            self.vy = 0

        # === FLOATING MODE VERTICAL MOVEMENT ===
        # Handle vertical input for floating mode in no-clip before physics() early-return.
        if getattr(self, 'floating_mode', False) and getattr(self, 'no_clip', False):
            if self.stunned <= 0:
                if keys[pygame.K_w]:
                    self.vy = -8
                elif keys[pygame.K_s]:
                    self.vy = 8
                else:
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

            # Update facing only when there is horizontal input AND not actively charging/shooting
            # For Ranger: Lock facing to mouse direction during charge/shoot
            is_ranger_aiming = (self.cls == 'Ranger' and 
                               (getattr(self, 'charging', False) or 
                                (self.anim_manager and self.anim_manager.current_state == AnimationState.SHOOT)))
            
            if move != 0 and not is_ranger_aiming:
                self.facing = move

        # Update Ranger facing direction when actively charging or shooting
        if self.cls == 'Ranger':
            # Lock facing to mouse during charge AND shoot animation
            is_shooting = (self.anim_manager and self.anim_manager.current_state == AnimationState.SHOOT)
            if getattr(self, 'charging', False) or is_shooting:
                mx, my = pygame.mouse.get_pos()
                # Convert mouse screen position to world position
                world_x = (mx / camera.zoom) + camera.x
                # Update facing based on mouse position relative to player
                if world_x < self.rect.centerx:
                    self.facing = -1  # Facing left
                elif world_x > self.rect.centerx:
                    self.facing = 1   # Facing right
      
        # Jump input buffering - allow jumping when in god mode with floating mode OFF
        in_no_clip_but_not_floating = getattr(self, 'no_clip', False) and not getattr(self, 'floating_mode', False)
        if not getattr(self, 'no_clip', False) or in_no_clip_but_not_floating:
            jump_key_down = keys[pygame.K_SPACE] or keys[pygame.K_k]
            if not stunned and self.mobility_cd == 0 and jump_key_down and not self.jump_key_pressed:
                self.jump_buffer = JUMP_BUFFER_FRAMES
            
            if self.vy < 0:
                if not jump_key_down:
                    self.vy *= PLAYER_SMALL_JUMP_CUT
            
            self.jump_key_pressed = jump_key_down

        # NEW: Simplified dash - only if mobility cooldown is free
        free_dash_available = False
        dash_key_down = keys[pygame.K_LSHIFT] or keys[pygame.K_j]
        if (
            not stunned
            and (self.mobility_cd == 0 or free_dash_available)
            and dash_key_down
            and not self.dash_key_pressed  # Only trigger on press, not hold
            and (self.dash_charges > 0 or free_dash_available)
            and not self.dashing
        ):
            self.start_dash(free_action=free_dash_available)
        
        # Update dash key state
        self.dash_key_pressed = dash_key_down

        # Parry: Right mouse button or E (Knight only)
        rmb = pygame.mouse.get_pressed()[2]
        if not stunned and (rmb or keys[pygame.K_e]) and self.cls == 'Knight':
            if self.combat.activate_parry():
                # Optional: Add feedback for successful parry activation
                pass
        # Wizard teleport skill: R (teleport toward mouse)
        if not stunned and keys[pygame.K_r] and self.cls == 'Wizard':
            self.teleport_to_mouse(level, camera)

        # Skill keys per class (1/2/3) - Wizard uses select-then-cast system
        if self.cls == 'Wizard':
            # Press 1/2/3 to select skill (don't cast yet) - check if skill is available
            if not stunned and keys[pygame.K_1] and not getattr(self, '_prev_key_1', False):
                # Only select fireball if it's available (has mana and not on cooldown)
                if getattr(self, 'mana', 0) >= 15 and self.skill_cd1 == 0:
                    self.selected_skill = 'fireball'
            elif not stunned and keys[pygame.K_2] and not getattr(self, '_prev_key_2', False):
                # Only select cold feet if it's available
                if getattr(self, 'mana', 0) >= 25 and self.skill_cd2 == 0:
                    self.selected_skill = 'coldfeet'
            elif not stunned and keys[pygame.K_3] and not getattr(self, '_prev_key_3', False):
                # Only select magic missile if it's available
                if getattr(self, 'mana', 0) >= 30 and self.skill_cd3 == 0:
                    self.selected_skill = 'magic_missile'
            
            # ESC or right-click cancels skill selection
            rmb = pygame.mouse.get_pressed()[2]
            if (keys[pygame.K_ESCAPE] or rmb) and self.selected_skill:
                self.selected_skill = None
            
            # Store previous key states for edge detection
            self._prev_key_1 = keys[pygame.K_1]
            self._prev_key_2 = keys[pygame.K_2]
            self._prev_key_3 = keys[pygame.K_3]
        else:
            # Other classes use immediate cast
            if not stunned and keys[pygame.K_1]:
                self.activate_skill(1, level, camera)
            elif not stunned and keys[pygame.K_2]:
                self.activate_skill(2, level, camera)
            elif not stunned and keys[pygame.K_3]:
                self.activate_skill(3, level, camera)

        # Attack / Ranger charge handling / Wizard skill casting
        lmb = pygame.mouse.get_pressed()[0]
        if not stunned and self.attack_cd == 0:
            if self.cls == 'Wizard':
                # If a skill is selected, cast it on left-click
                if self.selected_skill and lmb and not self._prev_lmb:
                    if self.selected_skill == 'fireball':
                        self.cast_fireball(level, camera)
                        self.selected_skill = None
                    elif self.selected_skill == 'coldfeet':
                        self.cast_coldfeet(level, camera)
                        self.selected_skill = None
                    elif self.selected_skill == 'magic_missile':
                        self.cast_magic_missile(level, camera)
                        self.selected_skill = None
                # Otherwise, normal attack
                elif not self.selected_skill and (keys[pygame.K_l] or lmb):
                    self.start_attack(keys, camera)
            elif self.cls == 'Ranger':
                # start charging on press
                if lmb and not self._prev_lmb:
                    self.charging = True
                    self.charge_time = 0
                if self.charging and lmb:
                    self.charge_time += 1
                # on release, fire arrow
                if self.charging and not lmb and self._prev_lmb:
                    # Calculate charge percentage (0.0 to 1.0)
                    charge_pct = min(1.0, self.charge_time / self.charge_threshold)
                    charged = self.charge_time >= self.charge_threshold
                    
                    # Calculate mana cost based on charge level
                    base_mana_cost = 3.0
                    charged_mana_cost = 8.0
                    mana_cost = base_mana_cost + (charged_mana_cost - base_mana_cost) * charge_pct
                    
                    # Check if player has enough mana
                    if getattr(self, 'mana', 0) < mana_cost:
                        # Not enough mana - show feedback and don't fire
                        from .entity_common import floating, DamageNumber
                        floating.append(DamageNumber(
                            self.rect.centerx,
                            self.rect.top - 12,
                            "Not enough mana!",
                            (200, 100, 100)
                        ))
                        self.charging = False
                    else:
                        # Consume mana
                        self.mana = max(0.0, self.mana - mana_cost)
                        
                        # Triple-shot: force 3 arrows each dealing 7 dmg (example: 3*7=21)
                        if getattr(self, 'triple_timer', 0) > 0:
                            base = 7
                            dmg = base
                            # allow sniper multiplier to apply if charged
                            if charged and self.sniper_ready:
                                dmg = int(base * self.sniper_mult)
                                self.sniper_ready = False
                                # Visual feedback: Show sniper damage multiplier
                                from .entity_common import floating, DamageNumber
                                floating.append(DamageNumber(
                                    self.rect.centerx,
                                    self.rect.top - 10,
                                    f"×{self.sniper_mult}!",
                                    (255, 60, 60)
                                ))
                            speed = 14
                            # Triple shot consumes 1.5x mana (already deducted above with adjusted cost)
                            triple_mana_cost = mana_cost * 1.5
                            self.mana = max(0.0, self.mana - (triple_mana_cost - mana_cost))
                            self.fire_triple_arrows(dmg, speed, camera, pierce=charged)
                        else:
                            # Scale damage based on charge time (2 to 7 damage)
                            min_damage = 2
                            max_damage = 7
                            dmg = int(min_damage + (max_damage - min_damage) * charge_pct)
                            # Sniper buff multiplies charged shot
                            if charged and self.sniper_ready:
                                dmg = int(dmg * self.sniper_mult)
                                self.sniper_ready = False
                                # Visual feedback: Show sniper damage multiplier
                                from .entity_common import floating, DamageNumber
                                floating.append(DamageNumber(
                                    self.rect.centerx,
                                    self.rect.top - 10,
                                    f"×{self.sniper_mult}!",
                                    (255, 60, 60)
                                ))
                            # Speed scales with charge
                            speed = 10 + int(4 * charge_pct)  # 10 to 14
                            self.fire_arrow(dmg, speed, camera, pierce=charged)
                        
                        attack_speed_mult = getattr(self, 'attack_speed_mult', 1.0)
                        self.attack_cd = ATTACK_COOLDOWN / attack_speed_mult
                        self.charging = False
            else:
                if keys[pygame.K_l] or lmb:
                    self.start_attack(keys, camera)
        # update prev mouse state
        self._prev_lmb = lmb

    def start_dash(self, free_action=False):
        # require some stamina to dash (unless it's a free action)
        if not free_action:
            dash_cost = 2.0 * getattr(self, 'dash_stamina_mult', 1.0)
            if getattr(self, 'stamina', 0) <= 0:
                return
            # consume stamina if available
            if hasattr(self, 'stamina'):
                self.stamina = max(0.0, self.stamina - dash_cost)
            # start stamina regen cooldown (1 second)
            self._stamina_cooldown = int(FPS)
            # Consume a dash charge
            self.dash_charges = max(0, self.dash_charges - 1)
            self.dash_cd = DASH_COOLDOWN
            # trigger shared mobility cooldown
            self.mobility_cd = MOBILITY_COOLDOWN_FRAMES
        else:
            # Dash cancels wall jump state
            self.wall_jump_state = None
        
        # Determine dash direction from current movement input, fallback to facing
        dash_direction = getattr(self, '_current_move_input', 0)
        if dash_direction == 0:
            # No input, use facing direction as fallback
            dash_direction = self.facing
        
        # grant short invincibility when dash starts (0.25s)
        self.combat.invincible_frames = int(0.25 * FPS)
        self.dashing = DASH_TIME
        self.vy = 0
        self.vx = dash_direction * DASH_SPEED

    def _spawn_knight_attack_hitbox(self):
        """
        Spawn Knight's normal attack hitbox.
        Called automatically by frame event system on attack animation frame 4.
        """
        # Store attack direction when attack started (accessed via instance variables)
        dir_vec = getattr(self, '_attack_dir_vec', (self.facing, 0))
        
        if dir_vec == (0, -1):
            # upward hitbox: increased reach to match sword arc
            hb = pygame.Rect(0, 0, int(self.rect.w * 1.2), int(self.rect.h * 1.0))
            hb.midbottom = self.rect.midtop
        elif dir_vec == (0, 1):
            # downward hitbox: increased reach to match sword swing
            hb = pygame.Rect(0, 0, int(self.rect.w * 1.2), int(self.rect.h * 1.4))
            hb.midtop = self.rect.midbottom
        else:
            # forward hitbox: increased horizontal reach to match sword sprite extension
            hb = pygame.Rect(0, 0, int(self.rect.w * 2.2), int(self.rect.h * 1.1))
            if self.facing > 0:
                hb.midleft = (self.rect.right, self.rect.centery)
            else:
                hb.midright = (self.rect.left, self.rect.centery)
        
        # use class attack damage (melee)
        dmg = self.attack_damage + self.combat.atk_bonus
        hitboxes.append(Hitbox(hb, ATTACK_LIFETIME, dmg, self, dir_vec, pogo=(dir_vec==(0,1))))
    
    def _spawn_knight_dash_attack_hitbox(self):
        """
        Spawn Knight's dash attack (charge skill) hitbox.
        Called automatically by frame event system on dash attack animation frame 3.
        """
        dash_speed = 10
        # Increased dash attack range to match animation sprite
        hb = pygame.Rect(0, 0, int(self.rect.w*1.8), int(self.rect.h*1.2))
        if self.facing > 0:
            hb.midleft = (self.rect.right, self.rect.centery)
        else:
            hb.midright = (self.rect.left, self.rect.centery)
        hitboxes.append(Hitbox(hb, 12, 4, self, dir_vec=(self.facing,0), vx=self.facing*dash_speed))
        # Give the player a burst of speed
        self.vx = self.facing * dash_speed
        self.dashing = 8
        print(f"[Knight] Dash attack hitbox spawned on frame {self.anim_manager.get_current_frame_index() if self.anim_manager else '?'}")
    
    def start_attack(self, keys, camera):
        # Wizard: ranged normal attack toward mouse
        if self.cls == 'Wizard':
            # Wizard basic attack costs mana
            mana_cost = 2.0
            if getattr(self, 'mana', 0) < mana_cost:
                # Not enough mana - show feedback and don't fire
                from .entity_common import floating, DamageNumber
                floating.append(DamageNumber(
                    self.rect.centerx,
                    self.rect.top - 12,
                    "Not enough mana!",
                    (200, 100, 100)
                ))
                return
            
            # Consume mana
            self.mana = max(0.0, self.mana - mana_cost)
            
            attack_speed_mult = getattr(self, 'attack_speed_mult', 1.0)
            self.attack_cd = ATTACK_COOLDOWN / attack_speed_mult
            self.combo_t = COMBO_RESET
            self.combo = (self.combo + 1) % 3
            mx, my = pygame.mouse.get_pos()
            # Convert mouse screen position to world position accounting for camera and zoom
            world_x = (mx / camera.zoom) + camera.x
            world_y = (my / camera.zoom) + camera.y
            dx = world_x - self.rect.centerx
            dy = world_y - self.rect.centery
            dist = (dx*dx + dy*dy) ** 0.5
            if dist == 0:
                nx, ny = (1, 0)
            else:
                nx, ny = dx / dist, dy / dist
            speed = 9.0
            damage = int(1 * getattr(self, 'skill_damage_mult', 1.0))
            hb = pygame.Rect(0, 0, 8, 8)
            hb.center = self.rect.center
            
            # Load animated normal attack projectile (4 frames)
            from .animation_system import load_projectile_animation
            normal_attack_frames = load_projectile_animation(
                [f"assets/Player/wizard/nm-attk-ball-projectile/nm-attk-ball{i}.png" for i in range(1, 5)],
                sprite_size=(16, 16)
            )
            
            # Create hitbox with animated projectile - smaller hitbox for better balance
            hb = pygame.Rect(0, 0, 14, 14)  # Reduced from 16×16 to 12×12 for tighter collision
            hb.center = self.rect.center
            hitbox = Hitbox(hb, 90, damage, self, dir_vec=(nx,ny), vx=nx*speed, vy=ny*speed, tag='spell')
            hitbox.anim_frames = normal_attack_frames
            hitbox.anim_index = 0
            hitbox.anim_speed = 2  # Change frame every 2 ticks
            hitbox.anim_timer = 0
            hitbox.sprite_display_size = (80, 80)  # Render 525% larger to compensate for padding
            hitbox.sprite_offset = (-5, -5)  # Adjust X and Y offset here: (x_offset, y_offset)
            hitboxes.append(hitbox)
            return

        # Knight: Use frame event system for attack
        if self.cls == 'Knight':
            up = keys[pygame.K_w] or keys[pygame.K_UP]
            down = keys[pygame.K_s] or keys[pygame.K_DOWN]
            dir_vec = (self.facing, 0)
            if up: dir_vec = (0, -1)
            elif down: dir_vec = (0, 1)
            
            # Store attack direction for frame event callback to use
            self._attack_dir_vec = dir_vec
            
            attack_speed_mult = getattr(self, 'attack_speed_mult', 1.0)
            self.attack_cd = ATTACK_COOLDOWN / attack_speed_mult
            self.combo_t = COMBO_RESET
            self.combo = (self.combo + 1) % 3
            
            # Play attack animation - hitbox will spawn on frame 4 automatically!
            if self.anim_manager:
                self.anim_manager.play(AnimationState.ATTACK, force=True)
            return

        # Ranger and other classes: Keep old immediate spawning behavior
        up = keys[pygame.K_w] or keys[pygame.K_UP]
        down = keys[pygame.K_s] or keys[pygame.K_DOWN]
        dir_vec = (self.facing, 0)
        if up: dir_vec = (0, -1)
        elif down: dir_vec = (0, 1)
        attack_speed_mult = getattr(self, 'attack_speed_mult', 1.0)
        self.attack_cd = ATTACK_COOLDOWN / attack_speed_mult
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
        dmg = self.attack_damage + self.combat.atk_bonus
        hitboxes.append(Hitbox(hb, ATTACK_LIFETIME, dmg, self, dir_vec, pogo=(dir_vec==(0,1))))

    def fire_arrow(self, damage, speed, camera, pierce=False):
        # Trigger shoot animation when firing
        if self.anim_manager:
            self.anim_manager.play(AnimationState.SHOOT)
        
        # spawn a moving arrow hitbox toward mouse direction
        mx, my = pygame.mouse.get_pos()
        # Convert mouse screen position to world position accounting for camera and zoom
        world_x = (mx / camera.zoom) + camera.x
        world_y = (my / camera.zoom) + camera.y
        # Use visual center (chest height) instead of collision box center
        visual_x, visual_y = self.visual_center
        dx = world_x - visual_x
        dy = world_y - visual_y
        dist = (dx*dx + dy*dy) ** 0.5
        if dist == 0:
            nx, ny = (1, 0)
        else:
            nx, ny = dx / dist, dy / dist
        # Increased arrow hitbox from 10×6 to 16×10 for better visibility
        hb = pygame.Rect(0, 0, 16, 10)
        hb.center = self.visual_center
        # Keep velocity as float for better precision
        vx = nx * speed
        vy = ny * speed
        hitboxes.append(Hitbox(hb, 120, damage, self, dir_vec=(nx,ny), vx=vx, vy=vy, pierce=pierce, has_sprite=True, arrow_sprite=True))

    def fire_triple_arrows(self, base_damage, speed, camera, pierce=False):
        # Trigger shoot animation when firing
        if self.anim_manager:
            self.anim_manager.play(AnimationState.SHOOT)
        
        # Fire three arrows with slight angle offsets
        import math
        mx, my = pygame.mouse.get_pos()
        # Convert mouse screen position to world position accounting for camera and zoom
        world_x = (mx / camera.zoom) + camera.x
        world_y = (my / camera.zoom) + camera.y
        # Use visual center (chest height) instead of collision box center
        visual_x, visual_y = self.visual_center
        dx = world_x - visual_x
        dy = world_y - visual_y
        base_ang = math.atan2(dy, dx)
        for ang in (base_ang - math.radians(8), base_ang, base_ang + math.radians(8)):
            nx, ny = math.cos(ang), math.sin(ang)
            # Increased arrow hitbox from 10×6 to 16×10 for better visibility
            hb = pygame.Rect(0, 0, 16, 10)
            hb.center = self.visual_center
            # Keep velocity as float for better precision
            vx = nx * speed
            vy = ny * speed
            hitboxes.append(Hitbox(hb, 120, base_damage, self, dir_vec=(nx,ny), vx=vx, vy=vy, pierce=pierce, bypass_ifr=True, has_sprite=True, arrow_sprite=True))

    # --- Wizard skill casts ---
    def cast_fireball(self, level, camera):
        from .animation_system import load_projectile_animation
        
        cost = 15
        if getattr(self, 'mana', 0) < cost or self.skill_cd1 > 0:
            return
        self.mana = max(0.0, self.mana - cost)
        skill_cdr = getattr(self, 'skill_cooldown_mult', 1.0)
        self.skill_cd1 = self.skill_cd1_max = int(5 * FPS * skill_cdr)  # 5s CD (increased from 1s)
        
        # Trigger fireball animation
        if self.anim_manager:
            self.anim_manager.play(AnimationState.SKILL_1, force=True)
        
        mx, my = pygame.mouse.get_pos()
        # Convert mouse screen position to world position accounting for camera and zoom
        world_x = (mx / camera.zoom) + camera.x
        world_y = (my / camera.zoom) + camera.y
        dx = world_x - self.rect.centerx
        dy = world_y - self.rect.centery
        dist = (dx*dx + dy*dy) ** 0.5
        if dist == 0:
            return
        nx = dx / dist
        ny = dy / dist
        speed = 6.0
        damage = int(6 * getattr(self, 'skill_damage_mult', 1.0))
        hb = pygame.Rect(0, 0, 12, 12)
        hb.center = self.rect.center
        
        # Load animated fireball projectile (10 frames)
        fireball_frames = load_projectile_animation(
            [f"assets/Player/wizard/fire-ball-projectile/ball{i}.png" for i in range(1, 11)],
            sprite_size=(24, 24)  # Slightly larger than hitbox for visual effect
        )
        
        # Create hitbox with animated projectile - normalize hitbox to sprite size
        hb = pygame.Rect(0, 0, 24, 24)  # Match sprite size
        hb.center = self.rect.center
        hitbox = Hitbox(hb, 180, damage, self, dir_vec=(nx, ny), vx=nx*speed, vy=ny*speed, aoe_radius=48, tag='spell')
        hitbox.anim_frames = fireball_frames
        hitbox.anim_index = 0
        hitbox.anim_speed = 2  # Change frame every 2 ticks
        hitbox.anim_timer = 0
        hitbox.sprite_display_size = (80, 80)  # Render 400% larger to compensate for padding
        hitbox.sprite_offset = (0, 0)  # Adjust X and Y offset here: (x_offset, y_offset)
        hitboxes.append(hitbox)

    def cast_coldfeet(self, level, camera):
        cost = 25
        if getattr(self, 'mana', 0) < cost or self.skill_cd2 > 0:
            return
        self.mana = max(0.0, self.mana - cost)
        skill_cdr = getattr(self, 'skill_cooldown_mult', 1.0)
        self.skill_cd2 = self.skill_cd2_max = int(8 * FPS * skill_cdr)  # 8s CD
        
        # Trigger lazer skill animation
        if self.anim_manager:
            self.anim_manager.play(AnimationState.SKILL_2, force=True)
        
        mx, my = pygame.mouse.get_pos()
        # Convert mouse screen position to world position accounting for camera and zoom
        world_x = (mx / camera.zoom) + camera.x
        world_y = (my / camera.zoom) + camera.y
        radius = 48
        # visual indicator for the cold feet area (no instant damage)
        hb = pygame.Rect(0,0,int(radius*2), int(radius*2))
        hb.center = (int(world_x), int(world_y))
        hitboxes.append(Hitbox(hb, 4*FPS, 0, self, aoe_radius=radius, visual_only=True))
        
        # Track affected enemies
        affected_count = 0
        from .entity_common import floating, DamageNumber
        
        for e in level.enemies:
            if getattr(e, 'alive', False):
                dx = e.rect.centerx - world_x
                dy = e.rect.centery - world_y
                if (dx*dx + dy*dy) ** 0.5 <= radius:
                    # apply DOT state
                    e.dot_remaining = 4 * FPS
                    e.dot_dps = 5  # damage per second (buffed)
                    e.dot_accum = 0.0
                    # apply slow effect - 50% slow (enemies move at half speed)
                    e.slow_mult = 0.5
                    e.slow_remaining = 4 * FPS
                    affected_count += 1
                    # Show SLOWED text on each enemy
                    floating.append(DamageNumber(
                        e.rect.centerx,
                        e.rect.top - 10,
                        "SLOWED",
                        (100, 200, 255)
                    ))

    def cast_magic_missile(self, level, camera):
        from .animation_system import load_projectile_animation
        
        cost = 30
        if getattr(self, 'mana', 0) < cost or self.skill_cd3 > 0:
            return
        self.mana = max(0.0, self.mana - cost)
        skill_cdr = getattr(self, 'skill_cooldown_mult', 1.0)
        self.skill_cd3 = self.skill_cd3_max = int(6 * FPS * skill_cdr)  # 6s CD (increased from 2s)
        
        # Trigger magic missile animation
        if self.anim_manager:
            self.anim_manager.play(AnimationState.SKILL_3, force=True)
        
        mx, my = pygame.mouse.get_pos()
        # Convert mouse screen position to world position accounting for camera and zoom
        world_x = (mx / camera.zoom) + camera.x
        world_y = (my / camera.zoom) + camera.y
        dx = world_x - self.rect.centerx
        dy = world_y - self.rect.centery
        dist = (dx*dx + dy*dy) ** 0.5
        if dist == 0:
            nx, ny = (1, 0)
        else:
            nx, ny = dx / dist, dy / dist
        speed = 20.0
        damage = int(12 * getattr(self, 'skill_damage_mult', 1.0))
        
        # Load animated laser projectile (3 frames)
        laser_frames = load_projectile_animation(
            [f"assets/Player/wizard/lazer-skill-projectile/lazer-skill{i}.png" for i in range(1, 4)],
            sprite_size=(32, 12)  # Wider laser beam sprite
        )
        
        # Create hitbox with animated laser - normalize hitbox to sprite size
        hb = pygame.Rect(0, 0, 26, 9)  # Match sprite size
        hb.center = self.rect.center
        vx = nx * speed
        vy = ny * speed
        
        # Create hitbox with animated laser
        hitbox = Hitbox(hb, 36, damage, self, dir_vec=(nx,ny), vx=vx, vy=vy, tag='spell')
        hitbox.anim_frames = laser_frames
        hitbox.anim_index = 0
        hitbox.anim_speed = 3  # Change frame every 3 ticks (slower for laser effect)
        hitbox.anim_timer = 0
        hitbox.sprite_display_size = (84, 30)  # Render 200% larger to compensate for padding
        hitbox.sprite_offset = (0, 0)  # Adjust X and Y offset here: (x_offset, y_offset)
        hitboxes.append(hitbox)



    def activate_skill(self, idx, level, camera):
        # Route skill casts by class and index
        if not self.alive:
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
            skill_cdr = getattr(self, 'skill_cooldown_mult', 1.0)
            if idx == 1 and self.skill_cd1 == 0:
                if self.combat.activate_shield():
                    self.skill_cd1 = self.skill_cd1_max = int(15 * FPS * skill_cdr)
                    # Visual feedback: Floating text
                    floating.append(DamageNumber(
                        self.rect.centerx,
                        self.rect.top - 20,
                        "SHIELD UP!",
                        (100, 200, 255)
                    ))
            elif idx == 2 and self.skill_cd2 == 0:
                if self.combat.activate_power_buff():
                    self.skill_cd2 = self.skill_cd2_max = int(25 * FPS * skill_cdr)
                    # Visual feedback: Floating text
                    floating.append(DamageNumber(
                        self.rect.centerx,
                        self.rect.top - 20,
                        "POWER SURGE!",
                        (255, 100, 100)
                    ))
            elif idx == 3 and self.skill_cd3 == 0:
                # Charge/Dash Attack: Use frame event system for proper animation sync
                self.skill_cd3 = self.skill_cd3_max = int(6 * FPS * skill_cdr)
                # Visual feedback: Floating text
                floating.append(DamageNumber(
                    self.rect.centerx,
                    self.rect.top - 20,
                    "CHARGE!",
                    (255, 200, 80)
                ))
                
                # Play dash attack animation - hitbox will spawn on frame 3 automatically!
                if self.anim_manager:
                    self.anim_manager.play(AnimationState.SKILL_1, force=True)
        elif self.cls == 'Ranger':
            # Ranger skills: Triple shot, Sniper, Speed boost
            skill_cdr = getattr(self, 'skill_cooldown_mult', 1.0)
            if idx == 1 and self.skill_cd1 == 0:
                self.triple_timer = 7 * FPS
                self.skill_cd1 = self.skill_cd1_max = int(20 * FPS * skill_cdr)
                # Visual feedback: Floating text
                floating.append(DamageNumber(
                    self.rect.centerx,
                    self.rect.top - 20,
                    "TRIPLE SHOT!",
                    (255, 180, 80)
                ))
            elif idx == 2 and self.skill_cd2 == 0:
                self.sniper_ready = True
                self.skill_cd2 = self.skill_cd2_max = int(10 * FPS * skill_cdr)
                # Visual feedback: Floating text
                floating.append(DamageNumber(
                    self.rect.centerx,
                    self.rect.top - 20,
                    "SNIPER READY!",
                    (255, 80, 80)
                ))
            elif idx == 3 and self.skill_cd3 == 0:
                self.speed_timer = 7 * FPS
                self.skill_cd3 = self.skill_cd3_max = int(15 * FPS * skill_cdr)
                # Visual feedback: Floating text
                floating.append(DamageNumber(
                    self.rect.centerx,
                    self.rect.top - 20,
                    "SPEED BOOST!",
                    (100, 255, 200)
                ))

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
        # Convert mouse screen position to world position accounting for camera and zoom
        world_x = (mx / camera.zoom) + camera.x
        world_y = (my / camera.zoom) + camera.y
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

    def physics(self, level, dt=1.0/FPS):
        if not self.alive:
            # Phoenix feather revival check
            if getattr(self, 'phoenix_feather_active', False):
                self.phoenix_feather_active = False
                self.alive = True
                self.combat.alive = True
                self.combat.hp = max(1, self.combat.max_hp // 2)
                self.hp = self.combat.hp
                
                # Visual feedback: Multiple large floating texts with staggered timing
                floating.append(DamageNumber(self.rect.centerx, self.rect.top - 30, "PHOENIX", (255, 200, 100)))
                floating.append(DamageNumber(self.rect.centerx, self.rect.top - 10, "REVIVE!", (255, 120, 50)))
                floating.append(DamageNumber(self.rect.centerx, self.rect.top + 10, f"+{self.combat.hp} HP", GREEN))
                
                # Create visual particle burst effect (spawn multiple damage numbers as "particles")
                import random
                for i in range(8):
                    angle = (i / 8.0) * 2 * math.pi
                    offset_x = int(math.cos(angle) * 30)
                    offset_y = int(math.sin(angle) * 20)
                    floating.append(DamageNumber(
                        self.rect.centerx + offset_x,
                        self.rect.centery + offset_y,
                        "✦",  # Sparkle/star character
                        (255, 180, 80)
                    ))
                
                # Grant brief invincibility after revival (3 seconds)
                self.combat.invincible_frames = 3 * FPS
                self.iframes_flash = True
            return

        # Update all combat timers and states
        self.combat.update()

        # Tick shared mobility cooldown
        if self.mobility_cd > 0:
            self.mobility_cd -= 1

        # Update attack cooldown timer regardless of mode
        speed_bonus = self.speed_potion_bonus if self.speed_potion_timer > 0 else 0.0
        cd_step = 1.0 + speed_bonus
        if self.attack_cd > 0: self.attack_cd = max(0.0, self.attack_cd - cd_step)

        # CRITICAL: In floating_mode, bypass all tile/solid collisions and move directly.
        if getattr(self, 'floating_mode', False):
            self.rect.x += int(self.vx)
            self.rect.y += int(self.vy)
            self.was_on_ground = False
            self.on_ground = False
            self.on_left_wall = False
            self.on_right_wall = False
            try:
                self.last_tile_collisions = []
            except Exception:
                pass
            return

        if self.on_ground:
            self.coyote = COYOTE_FRAMES
            self.double_jumps = DOUBLE_JUMPS + int(getattr(self, 'extra_jump_charges', 0))
            # Restore dash charges when landing
            extra_charges = int(getattr(self, 'extra_dash_charges', 0))
            self.dash_charges_max = 1 + extra_charges
            self.dash_charges = self.dash_charges_max
            # FIXED: Reset all wall jump related states when landing on ground
            if self.wall_jump_state is not None:
                self.wall_jump_state = None
                self.wall_jump_direction = 0
            self.wall_sliding = False
            self.wall_jump_coyote_timer = 0
            self.wall_jump_buffer_timer = 0
            self.on_left_wall = False
            self.on_right_wall = False
            self._left_wall_contact_frames = 0
            self._right_wall_contact_frames = 0
        else:
            self.coyote = max(0, self.coyote-1)

        if self.jump_buffer > 0:
            self.jump_buffer -= 1

        if self.wall_jump_cooldown > 0:
            self.wall_jump_cooldown -= 1
        if self.wall_jump_coyote_timer > 0:
            self.wall_jump_coyote_timer -= 1
        if self.wall_jump_buffer_timer > 0:
            self.wall_jump_buffer_timer -= 1
        if self.wall_reattach_timer > 0:
            self.wall_reattach_timer -= 1
        if self._left_wall_contact_frames > 0:
            self._left_wall_contact_frames -= 1
        if self._right_wall_contact_frames > 0:
            self._right_wall_contact_frames -= 1

        # CRITICAL FIX: Check wall sliding state BEFORE processing jumps
        # This ensures we know if player is actually in a wall slide state
        self.wall_sliding = False
        # FIXED: Add proper wall jump conditions - player must be in the air and falling/moving downward
        is_actually_in_air = not self.on_ground and (self.vy >= 0 or self.coyote < COYOTE_FRAMES - 2)
        if is_actually_in_air and self.wall_jump_cooldown == 0:
            if self.on_left_wall or self.on_right_wall:
                self.wall_sliding = True
                self.wall_jump_coyote_timer = WALL_JUMP_COYOTE_TIME
                if self.jump_buffer > 0 and self.wall_jump_buffer_timer == 0:
                    self.wall_jump_buffer_timer = WALL_JUMP_BUFFER_TIME

        want_jump = self.jump_buffer > 0 and self.mobility_cd == 0
        jump_mult = getattr(self, 'jump_force_multiplier', 1.0)
        if want_jump:
            did = False
            # CRITICAL FIX: Priority order - check GROUND jump first, then wall jump
            # This prevents wall jumps when player is actually on ground
            if self.on_ground or self.coyote > 0:
                # Normal ground jump (or coyote time jump)
                self.vy = PLAYER_JUMP_V * jump_mult
                did = True
            # FIXED: Only allow wall jump when actually sliding or just left wall (coyote time) AND not on ground
            elif (self.wall_sliding or self.wall_jump_coyote_timer > 0) and not self.on_ground:
                if self.wall_jump_cooldown == 0:
                    if self.on_left_wall:
                        self.wall_jump_direction = 1
                        self.rect.x += 1
                    elif self.on_right_wall:
                        self.wall_jump_direction = -1
                        self.rect.x -= 1
                    else:
                        self.wall_jump_direction = self.wall_jump_direction if self.wall_jump_direction != 0 else (-1 if self.facing > 0 else 1)
                    self.vx = WALL_LEAVE_H_BOOST * self.wall_jump_direction
                    self.vy = WALL_JUMP_V_SPEED * jump_mult
                    self.wall_jump_state = 'jumping'
                    self.wall_jump_cooldown = WALL_JUMP_COOLDOWN
                    self.wall_reattach_timer = WALL_REATTACH_TIME
                    self.wall_sliding = False
                    self.on_left_wall = False
                    self.on_right_wall = False
                    did = True
                elif self.double_jumps > 0:
                    self.vy = PLAYER_JUMP_V * jump_mult
                    self.double_jumps -= 1
                    did = True
            elif self.double_jumps > 0:
                self.vy = PLAYER_JUMP_V * jump_mult
                self.double_jumps -= 1
                did = True

            if did:
                self.jump_buffer = 0
                self.on_ground = False
                self.mobility_cd = MOBILITY_COOLDOWN_FRAMES

        if getattr(self, 'no_clip', False):
            keys = pygame.key.get_pressed()
            if getattr(self, 'floating_mode', False):
                if self.stunned <= 0:
                    if keys[pygame.K_w]: self.vy = -8
                    elif keys[pygame.K_s]: self.vy = 8
                    else: self.vy = 0
            else:
                if not self.dashing: self._apply_physics()
                else: self.dashing -= 1
        elif not self.dashing:
            self._apply_physics()
        else:
            self.dashing -= 1
            if self.dashing == 0 and not self.on_ground:
                self.vy = GRAVITY

        collisions = None
        if not getattr(self, 'no_clip', False):
            tile_collision = getattr(level, "tile_collision", None)
            if tile_collision is not None and getattr(level, "grid", None) is not None:
                try:
                    entity_rect = self.rect.copy()
                    velocity = pygame.math.Vector2(self.vx, self.vy)

                    new_rect, new_velocity, collision_info_list = tile_collision.resolve_collisions(entity_rect, velocity, level.grid, dt)

                    self.rect = new_rect
                    self.vx = float(new_velocity.x)
                    self.vy = float(new_velocity.y)
                    
                    # Store previous ground state
                    self.was_on_ground = self.on_ground 
                    
                    # Reset collision states
                    self.on_ground = False              
                    self.on_left_wall = False
                    self.on_right_wall = False
                    
                    # FIRST PASS: Check if we have ground collision
                    has_ground_collision = any(c.get("side") == "top" for c in collision_info_list)
                    
                    # Update from collision results
                    for c in collision_info_list:
                        side = c.get("side")
                        if side == "top":
                            self.on_ground = True
                        elif side == "left":
                            # Only set wall flags if NOT on ground
                            if not has_ground_collision:
                                self.on_right_wall = True
                                self._right_wall_contact_frames = WALL_STICK_FRAMES
                        elif side == "right":
                            # Only set wall flags if NOT on ground
                            if not has_ground_collision:
                                self.on_left_wall = True
                                self._left_wall_contact_frames = WALL_STICK_FRAMES
                        elif side == "bottom":
                            self.on_ground = False
                    
                    # CRITICAL FIX: Clear wall flags AND wall_sliding if on ground
                    # Wall contact only matters when airborne (for wall jumps/slides)
                    if self.on_ground:
                        # DEBUG: Print when we clear wall flags
                        if self.on_left_wall or self.on_right_wall or self.wall_sliding:
                            logger.debug(f"CLEARING wall states - on_ground={self.on_ground}, was L={self.on_left_wall}, R={self.on_right_wall}, sliding={self.wall_sliding}")
                        self.on_left_wall = False
                        self.on_right_wall = False
                        self._left_wall_contact_frames = 0
                        self._right_wall_contact_frames = 0
                        self.wall_sliding = False  # Also clear wall_sliding when landing
                    else:
                        # Only check for nearby walls when airborne
                        if not (self.on_left_wall or self.on_right_wall):
                            self._detect_wall_proximity(level)
                            
                            # Maintain wall contact briefly to prevent flicker (only when airborne)
                            if not self.on_left_wall and self._left_wall_contact_frames > 0:
                                self.on_left_wall = True
                            if not self.on_right_wall and self._right_wall_contact_frames > 0:
                                self.on_right_wall = True

                    if self.on_ground: self.coyote = COYOTE_FRAMES
                    collisions = collision_info_list
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).exception("Tile collision error: %s", e)
                    self.rect.x += int(self.vx)
                    self.rect.y += int(self.vy)
                    self.was_on_ground = self.on_ground
                    self.on_ground = False
                    self.on_left_wall = False
                    self.on_right_wall = False
                    self._left_wall_contact_frames = 0
                    self._right_wall_contact_frames = 0
                    collisions = []
            else:
                self.rect.x += int(self.vx)
                self.rect.y += int(self.vy)
                self.was_on_ground = self.on_ground
                self.on_ground = False
                self.on_left_wall = False
                self.on_right_wall = False
                self._left_wall_contact_frames = 0
                self._right_wall_contact_frames = 0
                collisions = []

        try:
            self.last_tile_collisions = list(collisions) if collisions else []

        except Exception:
            self.last_tile_collisions = []

        speed_bonus = self.speed_potion_bonus if self.speed_potion_timer > 0 else 0.0
        cd_step = 1.0 + speed_bonus
        if self.dash_cd > 0:
            self.dash_cd = max(0.0, self.dash_cd - cd_step)
            # Restore a dash charge when cooldown finishes
            if self.dash_cd == 0 and self.dash_charges < self.dash_charges_max:
                self.dash_charges = min(self.dash_charges + 1, self.dash_charges_max)
        if self.skill_cd1 > 0: self.skill_cd1 = max(0.0, self.skill_cd1 - cd_step)
        if self.skill_cd2 > 0: self.skill_cd2 = max(0.0, self.skill_cd2 - cd_step)
        if self.skill_cd3 > 0: self.skill_cd3 = max(0.0, self.skill_cd3 - cd_step)
        if self.combo_t > 0: self.combo_t -= 1
        else: self.combo = 0

        if self.triple_timer > 0: self.triple_timer -= 1
        if self.speed_timer > 0: self.speed_timer -= 1
        if getattr(self, '_stamina_cooldown', 0) > 0: self._stamina_cooldown -= 1
        if getattr(self, '_teleport_cooldown', 0) > 0: self._teleport_cooldown -= 1

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
        
        if getattr(self, 'lucky_charm_timer', 0) > 0:
            self.lucky_charm_timer -= 1
            if self.lucky_charm_timer <= 0:
                self.lucky_charm_timer = 0

        # Update animations after all physics is resolved
        if self.anim_manager:
            if self.cls == 'Ranger':
                self._update_ranger_animations()
            elif self.cls == 'Knight':
                self._update_knight_animations()
            elif self.cls == 'Wizard':
                self._update_wizard_animations()
            self.anim_manager.update()

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

                # FIXED: Check for wall proximity even in no-clip mode (for wall jumps)
                # But only when not on ground and actually falling to prevent false wall detection
                if not self.on_ground and (self.vy >= 0 or self.coyote < COYOTE_FRAMES - 2):
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

        # FIXED: Improved wall detection - allow proximity attach even without fresh side collisions
        if not self.on_left_wall and not self.on_right_wall:
            self._detect_wall_proximity(level)
            if not self.on_left_wall and self._left_wall_contact_frames > 0:
                self.on_left_wall = True
            if not self.on_right_wall and self._right_wall_contact_frames > 0:
                self.on_right_wall = True


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



    def draw(self, surf, camera, debug_hitboxes=False):
        # For Ranger/Knight/Wizard with animation system, use sprite rendering
        if self.anim_manager and self.cls in ('Ranger', 'Knight', 'Wizard'):
            # Draw the animated sprite
            sprite_drawn = self.anim_manager.draw(surf, camera, show_invincibility=True)
            
            # If sprite failed to draw, fall back to rectangle
            if not sprite_drawn:
                self._draw_fallback_rect(surf, camera)
        else:
            # For other classes, use the rectangle rendering
            self._draw_fallback_rect(surf, camera)
        
        # Draw collision box outline in debug mode (F3)
        if debug_hitboxes:
            pygame.draw.rect(surf, (255, 140, 0), camera.to_screen_rect(self.rect), width=2)
        
        # Draw Ranger crosshair/aim line
        if self.cls == 'Ranger' and self.alive:
            self._draw_ranger_crosshair(surf, camera)
        
        # Draw Wizard crosshair and skill selection indicator
        if self.cls == 'Wizard' and self.alive:
            if self.selected_skill:
                self._draw_wizard_skill_indicator(surf, camera)
            else:
                # Draw normal crosshair when no skill is selected
                self._draw_wizard_crosshair(surf, camera)
        
        # Draw debug overlays
        self._draw_debug_wall_jump(surf)

    def _draw_fallback_rect(self, surf, camera):
        """Draw player as colored rectangle (fallback or for non-Ranger classes)"""
        # Change color for visual feedback
        if getattr(self, 'no_clip', False):
            if getattr(self, 'floating_mode', False):
                # Cyan color for floating mode
                col = (100, 255, 200) if not self.iframes_flash else (100, 255, 80)
            else:
                # Purple/magenta color for regular no-clip mode
                col = (200, 100, 255) if not self.iframes_flash else (200, 100, 80)
        # Check for wall sliding ONLY (not just wall contact)
        # Wall sliding requires: NOT on ground AND falling with positive velocity AND on a wall
        # This prevents flicker when touching walls on ground
        elif not self.on_ground and self.vy > 1.0 and (self.on_left_wall or self.on_right_wall):
            col = (100, 150, 255) if not self.iframes_flash else (100, 150, 80)  # Blue tint when wall sliding
        else:
            col = ACCENT if not self.iframes_flash else (ACCENT[0], ACCENT[1], 80)

        pygame.draw.rect(surf, col, camera.to_screen_rect(self.rect), border_radius=4)

    def _draw_ranger_crosshair(self, surf, camera):
        """Draw crosshair for Ranger class with skill-based variations"""
        mx, my = pygame.mouse.get_pos()
        
        # Check active skill states
        sniper_active = getattr(self, 'sniper_ready', False)
        triple_active = getattr(self, 'triple_timer', 0) > 0
        speed_active = getattr(self, 'speed_timer', 0) > 0
        
        # Determine crosshair color and style based on active skills
        if getattr(self, 'charging', False):
            charge_progress = min(1.0, self.charge_time / self.charge_threshold)
            # Gradient from yellow to red as charge increases
            r = int(255)
            g = int(255 * (1.0 - charge_progress * 0.5))
            b = int(50)
            crosshair_color = (r, g, b)
            crosshair_size = 8
        elif sniper_active:
            # SNIPER MODE: Red precision crosshair with scope lines
            crosshair_color = (255, 60, 60)
            crosshair_size = 12
            # Draw scope lines (longer, thinner)
            pygame.draw.line(surf, crosshair_color,
                            (mx - crosshair_size - 8, my),
                            (mx - crosshair_size, my), 1)
            pygame.draw.line(surf, crosshair_color,
                            (mx + crosshair_size, my),
                            (mx + crosshair_size + 8, my), 1)
            pygame.draw.line(surf, crosshair_color,
                            (mx, my - crosshair_size - 8),
                            (mx, my - crosshair_size), 1)
            pygame.draw.line(surf, crosshair_color,
                            (mx, my + crosshair_size),
                            (mx, my + crosshair_size + 8), 1)
            # Draw precision circle
            pygame.draw.circle(surf, crosshair_color, (mx, my), 6, 1)
            pygame.draw.circle(surf, crosshair_color, (mx, my), 2, 1)
            # Add "SNIPER" text above crosshair
            try:
                font = pygame.font.Font(None, 18)
                text_surf = font.render("SNIPER", True, (255, 60, 60))
                text_rect = text_surf.get_rect(center=(mx, my - 25))
                surf.blit(text_surf, text_rect)
            except:
                pass
        elif triple_active:
            # TRIPLE SHOT MODE: Orange multi-target crosshair
            crosshair_color = (255, 180, 80)
            crosshair_size = 8
            # Draw 3 crosshairs with slight offset (showing 3-arrow pattern)
            import math
            for offset_angle in [-8, 0, 8]:  # degrees
                angle_rad = math.radians(offset_angle)
                offset_x = int(math.sin(angle_rad) * 15)
                offset_y = int(-math.cos(angle_rad) * 15)
                cx, cy = mx + offset_x, my + offset_y
                # Small crosshair at each position
                pygame.draw.line(surf, crosshair_color,
                                (cx - 4, cy), (cx + 4, cy), 1)
                pygame.draw.line(surf, crosshair_color,
                                (cx, cy - 4), (cx, cy + 4), 1)
            # Central crosshair
            pygame.draw.circle(surf, crosshair_color, (mx, my), 3, 1)
        elif speed_active:
            # SPEED BOOST MODE: Green dynamic crosshair with motion lines
            crosshair_color = (100, 255, 200)
            crosshair_size = 8
            # Add motion blur effect (trailing lines)
            pygame.draw.line(surf, (100, 255, 200, 128),
                            (mx - crosshair_size - 4, my),
                            (mx - crosshair_size, my), 1)
            pygame.draw.line(surf, (100, 255, 200, 128),
                            (mx, my - crosshair_size - 4),
                            (mx, my - crosshair_size), 1)
        else:
            # DEFAULT: Light blue standard crosshair
            crosshair_color = (100, 200, 255)
            crosshair_size = 8
        
        # Draw standard crosshair (unless sniper, which draws custom)
        if not sniper_active:
            # Horizontal line
            pygame.draw.line(surf, crosshair_color,
                            (mx - crosshair_size, my),
                            (mx + crosshair_size, my), 2)
            # Vertical line
            pygame.draw.line(surf, crosshair_color,
                            (mx, my - crosshair_size),
                            (mx, my + crosshair_size), 2)
            
            # Draw center circle
            pygame.draw.circle(surf, crosshair_color, (mx, my), 3, 1)
    
    def _draw_wizard_skill_indicator(self, surf, camera):
        """Draw visual indicator when Wizard has a skill selected"""
        mx, my = pygame.mouse.get_pos()
        
        # Skill-specific colors and text
        skill_info = {
            'fireball': {'color': (255, 100, 50), 'name': 'FIREBALL', 'radius': 48},
            'coldfeet': {'color': (100, 200, 255), 'name': 'COLD FEET', 'radius': 48},
            'magic_missile': {'color': (200, 100, 255), 'name': 'MAGIC MISSILE', 'radius': 0}
        }
        
        if self.selected_skill not in skill_info:
            return
        
        info = skill_info[self.selected_skill]
        color = info['color']
        
        # Draw crosshair at mouse position
        crosshair_size = 10
        pygame.draw.line(surf, color, (mx - crosshair_size, my), (mx + crosshair_size, my), 3)
        pygame.draw.line(surf, color, (mx, my - crosshair_size), (mx, my + crosshair_size), 3)
        pygame.draw.circle(surf, color, (mx, my), 5, 2)
        
        # Draw AOE radius indicator for area skills
        if info['radius'] > 0:
            # Draw a translucent circle showing AOE range
            pygame.draw.circle(surf, color, (mx, my), info['radius'], 2)
            # Draw inner circle for visual effect
            pygame.draw.circle(surf, (*color, 128), (mx, my), info['radius'] // 2, 1)
        
        # Draw skill name above mouse
        try:
            font = pygame.font.Font(None, 24)
            text_surf = font.render(info['name'], True, color)
            text_rect = text_surf.get_rect(center=(mx, my - 40))
            # Draw text shadow
            shadow_surf = font.render(info['name'], True, (0, 0, 0))
            surf.blit(shadow_surf, (text_rect.x + 2, text_rect.y + 2))
            surf.blit(text_surf, text_rect)
        except:
            pass  # Fail silently if font rendering fails
    
    def _draw_wizard_crosshair(self, surf, camera):
        """Draw normal crosshair for Wizard when no skill is selected"""
        mx, my = pygame.mouse.get_pos()
        
        # Purple/arcane themed crosshair for Wizard
        crosshair_color = (180, 120, 255)
        crosshair_size = 8
        
        # Draw magical crosshair with a slight glow effect
        # Outer glow (dimmer, larger)
        glow_color = (140, 80, 200)
        pygame.draw.line(surf, glow_color,
                        (mx - crosshair_size - 2, my),
                        (mx + crosshair_size + 2, my), 1)
        pygame.draw.line(surf, glow_color,
                        (mx, my - crosshair_size - 2),
                        (mx, my + crosshair_size + 2), 1)
        
        # Main crosshair
        pygame.draw.line(surf, crosshair_color,
                        (mx - crosshair_size, my),
                        (mx + crosshair_size, my), 2)
        pygame.draw.line(surf, crosshair_color,
                        (mx, my - crosshair_size),
                        (mx, my + crosshair_size), 2)
        
        # Center dot
        pygame.draw.circle(surf, crosshair_color, (mx, my), 2, 0)
        
        # Add small corner markers for magical aesthetic
        corner_offset = 12
        corner_size = 3
        for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            cx = mx + dx * corner_offset
            cy = my + dy * corner_offset
            pygame.draw.line(surf, crosshair_color,
                           (cx - corner_size * dx, cy),
                           (cx, cy), 1)
            pygame.draw.line(surf, crosshair_color,
                           (cx, cy - corner_size * dy),
                           (cx, cy), 1)
    
    def _draw_debug_wall_jump(self, surf):
        """DEBUG: Draw wall jump state indicators (remove in production)"""
        if getattr(self, '_debug_wall_jump', False):
            font = pygame.font.Font(None, 16)
            y_offset = 0
            
            # Ground state
            ground_text = f"Ground: {self.on_ground}"
            text_surf = font.render(ground_text, True, (255, 255, 255))
            surf.blit(text_surf, (10, 10 + y_offset))
            y_offset += 20
            
            # Wall state
            wall_text = f"LWall: {self.on_left_wall} RWall: {self.on_right_wall}"
            text_surf = font.render(wall_text, True, (255, 255, 255))
            surf.blit(text_surf, (10, 10 + y_offset))
            y_offset += 20
            
            # Wall sliding state
            slide_text = f"Sliding: {self.wall_sliding}"
            text_surf = font.render(slide_text, True, (255, 255, 255))
            surf.blit(text_surf, (10, 10 + y_offset))
            y_offset += 20
            
            # Jump buffer
            buffer_text = f"JumpBuf: {self.jump_buffer}"
            text_surf = font.render(buffer_text, True, (255, 255, 255))
            surf.blit(text_surf, (10, 10 + y_offset))
            y_offset += 20
            
            # Coyote time
            coyote_text = f"Coyote: {self.coyote}"
            text_surf = font.render(coyote_text, True, (255, 255, 255))
            surf.blit(text_surf, (10, 10 + y_offset))

    def _detect_wall_proximity(self, level) -> None:
        """Keep wall contact active when the player is adjacent without active horizontal input."""
        if self.wall_reattach_timer != 0:
            return

        if self.on_ground:
            return

        # Only allow attachment when falling or shortly after leaving ground to avoid ceiling grabs
        is_valid_air_state = self.vy >= 0 or self.coyote < COYOTE_FRAMES - 2
        if not is_valid_air_state:
            return

        solids = getattr(level, 'solids', None)
        if not solids:
            return

        expanded_rect = self.rect.inflate(2, 0)
        for solid in solids:
            if not expanded_rect.colliderect(solid):
                continue

            if self.rect.centerx < solid.centerx:
                if abs(self.rect.right - solid.left) <= 3:
                    self.on_right_wall = True
                    self._right_wall_contact_frames = WALL_STICK_FRAMES
                    return
            else:
                if abs(self.rect.left - solid.right) <= 3:
                    self.on_left_wall = True
                    self._left_wall_contact_frames = WALL_STICK_FRAMES
                    return

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

    @property
    def hp(self):
        return self.combat.hp

    @hp.setter
    def hp(self, value):
        self.combat.hp = value

    @property
    def max_hp(self):
        return self.combat.max_hp

    @max_hp.setter
    def max_hp(self, value):
        self.combat.max_hp = value
