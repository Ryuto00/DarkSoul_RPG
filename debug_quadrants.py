#!/usr/bin/env python3
"""
Debug script for door placement
"""

from src.level.procedural_generator import (
    get_spawn_quadrant,
    get_available_quadrants,
    randomly_assign_exit_quadrants
)

def debug_quadrant_logic():
    """Debug quadrant assignment logic"""
    
    # Test with spawn in top-left quadrant
    spawn_pos = (5, 5)  # top-left
    room_size = (20, 20)
    
    spawn_quadrant = get_spawn_quadrant(spawn_pos, room_size)
    print(f"Spawn position: {spawn_pos}")
    print(f"Spawn quadrant: {spawn_quadrant}")
    
    available_quadrants = get_available_quadrants(spawn_quadrant)
    print(f"Available quadrants: {available_quadrants}")
    
    # Test with 1 exit door
    exit_quadrants_1 = randomly_assign_exit_quadrants(available_quadrants, 1)
    print(f"1 exit door quadrants: {exit_quadrants_1}")
    
    # Test with 2 exit doors
    exit_quadrants_2 = randomly_assign_exit_quadrants(available_quadrants, 2)
    print(f"2 exit doors quadrants: {exit_quadrants_2}")

if __name__ == "__main__":
    debug_quadrant_logic()