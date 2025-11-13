# PCG Level and Room Data System

This system provides procedural generation of levels and rooms for the Haridd game, with configurable parameters and JSON-based data storage.

## Features

- **Configurable Generation**: Adjustable number of levels, rooms per level, and room dimensions
- **JSON Storage**: Levels are saved as JSON files for easy loading and debugging
- **Tile System Integration**: Uses numeric tile IDs compatible with existing tile system
- **Room Naming**: Automatic room naming (1A, 1B, 2A, etc.)
- **Door Support**: Optional entrance/exit doors in rooms

## Files

- `src/level/pcg_level_data.py` - Core generation logic and data structures
- `src/level/level_loader.py` - Utility for loading and accessing generated levels
- `src/level/config_loader.py` - Configuration management from JSON files
- `src/level/simple_pcg_demo.py` - Demo showing how to render PCG levels
- `config/pcg_config.json` - Configuration file for generation parameters

## Quick Start

### Generate Levels

```python
from src.level.pcg_level_data import generate_and_save

# Generate with default config (3 levels, 6 rooms each)
level_set = generate_and_save()

# Generate with custom config
from src.level.pcg_level_data import PCGConfig
config = PCGConfig(num_levels=5, rooms_per_level=8, room_width=50, room_height=40)
level_set = generate_and_save(config, "data/levels/custom_levels.json")
```

### Load and Use Levels

```python
from src.level.level_loader import get_room_tiles, get_starting_room

# Get tiles for a specific room
tiles = get_room_tiles(1, "1A")  # Level 1, Room A
if tiles:
    print(f"Room dimensions: {len(tiles)}x{len(tiles[0])}")

# Get starting room for a level
start_room = get_starting_room(1)
if start_room:
    print(f"Starting room: {start_room.room_code}")
```

### Configuration

Edit `config/pcg_config.json` to customize generation:

```json
{
  "pcg_config": {
    "num_levels": 3,
    "rooms_per_level": 6,
    "room_width": 40,
    "room_height": 30,
    "air_tile_id": 0,
    "wall_tile_id": 1,
    "add_doors": true,
    "door_entrance_tile_id": 2,
    "door_exit_tile_id": 3
  }
}
```

## Data Structure

### LevelSet
```json
{
  "levels": [
    {
      "level_id": 1,
      "rooms": [
        {
          "level_id": 1,
          "room_index": 0,
          "room_letter": "A",
          "room_code": "1A",
          "tiles": [[0, 1, 1, 0], ...]  // 2D array of tile IDs
        }
      ]
    }
  ]
}
```

### Tile IDs

The system uses numeric tile IDs that map to your existing tile system:
- `0` = Air (TILE_AIR)
- `1` = Wall (TILE_WALL)
- `2` = Door Entrance
- `3` = Door Exit

## Integration with Game

### Basic Rendering

```python
import pygame
from src.level.level_loader import get_room_tiles
from src.tiles.tile_renderer import TileRenderer
from src.tiles.tile_types import TileType

# Initialize
screen = pygame.display.set_mode((960, 540))
renderer = TileRenderer()

# Load room tiles
tiles = get_room_tiles(1, "1A")

# Render
for y, row in enumerate(tiles):
    for x, tile_id in enumerate(row):
        tile_type = TileType(tile_id)
        if tile_type != TileType.AIR:
            renderer.render_tile(screen, tile_type, x * 24, y * 24)
```

### Room Navigation

```python
from src.level.level_loader import level_loader

# Load level set
level_loader.load_levels()

# Get all rooms in level 1
level = level_loader.get_level(1)
if level:
    for room in level.rooms:
        print(f"Room: {room.room_code}")

# Navigate between rooms
current_room = level_loader.get_room(1, "1A")
if current_room:
    # Get next room in same level
    next_index = current_room.room_index + 1
    if next_index < len(level.rooms):
        next_room = level.rooms[next_index]
        tiles = next_room.tiles
```

## Demo

Run the demo to see PCG levels in action:

```bash
python src/level/simple_pcg_demo.py
```

Controls:
- Arrow Keys: Move camera
- 1-3: Switch levels
- A-F: Switch rooms
- R: Reset camera

## Extending the System

### Custom Room Generation

Replace the `generate_room_tiles()` function in `pcg_level_data.py` with your own algorithm:

```python
def generate_room_tiles(level_id, room_index, room_letter, width, height, config):
    # Your custom generation logic here
    tiles = [[config.air_tile_id for _ in range(width)] for _ in range(height)]
    
    # Add walls, features, etc.
    # ...
    
    return tiles
```

### Additional Tile Types

Add new tile types to your tile system and update the configuration:

```python
# In config.py
TILE_WATER = 4
TILE_LAVA = 5

# In pcg_config.json
{
  "pcg_config": {
    "water_tile_id": 4,
    "lava_tile_id": 5
  }
}
```

### Room Types

Extend the system to support different room types:

```python
@dataclass
class RoomData:
    level_id: int
    room_index: int
    room_letter: str
    room_code: str
    room_type: str  # "basic", "treasure", "enemy", "boss"
    tiles: List[List[int]]
```

## Performance Considerations

- Room sizes of 40x30 tiles (1200 tiles per room) are reasonable
- JSON files are human-readable and easy to debug
- Consider binary formats for very large levels
- Cache loaded rooms in memory during gameplay

## Troubleshooting

### Import Errors
Make sure you're running from the project root directory and Python can find the modules.

### Missing Config File
If `config/pcg_config.json` is missing, the system will use default values.

### Tile ID Mismatches
Ensure tile IDs in your configuration match the actual tile types in your tile system.