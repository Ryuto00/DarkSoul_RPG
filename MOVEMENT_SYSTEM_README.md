# Enemy Movement System Overhaul

## Overview
This document describes the new enemy movement system that provides character-appropriate movement patterns, intelligent pathfinding, and dynamic behaviors for each enemy type.

## Features

### 1. Modular Movement Strategies
Each enemy type now uses a specific movement strategy that reflects their character:

- **GroundPatrolStrategy**: For Bug and Boss - basic ground movement with patrol and pursuit
- **JumpingStrategy**: For Frog - explosive jumping over obstacles
- **RangedTacticalStrategy**: For Archer - maintains optimal distance and tactical positioning
- **FloatingStrategy**: For WizardCaster - hovers above ground with smooth drifts

### 2. Terrain System
Enemies interact with different terrain types:

- **Normal**: Standard ground (all enemies)
- **Rough**: Slows movement, makes noise (ground, flying)
- **Water**: Slows significantly, wet effect (amphibious, flying)
- **Mud**: Very slow, chance to get stuck (ground, flying)
- **Ice**: Fast but slippery, reduced control (all enemies)
- **Lava**: Damage over time (fire_resistant, flying)
- **Toxic**: Poison damage (poison_resistant, flying)
- **Steep**: Requires climbing ability (climbing, flying)
- **Narrow**: Only small enemies can pass (small, flying)
- **Destructible**: Can be broken by strong enemies (strong, flying)

### 3. Enemy-Specific Traits
Each enemy has terrain access traits:

- **Bug**: `['ground', 'small', 'narrow']` - Can squeeze through tight spaces
- **Boss**: `['ground', 'strong', 'destructible']` - Can break obstacles
- **Frog**: `['ground', 'amphibious']` - Can move through water
- **Archer**: `['ground']` - Standard ground movement
- **WizardCaster**: `['ground', 'floating']` - Hovers above terrain
- **Assassin**: `['ground', 'climbing']` - Can climb walls
- **Bee**: `['flying']` - Ignores most terrain
- **Golem**: `['ground', 'strong', 'destructible', 'fire_resistant']` - Unstoppable

### 4. Dynamic Movement Properties
Each enemy has configurable movement properties:

- `base_speed`: Base movement speed
- `speed_multiplier`: Modified by terrain effects
- `terrain_traits`: Defines which terrain can be accessed
- `gravity_affected`: Whether gravity applies
- `on_ground`: Tracks ground contact
- `friction`: Movement friction coefficient

## Implementation

### File Structure
```
enemy_movement.py      # Movement strategy classes
terrain_system.py     # Terrain types and effects
enemy_entities.py     # Updated enemy classes
test_movement.py      # Test script for movement system
```

### Integration Steps

1. **Import new modules**:
   ```python
   from enemy_movement import MovementStrategyFactory
   from terrain_system import terrain_system
   ```

2. **Enemy initialization**:
   ```python
   def _set_movement_strategy(self):
       self.movement_strategy = MovementStrategyFactory.create_strategy('ground_patrol')
   ```

3. **Movement update**:
   ```python
   def tick(self, level, player):
       # Create context for movement strategy
       context = {
           'player': player,
           'has_los': has_los,
           'distance_to_player': dist_to_player,
           'level': level
       }
       
       # Handle movement with new system
       self.handle_movement(level)
   ```

4. **Terrain integration**:
   ```python
   # Load terrain for level
   terrain_system.load_terrain_from_level(level)
   
   # Terrain effects are automatically applied in handle_movement()
   ```

## Testing

Run the test script to see movement in action:
```bash
python test_movement.py
```

Controls:
- Arrow Keys: Move player
- T: Toggle terrain overlay
- ESC: Exit

## Balancing Parameters

### Speed Multipliers
- Bug: 1.8 (fast, erratic)
- Boss: 1.2 (slow, deliberate)
- Frog: 1.5 (medium, explosive)
- Archer: 1.2 (tactical)
- WizardCaster: 0.8 (slow, floating)
- Assassin: 1.5 (stealthy, quick)
- Bee: 2.5 (fast, aerial)
- Golem: 0.8 (very slow, unstoppable)

### Terrain Effects
- Speed modifiers range from 0.4 (mud) to 1.5 (ice)
- Special effects include: sliding, sticking, damage, poison, etc.
- Pathfinding avoids inaccessible terrain

## Future Enhancements

### Phase 2: Dynamic States
- State machines for aggressive/defensive/flanking behaviors
- Player behavior analysis and prediction
- Adaptive tactics based on situation

### Phase 3: Special Abilities
- Flying, teleportation, wall-climbing
- Burrowing, dashing, super jumping
- Ability cooldowns and conditions

### Phase 4: Group Coordination
- Enemy formations (surround, flank, pincer)
- Communication system for coordinated attacks
- Leader-based group tactics

### Phase 5: Polish
- Performance optimization
- Debug tools and visualization
- Extensive playtesting and balancing

## Usage Tips

1. **Start Simple**: Implement basic movement first, then add complexity
2. **Test Iteratively**: Test each enemy type individually
3. **Monitor Performance**: Watch for impact on game performance
4. **Player Feedback**: Pay attention to how movement feels from player perspective
5. **Modular Design**: Keep components separate for easy adjustment

## Troubleshooting

### Common Issues

1. **Enemies not moving**: Check if movement strategy is set correctly
2. **Terrain not working**: Verify terrain_system.load_terrain_from_level() is called
3. **Performance issues**: Reduce pathfinding complexity or update frequency
4. **Strange movement**: Check speed multipliers and terrain effects

### Debug Tools

- Enable terrain overlay with 'T' key in test script
- Use show_los=True to see vision cones
- Check console output for strategy names and terrain types

## Conclusion

This new movement system provides:
- More varied and interesting enemy behaviors
- Better environmental interaction
- Foundation for advanced AI features
- Modular, extensible architecture

The system is designed to be gradually enhanced through the implementation phases, allowing for testing and refinement at each step.