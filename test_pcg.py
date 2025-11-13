#!/usr/bin/env python3

"""Test PCG integration"""

from src.level.config_loader import load_pcg_runtime_config
from src.level.pcg_generator_simple import generate_simple_pcg_level_set
from src.level.level_loader import level_loader

def test_pcg():
    print("Testing PCG integration...")
    
    # Load runtime config
    runtime = load_pcg_runtime_config()
    print(f"PCG enabled: {runtime.use_pcg}")
    print(f"Seed mode: {runtime.seed_mode}")
    print(f"Seed: {runtime.seed}")
    
    if runtime.use_pcg:
        # Generate levels
        level_set = generate_simple_pcg_level_set(seed=runtime.seed)
        print(f"Generated {len(level_set.levels)} levels")
        
        # Test level loader
        level_loader._level_set = level_set
        
        # Test getting starting room
        start_room = level_loader.get_starting_room(1)
        if start_room:
            print(f"Starting room: {start_room.room_code}")
            print(f"Room size: {len(start_room.tiles)}x{len(start_room.tiles[0])}")
            print(f"Door exits: {start_room.door_exits}")
        
        # Test navigation
        if start_room and start_room.door_exits:
            next_code = start_room.door_exits.get('door_exit_1')
            if next_code:
                next_room = level_loader.get_room(1, next_code)
                if next_room:
                    print(f"Next room: {next_room.room_code}")
                    print(f"Entrance from: {next_room.entrance_from}")
    
    print("PCG integration test complete!")

if __name__ == "__main__":
    test_pcg()