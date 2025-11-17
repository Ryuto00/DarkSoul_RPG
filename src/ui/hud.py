"""
HUD drawing utilities for Haridd.
This module contains one main entrypoint: `draw_hud(game, screen)` which draws
all player-facing HUD elements (HP, cooldown bars, skill slots, consumable hotbar, status text,
coins, class label, interactive prompts previously in `main.py`).

Guidelines:
- Use absolute imports.
- Accept the Game instance and read-only access its attributes.
- Keep draw-only logic here; avoid mutating `game` except for purely visual helper calls.
"""
from typing import Tuple
import logging
import pygame

from config import WIDTH, HEIGHT, FPS, CYAN, WHITE, WALL_JUMP_COOLDOWN, TILE
from src.core.utils import draw_text

logger = logging.getLogger(__name__)

# Cache for skill icons to prevent loading every frame (performance optimization)
_skill_icon_cache = {}


def draw_hud(game, screen: pygame.Surface) -> None:
    """Draw HUD elements using `game`'s state.

    Args:
        game: The running Game instance (read-only for HUD purposes).
        screen: Pygame surface to draw onto.
    """
    try:
        x, y = 16, 16

        # HP boxes
        for i in range(game.player.max_hp):
            c = (80, 200, 120) if i < game.player.hp else (60, 80, 60)
            pygame.draw.rect(screen, c, pygame.Rect(x + i * 18, y, 16, 10), border_radius=3)
        y += 16

        # Dash charges indicator (show charges as small circles)
        dash_charges = getattr(game.player, 'dash_charges', 1)
        dash_charges_max = getattr(game.player, 'dash_charges_max', 1)
        if dash_charges_max > 0:
            for i in range(dash_charges_max):
                charge_x = x + i * 14
                charge_color = CYAN if i < dash_charges else (60, 80, 80)
                pygame.draw.circle(screen, charge_color, (charge_x + 6, y + 4), 5)
            y += 12
        
        # Shared cooldown bar - shows both dash and wall jump with different colors
        dash_cd = getattr(game.player, 'dash_cd', 0)
        wall_jump_cd = getattr(game.player, 'wall_jump_cooldown', 0)
        
        # Draw the bar if either cooldown is active
        if dash_cd > 0 or wall_jump_cd > 0:
            # Background
            pygame.draw.rect(screen, (80, 80, 80), pygame.Rect(x, y, 120, 6), border_radius=3)
            
            # If both are active, split the bar
            if dash_cd > 0 and wall_jump_cd > 0:
                # Dash on left half (cyan)
                dash_pct = 1 - (dash_cd / 24)
                pygame.draw.rect(screen, CYAN, pygame.Rect(x, y, int(60 * dash_pct), 6), border_radius=3)
                
                # Wall jump on right half (orange)
                wall_pct = 1 - (wall_jump_cd / WALL_JUMP_COOLDOWN)
                pygame.draw.rect(screen, (255, 165, 0), pygame.Rect(x + 60, y, int(60 * wall_pct), 6), border_radius=3)
            elif dash_cd > 0:
                # Only dash cooldown (cyan)
                dash_pct = 1 - (dash_cd / 24)
                pygame.draw.rect(screen, CYAN, pygame.Rect(x, y, int(120 * dash_pct), 6), border_radius=3)
            else:
                # Only wall jump cooldown (orange)
                wall_pct = 1 - (wall_jump_cd / WALL_JUMP_COOLDOWN)
                pygame.draw.rect(screen, (255, 165, 0), pygame.Rect(x, y, int(120 * wall_pct), 6), border_radius=3)
            
            y += 12

        # Stamina bar
        if hasattr(game.player, 'stamina') and hasattr(game.player, 'max_stamina'):
            spct = max(0.0, min(1.0, game.player.stamina / max(1e-6, game.player.max_stamina)))
            pygame.draw.rect(screen, (60, 60, 60), pygame.Rect(x, y, 120, 6), border_radius=3)
            stamina_col = (120, 230, 160) if getattr(game.player, 'stamina_boost_timer', 0) > 0 else (200, 180, 60)
            pygame.draw.rect(screen, stamina_col, pygame.Rect(x, y, int(120 * spct), 6), border_radius=3)
            y += 12

        # Mana bar
        if hasattr(game.player, 'mana') and hasattr(game.player, 'max_mana'):
            mpct = max(0.0, min(1.0, game.player.mana / max(1e-6, game.player.max_mana)))
            pygame.draw.rect(screen, (60, 60, 60), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(screen, CYAN, pygame.Rect(x, y, int(120 * mpct), 6), border_radius=3)
            y += 12

        # Ranger charge bar
        if getattr(game.player, 'cls', '') == 'Ranger' and getattr(game.player, 'charging', False):
            pct = max(0.0, min(1.0, game.player.charge_time / max(1, game.player.charge_threshold)))
            pygame.draw.rect(screen, (60, 60, 60), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(screen, (200, 180, 60), pygame.Rect(x, y, int(120 * pct), 6), border_radius=3)
            if pct >= 1.0:
                draw_text(screen, "!", (x + 124, y - 6), (255, 80, 80), size=18, bold=True)
            y += 12

        # Room/Level info (PCG-aware)
        if getattr(game, 'use_pcg', False) and hasattr(game.level, 'room_code'):
            try:
                import re
                code = str(game.level.room_code)
                m = re.match(r"^(\d+?)([1-6][A-Za-z])$", code)
                if m:
                    lvl = int(m.group(1))
                    room_str = m.group(2)
                    draw_text(screen, f"Level:{lvl} Room:{room_str}", (WIDTH - 220, 8), WHITE, size=16)
                else:
                    m2 = re.match(r"^(\d+)(.+)$", code)
                    if m2:
                        lvl = int(m2.group(1))
                        room_str = m2.group(2)
                        draw_text(screen, f"Level:{lvl} Room:{room_str}", (WIDTH - 220, 8), WHITE, size=16)
                    else:
                        draw_text(screen, f"PCG: {game.level.room_code}", (WIDTH - 220, 8), WHITE, size=16)
            except Exception:
                draw_text(screen, f"PCG: {game.level.room_code}", (WIDTH - 220, 8), WHITE, size=16)
        else:
            from src.level.legacy_level import ROOM_COUNT
            draw_text(screen, f"Room {getattr(game, 'level_index', 0) + 1}/{ROOM_COUNT}", (WIDTH - 220, 8), WHITE, size=16)

        # Active item modifiers (show if significant)
        active_mods = []
        if getattr(game.player, 'attack_speed_mult', 1.0) > 1.1:
            active_mods.append(('⚔', (255, 200, 100), f"+{int((game.player.attack_speed_mult - 1.0) * 100)}% ATK SPD"))
        if getattr(game.player, 'skill_cooldown_mult', 1.0) < 0.9:
            active_mods.append(('⏱', (150, 200, 255), f"-{int((1.0 - game.player.skill_cooldown_mult) * 100)}% CDR"))
        if getattr(game.player, 'skill_damage_mult', 1.0) > 1.1:
            active_mods.append(('🔮', (200, 150, 255), f"+{int((game.player.skill_damage_mult - 1.0) * 100)}% SKILL"))
        if getattr(game.player, 'dash_stamina_mult', 1.0) < 0.95:
            active_mods.append(('💨', (100, 255, 200), f"-{int((1.0 - game.player.dash_stamina_mult) * 100)}% DASH"))
        
        # Consumable timers - moved to top left
        if getattr(game.player, 'speed_potion_timer', 0) > 0:
            secs = max(0, int(game.player.speed_potion_timer / FPS))
            active_mods.append(('⚡', (255, 220, 140), f"Haste {secs}s"))
        if getattr(game.player, 'jump_boost_timer', 0) > 0:
            secs = max(0, int(game.player.jump_boost_timer / FPS))
            active_mods.append(('☁', (200, 220, 255), f"Skybound {secs}s"))
        if getattr(game.player, 'stamina_boost_timer', 0) > 0:
            secs = max(0, int(game.player.stamina_boost_timer / FPS))
            active_mods.append(('💪', (150, 255, 180), f"Cavern Brew {secs}s"))
        if getattr(game.player, 'lucky_charm_timer', 0) > 0:
            secs = max(0, int(game.player.lucky_charm_timer / FPS))
            active_mods.append(('🍀', (255, 215, 0), f"Lucky! {secs}s"))
        
        # Phoenix Feather - in the modifiers section with pulsing effect
        if getattr(game.player, 'phoenix_feather_active', False):
            import math
            pulse = abs(math.sin(pygame.time.get_ticks() * 0.003)) * 0.4 + 0.6
            color = (int(255 * pulse), int(180 * pulse), int(80 * pulse))
            active_mods.append(('✦', color, "Phoenix Blessing"))
        
        # Time crystal effect
        time_crystal_active = any(getattr(e, 'slow_remaining', 0) > 0 for e in game.enemies if getattr(e, 'alive', False))
        if time_crystal_active:
            active_mods.append(('⏱', (150, 150, 255), "Time Distorted"))
        
        # Ranger skill timers
        if getattr(game.player, 'cls', '') == 'Ranger':
            if getattr(game.player, 'triple_timer', 0) > 0:
                secs = max(0, int(game.player.triple_timer / FPS))
                active_mods.append(('⇶', (255, 180, 80), f"Triple Shot {secs}s"))
            if getattr(game.player, 'sniper_ready', False):
                active_mods.append(('◎', (255, 60, 60), "Sniper Ready"))
            if getattr(game.player, 'speed_timer', 0) > 0:
                secs = max(0, int(game.player.speed_timer / FPS))
                active_mods.append(('⚡', (100, 255, 200), f"Speed +1.0 {secs}s"))
        
        # Knight skill timers
        if getattr(game.player, 'cls', '') == 'Knight':
            combat = getattr(game.player, 'combat', None)
            if combat:
                if getattr(combat, 'shield_timer', 0) > 0:
                    secs = max(0, int(combat.shield_timer / FPS))
                    hits_left = getattr(combat, 'shield_hits_left', 0)
                    active_mods.append(('🛡', (100, 200, 255), f"Shield [{hits_left}] {secs}s"))
                if getattr(combat, 'power_timer', 0) > 0:
                    secs = max(0, int(combat.power_timer / FPS))
                    atk_bonus = getattr(combat, 'atk_bonus', 0)
                    active_mods.append(('⚔', (255, 100, 100), f"Power +{atk_bonus} {secs}s"))
        
        if active_mods:
            mod_y = y
            for icon, color, text in active_mods:
                draw_text(screen, f"{icon} {text}", (x, mod_y), color, size=12, bold=True)
                mod_y += 14
            y = mod_y + 4
        
        # Class and coins
        draw_text(screen, f"Class: {getattr(game.player, 'cls', 'Unknown')}", (WIDTH - 220, 28), (200, 200, 200), size=16)
        draw_text(screen, f"Coins: {game.player.money}", (WIDTH - 220, 48), (255, 215, 0), bold=True)

        # Skill bar (3 slots) - top center - smaller size
        slot_w, slot_h = 40, 40  # Reduced from 56 to 40
        slot_spacing = 6  # Spacing between slots
        # Calculate total width for 6 slots (3 skills + 3 consumables)
        total_slots = 6
        total_width = slot_w * total_slots + slot_spacing * (total_slots - 1)
        # Start position to center all 6 slots
        start_x = (WIDTH - total_width) // 2
        sbx = start_x
        sby = 16  # Top of screen
        if game.player.cls == 'Knight':
            names = ['Shield', 'Power', 'Charge']
            actives = [getattr(game.player.combat, 'shield_timer', 0) > 0, getattr(game.player.combat, 'power_timer', 0) > 0, False]
            skill_icons = [
                'assets/Player/Knight/skill-1.png',
                'assets/Player/Knight/skill-2.png',
                'assets/Player/Knight/skill-3.png'
            ]
            # Icon scales - skill 1 and 2 are bigger
            icon_scales = [1.2, 1.2, 1.0]
        elif game.player.cls == 'Ranger':
            names = ['Triple', 'Sniper', 'Speed']
            actives = [game.player.triple_timer > 0, game.player.sniper_ready, game.player.speed_timer > 0]
            skill_icons = [
                'assets/Player/Ranger/skill-1.png',
                'assets/Player/Ranger/skill-2.png',
                'assets/Player/Ranger/skill-3.png'
            ]
            # Icon scales - skill 1 and 2 are bigger
            icon_scales = [1.2, 1.2, 1.0]
        else:
            names = ['Fireball', 'Cold', 'Missile']
            actives = [False, False, False]
            skill_icons = [
                'assets/Player/wizard/skill-1.png',
                'assets/Player/wizard/skill-2.png',
                'assets/Player/wizard/skill-3.png'
            ]
            # Icon scales - skill 1 and 2 are bigger
            icon_scales = [1.2, 1.2, 1.0]
        cds = [game.player.skill_cd1, game.player.skill_cd2, game.player.skill_cd3]
        maxcds = [max(1, game.player.skill_cd1_max), max(1, game.player.skill_cd2_max), max(1, game.player.skill_cd3_max)]
        for i in range(3):
            rx = sbx + i * (slot_w + slot_spacing)
            ry = sby
            pygame.draw.rect(screen, (40, 40, 50), pygame.Rect(rx, ry, slot_w, slot_h), border_radius=6)
            if actives[i]:
                pygame.draw.rect(screen, (120, 210, 220), pygame.Rect(rx - 2, ry - 2, slot_w + 4, slot_h + 4), width=2, border_radius=8)
            
            # Draw skill icon if available (cached for performance)
            if skill_icons[i]:
                icon_w = int((slot_w - 4) * icon_scales[i])
                icon_h = int((slot_h - 4) * icon_scales[i])
                icon_key = (skill_icons[i], icon_w, icon_h)
                if icon_key not in _skill_icon_cache:
                    try:
                        icon_img = pygame.image.load(skill_icons[i]).convert_alpha()
                        icon_img = pygame.transform.scale(icon_img, (icon_w, icon_h))
                        _skill_icon_cache[icon_key] = icon_img
                    except Exception:
                        _skill_icon_cache[icon_key] = None  # Cache the failure too
                
                if _skill_icon_cache[icon_key]:
                    # Center the icon in the slot
                    icon_x = rx + (slot_w - icon_w) // 2
                    icon_y = ry + (slot_h - icon_h) // 2
                    screen.blit(_skill_icon_cache[icon_key], (icon_x, icon_y))
            
            if cds[i] > 0:
                pct = cds[i] / maxcds[i]
                h = int(slot_h * pct)
                overlay = pygame.Rect(rx, ry + (slot_h - h), slot_w, h)
                try:
                    # try to draw semi-transparent overlay if supported
                    pygame.draw.rect(screen, (0, 0, 0, 120), overlay)
                except Exception:
                    pygame.draw.rect(screen, (0, 0, 0), overlay)
                secs = max(0.0, cds[i] / FPS)
                draw_text(screen, f"{secs:.0f}", (rx + 10, ry + 10), (220, 220, 220), size=14, bold=True)
            draw_text(screen, str(i + 1), (rx + 2, ry + 2), (200, 200, 200), size=12)

        # Consumable hotbar (delegated to inventory)
        try:
            game.inventory.draw_consumable_hotbar()
        except Exception:
            logger.exception("Inventory hotbar draw failed")

        # Gameplay hint text
        draw_text(screen,
                  "Move A/D | Jump Space/K | Dash Shift/J | Attack L/Mouse | Up/Down+Attack for Up/Down slash (Down=Pogo) | Shop F6 | God F1 | No-clip: Double-space in god mode (WASD to float)",
                  (12, HEIGHT - 28), (180, 180, 200), size=16)

        # God/no-clip tags
        hud_x = WIDTH - 64
        if getattr(game.player, 'no_clip', False):
            draw_text(screen, "NO-CLIP", (hud_x, 8), (200, 100, 255), bold=True)
            hud_x -= 8
            if getattr(game.player, 'floating_mode', False):
                draw_text(screen, "FLOAT", (hud_x, 8), (100, 255, 200), bold=True)
                hud_x -= 8
        if getattr(game.player, 'god', False):
            draw_text(screen, "GOD", (hud_x, 8), (255, 200, 80), bold=True)

        # Area overlay label
        if getattr(game, 'debug_show_area_overlay', False):
            try:
                area_label = game._get_player_area_labels()
                if area_label:
                    draw_text(screen, f"AREA: {area_label}", (WIDTH - 260, 8), (160, 220, 255), size=12)
                else:
                    draw_text(screen, "AREA: NONE", (WIDTH - 260, 8), (120, 160, 200), size=12)
            except Exception:
                pass

        # Boss hint
        if getattr(game.level, 'is_boss_room', False) and any(getattr(e, 'alive', False) for e in game.enemies):
            draw_text(screen, "Defeat the boss to open the door", (WIDTH // 2 - 160, 8), (255, 120, 120), size=16)

    except Exception:
        logger.exception("Unhandled exception in HUD draw")
