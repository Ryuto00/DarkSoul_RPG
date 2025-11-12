#!/usr/bin/env python3
"""
Test script for new door placement system
"""

from src.level.procedural_generator import generate_validated_room, GenerationConfig, MovementAttributes
from src.level.room_data import RoomData
from src.tiles.tile_types import TileType

def test_door_placement():
    """Test the new door placement system"""
    
    # Create test configuration
    config = GenerationConfig(
        seed=42,
        min_room_size=20,
        max_room_size=30
    )
    
    movement_attrs = MovementAttributes()
    
    print("Testing new door placement system...")
    
    # Generate a room with 1 exit door (linear level)
    room = generate_validated_room(
        config, 
        movement_attrs, 
        depth_from_start=0, 
        exit_doors=1
    )
    
    print(f"Room size: {room.size}")
    print(f"Player spawn: {room.player_spawn}")
    print(f"Number of doors: {len(room.doors)}")
    
    for door_id, door in room.doors.items():
        print(f"Door {door_id}: type={door.door_type}, position={door.position}")
    
    # Test with 2 exit doors (branching level)
    print("\nTesting with 2 exit doors...")
    room2 = generate_validated_room(
        config, 
        movement_attrs, 
        depth_from_start=0, 
        exit_doors=2
    )
    
    print(f"Room size: {room2.size}")
    print(f"Player spawn: {room2.player_spawn}")
    print(f"Number of doors: {len(room2.doors)}")
    
    for door_id, door in room2.doors.items():
        print(f"Door {door_id}: type={door.door_type}, position={door.position}")
    
    print("\nDoor placement test completed successfully!")

if __name__ == "__main__":
    test_door_placement()