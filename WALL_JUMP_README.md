# Wall Jump and Wall Slide System

## Overview
This game now features a wall jump and wall slide system similar to Super Meat Boy.

## How It Works

### Wall Slide
- When the player jumps and touches a wall, they will stick to it for a brief moment
- While touching the wall, the player slides down at a reduced speed
- The player turns blue when wall sliding for visual feedback

### Wall Jump
- While wall sliding, press the jump button (Space/K) to jump away from the wall.
- The wall jump provides strong horizontal momentum away from the wall.
- After a wall jump, there's a brief cooldown before the player can stick to walls again.
- NEW: Immediately after a wall jump, there is a short "float window":
  - Duration: `WALL_JUMP_FLOAT_FRAMES` (default 10 frames).
  - During this window, upward movement uses reduced gravity (`WALL_JUMP_FLOAT_GRAVITY_SCALE`, default 0.32),
    giving a small airborne/slow-mo feel while preserving the strong outward push.
  - The float only applies while the player is still traveling upward; once they start falling or the timer ends,
    normal gravity resumes.
  - The float phase is canceled if:
    - The player re-enters a wall slide.
    - A dash ends while airborne.

### Wall Jump Airborne Window
- NEW: After performing a wall jump, the player enters a 30-frame (0.5 second) airborne window.
- During this airborne window, the player can choose ONE free action:
  - **Free Jump**: Press jump again to perform an additional jump without consuming a double jump charge.
  - **Free Dash**: Press dash to perform a dash without consuming stamina or triggering normal dash cooldown.
- The airborne window is indicated by an orange cooldown bar above the dash cooldown bar.
- Once the free action is used or the window expires, the player returns to normal movement mechanics.
- This allows for enhanced mobility and combo potential after wall jumps.

## Controls
- **A/D**: Move left/right
- **Space/K**: Jump (also wall jump when sliding)
- **Shift/J**: Dash

## Configuration Parameters
- `WALL_SLIDE_SPEED`: Maximum speed while sliding down wall (2.0)
- `WALL_JUMP_H_SPEED`: Horizontal velocity for wall jump (6.5)
- `WALL_JUMP_V_SPEED`: Vertical velocity for wall jump (-9.5)
- `WALL_STICK_TIME`: Frames player sticks to wall after leaving ground (6)
- `WALL_JUMP_COOLDOWN`: Frames before player can stick to wall again after wall jump (16)
- `WALL_JUMP_FLOAT_FRAMES`: Duration of reduced gravity float after wall jump (10)
- `WALL_JUMP_FLOAT_GRAVITY_SCALE`: Gravity multiplier during float phase (0.32)
- `WALL_JUMP_CONTROL_FRAMES`: Duration of enhanced air control after wall jump (18)
- `WALL_JUMP_AIRBORNE_FRAMES`: Duration of airborne window for free action (45)
- `WALL_JUMP_AIRBORNE_COLOR`: Color of wall jump cooldown bar (orange: 255, 165, 0)

## Technical Implementation

### Wall Detection
The system detects wall collisions in the `move_and_collide()` method:
- `on_left_wall`: True when touching a wall on the left
- `on_right_wall`: True when touching a wall on the right

### Wall Slide State
The player enters wall slide state when:
- Not on ground
- Wall stick timer is active
- Touching either left or right wall

### Wall Jump Mechanics
When wall sliding and jump is pressed:
- Jump horizontally away from the wall
- Apply wall jump velocities
- Set cooldown to prevent immediate re-sticking

## Visual Feedback
- Player turns blue when wall sliding
- Normal color when not sliding
- Maintains invincibility flashing when damaged

## Testing Tips
1. Jump towards a wall to initiate wall slide
2. Press jump while sliding to perform wall jump
3. Try chaining wall jumps between parallel walls
4. Test different timing for optimal wall jumps
5. **NEW**: After wall jumping, immediately press jump again to test the free airborne jump
6. **NEW**: After wall jumping, immediately press dash to test the free airborne dash
7. **NEW**: Wait for the 0.75 second airborne window to expire and test normal movement
8. **NEW**: Try returning to a wall before the wall jump cooldown expires to test cooldown mechanics
9. **NEW**: Observe the orange cooldown bar positioned above the cyan dash bar during wall jump cooldown