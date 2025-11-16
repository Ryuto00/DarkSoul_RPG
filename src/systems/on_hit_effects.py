"""
On-Hit Effects System
Processes special effects from player augmentations when enemies are hit.
Handles poison, burn, bleed, freeze, and other combat effects.
"""

import random
import pygame
from typing import Dict, List, Optional, Any
from config import FPS
from ..entities.entities import floating, DamageNumber


class OnHitEffect:
    """Base class for on-hit effects from augmentations"""
    
    def __init__(self, source_item_key: str, effect_data: Dict[str, Any]):
        self.source_item = source_item_key
        self.effect_data = effect_data
    
    def apply(self, enemy, player, hitbox) -> bool:
        """Apply effect to enemy. Returns True if effect was applied."""
        raise NotImplementedError


class PoisonEffect(OnHitEffect):
    """Poison damage over time effect"""
    
    def apply(self, enemy, player, hitbox) -> bool:
        stacks = self.effect_data.get('on_hit_poison_stacks', 0)
        if stacks <= 0:
            return False
        
        dps = self.effect_data.get('on_hit_poison_dps', 1.0)
        duration = self.effect_data.get('on_hit_poison_duration', 4.0) * FPS
        
        # Apply or stack poison
        current_stacks = getattr(enemy, 'poison_stacks', 0)
        current_dps = getattr(enemy, 'poison_dps', 0.0)
        current_duration = getattr(enemy, 'poison_remaining', 0)
        
        # Stack effects: add stacks and DPS, extend duration
        new_stacks = current_stacks + stacks
        new_dps = current_dps + dps
        new_duration = max(current_duration, int(duration))
        
        enemy.poison_stacks = new_stacks
        enemy.poison_dps = new_dps
        enemy.poison_remaining = new_duration
        
        # Visual feedback
        floating.append(DamageNumber(
            enemy.rect.centerx,
            enemy.rect.top - 10,
            f"POISON +{stacks}",
            (100, 255, 100)  # Green poison color
        ))
        
        return True


class BurnEffect(OnHitEffect):
    """Burn damage over time effect"""
    
    def apply(self, enemy, player, hitbox) -> bool:
        always = self.effect_data.get('on_hit_burn_always', False)
        if not always and random.random() > 0.01:  # 99% chance to not apply (for non-always items)
            return False
        
        dps = self.effect_data.get('on_hit_burn_dps', 1.0)
        duration = self.effect_data.get('on_hit_burn_duration', 1.0) * FPS
        
        # Apply or stack burn
        current_dps = getattr(enemy, 'burn_dps', 0.0)
        current_duration = getattr(enemy, 'burn_remaining', 0)
        
        new_dps = current_dps + dps
        new_duration = max(current_duration, int(duration))
        
        enemy.burn_dps = new_dps
        enemy.burn_remaining = new_duration
        
        # Visual feedback
        floating.append(DamageNumber(
            enemy.rect.centerx,
            enemy.rect.top - 10,
            f"BURN +{dps:.0f}",
            (255, 150, 50)  # Orange burn color
        ))
        
        return True


class BleedEffect(OnHitEffect):
    """Bleed damage over time effect"""
    
    def apply(self, enemy, player, hitbox) -> bool:
        duration = self.effect_data.get('on_hit_bleed_duration', 0)
        if duration <= 0:
            return False
        
        dps = self.effect_data.get('on_hit_bleed_dps', 1.0)
        duration_frames = int(duration * FPS)
        
        # Apply or stack bleed
        current_dps = getattr(enemy, 'bleed_dps', 0.0)
        current_duration = getattr(enemy, 'bleed_remaining', 0)
        
        new_dps = current_dps + dps
        new_duration = max(current_duration, duration_frames)
        
        enemy.bleed_dps = new_dps
        enemy.bleed_remaining = new_duration
        
        # Visual feedback
        floating.append(DamageNumber(
            enemy.rect.centerx,
            enemy.rect.top - 10,
            f"BLEED +{dps:.0f}",
            (200, 50, 50)  # Red bleed color
        ))
        
        return True


class FreezeEffect(OnHitEffect):
    """Freeze (stun) chance effect"""
    
    def apply(self, enemy, player, hitbox) -> bool:
        chance = self.effect_data.get('on_hit_freeze_chance', 0.0)
        if chance <= 0 or random.random() > chance:
            return False
        
        duration = self.effect_data.get('on_hit_freeze_duration', 1.0) * FPS
        
        # Apply freeze (stun)
        enemy.stunned = max(getattr(enemy, 'stunned', 0), int(duration))
        enemy.frozen = True  # Add freeze flag for visual
        
        # Visual feedback
        floating.append(DamageNumber(
            enemy.rect.centerx,
            enemy.rect.top - 10,
            "FROZEN!",
            (150, 200, 255)  # Light blue freeze color
        ))
        
        return True


class DoubleAttackEffect(OnHitEffect):
    """Double attack effect"""
    
    def apply(self, enemy, player, hitbox) -> bool:
        # Create second hitbox with same damage
        original_rect = hitbox.rect.copy()
        second_hitbox = original_rect.copy()
        
        # Offset slightly for visual effect
        second_hitbox.x += 5
        second_hitbox.y += 5
        
        from ..entities.entity_common import Hitbox
        new_hitbox = Hitbox(
            second_hitbox,
            hitbox.lifetime,
            hitbox.damage,
            hitbox.owner,
            hitbox.dir_vec,
            hitbox.pogo,
            hitbox.vx,
            hitbox.vy,
            hitbox.aoe_radius,
            hitbox.visual_only,
            hitbox.pierce,
            hitbox.bypass_ifr,
            hitbox.tag
        )
        
        # Add to global hitboxes list
        from ..entities.entity_common import hitboxes
        hitboxes.append(new_hitbox)
        
        # Visual feedback on enemy
        floating.append(DamageNumber(
            enemy.rect.centerx,
            enemy.rect.top - 10,
            "DOUBLE HIT!",
            (255, 255, 100)  # Yellow double hit color
        ))
        
        # Visual feedback on player
        floating.append(DamageNumber(
            player.rect.centerx,
            player.rect.top - 20,
            "DOUBLE STRIKE!",
            (255, 220, 100)  # Orange-yellow for player
        ))
        
        return True


class OnHitEffectProcessor:
    """Main processor for all on-hit effects from player augmentations"""
    
    def __init__(self):
        self.effect_cache: Dict[str, List[OnHitEffect]] = {}
    
    def build_effect_cache(self, player) -> None:
        """Build cache of on-hit effects from player's equipped augmentations"""
        self.effect_cache.clear()
        
        if not hasattr(player, 'inventory') or not player.inventory:
            return
        
        # Get all equipped armaments
        for gear_key in player.inventory.gear_slots:
            if not gear_key:
                continue
            
            item = player.inventory.armament_catalog.get(gear_key)
            if not item or not hasattr(item, 'modifiers'):
                continue
            
            # Build effects from item modifiers
            effects = []
            
            # Poison effects
            if item.modifiers.get('on_hit_poison_stacks', 0) > 0:
                effects.append(PoisonEffect(gear_key, item.modifiers))
            
            # Burn effects
            if (item.modifiers.get('on_hit_burn_dps', 0) > 0 or 
                item.modifiers.get('on_hit_burn_always', False)):
                effects.append(BurnEffect(gear_key, item.modifiers))
            
            # Bleed effects
            if item.modifiers.get('on_hit_bleed_duration', 0) > 0:
                effects.append(BleedEffect(gear_key, item.modifiers))
            
            # Freeze effects
            if item.modifiers.get('on_hit_freeze_chance', 0) > 0:
                effects.append(FreezeEffect(gear_key, item.modifiers))
            
            # Double attack
            if item.modifiers.get('double_attack', 0) > 0:
                effects.append(DoubleAttackEffect(gear_key, item.modifiers))
            
            if effects:
                self.effect_cache[gear_key] = effects
    
    def process_on_hit_effects(self, enemy, player, hitbox) -> None:
        """Process all on-hit effects when enemy is successfully hit"""
        if not hasattr(player, 'inventory'):
            return
        
        # Rebuild cache if needed (lazy initialization)
        if not self.effect_cache:
            self.build_effect_cache(player)
        
        # Apply all effects from equipped items
        for gear_key, effects in self.effect_cache.items():
            for effect in effects:
                try:
                    effect.apply(enemy, player, hitbox)
                except Exception as e:
                    # Log error but don't crash game
                    print(f"Error applying on-hit effect from {gear_key}: {e}")
    
    def clear_cache(self) -> None:
        """Clear effect cache (call when player equipment changes)"""
        self.effect_cache.clear()


# Global processor instance
_on_hit_processor = OnHitEffectProcessor()


def get_on_hit_processor() -> OnHitEffectProcessor:
    """Get the global on-hit effect processor"""
    return _on_hit_processor


def process_on_hit_effects(enemy, player, hitbox) -> None:
    """Convenience function to process on-hit effects"""
    _on_hit_processor.process_on_hit_effects(enemy, player, hitbox)


def clear_on_hit_cache() -> None:
    """Clear the on-hit effect cache"""
    _on_hit_processor.clear_cache()