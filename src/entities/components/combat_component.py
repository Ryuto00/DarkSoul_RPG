"""
Combat Component - Shared combat logic for all entities
Eliminates code duplication in hit detection, damage application, and combat effects
"""

import random
from config import POGO_BOUNCE_VY, GREEN, CYAN, WHITE
from ..entity_common import DamageNumber, floating


class CombatComponent:
    """Handles combat mechanics for entities"""
    
    def __init__(self, entity):
        self.entity = entity
        self.invincible_frames = 0
        self.default_ifr = 8  # Default invincibility frames
        
    def take_damage(self, amount, knockback=(0, 0), source=None):
        """Apply damage to entity with knockback"""
        # Check for invincibility
        if self.invincible_frames > 0:
            return False
            
        # Apply damage
        self.entity.hp -= amount
        
        # Apply knockback
        if hasattr(self.entity, 'vx'):
            self.entity.vx += knockback[0]
        if hasattr(self.entity, 'vy'):
            self.entity.vy += knockback[1]
        
        # Set invincibility frames
        self.invincible_frames = self.default_ifr
        
        # Show damage number
        floating.append(DamageNumber(
            self.entity.rect.centerx,
            self.entity.rect.top - 6,
            f"-{amount}",
            WHITE
        ))
        
        # Check if entity died
        if self.entity.hp <= 0:
            self.entity.hp = 0
            self.entity.alive = False
            floating.append(DamageNumber(
                self.entity.rect.centerx,
                self.entity.rect.centery,
                "KO",
                CYAN
            ))
            
        return True
    
    def handle_hit(self, hitbox, player):
        """Handle being hit by a player attack"""
        # Check if entity can be hit
        if (self.invincible_frames > 0 and not getattr(hitbox, 'bypass_ifr', False)) or not self.entity.alive:
            return False
        
        # Apply damage
        damage_taken = self.take_damage(hitbox.damage, (0, 0), hitbox.owner)
        
        if not damage_taken:
            return False
        
        # Set invincibility frames (unless bypassed)
        if not getattr(hitbox, 'bypass_ifr', False):
            self.invincible_frames = self.default_ifr
        
        # Handle lifesteal for player
        if getattr(player, 'lifesteal', 0) > 0 and hitbox.damage > 0:
            old_hp = player.hp
            player.hp = min(player.max_hp, player.hp + 1)
            if player.hp != old_hp:
                floating.append(DamageNumber(
                    player.rect.centerx, 
                    player.rect.top - 10, 
                    "+1", 
                    GREEN
                ))
        
        # Handle pogo effect
        if hitbox.pogo:
            player.vy = POGO_BOUNCE_VY
            player.on_ground = False
        
        # Drop money if entity died
        if not self.entity.alive:
            self._drop_money(player)
        
        return True
    
    def _drop_money(self, player):
        """Drop money when entity dies"""
        # Get base amount based on enemy type
        enemy_type = self.entity.__class__.__name__
        if enemy_type == 'Bug':
            amount = random.randint(5, 15)
        elif enemy_type == 'Boss':
            amount = random.randint(50, 100)
        elif enemy_type == 'Bee':
            amount = random.randint(10, 25)
        elif enemy_type == 'Golem':
            amount = random.randint(50, 100)
        else:
            amount = random.randint(10, 20)  # Default amount
        
        # Apply lucky charm bonus if active
        if hasattr(player, 'lucky_charm_timer') and player.lucky_charm_timer > 0:
            amount = int(amount * 1.5)  # 50% bonus
        
        player.money += amount
        floating.append(DamageNumber(
            self.entity.rect.centerx,
            self.entity.rect.top - 12,
            f"+{amount}",
            (255, 215, 0)
        ))
    
    def update_invincibility(self):
        """Update invincibility frames"""
        if self.invincible_frames > 0:
            self.invincible_frames -= 1
            return True
        return False
    
    def is_invincible(self):
        """Check if entity is currently invincible"""
        return self.invincible_frames > 0
    
    def set_custom_ifr(self, frames):
        """Set custom invincibility frame duration"""
        self.default_ifr = frames
    
    def handle_player_collision(self, player, damage=1, knockback=(2, -6)):
        """Handle collision with player"""
        if self.entity.rect.colliderect(player.rect):
            # If player is parrying, reflect/hurt the enemy instead of player
            if getattr(player, 'parrying', 0) > 0:
                self.take_damage(1, (0, 0), player)
                floating.append(DamageNumber(
                    self.entity.rect.centerx,
                    self.entity.rect.top - 6,
                    "PARRY",
                    CYAN
                ))
                # Knockback away from player
                if hasattr(self.entity, 'vx'):
                    self.entity.vx = -((1 if player.rect.centerx > self.entity.rect.centerx else -1) * 3)
                if hasattr(player, 'vy'):
                    player.vy = -6
            elif player.inv == 0:
                player.damage(damage, (
                    (1 if player.rect.centerx > self.entity.rect.centerx else -1) * knockback[0],
                    knockback[1]
                ))