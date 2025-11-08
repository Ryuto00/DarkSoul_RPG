# Test Terrain & Area Coverage Map Specification

This markdown documents the intended behavior for the terrain/area test map and key bindings. Implementation in Python files should follow this spec.

## Goals

- Provide a deterministic test level that:
  - Includes all terrain base types:
    - platform, floor, wall, water
  - Includes all defined terrain IDs:
    - floor_normal, floor_sticky, floor_icy, floor_fire
    - platform_normal, platform_sticky, platform_icy, platform_fire
    - wall_solid
    - water
  - Includes all area types:
    - PLAYER_SPAWN
    - PORTAL_ZONE
    - GROUND_ENEMY_SPAWN
    - FLYING_ENEMY_SPAWN
    - WATER_AREA
    - MERCHANT_AREA
- Allow quick access to this map via F8.
- Allow visualization of area types as an overlay via F9:
  - Overlay should draw rectangles for each Area.
  - Each rectangle should be labeled with its area.type.
  - Overlay should be drawn on top of the current map (non-destructive).
  - When overlay is enabled, HUD should show:
    - "GOD" label (if active) and also:
    - "AREA: <type list / current tile areas>" or similar near the existing GOD label.

## Key Bindings (Desired Behavior)

- F7:
  - Keep current behavior (add 1000 coins + floating text).
  - No changes required.

- F8:
  - Behavior: Load or toggle a dedicated "TerrainTest" level.
  - Expected implementation:
    - If using procedural:
      - Call LevelGenerator to build a deterministic test layout (e.g., fixed seed and handcrafted grid).
      - Or directly construct a GeneratedLevel-like instance with:
        - terrain_grid covering all terrain IDs.
        - areas: AreaMap containing all AreaType variants.
    - If already in test map: pressing F8 again may reload it or return to previous level (optional; spec leaves it to implementation).
  - Motivation: One key press to jump into full coverage environment.

- F9:
  - Behavior: Toggle area/terrain overlay visualization (moved from current F8).
  - Expected implementation:
    - Introduce a boolean flag on Game:
      - debug_show_area_overlay (already exists).
    - F9 keydown should:
      - Toggle this flag.
    - Rendering:
      - In Game.draw(), when debug_show_area_overlay is True and current level has an `areas` or `terrain_grid`:
        - Draw semi-transparent rectangles for each Area in AreaMap.
        - Color code by area.type (simple hardcoded mapping is acceptable).
        - Draw area.type text label inside each rectangle.
        - Optionally, if multiple areas overlap at player position, display their types in HUD next to "GOD" label.

## Minimal Implementation Notes (for Python code)

These are implementation-oriented notes for main.py / level_generator.py:

1. Ensure terrain and area systems are initialized:
   - LevelGenerator already calls:
     - terrain_system.init_defaults()
     - area_system.init_defaults()
   - No extra init needed in Game if using LevelGenerator.

2. Test Map Integration:
   - Option A (recommended, non-invasive):
     - Add a helper in level_generator.py:
       - def generate_terrain_test_level() -> GeneratedLevel:
         - Builds a small grid (e.g., 40x30) with:
           - Regions for each terrain ID.
           - Water pool for WATER_AREA.
         - Constructs a corresponding AreaMap with all AreaType usages.
     - In Game (main.py), F8 handler:
       - Remember previous level_index and state if necessary.
       - Call helper to set:
         - self.level = generated_test_level
         - self.enemies = self.level.enemies
         - self.level_index = -999 (or another sentinel) to indicate "test"
         - self.use_procedural = True (or flag dedicated to "test runtime")
       - Reposition player at test PLAYER_SPAWN area.

   - Option B:
     - Inject deterministic test configuration via LevelGenerator using a fixed seed and special level_type like "terrain_test".

3. Area Overlay Rendering:
   - In Game.draw():
     - After drawing level and entities, check:
       - if self.debug_show_area_overlay and hasattr(self.level, "areas"):
         - For each area in self.level.areas.areas:
           - Compute pixel rect:
             - rect_x = area.x * TILE
             - rect_y = area.y * TILE
             - rect_w = area.width * TILE
             - rect_h = area.height * TILE
           - Project via camera.to_screen_rect.
           - Choose color by area.type.
           - Draw semi-transparent filled rect + label text.
     - HUD text:
       - If overlay enabled:
         - Get player tile:
           - tx = player.rect.centerx // TILE
           - ty = player.rect.centery // TILE
         - areas_here = level.areas.areas_at(tx, ty) if available.
         - Next to GOD label:
           - Show: "AREA: <comma-separated area.type for areas_here>" if any.
           - If none, show: "AREA: NONE".

4. Key Mapping Changes (summary):
   - F7: leave as is (1000 coins).
   - F8: repurpose from overlay toggle to test map loader.
   - F9: repurpose from goto_room to overlay toggle.

This spec should now be implemented in the Python code:
- Update main.py key handling for F8/F9.
- Add overlay drawing in Game.draw() based on debug_show_area_overlay and level.areas.
- Extend level_generator.py with a deterministic test map or special mode so F8 can reliably load all terrain/area types in one scene.