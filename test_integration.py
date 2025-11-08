"""
Integration tests for the procedural generation system.

Focus:
- End-to-end generation via LevelGenerator and generate_procedural_level
- Menu/Game configuration integration (without opening real windows)
- Backward compatibility: legacy Level fallback remains functional
- Graceful behavior when generation fails
- Full generation + validation pipeline testing
- Testing the three critical fixes: boundary, portal, enemies
"""

import types

from level_generator import (
    LevelGenerator,
    GeneratedLevel,
    generate_procedural_level,
)
from level import Level as LegacyLevel
from level_validator import LevelValidator
from menu import Menu
from main import Game
from config import (
    LEVEL_WIDTH,
    LEVEL_HEIGHT,
    LEVEL_TYPE,
    DIFFICULTY,
    TILE,
)


def _assert_generated_level_shape(level: GeneratedLevel):
    assert isinstance(level, GeneratedLevel)
    assert level.grid, "GeneratedLevel.grid is empty"
    h = len(level.grid)
    w = len(level.grid[0])
    assert h == LEVEL_HEIGHT, f"Generated grid height {h} != {LEVEL_HEIGHT}"
    assert w == LEVEL_WIDTH, f"Generated grid width {w} != {LEVEL_WIDTH}"
    assert hasattr(level, "solids") and level.solids, "GeneratedLevel must expose solids"
    assert hasattr(level, "spawn"), "GeneratedLevel must expose spawn"
    assert hasattr(level, "doors"), "GeneratedLevel must expose doors"
    assert isinstance(level.w, int) and isinstance(level.h, int)


def test_generate_procedural_level_function():
    """Smoke test the convenience wrapper used by external systems."""
    level = generate_procedural_level(
        level_index=0,
        level_type=LEVEL_TYPE,
        difficulty=DIFFICULTY,
        seed=42,
    )
    _assert_generated_level_shape(level)


def test_level_generator_end_to_end():
    """Direct LevelGenerator end-to-end generation with validation/terrain."""
    gen = LevelGenerator(width=LEVEL_WIDTH, height=LEVEL_HEIGHT)
    gen.set_world_seed(1234)

    lvl = gen.generate_level(
        level_index=1,
        level_type="dungeon",
        difficulty=2,
        seed=1234,
    )
    _assert_generated_level_shape(lvl)

    # Ensure stats are populated
    stats = gen.get_generation_stats()
    assert "generation_time_ms" in stats
    assert "validation_attempts" in stats
    assert "world_seed" in stats
    assert "seed_info" in stats


# NEW INTEGRATION TESTS FOR CRITICAL FIXES

def test_generation_pipeline_structure_and_placement_contract():
    """
    Integration-level assertion of the CURRENT contract:

    HARD:
    - Generated levels must be structurally valid:
      * correct grid size
      * sealed outer boundary walls
      * spawn_points present
    - Placement rules:
      * spawn_points on platform-like terrain
      * portal (if present) on platform-like terrain

    SOFT:
    - Portal/enemy reachability is validated elsewhere and treated as warnings only.
    """
    from terrain_system import TerrainTypeRegistry
    from config import TILE

    gen = LevelGenerator(width=LEVEL_WIDTH, height=LEVEL_HEIGHT)
    gen.set_world_seed(999)
    validator = LevelValidator()

    for level_type in ["dungeon", "hybrid"]:
        for difficulty in [1, 2, 3]:
            level = gen.generate_level(
                level_index=0,
                level_type=level_type,
                difficulty=difficulty,
                seed=999,
            )

            _assert_generated_level_shape(level)
            assert hasattr(level, "spawn_points"), "GeneratedLevel missing spawn_points"
            assert hasattr(level, "portal_pos"), "GeneratedLevel missing portal_pos"

            terrain_grid = getattr(level, "terrain_grid", None)
            assert terrain_grid is not None, "GeneratedLevel missing terrain_grid"

            # Spawn points on platform-like terrain.
            assert level.spawn_points, "No spawn_points defined"
            for sx, sy in level.spawn_points:
                assert 0 <= sx < LEVEL_WIDTH and 0 <= sy < LEVEL_HEIGHT
                tid = terrain_grid[sy][sx]
                tag = TerrainTypeRegistry.get_terrain(tid)
                assert TerrainTypeRegistry.is_platform_like(tag), (
                    f"Spawn at ({sx},{sy}) not on platform-like terrain"
                )

            # Portal (if present) on platform-like terrain.
            if level.portal_pos:
                px, py = level.portal_pos
                ptx, pty = px // TILE, py // TILE
                assert 0 <= ptx < LEVEL_WIDTH and 0 <= pty < LEVEL_HEIGHT
                tid = terrain_grid[pty][ptx]
                tag = TerrainTypeRegistry.get_terrain(tid)
                assert TerrainTypeRegistry.is_platform_like(tag), (
                    f"Portal at ({ptx},{pty}) not on platform-like terrain"
                )

            # Structural-only validation (no hard reachability assertions here).
            level_data = {
                "grid": level.grid,
                "rooms": getattr(level, "rooms", []),
                "spawn_points": level.spawn_points,
                "type": level_type,
                "terrain_grid": terrain_grid,
            }
            result = validator.validate(level_data)

            structural_markers = (
                "boundary",
                "no grid data",
                "empty grid dimensions",
                "no floor tiles found",
                "poor connectivity",
                "insufficient spawn points",
                "inconsistent grid row length",
            )
            joined = " ".join(s.lower() for s in result.issues)
            assert not any(m in joined for m in structural_markers), (
                f"Structural validation failed for {level_type}/D{difficulty}: {result.issues[:5]}"
            )


def test_generation_with_enforced_boundary_sealing():
    """Test that generation now enforces strict boundary sealing"""
    gen = LevelGenerator(width=LEVEL_WIDTH, height=LEVEL_HEIGHT)
    gen.set_world_seed(123)
    validator = LevelValidator()
    
    # Generate multiple levels
    for i in range(10):
        level = gen.generate_level(
            level_index=i,
            level_type="dungeon",
            difficulty=2,
            seed=123,
        )
        
        grid = level.grid
        assert len(grid) == LEVEL_HEIGHT
        assert len(grid[0]) == LEVEL_WIDTH
        
        # Check all boundaries are sealed
        # Top and bottom boundaries
        for x in range(LEVEL_WIDTH):
            assert grid[0][x] == 1, f"Top boundary hole at ({x}, 0) in level {i}"
            assert grid[LEVEL_HEIGHT-1][x] == 1, f"Bottom boundary hole at ({x}, {LEVEL_HEIGHT-1}) in level {i}"
        
        # Left and right boundaries
        for y in range(LEVEL_HEIGHT):
            assert grid[y][0] == 1, f"Left boundary hole at (0, {y}) in level {i}"
            assert grid[y][LEVEL_WIDTH-1] == 1, f"Right boundary hole at ({LEVEL_WIDTH-1}, {y}) in level {i}"
        
        # Structural validation only
        level_data = {
            "grid": grid,
            "rooms": getattr(level, "rooms", []),
            "spawn_points": level.spawn_points,
            "type": "dungeon",
            "terrain_grid": getattr(level, "terrain_grid", []),
        }
        
        result = validator.validate(level_data)
        structural_markers = (
            "boundary",
            "no grid data",
            "empty grid dimensions",
            "no floor tiles found",
            "poor connectivity",
            "insufficient spawn points",
            "inconsistent grid row length",
        )
        joined = " ".join(s.lower() for s in result.issues)
        assert not any(m in joined for m in structural_markers), (
            f"Level {i} failed structural validation: {result.issues[:3]}"
        )


def test_generation_with_reachable_portal():
    """
    Test that generation ensures portal is reachable from player spawn
    and that the portal is placed on valid platform-like terrain.
    """
    gen = LevelGenerator(width=LEVEL_WIDTH, height=LEVEL_HEIGHT)
    gen.set_world_seed(456)
    validator = LevelValidator()
    
    for i in range(5):
        level = gen.generate_level(
            level_index=i,
            level_type="dungeon",
            difficulty=2,
            seed=456,
        )
        
        # Check portal exists and is accessible
        assert hasattr(level, "portal_pos"), f"Level {i} missing portal_pos"
        assert level.portal_pos is not None, f"Level {i} portal_pos is None"
        portal_x, portal_y = level.portal_pos
        assert portal_x > 0 and portal_y > 0, f"Portal at invalid position ({portal_x}, {portal_y})"
        
        # Convert to tile coordinates for validation
        from terrain_system import TerrainTypeRegistry
        portal_tx = portal_x // TILE
        portal_ty = portal_y // TILE
        assert 0 <= portal_tx < LEVEL_WIDTH, f"Portal X out of bounds: {portal_tx}"
        assert 0 <= portal_ty < LEVEL_HEIGHT, f"Portal Y out of bounds: {portal_ty}"
        
        # Check portal is on platform-like terrain (FLOOR/PLATFORM)
        terrain_id = level.terrain_grid[portal_ty][portal_tx]
        tag = TerrainTypeRegistry.get_terrain(terrain_id)
        assert TerrainTypeRegistry.is_platform_like(tag), (
            f"Portal not on platform-like terrain at ({portal_tx}, {portal_ty}), base={tag.base_type}"
        )
        
        # Validate portal reachability via validator on full data
        level_data = {
            "grid": level.grid,
            "rooms": getattr(level, "rooms", []),
            "spawn_points": level.spawn_points,
            "type": "dungeon",
            "terrain_grid": getattr(level, "terrain_grid", []),
            "portal_pos": level.portal_pos,
            "enemies": level.enemies,
        }
        
        result = validator.validate(level_data)
        # Only assert no portal reachability issues; ignore any incidental enemy warnings here.
        joined = " ".join(s.lower() for s in result.issues)
        assert not ("portal" in joined and "reachable" in joined), (
            f"Level {i} portal reachability failed: {result.issues[:3]}"
        )


def test_generation_with_reachable_enemies():
    """Test that generation ensures at least one enemy is reachable from player"""
    gen = LevelGenerator(width=LEVEL_WIDTH, height=LEVEL_HEIGHT)
    gen.set_world_seed(789)
    validator = LevelValidator()
    
    for i in range(5):
        level = gen.generate_level(
            level_index=i,
            level_type="dungeon",
            difficulty=2,
            seed=789,
        )
        
        # Check enemies exist
        assert hasattr(level, "enemies"), f"Level {i} missing enemies"
        assert len(level.enemies) > 0, f"Level {i} has no enemies"
        
        # Check all enemies have required attributes
        for j, enemy in enumerate(level.enemies):
            assert hasattr(enemy, "x"), f"Enemy {j} missing x attribute"
            assert hasattr(enemy, "y"), f"Enemy {j} missing y attribute"
            assert hasattr(enemy, "type"), f"Enemy {j} missing type attribute"
            assert enemy.x > 0 and enemy.y > 0, f"Enemy {j} at invalid position ({enemy.x}, {enemy.y})"
        
        # Validate via validator and ensure at least one reachable enemy
        level_data = {
            "grid": level.grid,
            "rooms": getattr(level, "rooms", []),
            "spawn_points": level.spawn_points,
            "type": "dungeon",
            "terrain_grid": getattr(level, "terrain_grid", []),
            "enemies": level.enemies,
        }
        
        result = validator.validate(level_data)
        joined = " ".join(s.lower() for s in result.issues)
        # Validator should not report "no reachable enemies" for these generated levels.
        assert "no reachable enemies" not in joined, (
            f"Level {i} enemy reachability failed: {result.issues[:3]}"
        )
        
        # Independent pathfinding check using tile coords derived from enemy.x/y (pixels)
        if level.spawn_points:
            spawn_x, spawn_y = level.spawn_points[0]
            reachable_count = 0
            for enemy in level.enemies:
                enemy_tx = int(enemy.x) // TILE
                enemy_ty = int(enemy.y) // TILE
                if _can_pathfind(level.grid, (spawn_x, spawn_y), (enemy_tx, enemy_ty)):
                    reachable_count += 1
            
            assert reachable_count > 0, f"Level {i} has no reachable enemies (total: {len(level.enemies)})"


def test_generated_level_data_structure():
    """Test that GeneratedLevel objects have proper data structure for validation"""
    level = generate_procedural_level(
        level_index=0,
        level_type="dungeon",
        difficulty=2,
        seed=555,
    )
    
    # Test required attributes
    required_attrs = [
        "grid", "solids", "spawn", "doors", "spawn_points",
        "enemies", "portal_pos", "terrain_grid", "rooms"
    ]
    
    for attr in required_attrs:
        assert hasattr(level, attr), f"GeneratedLevel missing {attr} attribute"
    
    # Test attribute types and basic validity
    assert isinstance(level.grid, list), "grid should be a list"
    assert isinstance(level.enemies, list), "enemies should be a list"
    assert isinstance(level.spawn_points, list), "spawn_points should be a list"
    assert isinstance(level.portal_pos, tuple), "portal_pos should be a tuple"
    assert len(level.portal_pos) == 2, "portal_pos should be a 2-tuple"
    
    # Test grid dimensions
    assert len(level.grid) == LEVEL_HEIGHT, f"Grid height should be {LEVEL_HEIGHT}"
    if len(level.grid) > 0:
        assert len(level.grid[0]) == LEVEL_WIDTH, f"Grid width should be {LEVEL_WIDTH}"
    
    # Test that spawn_points contain valid coordinates
    for sp in level.spawn_points:
        assert isinstance(sp, tuple), "Spawn point should be a tuple"
        assert len(sp) == 2, "Spawn point should be a 2-tuple"
        assert 0 <= sp[0] < LEVEL_WIDTH, f"Spawn X out of bounds: {sp[0]}"
        assert 0 <= sp[1] < LEVEL_HEIGHT, f"Spawn Y out of bounds: {sp[1]}"
    
    # Test that enemies have valid pixel coordinates
    for enemy in level.enemies:
        assert isinstance(enemy.x, (int, float)), f"Enemy X should be numeric: {type(enemy.x)}"
        assert isinstance(enemy.y, (int, float)), f"Enemy Y should be numeric: {type(enemy.y)}"
        assert enemy.x >= 0 and enemy.y >= 0, f"Enemy at negative coordinates: ({enemy.x}, {enemy.y})"


def _can_pathfind(grid, start, end):
    """Simple pathfinding helper for testing"""
    if start == end:
        return True
    
    # Use BFS for pathfinding
    visited = set()
    to_check = [start]
    height, width = len(grid), len(grid[0])
    
    while to_check:
        x, y = to_check.pop(0)
        if (x, y) == end:
            return True
        
        if (x, y) in visited:
            continue
        
        visited.add((x, y))
        
        # Check 4-directional neighbors
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if (0 <= nx < width and 0 <= ny < height and
                grid[ny][nx] == 0 and (nx, ny) not in visited):
                to_check.append((nx, ny))
    
    return False


def test_validation_integration_failure_cases():
    """Test that validation properly catches and reports the three critical issues"""
    validator = LevelValidator()
    
    # Test 1: Boundary holes
    grid = [[1 for _ in range(LEVEL_WIDTH)] for _ in range(LEVEL_HEIGHT)]
    # Create interior floor
    for y in range(2, LEVEL_HEIGHT - 2):
        for x in range(2, LEVEL_WIDTH - 2):
            grid[y][x] = 0
    
    # Create boundary hole
    grid[0][5] = 0
    
    level_data = {
        "grid": grid,
        "rooms": [],
        "spawn_points": [(5, 5)],
        "type": "dungeon",
        "terrain_grid": [["normal" for _ in range(LEVEL_WIDTH)] for _ in range(LEVEL_HEIGHT)],
        "enemy_spawns": [],
        "enemies": [],
        "portal_pos": (10 * TILE, 10 * TILE)
    }
    
    result = validator.validate(level_data)
    assert not result.is_valid
    assert any("boundary" in issue.lower() for issue in result.issues)
    
    # Test 2: Unreachable portal
    grid = [[1 for _ in range(LEVEL_WIDTH)] for _ in range(LEVEL_HEIGHT)]
    # Create two separate areas
    for y in range(2, 8):
        for x in range(2, 8):
            grid[y][x] = 0  # Area 1
    
    for y in range(12, 18):
        for x in range(12, 18):
            grid[y][x] = 0  # Area 2
    
    level_data["grid"] = grid
    level_data["spawn_points"] = [(3, 3)]
    level_data["portal_pos"] = (15 * TILE, 15 * TILE)  # In isolated area
    
    result = validator.validate(level_data)
    assert not result.is_valid
    assert any("portal" in issue.lower() and "reachable" in issue.lower() for issue in result.issues)
    
    # Test 3: No enemies
    level_data["enemies"] = []
    level_data["enemy_spawns"] = []
    
    result = validator.validate(level_data)
    assert not result.is_valid
    assert any("enemy" in issue.lower() and "no enemies" in issue.lower() for issue in result.issues)


def test_legacy_level_still_constructs():
    """Ensure legacy Level (fallback) remains constructible and drawable."""
    lvl = LegacyLevel(0)
    assert lvl.solids, "Legacy Level must have solids"
    assert hasattr(lvl, "spawn")
    assert hasattr(lvl, "doors")


def test_game_procedural_initialization_monkeypatched_menu_and_quit():
    """
    Instantiate Game in a controlled way:

    - Monkeypatch Menu.title_screen to avoid real UI loop.
    - Force procedural generation ON.
    - Verify initial level is GeneratedLevel or legacy Level fallback without crashing.
    """
    # Monkeypatch Menu.title_screen to a no-op
    original_title = Menu.title_screen

    def fake_title(self):
        # Configure some deterministic options without blocking:
        self.game.use_procedural = True
        self.game.level_type = LEVEL_TYPE
        self.game.difficulty = DIFFICULTY
        # Leave world_seed as whatever SeedManager picks or already has.

    Menu.title_screen = fake_title

    try:
        g = Game()
        # On init, _load_level should have been called
        assert hasattr(g, "level")
        # Either procedural GeneratedLevel or legacy Level; both are acceptable.
        assert isinstance(g.level, (GeneratedLevel, LegacyLevel))
        assert hasattr(g.level, "solids")
        assert hasattr(g.level, "spawn")
        assert hasattr(g.level, "doors")
        # Ensure seed info wired
        assert hasattr(g, "world_seed")
    finally:
        # Restore original title_screen to avoid side effects
        Menu.title_screen = original_title


def test_game_fallback_to_legacy_on_failure(monkeypatch=None):
    """
    Simulate failure inside LevelGenerator.generate_level and confirm Game falls
    back to static Level without crashing.
    """
    # Monkeypatch LevelGenerator.generate_level to raise once
    original_generate = LevelGenerator.generate_level

    def failing_generate(self, *args, **kwargs):
        raise RuntimeError("Simulated generation failure")

    LevelGenerator.generate_level = failing_generate

    # Monkeypatch Menu.title_screen to skip UI
    original_title = Menu.title_screen

    def fake_title(self):
        self.game.use_procedural = True

    Menu.title_screen = fake_title

    try:
        g = Game()
        # Since procedural failed, use_procedural should be False and level a LegacyLevel
        assert g.use_procedural is False
        assert isinstance(g.level, LegacyLevel)
    finally:
        LevelGenerator.generate_level = original_generate
        Menu.title_screen = original_title


def test_terrain_test_level_includes_all_area_types_and_terrain_ids():
    """
    Verify that generate_terrain_test_level() produces a deterministic map that:
    - Is fully sealed by walls (grid boundary == 1).
    - Exposes all required AreaType zones.
    - Exposes all required terrain IDs.
    This ties test_terrain_level.md spec to the concrete implementation.
    """
    from level_generator import generate_terrain_test_level
    from area_system import AreaType
    from terrain_system import TerrainTypeRegistry

    lvl = generate_terrain_test_level()

    # Basic shape
    assert hasattr(lvl, "grid") and lvl.grid, "Test level has no grid"
    h = len(lvl.grid)
    w = len(lvl.grid[0])
    assert (w, h) == (40, 30), f"Expected 40x30, got {w}x{h}"

    # Boundaries sealed
    for x in range(w):
        assert lvl.grid[0][x] == 1, f"Top boundary hole at ({x}, 0)"
        assert lvl.grid[h - 1][x] == 1, f"Bottom boundary hole at ({x}, {h-1})"
    for y in range(h):
        assert lvl.grid[y][0] == 1, f"Left boundary hole at (0, {y})"
        assert lvl.grid[y][w - 1] == 1, f"Right boundary hole at ({w-1}, {y})"

    # Areas presence: ensure at least one of each required type.
    assert hasattr(lvl, "areas"), "Test level missing areas map"
    area_map = lvl.areas
    required_area_types = [
        AreaType.PLAYER_SPAWN,
        AreaType.PORTAL_ZONE,
        AreaType.GROUND_ENEMY_SPAWN,
        AreaType.FLYING_ENEMY_SPAWN,
        AreaType.WATER_AREA,
        AreaType.MERCHANT_AREA,
    ]
    for at in required_area_types:
        areas = area_map.find_areas_by_type(at)
        assert areas, f"Missing required area type: {at}"

    # Terrain IDs presence: sample through terrain_grid.
    assert hasattr(lvl, "terrain_grid"), "Test level missing terrain_grid"
    tgrid = lvl.terrain_grid
    all_ids = {tid for row in tgrid for tid in row}

    expected_ids = {
        "floor_normal",
        "floor_sticky",
        "floor_icy",
        "floor_fire",
        "platform_normal",
        "platform_sticky",
        "platform_icy",
        "platform_fire",
        "wall_solid",
        "water",
    }

    missing = expected_ids - all_ids
    assert not missing, f"Missing terrain IDs in test map: {sorted(missing)}"

    # Sanity: all ids are known to TerrainTypeRegistry (helps catch typos).
    for tid in expected_ids:
        TerrainTypeRegistry.get_terrain(tid)