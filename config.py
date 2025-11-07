# === Global configuration & tuning ===
WIDTH, HEIGHT = 960, 540
FPS = 60

# Colors
BG = (18, 20, 27)
TILE_COL = (54, 60, 78)
ACCENT = (255, 199, 95)
RED = (220, 72, 72)
GREEN = (80, 200, 120)
WHITE = (240, 240, 240)
CYAN = (80, 220, 220)

# Physics & player tuning
GRAVITY = 0.45
TERMINAL_VY = 18
PLAYER_SPEED = 4.2
PLAYER_AIR_SPEED = 3.6
PLAYER_JUMP_V = -10.2
PLAYER_SMALL_JUMP_CUT = 0.6
COYOTE_FRAMES = 8
JUMP_BUFFER_FRAMES = 8

# Air control tuning (for momentum preservation)
AIR_ACCEL = 0.4  # Horizontal acceleration in air
AIR_FRICTION = 0.98  # Slight decay when no input
MAX_AIR_SPEED = 5.5  # Cap on air |vx| (allows wall jump boosts)

DASH_SPEED = 12.0
DASH_TIME = 10
DASH_COOLDOWN = 24

# Shared mobility cooldown:
# Any ground jump, double jump, wall jump, or dash will start this cooldown,
# during which all of these mobility actions are locked.
MOBILITY_COOLDOWN_FRAMES = 10  # tweak for feel

# Player invincibility frames after taking damage (0.5s)
INVINCIBLE_FRAMES = int(0.5 * FPS)
# Blink interval during i-frames (seconds -> frames)
IFRAME_BLINK_INTERVAL = int(0.1 * FPS)
DOUBLE_JUMPS = 1

ATTACK_COOLDOWN = 10
ATTACK_LIFETIME = 7
COMBO_RESET = 18
SWORD_DAMAGE = 1
POGO_BOUNCE_VY = -11.5

# Wall jump and wall slide mechanics
WALL_SLIDE_SPEED = 2.0      # Maximum speed while sliding down wall
WALL_JUMP_H_SPEED = 6.5     # Horizontal velocity for wall jump (softer, less "cannon" feel)
WALL_JUMP_V_SPEED = -9.5    # Vertical velocity for wall jump
WALL_STICK_TIME = 6         # Frames player sticks to wall after leaving ground
WALL_JUMP_COOLDOWN = 16     # Frames before player can stick to wall again after wall jump

# Wall jump float & control tuning
WALL_JUMP_FLOAT_FRAMES = 10             # Slightly longer float for softer vertical arc
WALL_JUMP_FLOAT_GRAVITY_SCALE = 0.32    # Reduced gravity during float
WALL_JUMP_CONTROL_FRAMES = 18           # During this window, wall jump is more steerable & clamped

# Wall jump airborne window mechanics
WALL_JUMP_AIRBORNE_FRAMES = 45          # 0.75 second airborne window after wall jump for free action
WALL_JUMP_AIRBORNE_COLOR = (255, 165, 0)  # Orange color for wall jump cooldown bar

TILE = 24
