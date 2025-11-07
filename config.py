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

DASH_SPEED = 12.0
DASH_TIME = 10
DASH_COOLDOWN = 24
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

TILE = 24
