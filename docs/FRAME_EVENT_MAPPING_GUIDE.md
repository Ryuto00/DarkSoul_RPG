# Frame Event Mapping Guide

## Overview

The Animation System now supports **frame event mapping** - the ability to trigger specific actions (like spawning hitboxes, playing sounds, or item effects) at precise animation frames. This ensures attacks, skills, and item usage feel responsive and properly synchronized with their visual animations.

## Why Use Frame Events?

Without frame events:
- Attack hitbox spawns immediately when attack button is pressed
- Doesn't match the visual animation (sword hasn't swung yet)
- Feels unresponsive and disconnected

With frame events:
- Attack hitbox spawns exactly when the sword visually swings through
- Perfect synchronization between animation and gameplay
- Feels polished and professional

## Core Methods

### `set_frame_event(state, frame_index, callback)`

Register a callback to trigger at a specific animation frame.

```python
def spawn_attack():
    hitbox = Hitbox(self.rect.centerx, self.rect.centery, ...)
    hitboxes.append(hitbox)

# Trigger on frame 5 (0-based indexing)
self.anim_manager.set_frame_event(AnimationState.ATTACK, 5, spawn_attack)
```

### `set_attack_frame(state, frame_index, spawn_hitbox_callback)`

Convenience method specifically for attack animations.

```python
self.anim_manager.set_attack_frame(AnimationState.ATTACK, 6, self.spawn_sword_slash)
```

### `get_current_frame_index()`

Get the current animation frame (0-based).

```python
current_frame = self.anim_manager.get_current_frame_index()
print(f"Currently on frame {current_frame}")
```

### `is_on_frame(frame_index)`

Check if animation is on a specific frame.

```python
if self.anim_manager.is_on_frame(5):
    # Do something on frame 5
    pass
```

## Example 1: Knight Melee Attack

12-frame attack animation where the sword swings through on frame 6.

```python
class Knight(Player):
    def __init__(self, x, y):
        super().__init__(x, y, cls='Knight')
        
        # Load attack animation (12 frames)
        attack_frames = [
            "assets/Player/Knight/Attack/Warrior_Attack_4.png",
            "assets/Player/Knight/Attack/Warrior_Attack_5.png",
            "assets/Player/Knight/Attack/Warrior_Attack_6.png",
            "assets/Player/Knight/Attack/Warrior_Attack_7.png",
            "assets/Player/Knight/Attack/Warrior_Attack_8.png",
            "assets/Player/Knight/Attack/Warrior_Attack_9.png",
            "assets/Player/Knight/Attack/Warrior_Attack_10.png",
            "assets/Player/Knight/Attack/Warrior_Attack_11.png",
            "assets/Player/Knight/Attack/Warrior_Attack_12.png",
        ]
        
        self.anim_manager.load_animation(
            AnimationState.ATTACK,
            attack_frames,
            sprite_size=(96, 96),
            frame_duration=3,  # 3 game frames per sprite frame
            loop=False,
            next_state=AnimationState.IDLE
        )
        
        # Spawn hitbox on frame 6 (when sword is mid-swing)
        self.anim_manager.set_attack_frame(
            AnimationState.ATTACK,
            6,
            self.spawn_sword_slash
        )
    
    def spawn_sword_slash(self):
        """Create sword slash hitbox"""
        hitbox = Hitbox(
            self.rect.centerx + (30 * self.facing),  # In front of player
            self.rect.centery,
            40, 40,
            damage=self.attack_damage,
            owner=self,
            lifetime=8
        )
        hitboxes.append(hitbox)
    
    def attack(self):
        """Trigger attack"""
        if self.attack_cd <= 0:
            self.attack_cd = ATTACK_COOLDOWN
            self.anim_manager.play(AnimationState.ATTACK, force=True)
            # Hitbox will spawn automatically on frame 6!
```

## Example 2: Ranger Bow Shot

Charge → Shoot animation where arrow spawns on frame 2 of shoot animation.

```python
class Ranger(Player):
    def __init__(self, x, y):
        super().__init__(x, y, cls='Ranger')
        
        # Load shoot animation (3 frames)
        shoot_frames = [
            "assets/Player/Ranger/attk-adjust/shoot/na-5.png",
            "assets/Player/Ranger/attk-adjust/shoot/na-6.png",
        ]
        
        self.anim_manager.load_animation(
            AnimationState.SHOOT,
            shoot_frames,
            sprite_size=(64, 64),
            frame_duration=4,
            loop=False,
            next_state=AnimationState.IDLE
        )
        
        # Spawn arrow projectile on frame 1 (when bow releases)
        self.anim_manager.set_attack_frame(
            AnimationState.SHOOT,
            1,
            self.spawn_arrow
        )
    
    def spawn_arrow(self):
        """Create arrow projectile"""
        arrow = Hitbox(
            self.rect.centerx + (20 * self.facing),
            self.rect.centery - 10,
            16, 4,
            damage=self.attack_damage,
            owner=self,
            lifetime=60,
            vx=12 * self.facing  # Projectile velocity
        )
        hitboxes.append(arrow)
    
    def release_shot(self):
        """Release charged shot"""
        if self.charging and self.charge_time >= self.charge_threshold:
            self.charging = False
            self.anim_manager.play(AnimationState.SHOOT, force=True)
            # Arrow spawns automatically on frame 1!
```

## Example 3: Item Usage with Animation

Health flask with drinking animation.

```python
class Player:
    def use_health_flask(self):
        """Use health flask with animation"""
        if self.health_flasks <= 0:
            return
        
        self.health_flasks -= 1
        
        # Play drinking animation
        self.anim_manager.play(AnimationState.SKILL_1, force=True)
        
        # Heal on frame 8 (when flask tilts to mouth)
        def apply_healing():
            old_hp = self.combat.hp
            self.combat.hp = min(self.combat.max_hp, self.combat.hp + 3)
            heal_amount = self.combat.hp - old_hp
            floating.append(DamageNumber(
                self.rect.centerx,
                self.rect.top - 10,
                f"+{heal_amount}",
                GREEN
            ))
        
        self.anim_manager.set_frame_event(
            AnimationState.SKILL_1,
            8,
            apply_healing
        )
```

## Example 4: Enemy with Multi-Hit Combo

Enemy with 3-hit combo attack.

```python
class SwordEnemy(Enemy):
    def __init__(self, x, y):
        super().__init__(x, y)
        
        # 15-frame combo animation with 3 strikes
        combo_frames = load_numbered_frames("assets/enemy/combo_", 1, 15)
        
        self.anim_manager.load_animation(
            AnimationState.ATTACK,
            combo_frames,
            sprite_size=(96, 128),
            frame_duration=3,
            loop=False,
            next_state=AnimationState.IDLE
        )
        
        # First strike on frame 3
        self.anim_manager.set_frame_event(
            AnimationState.ATTACK,
            3,
            lambda: self.spawn_hitbox(damage=2)
        )
        
        # Second strike on frame 8
        self.anim_manager.set_frame_event(
            AnimationState.ATTACK,
            8,
            lambda: self.spawn_hitbox(damage=3)
        )
        
        # Final strike on frame 13
        self.anim_manager.set_frame_event(
            AnimationState.ATTACK,
            13,
            lambda: self.spawn_hitbox(damage=5)
        )
    
    def spawn_hitbox(self, damage):
        """Spawn attack hitbox"""
        hitbox = Hitbox(
            self.rect.centerx + (40 * self.facing),
            self.rect.centery,
            50, 50,
            damage=damage,
            owner=self,
            lifetime=6
        )
        hitboxes.append(hitbox)
```

## Example 5: Multiple Events per Frame

Sound effects + particle effects + hitbox all on same frame.

```python
class SpecialAttack:
    def __init__(self):
        # Load special attack animation
        self.anim_manager.load_animation(...)
        
        # Frame 10: Sound + particles + hitbox
        self.anim_manager.set_frame_event(
            AnimationState.SKILL_2,
            10,
            self.play_slash_sound
        )
        self.anim_manager.set_frame_event(
            AnimationState.SKILL_2,
            10,
            self.spawn_slash_particles
        )
        self.anim_manager.set_frame_event(
            AnimationState.SKILL_2,
            10,
            self.spawn_slash_hitbox
        )
    
    def play_slash_sound(self):
        # Play sword slash sound effect
        pass
    
    def spawn_slash_particles(self):
        # Create particle effect
        pass
    
    def spawn_slash_hitbox(self):
        # Spawn damage hitbox
        pass
```

## Example 6: Item Modifier Attack Mapping

Equipment that modifies attack behavior.

```python
class Player:
    def equip_fire_sword(self):
        """Equip fire sword - modifies attack"""
        self.has_fire_sword = True
        
        # Remove old attack event
        # (Frame events automatically reset when animation restarts)
        
        # Add fire sword event on frame 6
        def spawn_fire_slash():
            # Normal hitbox
            hitbox = Hitbox(
                self.rect.centerx + (30 * self.facing),
                self.rect.centery,
                40, 40,
                damage=self.attack_damage + 2,  # Fire sword bonus
                owner=self,
                lifetime=8
            )
            hitboxes.append(hitbox)
            
            # Fire particle effect
            for i in range(5):
                particle = create_fire_particle(...)
                particles.append(particle)
        
        self.anim_manager.set_attack_frame(
            AnimationState.ATTACK,
            6,
            spawn_fire_slash
        )
    
    def equip_ice_hammer(self):
        """Equip ice hammer - different timing"""
        self.has_ice_hammer = True
        
        # Ice hammer is slower - hitbox on frame 10 instead
        def spawn_ice_smash():
            hitbox = Hitbox(
                self.rect.centerx + (20 * self.facing),
                self.rect.bottom,
                60, 30,  # Wide ground smash
                damage=self.attack_damage + 4,
                owner=self,
                lifetime=12
            )
            hitboxes.append(hitbox)
            
            # Freeze effect
            self.apply_area_freeze(...)
        
        self.anim_manager.set_attack_frame(
            AnimationState.ATTACK,
            10,  # Later frame for heavier weapon
            spawn_ice_smash
        )
```

## Best Practices

### 1. **Match Visual to Gameplay**
- Spawn hitbox when weapon visually connects
- For sword: Mid-swing (usually frame 40-60% of animation)
- For bow: When arrow releases from string
- For magic: When spell projectile appears

### 2. **Frame Index is 0-Based**
```python
# 12-frame animation: frames 0-11
# Middle frame is 5 or 6
self.anim_manager.set_attack_frame(AnimationState.ATTACK, 5, callback)
```

### 3. **Events Auto-Reset on Animation Restart**
- Events only fire once per animation playthrough
- When animation loops or restarts, events reset automatically
- No need to manually clear events

### 4. **Multiple Events Per Frame**
- Call `set_frame_event` multiple times for same frame
- All callbacks will execute in order registered

### 5. **Error Handling**
- Invalid frame index prints warning but doesn't crash
- Callback exceptions are caught and logged
- Game continues even if event fails

### 6. **Debugging**
```python
# Check current frame during gameplay
print(f"Current frame: {self.anim_manager.get_current_frame_index()}")

# Check if on specific frame
if self.anim_manager.is_on_frame(5):
    print("On attack frame!")
```

## Common Frame Timings

### Fast Attack (8 frames total)
- Frame 3-4: Hitbox spawn (mid-swing)

### Medium Attack (12 frames total)
- Frame 5-6: Hitbox spawn (mid-swing)

### Heavy Attack (20 frames total)
- Frame 12-15: Hitbox spawn (late swing, more windup)

### Projectile Attack
- Frame 1-2: Release projectile (early in animation)

### Multi-Hit Combo
- Distribute evenly: frames 3, 8, 13 for 15-frame animation

### Item Usage
- Frame 8-10: Apply effect (mid-animation)

## Integration with Existing Code

This system works seamlessly with:
- ✅ CombatComponent damage system
- ✅ Lifesteal and on-hit effects
- ✅ Combo system
- ✅ Pogo mechanics
- ✅ Invincibility frames
- ✅ Item modifiers
- ✅ Equipment bonuses

## Performance Notes

- Frame event checking is O(1) lookup (dictionary)
- Event triggering uses set for duplicate prevention
- Minimal overhead even with many events
- Safe for 60 FPS gameplay

## Troubleshooting

**Hitbox spawns multiple times:**
- Events auto-reset, but check if animation is looping unexpectedly
- Ensure `loop=False` for attack animations

**Hitbox never spawns:**
- Check frame index (0-based, not 1-based)
- Verify animation has that many frames
- Check console for warnings

**Timing feels off:**
- Adjust `frame_duration` to speed up/slow down animation
- Try different frame indices (earlier/later in animation)
- Use `get_current_frame_index()` to debug

**Events fire on loop:**
- Expected behavior for looping animations
- Events reset when animation loops
- Use `loop=False` if you don't want this

## Next Steps

1. Load your attack animation
2. Identify the perfect frame visually
3. Use `set_attack_frame()` to spawn hitbox
4. Test and adjust frame index as needed
5. Add sound effects, particles, etc. on same frame

See `PLAYER_ANIMATION_GUIDE.md` and `SPRITE_ANIMATION_GUIDE.md` for more animation setup examples.
