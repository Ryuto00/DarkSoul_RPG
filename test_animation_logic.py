#!/usr/bin/env python3
"""
Simple test to verify assassin animation logic without sprite loading
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.entities.animation_system import AnimationState

def test_animation_state_logic():
    """Test the animation state transition logic"""
    
    print("=== Testing Animation State Logic ===")
    
    # Simulate the conditions from assassin tick method
    def check_animation_state(state, attacking, current_anim_state, vx):
        """Simulate the animation decision logic"""
        
        # This is the fixed logic from our changes
        if state == 'dash':
            return AnimationState.DASH
        elif attacking:
            return current_anim_state  # Let attack complete
        elif abs(vx) > 0.8:
            return AnimationState.RUN
        else:
            return AnimationState.IDLE
    
    # Test scenarios
    test_cases = [
        # (state, attacking, current_anim, vx, expected_result, description)
        ('idle', False, AnimationState.IDLE, 0.0, AnimationState.IDLE, "Normal idle"),
        ('idle', False, AnimationState.IDLE, 2.0, AnimationState.RUN, "Normal running"),
        ('idle', True, AnimationState.ATTACK, 0.0, AnimationState.ATTACK, "During attack - should stay in attack"),
        ('idle', False, AnimationState.ATTACK, 0.0, AnimationState.IDLE, "After attack completes - should go to idle"),
        ('dash', False, AnimationState.DASH, 5.0, AnimationState.DASH, "During dash - should stay in dash"),
        ('dash', False, AnimationState.DASH, 0.0, AnimationState.DASH, "Dash ending - should stay in dash until state changes"),
    ]
    
    print("Testing animation state decisions:")
    for i, (state, attacking, current, vx, expected, desc) in enumerate(test_cases, 1):
        result = check_animation_state(state, attacking, current, vx)
        status = "✓" if result == expected else "✗"
        print(f"{i}. {status} {desc}")
        print(f"   Input: state={state}, attacking={attacking}, current={current.value}, vx={vx}")
        print(f"   Expected: {expected.value}, Got: {result.value}")
        if result != expected:
            print(f"   *** MISMATCH! ***")
        print()
    
    print("=== Testing Problematic Original Logic ===")
    
    # Original problematic logic for comparison
    def check_original_logic(state, attacking, current_anim_state, vx):
        """Original problematic logic"""
        if not attacking and current_anim_state != AnimationState.ATTACK:
            if state == 'dash':
                return AnimationState.DASH
            elif abs(vx) > 0.8:
                return AnimationState.RUN
            else:
                return AnimationState.IDLE
        else:
            return current_anim_state  # Stays stuck
    
    # Test the problematic case
    problematic_cases = [
        (True, AnimationState.ATTACK, 0.0, "Attack animation playing but should be able to transition"),
        (False, AnimationState.ATTACK, 0.0, "Attack completed but stuck in ATTACK state"),
    ]
    
    print("Testing cases where original logic gets stuck:")
    for i, (attacking, current, vx, desc) in enumerate(problematic_cases, 1):
        result = check_original_logic('idle', attacking, current, vx)
        fixed_result = check_animation_state('idle', attacking, current, vx)
        
        print(f"{i}. {desc}")
        print(f"   Input: attacking={attacking}, current={current.value}, vx={vx}")
        print(f"   Original logic result: {result.value}")
        print(f"   Fixed logic result: {fixed_result.value}")
        
        if result == AnimationState.ATTACK and not attacking:
            print("   *** Original logic gets stuck here! ***")
        print()

if __name__ == "__main__":
    test_animation_state_logic()