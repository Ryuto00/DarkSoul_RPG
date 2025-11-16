# === Global configuration & tuning ===
WIDTH, HEIGHT = 960, 540
FPS = 60

# Colors
BG = (18, 20, 27)  # Fallback background color
TILE_COL = (54, 60, 78)

# Background image
BACKGROUND_IMAGE_PATH = "assets/background/ds32.png"
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

# Wall jump and wall slide mechanics - NEW PHYSICS-BASED SYSTEM
WALL_SLIDE_SPEED = 1.5          # Controlled descent speed when sliding
WALL_SLIDE_GRAVITY_SCALE = 0.3  # Reduced gravity while on wall for controlled slide

# Wall jump physics (acceleration-based instead of instant velocity)
WALL_JUMP_H_ACCEL = 0.6         # Horizontal acceleration away from wall
WALL_JUMP_H_MAX_SPEED = 4.0     # Maximum horizontal speed (gentler than old 7.5)
WALL_JUMP_V_SPEED = -10.5       # Initial vertical jump velocity
WALL_JUMP_GRAVITY_SCALE = 0.8   # Gravity scale during wall jump ascent

# Wall jump timing and forgiveness
WALL_JUMP_COYOTE_TIME = 8       # Frames after leaving wall you can still jump
WALL_JUMP_BUFFER_TIME = 6       # Frames jump input is remembered when touching wall
WALL_JUMP_COOLDOWN = 10         # Minimum frames between wall jumps
WALL_REATTACH_TIME = 8          # Minimum frames before can reattach to wall

# Wall slide and control
WALL_LEAVE_H_BOOST = 2.0        # Gentle initial push to detach from wall
WALL_CONTROL_MULTIPLIER = 1.5   # Enhanced air control during wall jump
WALL_STICK_FRAMES = 4           # Frames player "sticks" to wall for precision

TILE = 24

# === Tile System Constants ===
# Tile type values for the grid system
TILE_AIR = 0          # Empty/air - no collision
TILE_WALL = 1         # Wall - full collision from all sides

# Tile colors for visual distinction
TILE_COLORS = {
    TILE_AIR: None,           # Transparent - no rendering
    TILE_WALL: (54, 60, 78),    # Dark gray - full wall
}

# === Procedural Level Generation Configuration ===
# Level generation parameters
LEVEL_WIDTH = 40  # tiles
LEVEL_HEIGHT = 30  # tiles
LEVEL_TYPE = "dungeon"  # "dungeon", "cave", "outdoor", "hybrid"
DIFFICULTY = 1  # 1=Easy, 2=Normal, 3=Hard

# Generation algorithm weights
ROOM_DENSITY = 0.6  # Fraction of level filled with rooms
CORRIDOR_WIDTH = 2  # Width of corridors in tiles
ENEMY_DENSITY = 0.8  # Base enemy density multiplier
TREASURE_DENSITY = 0.3  # Base treasure density multiplier

# Terrain generation parameters
TERRAIN_VARIATION = 0.4  # How much terrain varies (0-1)
SPECIAL_TERRAIN_CHANCE = 0.1  # Chance of special terrain features

# Validation parameters
MAX_VALIDATION_ATTEMPTS = 10  # Maximum attempts to validate/repair level
REPAIR_ATTEMPTS = 3  # Maximum repair attempts before regeneration

# Performance targets
GENERATION_TIME_TARGET = 100  # Target generation time in milliseconds
VALIDATION_SUCCESS_RATE = 0.95  # Target validation success rate

# Level type templates
LEVEL_TYPES = ["dungeon", "cave", "outdoor", "hybrid"]
DIFFICULTY_LEVELS = [1, 2, 3]  # Easy, Normal, Hard
