from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional
from functools import wraps

from config import FPS, GREEN, CYAN, WHITE, DOUBLE_JUMPS
from ..entities.entities import floating, DamageNumber


Color = Tuple[int, int, int]


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
        
        return cls(**kwargs)
    
    @staticmethod
    def create_armament(**kwargs) -> ArmamentItem:
        """Create an armament item with proper initialization"""
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
    """Build armament items dictionary"""
    items = [
        ItemFactory.create_armament(
            key="tower_bulwark",
            name="Tower Bulwark",
            color=(120, 140, 200),
            icon_letter="B",
            description="+3 HP, +2 Stamina capacity.",
            modifiers={'max_hp': 3, 'max_stamina': 2},
            flavor="Plated shield core carried by royal sentries."
        ),
        ItemFactory.create_armament(
            key="gale_boots",
            name="Gale Boots",
            color=(180, 220, 255),
            icon_letter="G",
            description="+0.6 ground / +0.4 air speed.",
            modifiers={'player_speed': 0.6, 'player_air_speed': 0.4},
            flavor="Canvas shoes threaded with windglass fibers."
        ),
        ItemFactory.create_armament(
            key="ember_blade",
            name="Ember Blade",
            color=(250, 150, 90),
            icon_letter="E",
            description="+2 Attack Power.",
            modifiers={'attack_damage': 2},
            flavor="Still warm from the forge at Ashen Gate."
        ),
        ItemFactory.create_armament(
            key="sages_focus",
            name="Sage's Focus",
            color=(170, 140, 255),
            icon_letter="S",
            description="+20 Mana, +0.5 mana regen.",
            modifiers={'max_mana': 20, 'mana_regen': 0.5 / FPS},
            flavor="Crystal monocle tuned to astral tides."
        ),
        ItemFactory.create_armament(
            key="hunter_totem",
            name="Hunter's Totem",
            color=(120, 200, 160),
            icon_letter="H",
            description="+1 Attack, steadier stamina regen.",
            modifiers={'attack_damage': 1, 'stamina_regen': 0.02},
            flavor="Bone charm carved for tireless stalking."
        ),
        ItemFactory.create_armament(
            key="stone_idol",
            name="Stone Idol",
            color=(160, 150, 130),
            icon_letter="I",
            description="+1 HP, +4 Stamina.",
            modifiers={'max_hp': 1, 'max_stamina': 4},
            flavor="A heavy relic that steadies every breath."
        ),
        ItemFactory.create_armament(
            key="void_thread",
            name="Void Thread",
            color=(90, 110, 190),
            icon_letter="V",
            description="+10 Mana, +0.2 air speed.",
            modifiers={'max_mana': 10, 'player_air_speed': 0.2},
            flavor="Cloak strand cut from a leaper between worlds."
        ),
        ItemFactory.create_armament(
            key="aurora_band",
            name="Aurora Band",
            color=(220, 200, 120),
            icon_letter="A",
            description="+1 HP, warm stamina trickle.",
            modifiers={'max_hp': 1, 'stamina_regen': 0.03},
            flavor="Glows softly when danger is near."
        ),
        ItemFactory.create_armament(
            key="wyrm_scale",
            name="Wyrm Scale",
            color=(200, 120, 160),
            icon_letter="W",
            description="+1 Attack, +1 HP.",
            modifiers={'attack_damage': 1, 'max_hp': 1},
            flavor="Hard enough to parry dragonfire."
        ),
    ]
    
    # Add shop-only equipment if not shop_only
    if not shop_only:
        items.extend([
            ItemFactory.create_armament(
                key="gold_plated_armor",
                name="Gold-Plated Armor",
                color=(255, 215, 0),
                icon_letter="G",
                description="+2 HP, +10% damage resistance",
                modifiers={'max_hp': 2, 'damage_resistance': 0.1},
                flavor="Heavy armor that turns aside lethal blows."
            ),
            ItemFactory.create_armament(
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
            ItemFactory.create_armament(
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
        ])
    
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
