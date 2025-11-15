from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional
from functools import wraps

from config import FPS, GREEN, CYAN, WHITE, DOUBLE_JUMPS
from ..entities.entities import floating, DamageNumber


Color = Tuple[int, int, int]

import pygame
import logging
from pathlib import Path

# Simple icon cache and loader for item icons
ICON_CACHE: Dict[str, Optional[pygame.Surface]] = {}
ICON_INFO_CACHE: Dict[str, bool] = {}


# Rarity -> border color mapping (used for item borders)
RARITY_BORDER_COLORS: Dict[str, Color] = {
    'Normal': (160, 160, 190),
    'Rare': (100, 170, 255),
    'Epic': (200, 120, 255),
    'Legendary': (255, 200, 80),
}


def darken_color(color: Color, factor: float = 0.6) -> Color:
    """Return a darker variant of a color."""
    return tuple(max(0, int(c * factor)) for c in color)


def rarity_border_color(item_or_rarity: Any) -> Color:
    """Get a border color for an item or rarity string.

    Accepts either an item object (with a `rarity` attribute) or a rarity string.
    Falls back to the Normal rarity color if unknown.
    """
    rarity = None
    if isinstance(item_or_rarity, str):
        rarity = item_or_rarity
    elif item_or_rarity is None:
        rarity = 'Normal'
    else:
        rarity = getattr(item_or_rarity, 'rarity', 'Normal')
    return RARITY_BORDER_COLORS.get(rarity, RARITY_BORDER_COLORS['Normal'])


def load_icon(path: str, size: tuple = (24,24)) -> Optional[pygame.Surface]:
    """Load and cache an icon surface (returns Surface or None).

    This keeps the old API returning a Surface (or None) so existing code stays compatible.
    """
    if not path:
        return None
    p = Path(path)
    key = str(p)
    cache_key = f"{key}:{size[0]}x{size[1]}"
    if cache_key in ICON_CACHE:
        return ICON_CACHE[cache_key]
    try:
        surf = pygame.image.load(key).convert_alpha()
        if surf.get_size() != size:
            surf = pygame.transform.smoothscale(surf, size)
        ICON_CACHE[cache_key] = surf
        return surf
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to load icon '%s': %s", key, e)
        ICON_CACHE[cache_key] = None
        return None


def icon_has_transparency(path: str, size: tuple = (24,24)) -> bool:
    """Return True if the given icon image contains any transparent pixels.

    This caches the boolean result separately so we don't recompute masks repeatedly.
    """
    if not path:
        return False
    p = Path(path)
    key = str(p)
    cache_key = f"{key}:{size[0]}x{size[1]}"
    if cache_key in ICON_INFO_CACHE:
        return ICON_INFO_CACHE[cache_key]
    surf = load_icon(path, size)
    if not surf:
        ICON_INFO_CACHE[cache_key] = False
        return False
    try:
        mask = pygame.mask.from_surface(surf)
        total_pixels = surf.get_width() * surf.get_height()
        non_transparent = mask.count()
        has_transparency = non_transparent < total_pixels
        ICON_INFO_CACHE[cache_key] = has_transparency
        return has_transparency
    except Exception:
        ICON_INFO_CACHE[cache_key] = False
        return False


# Cache for masked icons keyed by path:size:radius
MASKED_ICON_CACHE: Dict[str, Optional[pygame.Surface]] = {}


def mask_surface_rounded(surf: pygame.Surface, radius: int) -> Optional[pygame.Surface]:
    """Return a new Surface where pixels outside a rounded rect of given radius are transparent.

    This multiplies the image's alpha by a mask shaped as a rounded rect using BLEND_RGBA_MULT.
    """
    if surf is None:
        return None
    try:
        size = surf.get_size()
        mask = pygame.Surface(size, pygame.SRCALPHA)
        mask.fill((255, 255, 255, 0))
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        result = surf.copy()
        result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return result
    except Exception:
        # Fallback: return original surface if masking fails
        return surf


def load_icon_masked(path: str, size: tuple = (24,24), radius: int = 6) -> Optional[pygame.Surface]:
    """Load an icon and return a version masked to a rounded rect of `radius`.

    Results are cached by path:size:radius to avoid repeated work.
    """
    if not path:
        return None
    p = Path(path)
    key = str(p)
    cache_key = f"{key}:{size[0]}x{size[1]}:r{radius}"
    if cache_key in MASKED_ICON_CACHE:
        return MASKED_ICON_CACHE[cache_key]
    surf = load_icon(path, size)
    if not surf:
        MASKED_ICON_CACHE[cache_key] = None
        return None
    try:
        masked = mask_surface_rounded(surf, radius)
    except Exception:
        masked = None
    MASKED_ICON_CACHE[cache_key] = masked
    return masked





def validate_consumable_use(func):
    """Decorator to validate common consumable parameters"""
    @wraps(func)
    def wrapper(self, game):
        player = game.player
        if not player:
            return False
        
        # Common validations for duration-based consumables
        if hasattr(self, 'duration') and hasattr(self, 'amount'):
            frames = int(self.duration * FPS)
            if frames <= 0 or self.amount <= 0:
                return False
        elif hasattr(self, 'duration'):
            frames = int(self.duration * FPS)
            if frames <= 0:
                return False
        
        return func(self, game)
    return wrapper


class TooltipMixin:
    """Common tooltip functionality for all items"""
    
    def tooltip_lines(self) -> List[str]:
        lines = [getattr(self, 'name', 'Unknown Item')]
        if hasattr(self, 'effect_text') and self.effect_text:
            lines.append(self.effect_text)
        if hasattr(self, 'description') and self.description:
            lines.append(self.description)
        if hasattr(self, 'flavor') and self.flavor:
            lines.append(self.flavor)
        return lines


class ConsumableEffect:
    """Base class for consumable effects with common patterns"""
    
    def _show_feedback(self, player, text: str, color: Color) -> None:
        """Show floating text feedback"""
        floating.append(DamageNumber(
            player.rect.centerx, 
            player.rect.top - 12, 
            text, 
            color
        ))


@dataclass(frozen=True)
class Consumable(TooltipMixin):
    key: str
    name: str
    color: Color
    max_stack: int = 3
    effect_text: str = ""
    description: str = ""
    flavor: str = ""
    icon_letter: str = ""
    icon_path: str = ""

    def use(self, game) -> bool:
        """Apply the consumable effect to the running game. Returns True when consumed."""
        raise NotImplementedError


@dataclass(frozen=True)
class HealConsumable(Consumable, ConsumableEffect):
    amount: int = 0

    @validate_consumable_use
    def use(self, game) -> bool:
        player = game.player
        before = player.hp
        player.hp = min(player.max_hp, player.hp + self.amount)
        healed = player.hp - before
        if healed <= 0:
            return False
        self._show_feedback(player, f"+{healed} HP", GREEN)
        return True


@dataclass(frozen=True)
class ManaConsumable(Consumable, ConsumableEffect):
    amount: float = 0.0

    @validate_consumable_use
    def use(self, game) -> bool:
        player = game.player
        if not hasattr(player, 'mana'):
            return False
        before = player.mana
        player.mana = min(player.max_mana, player.mana + self.amount)
        restored = player.mana - before
        if restored <= 0:
            return False
        self._show_feedback(player, f"+{restored:.0f} MP", CYAN)
        return True


@dataclass(frozen=True)
class SpeedConsumable(Consumable, ConsumableEffect):
    amount: float = 0.0
    duration: float = 0.0  # seconds

    @validate_consumable_use
    def use(self, game) -> bool:
        player = game.player
        frames = int(self.duration * FPS)
        current = getattr(player, 'speed_potion_timer', 0)
        player.speed_potion_timer = max(current, frames)
        player.speed_potion_bonus = max(getattr(player, 'speed_potion_bonus', 0.0), self.amount)
        self._show_feedback(player, "Haste", WHITE)
        return True


@dataclass(frozen=True)
class JumpBoostConsumable(Consumable, ConsumableEffect):
    duration: float = 10.0
    jump_multiplier: float = 1.2
    extra_jumps: int = 2

    @validate_consumable_use
    def use(self, game) -> bool:
        player = game.player
        frames = int(self.duration * FPS)
        player.jump_boost_timer = frames
        player.jump_force_multiplier = max(self.jump_multiplier, getattr(player, 'jump_force_multiplier', 1.0))
        player.extra_jump_charges = max(self.extra_jumps, getattr(player, 'extra_jump_charges', 0))
        player.double_jumps = max(player.double_jumps, DOUBLE_JUMPS + self.extra_jumps)
        self._show_feedback(player, "Skybound", WHITE)
        return True


@dataclass(frozen=True)
class StaminaBoostConsumable(Consumable, ConsumableEffect):
    bonus_pct: float = 0.25
    duration: float = 30.0

    @validate_consumable_use
    def use(self, game) -> bool:
        player = game.player
        frames = int(self.duration * FPS)
        player.stamina_boost_timer = frames
        player.stamina_buff_mult = 1.0 + self.bonus_pct
        self._show_feedback(player, "+Stamina", GREEN)
        if hasattr(game, 'recalculate_player_stats'):
            game.recalculate_player_stats()
        return True


@dataclass(frozen=True)
class PhoenixFeather(Consumable, ConsumableEffect):
    key: str = "phoenix_feather"
    name: str = "Phoenix Feather"
    color: Color = (255, 150, 50)
    max_stack: int = 1
    effect_text: str = "Auto-revive with 50% HP on death"
    description: str = "A mystical feather that ignites when life fades."
    flavor: str = "Reborn from ashes, just like the legendary phoenix."
    icon_letter: str = "P"

    def use(self, game) -> bool:
        player = game.player
        if not hasattr(player, 'phoenix_feather_active'):
            player.phoenix_feather_active = False
        
        if player.phoenix_feather_active:
            self._show_feedback(player, "Already Active", WHITE)
            return False
            
        player.phoenix_feather_active = True
        self._show_feedback(player, "Phoenix Blessing", self.color)
        return True


@dataclass(frozen=True)
class TimeCrystal(Consumable, ConsumableEffect):
    key: str = "time_crystal"
    name: str = "Time Crystal"
    color: Color = (150, 150, 255)
    max_stack: int = 2
    effect_text: str = "Slows all enemies for 10 seconds"
    description: str = "Crystallized time that bends reality around foes."
    flavor: str = "Feel time itself slow to a crawl."
    icon_letter: str = "T"

    def use(self, game) -> bool:
        # Apply slow effect to all enemies
        for enemy in game.enemies:
            if getattr(enemy, 'alive', False):
                enemy.slow_mult = 0.3
                enemy.slow_remaining = 10 * FPS
                floating.append(DamageNumber(enemy.rect.centerx, enemy.rect.top - 6, "SLOWED", CYAN))
        
        self._show_feedback(game.player, "Time Distorted", self.color)
        return True


@dataclass(frozen=True)
class LuckyCharm(Consumable, ConsumableEffect):
    key: str = "lucky_charm"
    name: str = "Lucky Charm"
    color: Color = (255, 215, 0)
    max_stack: int = 1
    effect_text: str = "+50% money drops for 2 minutes"
    description: str = "A charm that attracts wealth from defeated foes."
    flavor: str = "Fortune favors the bold... and the charmed."
    icon_letter: str = "L"

    def use(self, game) -> bool:
        player = game.player
        if not hasattr(player, 'lucky_charm_timer'):
            player.lucky_charm_timer = 0
        
        if player.lucky_charm_timer > 0:
            self._show_feedback(player, "Already Active", WHITE)
            return False
            
        player.lucky_charm_timer = 120 * FPS  # 2 minutes
        self._show_feedback(player, "Lucky!", self.color)
        return True


@dataclass(frozen=True)
class ArmamentItem(TooltipMixin):
    key: str
    name: str
    color: Color
    icon_letter: str
    description: str
    modifiers: Dict[str, float]
    rarity: str = "Normal"
    icon_path: str = ""
    flavor: str = ""


class ItemFactory:
    """Factory for creating items with consistent initialization"""
    
    @staticmethod
    def create_consumable(item_type: str, **kwargs) -> Consumable:
        """Create a consumable item with proper initialization"""
        consumable_classes = {
            'health': HealConsumable,
            'mana': ManaConsumable,
            'speed': SpeedConsumable,
            'skyroot': JumpBoostConsumable,
            'stamina': StaminaBoostConsumable,
            'phoenix_feather': PhoenixFeather,
            'time_crystal': TimeCrystal,
            'lucky_charm': LuckyCharm,
        }
        
        cls = consumable_classes.get(item_type)
        if not cls:
            raise ValueError(f"Unknown consumable type: {item_type}")
        # Provide a default icon_path if not set
        if 'icon_path' not in kwargs or not kwargs.get('icon_path'):
            kwargs['icon_path'] = 'assets/consumable/con_placeholder.png'
        
        return cls(**kwargs)
    
    @staticmethod
    def create_armament(**kwargs) -> ArmamentItem:
        """Create an armament item with proper initialization"""
        # Provide a default icon if not supplied
        if 'icon_path' not in kwargs or not kwargs.get('icon_path'):
            kwargs['icon_path'] = 'assets/armament/aug_placeholder.png'
        # Default rarity if not provided
        if 'rarity' not in kwargs or not kwargs.get('rarity'):
            kwargs['rarity'] = 'Normal'
        return ArmamentItem(**kwargs)


def _build_consumable_items(shop_only: bool = False) -> Dict[str, Consumable]:
    """Build consumable items dictionary"""
    consumables = [
        ItemFactory.create_consumable(
            'health',
            key='health',
            name="Health Flask",
            color=(215, 110, 120),
            icon_letter="H",
            max_stack=5,
            amount=3,
            effect_text="Restore 3 HP instantly.",
            description="Distilled petals from palace gardens.",
        ),
        ItemFactory.create_consumable(
            'mana',
            key='mana',
            name="Mana Vial",
            color=(120, 180, 240),
            icon_letter="M",
            max_stack=5,
            amount=10,
            effect_text="Restore 10 mana.",
            description="Clinks with crystallized star-salts.",
        ),
        ItemFactory.create_consumable(
            'speed',
            key='speed',
            name="Haste Draught",
            color=(255, 200, 120),
            icon_letter="S",
            max_stack=3,
            amount=0.05,
            duration=8.0,
            effect_text="Short burst of speed and cooldown haste.",
            description="Citrus fizz harvested from sun-basil.",
        ),
        ItemFactory.create_consumable(
            'skyroot',
            key='skyroot',
            name="Skyroot Elixir",
            color=(200, 220, 255),
            icon_letter="J",
            max_stack=3,
            duration=12.0,
            jump_multiplier=1.25,
            extra_jumps=1,
            effect_text="Higher jumps and triple-jump for 12s.",
            description="Sap of levitating Skyroot tree.",
            flavor="Feels like standing on stormclouds.",
        ),
        ItemFactory.create_consumable(
            'stamina',
            key='stamina',
            name="Cavern Brew",
            color=(120, 200, 140),
            icon_letter="C",
            max_stack=3,
            duration=30.0,
            bonus_pct=0.25,
            effect_text="+25% stamina for 30s. Bar glows green.",
            description="Hidden-cave tonic that stretches every breath.",
            flavor="Thick, earthy, stubborn.",
        ),
    ]
    
    # Add shop-only consumables if not shop_only
    if not shop_only:
        consumables.extend([
            ItemFactory.create_consumable('phoenix_feather'),
            ItemFactory.create_consumable('time_crystal'),
            ItemFactory.create_consumable('lucky_charm'),
        ])
    
    return {item.key: item for item in consumables}


def _build_armament_items(shop_only: bool = False) -> Dict[str, ArmamentItem]:
    """Build armament items dictionary from the AUG list provided by the designer.

    Each entry includes `rarity` and may include on-hit metadata as custom modifier keys
    (e.g., `on_hit_poison_stacks`, `lifesteal_pct`, `skill_damage_mult`).
    Icons default to the placeholder unless `icon_path` is overridden per-item.
    """
    items = [
        # Normal
        ItemFactory.create_armament(key="AUG-001", name="Worn Crest", color=(200,160,120), icon_letter="C",
                                    description="Attack +2", modifiers={'attack_damage': 2}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-002", name="Worn Ward", color=(170,180,200), icon_letter="W",
                                    description="Defense +2", modifiers={'max_hp': 2}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-003", name="Lesser Venom Locus", color=(160,200,120), icon_letter="V",
                                    description="Increase poison damage by 5%", modifiers={'poison_damage_pct': 0.05}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-004", name="Smoldering Ember", color=(240,110,70), icon_letter="E",
                                    description="Attacks inflict Burn (1s)", modifiers={'on_hit_burn_duration': 1.0, 'on_hit_burn_dps': 1.0}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-005", name="Tainted Shard", color=(120,180,100), icon_letter="T",
                                    description="Attacks inflict 1 stack of Poison", modifiers={'on_hit_poison_stacks': 1, 'on_hit_poison_dps': 1.0, 'on_hit_poison_duration': 4.0}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-006", name="Jagged Edge", color=(200,120,100), icon_letter="J",
                                    description="Attacks inflict Bleed (1s)", modifiers={'on_hit_bleed_duration': 1.0, 'on_hit_bleed_dps': 1.0}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-007", name="Rime Fragment", color=(160,200,230), icon_letter="R",
                                    description="5% chance to Freeze on hit", modifiers={'on_hit_freeze_chance': 0.05, 'on_hit_freeze_duration': 1.0}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-008", name="Leeching Sigil", color=(140,110,90), icon_letter="L",
                                    description="Lifesteal 1%", modifiers={'lifesteal_pct': 0.01}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-009", name="Swiftlet Feather", color=(200,220,180), icon_letter="S",
                                    description="Attack speed +5%", modifiers={'attack_speed': 0.05}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-010", name="Worn Boot-charm", color=(180,160,140), icon_letter="B",
                                    description="Move speed +5%", modifiers={'player_speed': 0.05}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-011", name="Lesser Core of Vigor", color=(160,200,180), icon_letter="V",
                                    description="Stamina regen +5%", modifiers={'stamina_regen': 0.05}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-012", name="Evasion Module", color=(170,220,240), icon_letter="E",
                                    description="Dash stamina cost -10%", modifiers={'dash_stamina_cost_mult': 0.9}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-013", name="Rusted Chrono-lens", color=(210,190,200), icon_letter="C",
                                    description="Skill cooldown -5%", modifiers={'skill_cooldown_reduction': 0.05}, rarity='Normal'),
        ItemFactory.create_armament(key="AUG-014", name="Faded Amplifier", color=(200,160,220), icon_letter="F",
                                    description="Skill damage +5%", modifiers={'skill_damage_mult': 0.05}, rarity='Normal'),
        # Rare
        ItemFactory.create_armament(key="AUG-101", name="Soldier's Crest", color=(190,140,120), icon_letter="C",
                                    description="Attack +5", modifiers={'attack_damage': 5}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-102", name="Sentry's Ward", color=(140,160,180), icon_letter="W",
                                    description="Defense +5", modifiers={'max_hp': 5}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-103", name="Venom Locus", color=(120,190,110), icon_letter="V",
                                    description="Increase poison damage by 10%", modifiers={'poison_damage_pct': 0.10}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-104", name="Burning Ember", color=(255,110,60), icon_letter="B",
                                    description="Attacks inflict Burn (2s)", modifiers={'on_hit_burn_duration': 2.0, 'on_hit_burn_dps': 2.0}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-105", name="Corrupted Shard", color=(130,160,90), icon_letter="C",
                                    description="Attacks inflict 2 stacks of Poison", modifiers={'on_hit_poison_stacks': 2, 'on_hit_poison_dps': 1.5, 'on_hit_poison_duration': 5.0}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-106", name="Serrated Edge", color=(190,110,110), icon_letter="S",
                                    description="Attacks inflict Bleed (2s)", modifiers={'on_hit_bleed_duration': 2.0, 'on_hit_bleed_dps': 1.5}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-107", name="Frostbitten Core", color=(160,200,250), icon_letter="F",
                                    description="10% chance to Freeze on hit", modifiers={'on_hit_freeze_chance': 0.10, 'on_hit_freeze_duration': 1.5}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-108", name="Siphoning Sigil", color=(150,100,120), icon_letter="S",
                                    description="Lifesteal 3%", modifiers={'lifesteal_pct': 0.03}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-109", name="Raptor Feather", color=(210,180,130), icon_letter="R",
                                    description="Attack speed +10%", modifiers={'attack_speed': 0.10}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-110", name="Runner's Charm", color=(170,200,240), icon_letter="R",
                                    description="Move speed +10%", modifiers={'player_speed': 0.10}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-111", name="Core of Vigor", color=(160,220,150), icon_letter="C",
                                    description="Stamina regen +10%", modifiers={'stamina_regen': 0.10}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-112", name="Agility Module", color=(170,210,230), icon_letter="A",
                                    description="Dash stamina cost -20%", modifiers={'dash_stamina_cost_mult': 0.8}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-113", name="Polished Chrono-lens", color=(200,180,220), icon_letter="P",
                                    description="Skill cooldown -10%", modifiers={'skill_cooldown_reduction': 0.10}, rarity='Rare'),
        ItemFactory.create_armament(key="AUG-114", name="Arcane Amplifier", color=(215,160,255), icon_letter="A",
                                    description="Skill damage +15%", modifiers={'skill_damage_mult': 0.15}, rarity='Rare'),
        # Epic
        ItemFactory.create_armament(key="AUG-201", name="Knight's Crest", color=(210,160,150), icon_letter="K",
                                    description="Attack +10", modifiers={'attack_damage': 10}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-202", name="Guardian's Ward", color=(150,170,190), icon_letter="G",
                                    description="Defense +10", modifiers={'max_hp': 10}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-203", name="Virulent Locus", color=(110,180,100), icon_letter="V",
                                    description="Increase poison damage by 20%", modifiers={'poison_damage_pct': 0.20}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-204", name="Blazing Ember", color=(255,120,70), icon_letter="B",
                                    description="Attacks inflict Burn (3s)", modifiers={'on_hit_burn_duration': 3.0, 'on_hit_burn_dps': 3.0}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-205", name="Pestilent Shard", color=(120,150,80), icon_letter="P",
                                    description="Attacks inflict 3 stacks of Poison", modifiers={'on_hit_poison_stacks': 3, 'on_hit_poison_dps': 2.0, 'on_hit_poison_duration': 6.0}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-206", name="Grieving Edge", color=(200,100,120), icon_letter="G",
                                    description="Attacks inflict Bleed (3s)", modifiers={'on_hit_bleed_duration': 3.0, 'on_hit_bleed_dps': 2.0}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-207", name="Glacial Core", color=(150,210,240), icon_letter="G",
                                    description="20% chance to Freeze on hit", modifiers={'on_hit_freeze_chance': 0.20, 'on_hit_freeze_duration': 2.0}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-208", name="Vampiric Sigil", color=(180,120,120), icon_letter="V",
                                    description="Lifesteal 5%", modifiers={'lifesteal_pct': 0.05}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-209", name="Cyclone Feather", color=(220,200,140), icon_letter="C",
                                    description="Attack speed +15%", modifiers={'attack_speed': 0.15}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-210", name="Greater Core of Vigor", color=(140,230,170), icon_letter="G",
                                    description="Stamina regen +20%", modifiers={'stamina_regen': 0.20}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-211", name="Flow-State Module", color=(200,220,240), icon_letter="F",
                                    description="Dash stamina cost -35%", modifiers={'dash_stamina_cost_mult': 0.65}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-212", name="Focused Chrono-lens", color=(210,190,230), icon_letter="F",
                                    description="Skill cooldown -20%", modifiers={'skill_cooldown_reduction': 0.20}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-213", name="Resonant Amplifier", color=(240,160,220), icon_letter="R",
                                    description="Skill damage +30%", modifiers={'skill_damage_mult': 0.30}, rarity='Epic'),
        ItemFactory.create_armament(key="AUG-214", name="Windwalker's Charm", color=(200,230,200), icon_letter="W",
                                    description="Move speed +15%", modifiers={'player_speed': 0.15}, rarity='Epic'),
        # Legendary (omit double-jump AUG-301 per request)
        ItemFactory.create_armament(key="AUG-302", name="Echoing Blade Shard", color=(255,180,160), icon_letter="E",
                                    description="Double attack", modifiers={'double_attack': 1}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-303", name="Mark of the Inferno", color=(255,120,80), icon_letter="M",
                                    description="Attacks always inflict Burn (2s)", modifiers={'on_hit_burn_duration': 2.0, 'on_hit_burn_dps': 5.0, 'on_hit_burn_always': True}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-304", name="Heart of the Plague", color=(130,180,90), icon_letter="H",
                                    description="Attacks inflict 5 stacks of Poison", modifiers={'on_hit_poison_stacks': 5, 'on_hit_poison_dps': 3.0, 'on_hit_poison_duration': 8.0}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-305", name="Winter's Grasp", color=(170,220,255), icon_letter="W",
                                    description="40% chance to Freeze on hit", modifiers={'on_hit_freeze_chance': 0.40, 'on_hit_freeze_duration': 3.0}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-306", name="Blink-Dash Actuator", color=(200,170,240), icon_letter="B",
                                    description="Gain a second dash (consumes stamina)", modifiers={'extra_dash_charges': 1, 'double_dash': True}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-307", name="Titan's Lung", color=(220,200,160), icon_letter="T",
                                    description="Max stamina +100", modifiers={'max_stamina': 100}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-308", name="Heart of the Marathon", color=(180,230,200), icon_letter="H",
                                    description="Stamina regen +40%", modifiers={'stamina_regen': 0.40}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-309", name="Zephyr's Soul", color=(230,220,200), icon_letter="Z",
                                    description="Attack speed +25%", modifiers={'attack_speed': 0.25}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-310", name="Gale-Force Essence", color=(220,240,255), icon_letter="G",
                                    description="Move speed +25%", modifiers={'player_speed': 0.25}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-311", name="Sands of Perpetuity", color=(255,230,180), icon_letter="S",
                                    description="Skill cooldown -35%", modifiers={'skill_cooldown_reduction': 0.35}, rarity='Legendary'),
        ItemFactory.create_armament(key="AUG-312", name="Echo of the Void", color=(180,160,240), icon_letter="E",
                                    description="Skill damage +50%", modifiers={'skill_damage_mult': 0.50}, rarity='Legendary'),
    ]

    # Optionally include shop-only items (none extra currently)
    if shop_only:
        # If shop_only=True, filter items to those intended only for shops (none at the moment)
        pass

    return {item.key: item for item in items}



def build_item_catalog(item_types: Optional[List[str]] = None, shop_only: bool = False) -> Dict[str, Any]:
    """
    Build item catalogs with configurable options
    
    Args:
        item_types: List of item types to include ('consumables', 'armaments', 'all')
        shop_only: If True, only include shop-only items
    
    Returns:
        Dictionary of items keyed by their key
    """
    if item_types is None:
        item_types = ['consumables', 'armaments']
    
    catalog = {}
    
    if 'consumables' in item_types or 'all' in item_types:
        catalog.update(_build_consumable_items(shop_only))
    
    if 'armaments' in item_types or 'all' in item_types:
        catalog.update(_build_armament_items(shop_only))
    
    return catalog


# Legacy functions for backward compatibility
def build_armament_catalog() -> Dict[str, ArmamentItem]:
    """Legacy function - use build_item_catalog instead"""
    return _build_armament_items()


def build_consumable_catalog() -> Dict[str, Consumable]:
    """Legacy function - use build_item_catalog instead"""
    return _build_consumable_items()


def build_shop_consumables() -> Dict[str, Consumable]:
    """Legacy function - use build_item_catalog instead"""
    return {
        'phoenix_feather': ItemFactory.create_consumable('phoenix_feather'),
        'time_crystal': ItemFactory.create_consumable('time_crystal'),
        'lucky_charm': ItemFactory.create_consumable('lucky_charm'),
    }


def build_shop_equipment() -> Dict[str, ArmamentItem]:
    """Legacy function - use build_item_catalog instead"""
    return {
        'gold_plated_armor': ItemFactory.create_armament(
            key="gold_plated_armor",
            name="Gold-Plated Armor",
            color=(255, 215, 0),
            icon_letter="G",
            description="+2 HP, +10% damage resistance",
            modifiers={'max_hp': 2, 'damage_resistance': 0.1},
            flavor="Heavy armor that turns aside lethal blows."
        ),
        'swift_boots': ItemFactory.create_armament(
            key="swift_boots",
            name="Swift Boots",
            color=(100, 200, 255),
            icon_letter="S",
            description="+0.3 speed, +0.2 air speed, -20% dash cooldown",
            modifiers={
                'player_speed': 0.3,
                'player_air_speed': 0.2,
                'dash_cooldown_reduction': 0.2
            },
            flavor="Light as air, swift as the wind."
        ),
        'mana_siphon': ItemFactory.create_armament(
            key="mana_siphon",
            name="Mana Siphon",
            color=(200, 100, 255),
            icon_letter="M",
            description="+15 max mana, +0.3 mana regen, spell lifesteal",
            modifiers={
                'max_mana': 15,
                'mana_regen': 0.3 / FPS,
                'spell_lifesteal': 0.2
            },
            flavor="Draw power from both the ether and your foes."
        ),
    }
