#!/usr/bin/env python3
"""
Debug door placement in detail
"""

from src.level.procedural_generator import (
    generate_validated_room, 
    GenerationConfig, 
    MovementAttributes,
    flood_fill_find_regions
)

def debug_detailed_placement():
    """Debug door placement in detail"""
    
    config = GenerationConfig(seed=42, min_room_size=20, max_room_size=30)
    movement_attrs = MovementAttributes()
    
    print("=== Generating room ===")
    room = generate_validated_room(config, movement_attrs, depth_from_start=0, exit_doors=2)
    
    print(f"Room size: {room.size}")
    print(f"Player spawn: {room.player_spawn}")
    
    # Check regions
    regions = flood_fill_find_regions(room)
    print(f"Number of connected regions: {len(regions)}")
    for i, region in enumerate(regions):
        print(f"Region {i}: {len(region)} tiles")
    
    print(f"\nDoors placed: {len(room.doors)}")
    for door_id, door in room.doors.items():
        print(f"Door {door_id}: type={door.door_type}, position={door.position}")

if __name__ == "__main__":
    debug_detailed_placement()