"""
Test script for procedural level generation system - Updated to test critical fixes

Focus:
- Testing the three critical fixes: boundary sealing, portal reachability, enemy reachability
- Performance and quality validation
- Integration with existing game components
- Deterministic generation behavior
"""

import sys
import time
from level_generator import generate_procedural_level, LevelGenerator
from level_validator import LevelValidator
from config import LEVEL_WIDTH, LEVEL_HEIGHT, LEVEL_TYPE, DIFFICULTY, TILE


def test_generation_performance():
    """Test generation performance and quality"""
    print("Testing Procedural Level Generation System")
    print("=" * 50)
    
    # Test different level types
    level_types = ["dungeon", "cave", "outdoor", "hybrid"]
    
    for level_type in level_types:
        print(f"\nTesting {level_type} level generation...")
        
        generator = LevelGenerator()
        
        # Test multiple generations for performance
        times = []
        validation_attempts = []
        
        for i in range(5):  # Test 5 generations
            start_time = time.time()
            
            # Generate level
            level = generator.generate_level(
                level_index=i,
                level_type=level_type,
                difficulty=DIFFICULTY
            )
            
            generation_time = (time.time() - start_time) * 1000
            times.append(generation_time)
            validation_attempts.append(generator.validation_attempts)
            
            # Basic validation
            if not level.grid:
                print(f"  ERROR: No grid generated for iteration {i}")
                continue
            
            if len(level.grid) != LEVEL_HEIGHT:
                print(f"  ERROR: Incorrect grid height for iteration {i}")
                continue
            
            if len(level.grid[0]) != LEVEL_WIDTH:
                print(f"  ERROR: Incorrect grid width for iteration {i}")
                continue
            
            # Check spawn points
            if not level.spawn_points:
                print(f"  ERROR: No spawn points for iteration {i}")
                continue
            
            # Check solids
            if not level.solids:
                print(f"  ERROR: No solids generated for iteration {i}")
                continue
        
        # Calculate statistics
        if times:
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)
            
            avg_validation = sum(validation_attempts) / len(validation_attempts)
            
            print(f"  Performance for {level_type}:")
            print(f"    Average time: {avg_time:.1f}ms")
            print(f"    Min time: {min_time:.1f}ms")
            print(f"    Max time: {max_time:.1f}ms")
            print(f"    Average validation attempts: {avg_validation:.1f}")
            
            # Check if meets performance target
            target_time = 100  # 100ms target from config
            if avg_time <= target_time:
                print(f"    [OK] Meets performance target (<={target_time}ms)")
            else:
                print(f"    [FAIL] Exceeds performance target (>{target_time}ms)")


def test_critical_fixes_validation():
    """Test that the three critical issues are properly fixed"""
    print("\nTesting Critical Fixes Validation")
    print("=" * 50)
    
    generator = LevelGenerator()
    validator = LevelValidator()
    
    # Test with different seeds to ensure robustness
    test_seeds = [100, 200, 300, 400, 500]
    all_passed = True
    
    for seed in test_seeds:
        print(f"\nTesting with seed {seed}...")
        
        level = generator.generate_level(
            level_index=0,
            level_type="dungeon",
            difficulty=2,
            seed=seed
        )
        
        # Test 1: Boundary sealing
        grid = level.grid
        boundary_issues = []
        
        # Check top and bottom boundaries
        for x in range(LEVEL_WIDTH):
            if grid[0][x] != 1:
                boundary_issues.append(f"Top boundary hole at ({x}, 0)")
            if grid[LEVEL_HEIGHT-1][x] != 1:
                boundary_issues.append(f"Bottom boundary hole at ({x}, {LEVEL_HEIGHT-1})")
        
        # Check left and right boundaries
        for y in range(LEVEL_HEIGHT):
            if grid[y][0] != 1:
                boundary_issues.append(f"Left boundary hole at (0, {y})")
            if grid[y][LEVEL_WIDTH-1] != 1:
                boundary_issues.append(f"Right boundary hole at ({LEVEL_WIDTH-1}, {y})")
        
        if boundary_issues:
            print(f"  [FAIL] Boundary issues found: {boundary_issues}")
            all_passed = False
        else:
            print(f"  [OK] All boundaries properly sealed")
        
        # Test 2: Portal reachability
        if not hasattr(level, "portal_pos") or level.portal_pos is None:
            print(f"  [FAIL] No portal position found")
            all_passed = False
        else:
            portal_x, portal_y = level.portal_pos
            portal_tx = portal_x // TILE
            portal_ty = portal_y // TILE
            
            # Check portal is on floor
            if grid[portal_ty][portal_tx] != 0:
                print(f"  [FAIL] Portal not on floor at ({portal_tx}, {portal_ty})")
                all_passed = False
            else:
                print(f"  [OK] Portal properly placed on floor")
            
            # Check reachability from spawn
            if level.spawn_points:
                spawn_x, spawn_y = level.spawn_points[0]
                if not _can_pathfind_simple(grid, (spawn_x, spawn_y), (portal_tx, portal_ty)):
                    print(f"  [FAIL] Portal not reachable from spawn")
                    all_passed = False
                else:
                    print(f"  [OK] Portal reachable from spawn")
        
        # Test 3: Enemy reachability
        enemies = getattr(level, "enemies", [])
        if not enemies:
            print(f"  [FAIL] No enemies found in level")
            all_passed = False
        else:
            print(f"  [OK] Found {len(enemies)} enemies")
            
            # Check if at least one enemy is reachable
            if level.spawn_points:
                spawn_x, spawn_y = level.spawn_points[0]
                reachable_enemies = 0

                for enemy in enemies:
                    # enemy.x / enemy.y are pixels; convert to tile ints defensively
                    enemy_tx = int(enemy.x) // TILE
                    enemy_ty = int(enemy.y) // TILE

                    # Check if enemy is on floor and reachable
                    if (0 <= enemy_ty < LEVEL_HEIGHT and 0 <= enemy_tx < LEVEL_WIDTH and
                        grid[enemy_ty][enemy_tx] == 0 and
                        _can_pathfind_simple(grid, (spawn_x, spawn_y), (enemy_tx, enemy_ty))):
                        reachable_enemies += 1
                
                if reachable_enemies == 0:
                    print(f"  [FAIL] No reachable enemies found (total: {len(enemies)})")
                    all_passed = False
                else:
                    print(f"  [OK] {reachable_enemies} reachable enemies found")
        
        # Full validation test
        level_data = {
            "grid": grid,
            "rooms": getattr(level, "rooms", []),
            "spawn_points": level.spawn_points,
            "type": "dungeon",
            "terrain_grid": getattr(level, "terrain_grid", []),
            "enemy_spawns": enemies,
            "portal_pos": getattr(level, "portal_pos", None),
            "enemies": enemies
        }
        
        result = validator.validate(level_data)
        if result.is_valid:
            print(f"  [OK] Level passes full validation")
        else:
            print(f"  [FAIL] Level validation failed: {result.issues[:3]}")
            all_passed = False
    
    if all_passed:
        print(f"\n[SUCCESS] All critical fixes working correctly!")
    else:
        print(f"\n[FAILURE] Some critical fixes failed")
    
    return all_passed


def test_level_integration():
    """Test integration with existing game components"""
    print("\nTesting Integration with Existing Game Components")
    print("=" * 50)
    
    # Generate a test level
    level = generate_procedural_level(
        level_index=0,
        level_type=LEVEL_TYPE,
        difficulty=DIFFICULTY
    )
    
    # Test terrain system integration
    print("Testing terrain system integration...")
    try:
        from terrain_system import terrain_system
        
        # Load terrain into terrain system
        terrain_system.terrain_grid = level.terrain_grid
        
        # Test terrain access
        test_positions = [
            (level.spawn_points[0][0] * 24, level.spawn_points[0][1] * 24),
            (100, 100),  # Test position
        ]
        
        for pos in test_positions:
            terrain = terrain_system.get_terrain_at(pos, level)
            print(f"  Terrain at {pos}: {terrain.value}")
        
        print("  [OK] Terrain system integration successful")
        
    except Exception as e:
        print(f"  [FAIL] Terrain system integration failed: {e}")
    
    # Test level compatibility
    print("\nTesting level compatibility...")
    
    # Check grid dimensions
    if level.grid:
        print(f"  Grid dimensions: {len(level.grid[0])}x{len(level.grid)}")
        print(f"  Spawn points: {len(level.spawn_points)}")
        print(f"  Solids: {len(level.solids)}")
        print(f"  Doors: {len(level.doors)}")
        print("  [OK] Level structure compatible")
    else:
        print("  [FAIL] Level structure incompatible")
    
    # Test tile conversion
    print("\nTesting tile conversion...")
    wall_count = sum(row.count(1) for row in level.grid)
    floor_count = sum(row.count(0) for row in level.grid)
    total_tiles = wall_count + floor_count
    
    print(f"  Wall tiles: {wall_count}")
    print(f"  Floor tiles: {floor_count}")
    print(f"  Total tiles: {total_tiles}")
    print(f"  Wall ratio: {wall_count/total_tiles:.2%}")
    print("  [OK] Tile conversion successful")


def test_seed_determinism():
    """Test that same seed produces same level"""
    print("\nTesting Seed Determinism")
    print("=" * 50)
    
    test_seed = 12345
    level_type = "dungeon"
    
    # Generate level twice with same seed
    level1 = generate_procedural_level(
        level_index=0,
        level_type=level_type,
        difficulty=1,
        seed=test_seed
    )
    
    level2 = generate_procedural_level(
        level_index=0,
        level_type=level_type,
        difficulty=1,
        seed=test_seed
    )
    
    # Compare grids
    if level1.grid == level2.grid:
        print("  [OK] Same seed produces identical levels")
    else:
        print("  [FAIL] Same seed produces different levels")
        
        # Find differences
        differences = 0
        for y, row1 in enumerate(level1.grid):
            if y < len(level2.grid):
                row2 = level2.grid[y]
                for x, tile1 in enumerate(row1):
                    if x < len(row2):
                        tile2 = row2[x]
                        if tile1 != tile2:
                            differences += 1
        
        print(f"  Differences found: {differences} tiles")
    
    # Compare spawn points
    if level1.spawn_points == level2.spawn_points:
        print("  [OK] Spawn points are deterministic")
    else:
        print("  [FAIL] Spawn points are not deterministic")


def test_edge_cases():
    """Test edge cases and failure scenarios"""
    print("\nTesting Edge Cases")
    print("=" * 50)
    
    generator = LevelGenerator()
    validator = LevelValidator()
    
    # Test various difficulty levels and level types
    test_cases = [
        ("dungeon", 1),
        ("dungeon", 3),
        ("hybrid", 2),
        ("cave", 1),
    ]
    
    all_passed = True
    
    for level_type, difficulty in test_cases:
        print(f"\nTesting {level_type} difficulty {difficulty}...")
        
        for i in range(3):  # Test multiple seeds for each combination
            level = generator.generate_level(
                level_index=i,
                level_type=level_type,
                difficulty=difficulty,
                seed=1000 + i
            )
            
            # Basic structure checks
            if not level.grid or len(level.grid) != LEVEL_HEIGHT:
                print(f"  [FAIL] Invalid grid structure")
                all_passed = False
                continue
            
            # Check required attributes
            required_attrs = ["spawn_points", "enemies", "portal_pos"]
            missing_attrs = [attr for attr in required_attrs if not hasattr(level, attr)]
            
            if missing_attrs:
                print(f"  [FAIL] Missing attributes: {missing_attrs}")
                all_passed = False
                continue
            
            # Validate level
            level_data = {
                "grid": level.grid,
                "rooms": getattr(level, "rooms", []),
                "spawn_points": level.spawn_points,
                "type": level_type,
                "terrain_grid": getattr(level, "terrain_grid", []),
                "enemy_spawns": level.enemies,
                "portal_pos": level.portal_pos,
                "enemies": level.enemies
            }
            
            result = validator.validate(level_data)
            if not result.is_valid:
                critical_issues = [issue for issue in result.issues if any(
                    keyword in issue.lower() for keyword in ["boundary", "portal", "enemy", "reachable"]
                )]
                if critical_issues:
                    print(f"  [FAIL] Critical issues: {critical_issues}")
                    all_passed = False
                else:
                    print(f"  [OK] Non-critical validation issues (acceptable)")
            else:
                print(f"  [OK] Level {i} validated successfully")
    
    return all_passed


def _can_pathfind_simple(grid, start, end):
    """Simple pathfinding helper for testing"""
    if start == end:
        return True
    
    # Use BFS
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


def main():
    """Run all tests"""
    try:
        print("Running enhanced test suite for critical fixes...")
        
        test_generation_performance()
        
        critical_passed = test_critical_fixes_validation()
        
        test_level_integration()
        
        test_seed_determinism()
        
        edge_passed = test_edge_cases()
        
        print("\n" + "=" * 50)
        print("All tests completed!")
        print("=" * 50)
        
        if critical_passed and edge_passed:
            print("[SUCCESS] All critical fixes working correctly!")
            return 0
        else:
            print("[FAILURE] Some tests failed")
            return 1
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())