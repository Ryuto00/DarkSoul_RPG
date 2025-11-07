from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from config import FPS, GREEN, CYAN, WHITE, DOUBLE_JUMPS
from entities import floating, DamageNumber


Color = Tuple[int, int, int]


@dataclass(frozen=True)
class Consumable:
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

    def tooltip_lines(self) -> List[str]:
        lines = [self.name]
        if self.effect_text:
            lines.append(self.effect_text)
        if self.description:
            lines.append(self.description)
        if self.flavor:
            lines.append(self.flavor)
        return lines


@dataclass(frozen=True)
class HealConsumable(Consumable):
    amount: int = 0

    def use(self, game) -> bool:
        player = game.player
        before = player.hp
        player.hp = min(player.max_hp, player.hp + self.amount)
        healed = player.hp - before
        if healed <= 0:
            return False
        floating.append(DamageNumber(player.rect.centerx, player.rect.top - 12, f"+{healed} HP", GREEN))
        return True


@dataclass(frozen=True)
class ManaConsumable(Consumable):
    amount: float = 0.0

    def use(self, game) -> bool:
        player = game.player
        if not hasattr(player, 'mana'):
            return False
        before = player.mana
        player.mana = min(player.max_mana, player.mana + self.amount)
        restored = player.mana - before
        if restored <= 0:
            return False
        floating.append(DamageNumber(player.rect.centerx, player.rect.top - 12, f"+{restored:.0f} MP", CYAN))
        return True


@dataclass(frozen=True)
class SpeedConsumable(Consumable):
    amount: float = 0.0
    duration: float = 0.0  # seconds

    def use(self, game) -> bool:
        player = game.player
        frames = int(self.duration * FPS)
        if frames <= 0 or self.amount <= 0:
            return False
        current = getattr(player, 'speed_potion_timer', 0)
        player.speed_potion_timer = max(current, frames)
        player.speed_potion_bonus = max(getattr(player, 'speed_potion_bonus', 0.0), self.amount)
        floating.append(DamageNumber(player.rect.centerx, player.rect.top - 12, "Haste", WHITE))
        return True


@dataclass(frozen=True)
class JumpBoostConsumable(Consumable):
    duration: float = 10.0
    jump_multiplier: float = 1.2
    extra_jumps: int = 2

    def use(self, game) -> bool:
        player = game.player
        frames = int(self.duration * FPS)
        if frames <= 0:
            return False
        player.jump_boost_timer = frames
        player.jump_force_multiplier = max(self.jump_multiplier, getattr(player, 'jump_force_multiplier', 1.0))
        player.extra_jump_charges = max(self.extra_jumps, getattr(player, 'extra_jump_charges', 0))
        player.double_jumps = max(player.double_jumps, DOUBLE_JUMPS + self.extra_jumps)
        floating.append(DamageNumber(player.rect.centerx, player.rect.top - 12, "Skybound", WHITE))
        return True


@dataclass(frozen=True)
class StaminaBoostConsumable(Consumable):
    bonus_pct: float = 0.25
    duration: float = 30.0

    def use(self, game) -> bool:
        player = game.player
        frames = int(self.duration * FPS)
        if frames <= 0:
            return False
        player.stamina_boost_timer = frames
        player.stamina_buff_mult = 1.0 + self.bonus_pct
        floating.append(DamageNumber(player.rect.centerx, player.rect.top - 12, "+Stamina", GREEN))
        if hasattr(game, 'recalculate_player_stats'):
            game.recalculate_player_stats()
        return True


@dataclass(frozen=True)
class ArmamentItem:
    key: str
    name: str
    color: Color
    icon_letter: str
    description: str
    modifiers: Dict[str, float]
    flavor: str = ""

    def tooltip_lines(self) -> List[str]:
        lines = [self.name, self.description]
        if self.flavor:
            lines.append(self.flavor)
        return lines


def build_armament_catalog() -> Dict[str, ArmamentItem]:
    items = [
        ArmamentItem(
            key="tower_bulwark",
            name="Tower Bulwark",
            color=(120, 140, 200),
            icon_letter="B",
            description="+3 HP, +2 Stamina capacity.",
            modifiers={'max_hp': 3, 'max_stamina': 2},
            flavor="Plated shield core carried by royal sentries."
        ),
        ArmamentItem(
            key="gale_boots",
            name="Gale Boots",
            color=(180, 220, 255),
            icon_letter="G",
            description="+0.6 ground / +0.4 air speed.",
            modifiers={'player_speed': 0.6, 'player_air_speed': 0.4},
            flavor="Canvas shoes threaded with windglass fibers."
        ),
        ArmamentItem(
            key="ember_blade",
            name="Ember Blade",
            color=(250, 150, 90),
            icon_letter="E",
            description="+2 Attack Power.",
            modifiers={'attack_damage': 2},
            flavor="Still warm from the forge at Ashen Gate."
        ),
        ArmamentItem(
            key="sages_focus",
            name="Sage's Focus",
            color=(170, 140, 255),
            icon_letter="S",
            description="+20 Mana, +0.5 mana regen.",
            modifiers={'max_mana': 20, 'mana_regen': 0.5 / FPS},
            flavor="Crystal monocle tuned to astral tides."
        ),
        ArmamentItem(
            key="hunter_totem",
            name="Hunter's Totem",
            color=(120, 200, 160),
            icon_letter="H",
            description="+1 Attack, steadier stamina regen.",
            modifiers={'attack_damage': 1, 'stamina_regen': 0.02},
            flavor="Bone charm carved for tireless stalking."
        ),
        ArmamentItem(
            key="stone_idol",
            name="Stone Idol",
            color=(160, 150, 130),
            icon_letter="I",
            description="+1 HP, +4 Stamina.",
            modifiers={'max_hp': 1, 'max_stamina': 4},
            flavor="A heavy relic that steadies every breath."
        ),
        ArmamentItem(
            key="void_thread",
            name="Void Thread",
            color=(90, 110, 190),
            icon_letter="V",
            description="+10 Mana, +0.2 air speed.",
            modifiers={'max_mana': 10, 'player_air_speed': 0.2},
            flavor="Cloak strand cut from a leaper between worlds."
        ),
        ArmamentItem(
            key="aurora_band",
            name="Aurora Band",
            color=(220, 200, 120),
            icon_letter="A",
            description="+1 HP, warm stamina trickle.",
            modifiers={'max_hp': 1, 'stamina_regen': 0.03},
            flavor="Glows softly when danger is near."
        ),
        ArmamentItem(
            key="wyrm_scale",
            name="Wyrm Scale",
            color=(200, 120, 160),
            icon_letter="W",
            description="+1 Attack, +1 HP.",
            modifiers={'attack_damage': 1, 'max_hp': 1},
            flavor="Hard enough to parry dragonfire."
        ),
    ]
    return {item.key: item for item in items}
