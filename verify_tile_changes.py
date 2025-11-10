import sys
import os

# Add the project root to the Python path
# This allows importing modules like 'src.tiles.tile_types'
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from src.tiles.tile_types import TileType
from src.tiles.tile_registry import TileRegistry
from src.core.constants import TILE_CHAR_MAP

def run_verification_tests():
    print("Running tile system verification tests...")

    # 1. Instantiate TileRegistry
    registry = TileRegistry()
    print("TileRegistry instantiated.")

    # Expected tiles to be present
    expected_present_tiles = [
        TileType.AIR,
        TileType.WALL,
        TileType.PLATFORM,
        TileType.BREAKABLE_WALL,
    ]

    # Expected tiles to be absent
    expected_absent_tiles = [
        # TileType.FLOOR, # Removed
        # TileType.SOLID, # Removed
        # TileType.BREAKABLE_FLOOR, # Removed
        # TileType.MOVING_PLATFORM, # Removed
        # TileType.SLOPE_UP, # Removed
        # TileType.SLOPE_DOWN, # Removed
        # TileType.LADDER, # Removed
        # TileType.LAVA, # Removed
        # TileType.SPIKE, # Removed
        # TileType.SWITCH, # Removed
    ]

    # 2. Verify registered tiles
    all_registered_tiles = registry.get_all_tiles()
    for tile_type in expected_present_tiles:
        assert tile_type in all_registered_tiles, f"FAIL: {tile_type.name} not found in registry."
        print(f"PASS: {tile_type.name} found in registry.")

    # For absent tiles, we need to check if their *values* are not present in the registry's keys
    # This is because the enum members themselves might still exist if not explicitly deleted,
    # but they shouldn't be registered in the TileRegistry.
    # However, since we completely removed them from TileType enum, this check is less critical
    # but still good to have for robustness.
    for tile_type_name in ["FLOOR", "SOLID", "BREAKABLE_FLOOR", "MOVING_PLATFORM", "SLOPE_UP", "SLOPE_DOWN", "LADDER", "LAVA", "SPIKE", "SWITCH", "ONE_WAY_PLATFORM", "WATER", "DOOR"]:
        try:
            # Attempt to access the removed TileType member. This should raise an AttributeError.
            getattr(TileType, tile_type_name)
            assert False, f"FAIL: TileType.{tile_type_name} still exists in TileType enum."
        except AttributeError:
            print(f"PASS: TileType.{tile_type_name} does not exist in TileType enum as expected.")


    # 3. Verify tile properties
    # TileType.WALL
    assert TileType.WALL.is_solid is True, "FAIL: TileType.WALL.is_solid is not True."
    assert TileType.WALL.is_platform is False, "FAIL: TileType.WALL.is_platform is not False."
    assert TileType.WALL.is_breakable is False, "FAIL: TileType.WALL.is_breakable is not False."
    print("PASS: TileType.WALL properties are correct.")

    # TileType.PLATFORM
    assert TileType.PLATFORM.is_solid is False, "FAIL: TileType.PLATFORM.is_solid is not False."
    assert TileType.PLATFORM.is_platform is True, "FAIL: TileType.PLATFORM.is_platform is not True."
    assert TileType.PLATFORM.is_breakable is False, "FAIL: TileType.PLATFORM.is_breakable is not False."
    print("PASS: TileType.PLATFORM properties are correct.")

    # TileType.BREAKABLE_WALL
    assert TileType.BREAKABLE_WALL.is_solid is True, "FAIL: TileType.BREAKABLE_WALL.is_solid is not True."
    assert TileType.BREAKABLE_WALL.is_platform is False, "FAIL: TileType.BREAKABLE_WALL.is_platform is not False."
    assert TileType.BREAKABLE_WALL.is_breakable is True, "FAIL: TileType.BREAKABLE_WALL.is_breakable is not True."
    print("PASS: TileType.BREAKABLE_WALL properties are correct.")

    # TileType.AIR
    assert TileType.AIR.has_collision is False, "FAIL: TileType.AIR.has_collision is not False."
    print("PASS: TileType.AIR properties are correct.")

    # 4. Verify TILE_CHAR_MAP
    assert TILE_CHAR_MAP['.'] == TileType.WALL, "FAIL: TILE_CHAR_MAP['.'] is not TileType.WALL."
    assert TILE_CHAR_MAP['#'] == TileType.WALL, "FAIL: TILE_CHAR_MAP['#'] is not TileType.WALL."
    assert TILE_CHAR_MAP['_'] == TileType.PLATFORM, "FAIL: TILE_CHAR_MAP['_'] is not TileType.PLATFORM."
    assert TILE_CHAR_MAP['@'] == TileType.BREAKABLE_WALL, "FAIL: TILE_CHAR_MAP['@'] is not TileType.BREAKABLE_WALL."
    assert TILE_CHAR_MAP[' '] == TileType.AIR, "FAIL: TILE_CHAR_MAP[' '] is not TileType.AIR."
    print("PASS: TILE_CHAR_MAP mappings are correct.")

    print("\nAll verification tests passed successfully!")

if __name__ == "__main__":
    run_verification_tests()