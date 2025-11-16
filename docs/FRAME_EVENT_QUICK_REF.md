# Frame Event Mapping - Quick Reference

## What is Frame Event Mapping?

Frame event mapping lets you trigger actions (like spawning hitboxes) at **specific animation frames**, ensuring attacks feel responsive and synchronized with visuals.

**Without frame events:** Hitbox spawns immediately → doesn't match animation → feels bad  
**With frame events:** Hitbox spawns when sword visually swings → perfect sync → feels great

---

## Quick Start (3 Steps)

### 1. Load Animation (already doing this)
```python
self.anim_manager.load_animation(
    AnimationState.ATTACK,
    attack_frame_paths,
    sprite_size=(96, 96),
    frame_duration=3,
    loop=False,
    next_state=AnimationState.IDLE
)
```

### 2. Create Hitbox Spawn Function
```python
def spawn_sword_slash(self):
    hitbox = Hitbox(
        self.rect.centerx + (30 * self.facing),
        self.rect.centery,
        40, 40,
        damage=self.attack_damage,
        owner=self,
        lifetime=8
    )
    hitboxes.append(hitbox)
```

### 3. Map Hitbox to Animation Frame
```python
# Spawn hitbox on frame 5 (0-based, so 6th frame)
self.anim_manager.set_attack_frame(
    AnimationState.ATTACK,
    5,  # Frame number where sword swings through
    self.spawn_sword_slash
)
```

**Done!** Now hitbox spawns automatically at the perfect frame.

---

## Core Methods

| Method | Purpose | Example |
|--------|---------|---------|
| `set_attack_frame(state, frame, callback)` | Spawn hitbox at frame | `self.anim_manager.set_attack_frame(AnimationState.ATTACK, 5, self.spawn_hitbox)` |
| `set_frame_event(state, frame, callback)` | Any action at frame | `self.anim_manager.set_frame_event(AnimationState.SKILL_1, 8, self.heal_player)` |
| `get_current_frame_index()` | Check current frame | `frame = self.anim_manager.get_current_frame_index()` |
| `is_on_frame(frame)` | Is on specific frame? | `if self.anim_manager.is_on_frame(5): ...` |

---

## Common Patterns

### Pattern 1: Basic Attack
```python
# In __init__:
self.anim_manager.set_attack_frame(AnimationState.ATTACK, 5, self.spawn_hitbox)

# Hitbox spawns automatically when attack plays!
```

### Pattern 2: Item Usage (Health Flask)
```python
# In use_health_flask():
self.anim_manager.play(AnimationState.SKILL_1, force=True)

def heal():
    self.combat.hp = min(self.combat.max_hp, self.combat.hp + 3)

self.anim_manager.set_frame_event(AnimationState.SKILL_1, 8, heal)
```

### Pattern 3: Multi-Hit Combo
```python
# Hit 1 on frame 3
self.anim_manager.set_frame_event(AnimationState.ATTACK, 3, 
    lambda: self.spawn_hit(damage=2))

# Hit 2 on frame 8
self.anim_manager.set_frame_event(AnimationState.ATTACK, 8,
    lambda: self.spawn_hit(damage=3))

# Hit 3 on frame 13
self.anim_manager.set_frame_event(AnimationState.ATTACK, 13,
    lambda: self.spawn_hit(damage=5))
```

### Pattern 4: Equipment Changes Timing
```python
def equip_dagger(self):
    # Fast weapon - early frame
    self.anim_manager.set_attack_frame(AnimationState.ATTACK, 2, self.spawn_hitbox)

def equip_hammer(self):
    # Slow weapon - late frame (long windup)
    self.anim_manager.set_attack_frame(AnimationState.ATTACK, 10, self.spawn_hitbox)
```

---

## How to Find the Perfect Frame

### Method 1: Visual Inspection
1. Run the game
2. Trigger attack animation
3. Watch which frame the weapon swings through
4. Try frame 5-6 for 12-frame animation (roughly 50%)

### Method 2: Debug Print
```python
# In tick():
if self.anim_manager.current_state == AnimationState.ATTACK:
    frame = self.anim_manager.get_current_frame_index()
    print(f"Attack frame: {frame}")
```

Watch the numbers scroll and note when the swing happens visually.

### Method 3: Trial and Error
Start with frame 5, test it, adjust up/down until it feels right.

---

## Common Frame Timings

| Animation Length | Mid-Point Frame | Use For |
|------------------|-----------------|---------|
| 6 frames | 3 | Fast attacks |
| 9 frames | 4-5 | Medium attacks |
| 12 frames | 5-6 | Normal attacks |
| 15 frames | 7-8 | Heavy attacks |
| 20 frames | 10-12 | Very slow attacks |

**Rule of thumb:** Spawn hitbox at **40-60% through animation**

---

## Important Notes

✅ **Frame index is 0-based** (first frame = 0, second frame = 1, etc.)  
✅ **Events auto-reset** when animation restarts (no cleanup needed)  
✅ **Multiple events per frame** are supported (sound + hitbox + particles)  
✅ **Events only fire once** per animation playthrough  
✅ **Works for players AND enemies**  

❌ Don't use frame events on looping animations (unless you want repeated triggers)  
❌ Don't spawn hitbox in attack() method anymore - use frame events instead  

---

## Before & After Comparison

### BEFORE (Old Way - Bad)
```python
def attack(self):
    if self.attack_cd <= 0:
        self.attack_cd = ATTACK_COOLDOWN
        
        # Play animation
        self.anim_manager.play(AnimationState.ATTACK, force=True)
        
        # Spawn hitbox IMMEDIATELY (doesn't match animation!)
        hitbox = Hitbox(...)
        hitboxes.append(hitbox)
```

### AFTER (New Way - Good)
```python
def __init__(self):
    # ... load animation ...
    
    # Map hitbox to frame 5
    self.anim_manager.set_attack_frame(AnimationState.ATTACK, 5, self.spawn_hitbox)

def spawn_hitbox(self):
    hitbox = Hitbox(...)
    hitboxes.append(hitbox)

def attack(self):
    if self.attack_cd <= 0:
        self.attack_cd = ATTACK_COOLDOWN
        # Just play animation - hitbox spawns automatically at frame 5!
        self.anim_manager.play(AnimationState.ATTACK, force=True)
```

---

## Troubleshooting

**Hitbox spawns multiple times:**
- Events reset on loop - ensure `loop=False` for attack animations

**Hitbox never spawns:**
- Check frame index (0-based, not 1-based!)
- Verify animation has that many frames
- Check console for warnings

**Timing feels off:**
- Try frame +/- 1
- Adjust `frame_duration` to speed up/slow down animation
- Use debug prints to find exact frame

---

## See Also

- `FRAME_EVENT_MAPPING_GUIDE.md` - Full detailed guide with examples
- `ANIMATION_SYSTEM_SUMMARY.txt` - Animation system overview
- `PLAYER_ANIMATION_GUIDE.md` - Player-specific animation setup
- `SPRITE_ANIMATION_GUIDE.md` - Enemy animation examples

---

**TL;DR:** Use `set_attack_frame()` to spawn hitboxes at the perfect animation frame. No more manual timing!
