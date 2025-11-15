"""
Input handling utilities for Haridd.

This module implements `InputHandler.process_events(game, dt)` that encapsulates
all branches currently in the main loop for `pygame` events: mouse clicks,
wheel scrolls, keydowns, and high-level developer hotkeys. It should call into
`game`'s subsystems (inventory, shop, menu, level_manager, dev_tools) rather than
modify internals directly.

Design:
- Use absolute imports.
- Avoid heavy logic; delegate to `game` methods when practical.
- Raise no exceptions (catch within handler); log errors.
"""
from typing import Optional
import sys
import logging
import pygame

logger = logging.getLogger(__name__)


class InputHandler:
    """Centralized input/event processing.

    Usage:
        handler = InputHandler()
        handler.process_events(game, dt)
    """

    def process_events(self, game, dt: float) -> None:
        """Process pygame events and invoke game subsystems.

        Args:
            game: Game instance (used to access inventory, shop, menu, camera, etc.)
            dt: time delta in seconds (not usually needed by input but kept for parity)
        """
        try:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()

                # Mouse button handling (wheel + left click)
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    # Wheel scroll for inventory stock panel
                    if getattr(game, 'inventory', None) and getattr(game.inventory, 'inventory_open', False):
                        if ev.button == 4:
                            try:
                                game.inventory._scroll_stock(-50)
                            except Exception:
                                logger.exception("inventory _scroll_stock failed")
                            continue
                        elif ev.button == 5:
                            try:
                                game.inventory._scroll_stock(50)
                            except Exception:
                                logger.exception("inventory _scroll_stock failed")
                            continue

                    # Left click
                    if ev.button == 1:
                        try:
                            if getattr(game, 'inventory', None) and getattr(game.inventory, 'inventory_open', False):
                                game.inventory._handle_inventory_click(ev.pos)
                            elif getattr(game, 'shop', None) and getattr(game.shop, 'shop_open', False):
                                game.shop.handle_mouse_click(ev.pos)
                        except Exception:
                            logger.exception("Mouse click handling failed")
                        continue

                # Keyboard handling
                elif ev.type == pygame.KEYDOWN:
                    # Shop input has priority
                    if getattr(game, 'shop', None) and getattr(game.shop, 'shop_open', False):
                        try:
                            game.shop.handle_event(ev)
                        except Exception:
                            logger.exception("Shop event handler failed")
                        continue

                    # Toggle collision report debugger (overlay + capture) with F9
                    if ev.key == pygame.K_F9:
                        game.debug_collision_log = not getattr(game, 'debug_collision_log', False)
                        continue

                    # Toggle area overlay (F10)
                    elif ev.key == pygame.K_F10:
                        game.debug_show_area_overlay = not getattr(game, 'debug_show_area_overlay', False)
                        try:
                            from src.entities.entities import floating, DamageNumber
                            floating.append(DamageNumber(
                                game.player.rect.centerx,
                                game.player.rect.top - 12,
                                f"Area Overlay {'ON' if game.debug_show_area_overlay else 'OFF'}",
                                (160, 220, 255) if game.debug_show_area_overlay else (200, 200, 200)
                            ))
                        except Exception:
                            pass
                        continue

                    # inventory toggle (i)
                    if ev.key == pygame.K_i:
                        if not getattr(game, 'shop', None) or not getattr(game.shop, 'shop_open', False):
                            prev = getattr(game.inventory, 'inventory_open', False)
                            game.inventory.inventory_open = not prev
                            logger.info("Inventory toggle requested: was=%s now=%s", prev, game.inventory.inventory_open)
                            # small debug print to ensure log shows up in consoles without configured logging
                            try:
                                print(f"[DEBUG] Inventory toggle: was={prev} now={game.inventory.inventory_open}")
                            except Exception:
                                pass
                            if not game.inventory.inventory_open:
                                try:
                                    game.inventory._clear_inventory_selection()
                                except Exception:
                                    logger.exception("_clear_inventory_selection failed")
                        continue

                    # camera zoom (z)
                    if ev.key == pygame.K_z:
                        try:
                            game.camera.toggle_zoom()
                            from src.entities.entities import floating, DamageNumber
                            floating.append(DamageNumber(
                                game.player.rect.centerx,
                                game.player.rect.top - 12,
                                game.camera.get_zoom_label(),
                                (255, 255, 100)
                            ))
                        except Exception:
                            logger.exception("Failed to toggle camera zoom")
                        continue

                    # F5 = open debug menu
                    if ev.key == pygame.K_F5:
                        try:
                            pygame.event.clear(pygame.KEYDOWN)
                        except Exception:
                            pass
                        try:
                            if hasattr(game, 'dev_tools') and game.dev_tools is not None:
                                game.dev_tools.debug_menu()
                            else:
                                # fallback to game.debug_menu if still present
                                if hasattr(game, 'debug_menu'):
                                    game.debug_menu()
                        except Exception:
                            logger.exception("debug_menu failed")
                        continue

                    # Escape handling: close inventory/shop or open pause menu
                    if ev.key == pygame.K_ESCAPE:
                        if getattr(game, 'shop', None) and getattr(game.shop, 'shop_open', False):
                            try:
                                game.shop.close_shop()
                            except Exception:
                                logger.exception("shop.close_shop failed")
                        else:
                            try:
                                game.menu.pause_menu()
                            except Exception:
                                logger.exception("menu.pause_menu failed")
                        continue

                    # Consumable hotkeys
                    used_consumable = False
                    try:
                        for idx, keycode in enumerate(getattr(game.inventory, 'consumable_hotkeys', [])):
                            if ev.key == keycode:
                                try:
                                    game.inventory.consume_slot(idx)
                                except Exception:
                                    logger.exception("consume_slot failed")
                                used_consumable = True
                                break
                    except Exception:
                        logger.exception("Consumable hotkeys lookup failed")
                    if used_consumable:
                        continue

                    # Developer cheat keys and other debug toggles that mutate game state
                    try:
                        if ev.key == pygame.K_F1:
                            current_god = getattr(game.player, 'god', False)
                            setattr(game.player, 'god', not current_god)
                            try:
                                from src.entities.entities import floating, DamageNumber
                                floating.append(DamageNumber(
                                    game.player.rect.centerx,
                                    game.player.rect.top - 12,
                                    f"God Mode {'ON' if not current_god else 'OFF'}!",
                                    (255, 200, 80) if not current_god else (200, 200, 200)
                                ))
                            except Exception:
                                pass
                            continue

                        elif ev.key == pygame.K_F2:
                            try:
                                game.inventory.add_all_consumables()
                            except Exception:
                                logger.exception("add_all_consumables failed")
                            continue

                        elif ev.key == pygame.K_F3:
                            game.debug_enemy_rays = not getattr(game, 'debug_enemy_rays', False)
                            continue

                        elif ev.key == pygame.K_F4:
                            game.debug_enemy_nametags = not getattr(game, 'debug_enemy_nametags', False)
                            continue

                        elif ev.key == pygame.K_F6:
                            if not getattr(game, 'inventory', None) or not getattr(game.inventory, 'inventory_open', False):
                                if getattr(game, 'shop', None) and getattr(game.shop, 'shop_open', False):
                                    try:
                                        game.shop.close_shop()
                                    except Exception:
                                        logger.exception("shop.close_shop failed")
                                else:
                                    try:
                                        game.shop.open_shop()
                                    except Exception:
                                        logger.exception("shop.open_shop failed")
                            continue

                        elif ev.key == pygame.K_F7:
                            try:
                                game.player.money += 1000
                                from src.entities.entities import floating, DamageNumber
                                floating.append(DamageNumber(
                                    game.player.rect.centerx,
                                    game.player.rect.top - 12,
                                    "+1000 coins!",
                                    (255, 215, 0)
                                ))
                            except Exception:
                                logger.exception("F7 coin add failed")
                            continue

                        elif ev.key == pygame.K_F8:
                            game.debug_tile_inspector = not getattr(game, 'debug_tile_inspector', False)
                            continue

                        elif ev.key == pygame.K_F9:
                            game.debug_wall_jump = not getattr(game, 'debug_wall_jump', False)
                            # Set debug flag on player
                            if hasattr(game, 'player'):
                                game.player._debug_wall_jump = game.debug_wall_jump
                            continue

                        elif ev.key == pygame.K_F11:
                            try:
                                if getattr(game, 'use_pcg', False) and hasattr(game.level, 'room_code'):
                                    if hasattr(game, 'level_manager'):
                                        game.level_manager.follow_exit(game, 'door_exit_1')
                                    else:
                                        game._load_pcg_level_call = getattr(game, '_load_pcg_level', None)
                                        if callable(game._load_pcg_level_call):
                                            # fallback: attempt to follow by inspecting level_loader
                                            from src.level.level_loader import level_loader
                                            room = level_loader.get_room(game.level.level_id, game.level.room_code)
                                            if room and room.door_exits and 'door_exit_1' in room.door_exits:
                                                target = room.door_exits['door_exit_1']
                                                try:
                                                    if isinstance(target, dict):
                                                        target_level_id = int(target.get('level_id', 1))
                                                        target_room_code = str(target.get('room_code', '1A'))
                                                    else:
                                                        target_room_code = str(target)
                                                        if len(target_room_code) >= 2:
                                                            target_level_id = int(target_room_code[:-1])
                                                        else:
                                                            raise ValueError("Invalid room code")
                                                    game._load_pcg_level_call(target_level_id, target_room_code, initial=False)
                                                    sx, sy = game.level.spawn
                                                    game.player.rect.topleft = (sx, sy)
                                                except Exception:
                                                    logger.exception("Failed to follow door_exit_1 (fallback)")
                            except Exception:
                                logger.exception("F11 follow failed")
                            continue

                        elif ev.key == pygame.K_F12:
                            try:
                                if getattr(game, 'use_pcg', False) and hasattr(game.level, 'room_code'):
                                    if hasattr(game, 'level_manager'):
                                        game.level_manager.follow_exit(game, 'door_exit_2')
                                    else:
                                        game._load_pcg_level_call = getattr(game, '_load_pcg_level', None)
                                        if callable(game._load_pcg_level_call):
                                            from src.level.level_loader import level_loader
                                            room = level_loader.get_room(game.level.level_id, game.level.room_code)
                                            if room and room.door_exits and 'door_exit_2' in room.door_exits:
                                                target = room.door_exits['door_exit_2']
                                                try:
                                                    if isinstance(target, dict):
                                                        target_level_id = int(target.get('level_id', 1))
                                                        target_room_code = str(target.get('room_code', '1A'))
                                                    else:
                                                        target_room_code = str(target)
                                                        if len(target_room_code) >= 2:
                                                            target_level_id = int(target_room_code[:-1])
                                                        else:
                                                            raise ValueError("Invalid room code")
                                                    game._load_pcg_level_call(target_level_id, target_room_code, initial=False)
                                                    sx, sy = game.level.spawn
                                                    game.player.rect.topleft = (sx, sy)
                                                except Exception:
                                                    logger.exception("Failed to follow door_exit_2 (fallback)")
                                else:
                                    # Legacy: Teleport to room 6 (boss room) for debug
                                    game.goto_room(5)
                            except Exception:
                                logger.exception("F12 teleport failed")
                            continue

                    except Exception:
                        logger.exception("Error handling developer hotkeys")
                        continue

            # End event loop
        except Exception:
            logger.exception("Unhandled exception in InputHandler.process_events")
