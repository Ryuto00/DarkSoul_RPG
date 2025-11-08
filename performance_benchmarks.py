"""
Performance and quality benchmarking utilities for the procedural generation system.

Usage:
    python performance_benchmarks.py

This is a standalone, non-pytest script intended for:
- Measuring generation time across many seeds / level types / difficulties
- Estimating memory usage from grids and terrain
- Tracking validation success rate using LevelValidator
- Emitting summary metrics to guide parameter tuning
"""

import time
import statistics

from level_generator import LevelGenerator
from level_validator import LevelValidator
from config import (
    LEVEL_WIDTH,
    LEVEL_HEIGHT,
    LEVEL_TYPES,
    DIFFICULTY_LEVELS,
    GENERATION_TIME_TARGET,
    TILE,
)
# terrain_system removed - using hardcoded enemy behaviors


def estimate_memory_bytes(grid, terrain_grid):
    """Rough memory estimate for level data structures."""
    if not grid:
        return 0

    h = len(grid)
    w = len(grid[0])

    # Assume 4 bytes per tile int
    grid_bytes = h * w * 4

    terrain_bytes = 0
    if terrain_grid and len(terrain_grid) == h and len(terrain_grid[0]) == w:
        # Approx. 20 bytes per terrain string
        terrain_bytes = h * w * 20

    return grid_bytes + terrain_bytes


def benchmark_configuration(
    level_type: str,
    difficulty: int,
    world_seed: int,
    runs: int = 50,
):
    gen = LevelGenerator(width=LEVEL_WIDTH, height=LEVEL_HEIGHT)
    gen.set_world_seed(world_seed)
    validator = LevelValidator()

    gen_times = []
    val_times = []
    mem_samples = []
    valid_count = 0
    critical_issues_count = 0
    boundary_issues = 0
    portal_issues = 0
    enemy_issues = 0

    for i in range(runs):
        start = time.perf_counter()
        level = gen.generate_level(
            level_index=i,
            level_type=level_type,
            difficulty=difficulty,
            seed=world_seed,
        )
        gen_ms = (time.perf_counter() - start) * 1000.0
        gen_times.append(gen_ms)

        grid = getattr(level, "grid", [])
        terrain_grid = getattr(level, "terrain_grid", [])
        if grid:
            mem_samples.append(estimate_memory_bytes(grid, terrain_grid))

        # Validation timing with enhanced data
        data = {
            "grid": grid,
            "rooms": getattr(level, "rooms", []),
            "spawn_points": getattr(level, "spawn_points", []),
            "type": level_type,
            "terrain_grid": terrain_grid,
            "enemy_spawns": getattr(level, "enemies", []),
            "portal_pos": getattr(level, "portal_pos", None),
            "enemies": getattr(level, "enemies", [])
        }
        v_start = time.perf_counter()
        res = validator.validate(data)
        v_ms = (time.perf_counter() - v_start) * 1000.0
        val_times.append(v_ms)
        
        if res.is_valid:
            valid_count += 1
        else:
            # Count critical issues specifically
            issues_text = " ".join(res.issues).lower()
            if any(keyword in issues_text for keyword in ["boundary", "sealed"]):
                boundary_issues += 1
            if any(keyword in issues_text for keyword in ["portal", "reachable"]):
                portal_issues += 1
            if any(keyword in issues_text for keyword in ["enemy", "reachable", "no enemies"]):
                enemy_issues += 1
            if any(keyword in issues_text for keyword in ["boundary", "portal", "enemy", "reachable"]):
                critical_issues_count += 1

    avg_gen = statistics.mean(gen_times)
    p95_gen = sorted(gen_times)[int(0.95 * (len(gen_times) - 1))]
    max_gen = max(gen_times)

    avg_val = statistics.mean(val_times) if val_times else 0.0
    p95_val = sorted(val_times)[int(0.95 * (len(val_times) - 1))] if val_times else 0.0

    avg_mem_mb = (statistics.mean(mem_samples) / (1024 * 1024)) if mem_samples else 0.0

    success_rate = valid_count / runs if runs else 0.0
    critical_issue_rate = critical_issues_count / runs if runs else 0.0

    return {
        "level_type": level_type,
        "difficulty": difficulty,
        "runs": runs,
        "avg_gen_ms": avg_gen,
        "p95_gen_ms": p95_gen,
        "max_gen_ms": max_gen,
        "avg_val_ms": avg_val,
        "p95_val_ms": p95_val,
        "avg_mem_mb": avg_mem_mb,
        "validation_success_rate": success_rate,
        "critical_issue_rate": critical_issue_rate,
        "boundary_issues": boundary_issues,
        "portal_issues": portal_issues,
        "enemy_issues": enemy_issues,
    }


def benchmark_critical_fixes():
    """Benchmark specifically the three critical fixes"""
    print("=== Critical Fixes Benchmark ===")
    
    gen = LevelGenerator(width=LEVEL_WIDTH, height=LEVEL_HEIGHT)
    gen.set_world_seed(20251108)
    validator = LevelValidator()
    
    runs = 100
    level_type = "dungeon"
    difficulty = 2
    
    boundary_failures = 0
    portal_failures = 0
    enemy_failures = 0
    total_failures = 0
    validation_times = []
    
    for i in range(runs):
        start = time.perf_counter()
        level = gen.generate_level(
            level_index=i,
            level_type=level_type,
            difficulty=difficulty,
            seed=20251108,
        )
        
        # Test boundary sealing
        grid = level.grid
        boundary_ok = True
        for x in range(LEVEL_WIDTH):
            if grid[0][x] != 1 or grid[LEVEL_HEIGHT-1][x] != 1:
                boundary_ok = False
                break
        for y in range(LEVEL_HEIGHT):
            if grid[y][0] != 1 or grid[y][LEVEL_WIDTH-1] != 1:
                boundary_ok = False
                break
        
        if not boundary_ok:
            boundary_failures += 1
        
        # Test portal reachability
        portal_ok = True
        if not hasattr(level, "portal_pos") or level.portal_pos is None:
            portal_ok = False
        else:
            portal_x, portal_y = level.portal_pos
            portal_tx = portal_x // TILE
            portal_ty = portal_y // TILE
            
            if grid[portal_ty][portal_tx] != 0:
                portal_ok = False
            elif level.spawn_points:
                spawn_x, spawn_y = level.spawn_points[0]
                if not _can_pathfind_simple(grid, (spawn_x, spawn_y), (portal_tx, portal_ty)):
                    portal_ok = False
        
        if not portal_ok:
            portal_failures += 1
        
        # Test enemy reachability
        enemy_ok = True
        enemies = getattr(level, "enemies", [])
        if not enemies:
            enemy_ok = False
        elif level.spawn_points:
            spawn_x, spawn_y = level.spawn_points[0]
            reachable_enemies = 0
            for enemy in enemies:
                enemy_tx = enemy.x // TILE
                enemy_ty = enemy.y // TILE
                if _can_pathfind_simple(grid, (spawn_x, spawn_y), (enemy_tx, enemy_ty)):
                    reachable_enemies += 1
                    break  # Just need at least one
            
            if reachable_enemies == 0:
                enemy_ok = False
        
        if not enemy_ok:
            enemy_failures += 1
        
        # Full validation
        level_data = {
            "grid": grid,
            "rooms": getattr(level, "rooms", []),
            "spawn_points": level.spawn_points,
            "type": level_type,
            "terrain_grid": getattr(level, "terrain_grid", []),
            "enemy_spawns": enemies,
            "portal_pos": getattr(level, "portal_pos", None),
            "enemies": enemies
        }
        
        res = validator.validate(level_data)
        if not res.is_valid:
            total_failures += 1
        
        validation_time = (time.perf_counter() - start) * 1000.0
        validation_times.append(validation_time)
    
    print(f"Runs: {runs}")
    print(f"Boundary sealing failures: {boundary_failures} ({boundary_failures/runs:.1%})")
    print(f"Portal reachability failures: {portal_failures} ({portal_failures/runs:.1%})")
    print(f"Enemy reachability failures: {enemy_failures} ({enemy_failures/runs:.1%})")
    print(f"Total validation failures: {total_failures} ({total_failures/runs:.1%})")
    print(f"Average validation time: {statistics.mean(validation_times):.2f}ms")
    print(f"p95 validation time: {sorted(validation_times)[int(0.95 * (len(validation_times) - 1))]:.2f}ms")
    
    # Success criteria
    success = True
    if boundary_failures > 0:
        print(f"[FAIL] Boundary sealing not working: {boundary_failures} failures")
        success = False
    if portal_failures > runs * 0.05:  # Allow up to 5% portal failures
        print(f"[FAIL] Portal reachability issues: {portal_failures} failures")
        success = False
    if enemy_failures > runs * 0.05:  # Allow up to 5% enemy failures
        print(f"[FAIL] Enemy reachability issues: {enemy_failures} failures")
        success = False
    if total_failures > runs * 0.10:  # Allow up to 10% total failures
        print(f"[FAIL] Overall validation success rate too low: {total_failures} failures")
        success = False
    
    if success:
        print("[OK] All critical fixes working within acceptable parameters")
    
    return success


def _can_pathfind_simple(grid, start, end):
    """Simple pathfinding helper for benchmarking"""
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


def print_report_row(label: str, value: str):
    print(f"{label:<34} {value}")


def run_all_benchmarks():
    print("=== Procedural Generation Benchmarks ===")
    print(f"Target generation time: {GENERATION_TIME_TARGET} ms")
    print("Grid size:", LEVEL_WIDTH, "x", LEVEL_HEIGHT)
    print("========================================\n")

    # Run critical fixes benchmark first
    print("Running critical fixes benchmark...")
    critical_ok = benchmark_critical_fixes()
    print("")

    world_seed = 20251108
    configs = []
    for lt in LEVEL_TYPES:
        for diff in DIFFICULTY_LEVELS:
            configs.append((lt, diff))

    results = []
    for (lt, diff) in configs:
        print(f"[Benchmark] type={lt}, difficulty={diff}")
        r = benchmark_configuration(lt, diff, world_seed=world_seed, runs=30)
        results.append(r)

        print_report_row("Runs:", str(r["runs"]))
        print_report_row("Avg gen time:", f"{r['avg_gen_ms']:.2f} ms")
        print_report_row("p95 gen time:", f"{r['p95_gen_ms']:.2f} ms")
        print_report_row("Max gen time:", f"{r['max_gen_ms']:.2f} ms")
        print_report_row("Avg validation time:", f"{r['avg_val_ms']:.2f} ms")
        print_report_row("p95 validation time:", f"{r['p95_val_ms']:.2f} ms")
        print_report_row("Avg memory usage:", f"{r['avg_mem_mb']:.3f} MB")
        print_report_row(
            "Validation success rate:",
            f"{r['validation_success_rate']*100:.1f}%",
        )
        print_report_row(
            "Critical issue rate:",
            f"{r['critical_issue_rate']*100:.1f}%",
        )

        status = []
        if r["avg_gen_ms"] <= GENERATION_TIME_TARGET:
            status.append("GEN_OK")
        else:
            status.append("GEN_SLOW")

        if r["validation_success_rate"] >= 0.95:
            status.append("VAL_OK")
        else:
            status.append("VAL_LOW")
            
        if r["critical_issue_rate"] <= 0.05:  # Less than 5% critical issues
            status.append("CRITICAL_OK")
        else:
            status.append("CRITICAL_ISSUES")

        print_report_row("Status:", " / ".join(status))
        print("")

    # Summary hint block for tuning
    print("=== Summary ===")
    if critical_ok:
        print("[OK] Critical fixes are working properly")
    else:
        print("[FAIL] Critical fixes have issues that need attention")
    
    print("\n=== Tuning Hints ===")
    print(
        "- If GEN_SLOW: consider reducing LEVEL_WIDTH/HEIGHT or complexity in generation_algorithms.HybridGenerator()."
    )
    print(
        "- If VAL_LOW: adjust validation thresholds in level_validator.py or tune ROOM_DENSITY/CORRIDOR_WIDTH, etc."
    )
    print(
        "- If CRITICAL_ISSUES: check boundary sealing, portal placement, and enemy spawn logic."
    )
    print(
        "- If memory > ~10MB: shrink LEVEL_WIDTH/HEIGHT or simplify terrain variety."
    )
    print("\nDone.")


if __name__ == "__main__":
    run_all_benchmarks()