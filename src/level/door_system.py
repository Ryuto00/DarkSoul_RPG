"""Door interaction handler for PCG level system."""

import pygame
import os
import sys
from typing import Optional, Tuple

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.interaction import handle_proximity_interactions, find_spawn_point
from src.tiles.tile_types import TileType
from src.level.level_loader import (
    get_room_tiles, get_room_exits, get_room_entrance_from
)


class DoorSystem:
    """Handles door interactions and room transitions in PCG levels."""
    
    def __init__(self):
        self.current_level_id = 1
        self.current_room_code = "1A"
        self.current_tiles = None
    
    def load_room(self, level_id: int, room_code: str) -> bool:
        """
        Load a specific room.
        
        Args:
            level_id: The level number (1-based)
            room_code: Room code like "1A", "2B", etc.
            
        Returns:
            True if room loaded successfully, False otherwise
        """
        tiles = get_room_tiles(level_id, room_code)
        if tiles:
            self.current_level_id = level_id
            self.current_room_code = room_code
            self.current_tiles = tiles
            return True
        return False
    
    def handle_door_interaction(
        self, 
        player_rect: pygame.Rect, 
        tile_size: int,
        is_e_pressed: bool
    ) -> Optional[Tuple[str, int, int]]:
        """
        Handle door interactions for current room.
        
        Args:
            player_rect: Player's collision rectangle
            tile_size: Size of each tile (usually 24)
            is_e_pressed: Whether E key was pressed this frame
            
        Returns:
            Tuple of (prompt_text, world_x, world_y) for UI display,
            or None if no interactable tile is nearby.
        """
        if not self.current_tiles:
            return None
        
        def on_interact(tile_data, tile_coords):
            """Handle door interaction."""
            self._process_door_interaction(tile_data, tile_coords)
        
        return handle_proximity_interactions(
            player_rect=player_rect,
            tile_grid=self.current_tiles,
            tile_size=tile_size,
            is_e_pressed=is_e_pressed,
            on_interact=on_interact
        )
    
    def _process_door_interaction(self, tile_data, tile_coords: Tuple[int, int]):
        """Process a door interaction and perform room transition."""
        tile_type = tile_data.tile_type
        on_interact_id = tile_data.interaction.on_interact_id
        
        # Handle different door types
        if tile_type == TileType.DOOR_EXIT_1:
            exit_key = "door_exit_1"
        elif tile_type == TileType.DOOR_EXIT_2:
            exit_key = "door_exit_2"
        else:
            # Not a door exit we handle
            return
        
        # Get target room from current room's exit mapping
        exits = get_room_exits(self.current_level_id, self.current_room_code)
        target_room_code = exits.get(exit_key)
        
        if not target_room_code:
            print(f"No target room for {exit_key} in {self.current_room_code}")
            return
        
        # Parse target room code to get level_id
        try:
            target_level_id = int(target_room_code[0])
        except (ValueError, IndexError):
            print(f"Invalid room code format: {target_room_code}")
            return
        
        # Load target room
        if self.load_room(target_level_id, target_room_code):
            print(f"Transitioned to {target_room_code}")
            
            # Find spawn point in new room
            spawn_coords = find_spawn_point(self.current_tiles)
            if spawn_coords:
                spawn_tx, spawn_ty = spawn_coords
                spawn_x = spawn_tx * 24  # TILE_SIZE
                spawn_y = spawn_ty * 24  # TILE_SIZE
                print(f"Spawn point: ({spawn_x}, {spawn_y})")
                # In actual game, you would move player here
                return spawn_x, spawn_y
            else:
                print("No spawn point found in target room")
        else:
            print(f"Failed to load room: {target_room_code}")
    
    def get_spawn_point(self) -> Optional[Tuple[int, int]]:
        """Get spawn point for current room."""
        if not self.current_tiles:
            return None
        
        spawn_coords = find_spawn_point(self.current_tiles)
        if spawn_coords:
            spawn_tx, spawn_ty = spawn_coords
            return (spawn_tx * 24, spawn_ty * 24)  # Convert to world coordinates
        return None
    
    def get_current_room_info(self) -> dict:
        """Get information about current room."""
        if not self.current_tiles:
            return {}
        
        exits = get_room_exits(self.current_level_id, self.current_room_code)
        entrance_from = get_room_entrance_from(self.current_level_id, self.current_room_code)
        
        return {
            "level_id": self.current_level_id,
            "room_code": self.current_room_code,
            "entrance_from": entrance_from,
            "exits": exits,
            "room_size": f"{len(self.current_tiles)}x{len(self.current_tiles[0])}"
        }


def test_door_system():
    """Test the door system with generated levels."""
    from src.level.pcg_level_data import generate_and_save
    
    print("=== Generating test levels ===")
    level_set = generate_and_save()
    
    print("\n=== Testing Door System ===")
    door_system = DoorSystem()
    
    # Load first room
    if door_system.load_room(1, "1A"):
        print("✓ Loaded room 1A")
        
        # Show room info
        info = door_system.get_current_room_info()
        print(f"Room info: {info}")
        
        # Test spawn point
        spawn = door_system.get_spawn_point()
        if spawn:
            print(f"✓ Spawn point: {spawn}")
        
        # Test door exits
        exits = info.get("exits", {})
        for exit_key, target_room in exits.items():
            print(f"  {exit_key} → {target_room}")
    
    print("\n=== Testing room transitions ===")
    # Simulate door interaction
    door_system.load_room(1, "1A")
    
    # Simulate using door_exit_1
    print("Simulating door_exit_1 interaction...")
    # Create fake tile data for testing
    from src.tiles.tile_data import TileData, InteractionProperties
    from src.tiles.tile_types import TileType
    
    fake_door_tile = TileData(
        tile_type=TileType.DOOR_EXIT_1,
        name="Test Door",
        interaction=InteractionProperties(
            on_interact_id="door_exit_1"
        )
    )
    
    door_system._process_door_interaction(fake_door_tile, (38, 13))  # Approx door position
    
    # Show current room after transition
    info = door_system.get_current_room_info()
    print(f"After transition: {info}")


if __name__ == "__main__":
    test_door_system()