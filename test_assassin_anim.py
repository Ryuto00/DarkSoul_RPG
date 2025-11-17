#!/usr/bin/env python3
"""
Test script to verify assassin animation state transitions
"""

import pygame
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.entities.enemy_entities import Assassin
from src.entities.animation_system import AnimationState

def test_assassin_animations():
    """Test assassin animation state transitions"""
    pygame.init()
    
    # Create a mock level and player for testing
    class MockLevel:
        def __init__(self):
            self.solids = []
    
    class MockPlayer:
        def __init__(self):
            self.rect = pygame.Rect(500, 300, 32, 32)
    
    # Create assassin
    assassin = Assassin(400, 300)
    level = MockLevel()
    player = MockPlayer()
    
    print("=== Assassin Animation Test ===")
    print(f"Initial state: {assassin.state}")
    print(f"Initial animation: {assassin.anim_manager.current_state}")
    print(f"Initial attacking: {assassin.attacking}")
    
    # Test 1: Check if animations are loaded
    print("\n=== Test 1: Animation Loading ===")
    expected_animations = [AnimationState.IDLE, AnimationState.RUN, AnimationState.ATTACK, AnimationState.DASH]
    for anim_state in expected_animations:
        if anim_state in assassin.anim_manager.animations:
            frames = len(assassin.anim_manager.animations[anim_state].frames)
            print(f"✓ {anim_state.value}: {frames} frames")
        else:
            print(f"✗ {anim_state.value}: NOT LOADED")
    
    # Test 2: Simulate attack sequence
    print("\n=== Test 2: Attack Animation Sequence ===")
    
    # Start attack
    assassin.action = 'slash'
    assassin.tele_t = 1
    assassin.attacking = True
    assassin.tick(level, player)
    
    print(f"After attack start - Animation: {assassin.anim_manager.current_state}, Attacking: {assassin.attacking}")
    
    # Simulate attack completion
    for i in range(20):
        assassin.tick(level, player)
        if not assassin.attacking:
            print(f"Attack completed at frame {i} - Animation: {assassin.anim_manager.current_state}")
            break
    
    # Test 3: Simulate dash sequence
    print("\n=== Test 3: Dash Animation Sequence ===")
    
    assassin.action = 'dash'
    assassin.tele_t = 1
    assassin.tick(level, player)
    
    print(f"After dash start - Animation: {assassin.anim_manager.current_state}, State: {assassin.state}")
    
    # Simulate dash completion
    for i in range(25):
        assassin.tick(level, player)
        if assassin.state == 'idle':
            print(f"Dash completed at frame {i} - Animation: {assassin.anim_manager.current_state}")
            break
    
    # Test 4: Test movement animations
    print("\n=== Test 4: Movement Animations ===")
    
    # Test running
    assassin.vx = 2.0
    assassin.tick(level, player)
    print(f"Running (vx=2.0) - Animation: {assassin.anim_manager.current_state}")
    
    # Test idle
    assassin.vx = 0.0
    assassin.tick(level, player)
    print(f"Idle (vx=0.0) - Animation: {assassin.anim_manager.current_state}")
    
    print("\n=== Test Complete ===")
    
    pygame.quit()

if __name__ == "__main__":
    test_assassin_animations()