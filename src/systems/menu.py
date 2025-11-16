import sys
import os

# Add root directory to Python path so we can import config
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, root_dir)

import pygame
from config import WIDTH, HEIGHT, FPS
from src.core.utils import draw_text, get_font, draw_centered_text
from src.level.legacy_level import LegacyLevel, ROOM_COUNT
from src.entities.entities import Player, hitboxes, floating
from src.systems.camera import Camera


class Menu:
    def __init__(self, game):
        self.game = game
        self.screen = game.screen
        self.clock = game.clock
        
    def select_class(self):
        """Blocking title + class selection screen. Returns chosen class name."""
        options = ["Knight", "Ranger", "Wizard"]
        idx = 0
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    # Navigation: Arrow keys and WASD
                    elif ev.key in (pygame.K_UP, pygame.K_w):
                        idx = (idx - 1) % len(options)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        chosen_class = options[idx]
                        self._save_selected_class(chosen_class)
                        return chosen_class
                    # Direct hotkeys
                    elif ev.key == pygame.K_1:
                        self._save_selected_class(options[0])
                        return options[0]
                    elif ev.key == pygame.K_2:
                        self._save_selected_class(options[1])
                        return options[1]
                    elif ev.key == pygame.K_3:
                        self._save_selected_class(options[2])
                        return options[2]

            # draw
            self.screen.fill((12, 12, 18))
            title_font = get_font(48, bold=True)
            draw_text(self.screen, "HARIDD", (WIDTH//2 - 120, 60), (255,220,140), size=48, bold=True)
            draw_text(self.screen, "Choose your class:", (WIDTH//2 - 120, 140), (200,200,220), size=22)
            for i, opt in enumerate(options):
                y = 200 + i*48
                col = (255,220,140) if i == idx else (200,200,200)
                draw_text(self.screen, f"{i+1}. {opt}", (WIDTH//2 - 80, y), col, size=28)
            draw_text(self.screen, "Use Up/Down or 1-3, Enter to confirm", (WIDTH//2 - 160, HEIGHT-64), (160,160,180), size=16)
            pygame.display.flip()
    
    def _save_selected_class(self, class_name: str):
        """Save the selected class to config file."""
        try:
            from src.level.config_loader import load_pcg_runtime_config, save_pcg_runtime_config
            runtime = load_pcg_runtime_config()
            updated_runtime = runtime._replace(selected_class=class_name)
            save_pcg_runtime_config(updated_runtime)
        except Exception:
            pass  # Fail silently if config save fails

    def how_to_play_screen(self):
        """Blocking help/instructions screen. Return to caller on Esc/Enter."""
        lines = [
            "Goal: Clear rooms and defeat boss to progress.",
            "",
            "Controls:",
            "  Move: A / D",
            "  Jump: Space or K",
            "  Dash: Left Shift or J",
            "  Attack: L or Left Mouse",
            "  Up/Down + Attack: Up/Down slash (Down = Pogo)",
            "",
            "Classes:",
            "  Knight: Tanky melee; shield/power/charge skills.",
            "  Ranger: Arrows, charge shot, triple-shot.",
            "  Wizard: Fireball, cold field, homing missiles.",
            "",
            "Tips:",
            "  - Invulnerability frames protect after getting hit.",
            "  - Doors in boss rooms stay locked until boss is defeated.",
            "  - Enemies don't hurt each other; watch telegraphs (! / !!).",
            "",
            "Dev Cheats:",
            "  F1: Toggle God Mode",
            "  F2: Refill Consumables",
            "  F3: Toggle Enemy Vision Rays & Hitboxes",
            "  F4: Open Debugger Menu",
        ]
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        return

            self.screen.fill((12, 12, 18))
            draw_text(self.screen, "HOW TO PLAY", (WIDTH//2 - 140, 40), (255,220,140), size=48, bold=True)
            y = 120
            for s in lines:
                draw_text(self.screen, s, (64, y), (200,200,210), size=20)
                y += 28
            draw_text(self.screen, "Press Esc or Enter to return", (WIDTH//2 - 180, HEIGHT-48), (160,160,180), size=16)
            pygame.display.flip()

    def title_screen(self):
        """Blocking title menu: Start Game / Class Select / How to Play / Quit.
        Static-only version (procedural generation disabled).
        """
        # 1. Start Game, 2. Class Select, 3. PCG Options, 4. How to Play, 5. Quit
        options = ["Start Game", "Class Select", "PCG Options", "How to Play", "Quit"]
        idx = 0
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    # Navigation: Arrow keys and WASD
                    elif ev.key in (pygame.K_UP, pygame.K_w):
                        idx = (idx - 1) % len(options)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        choice = options[idx]
                        if choice == "Start Game":
                            return
                        elif choice == "Class Select":
                            self.game.selected_class = self.select_class()
                        elif choice == "PCG Options":
                            self.pcg_options_menu()
                        elif choice == "How to Play":
                            self.how_to_play_screen()
                        elif choice == "Quit":
                            pygame.quit(); sys.exit()
                    # Hotkeys (unchanged behavior)
                    elif ev.key in (pygame.K_1, pygame.K_s):
                        return
                    elif ev.key in (pygame.K_2, pygame.K_c):
                        self.game.selected_class = self.select_class()
                    elif ev.key in (pygame.K_3, pygame.K_p):
                        self.pcg_options_menu()
                    elif ev.key in (pygame.K_4, pygame.K_h):
                        self.how_to_play_screen()
                    elif ev.key in (pygame.K_5, pygame.K_q): # Hotkey for Quit
                        pygame.quit(); sys.exit()

            # draw title menu with centered layout
            self.screen.fill((8, 8, 12))

            # layout configuration
            title_y = 80
            subtitle_y = title_y + 48
            first_option_y = subtitle_y + 64
            option_spacing = 40
            bottom_hint_y = HEIGHT - 64
            bottom_summary_y = bottom_hint_y - 28

            # title & subtitle
            draw_centered_text(self.screen, "HARIDD", (WIDTH // 2, title_y), (255,220,140), size=60, bold=True)
            draw_centered_text(self.screen, "A tiny action roguelite", (WIDTH // 2, subtitle_y), (180,180,200), size=20)

            # options: numbers and labels in aligned columns, block centered
            option_font_size = 28
            font = get_font(size=option_font_size, bold=False)

            # measure widest label so we can align nicely
            max_label_width = 0
            for opt in options:
                label_surface = font.render(opt, True, (0, 0, 0))
                max_label_width = max(max_label_width, label_surface.get_width())

            # fixed width for number column (e.g. "5.") + small space
            num_col_width = font.render("5.", True, (0, 0, 0)).get_width() + 16
            total_block_width = num_col_width + max_label_width

            # left edge so the whole block is horizontally centered
            block_left_x = WIDTH // 2 - total_block_width // 2

            for i, opt in enumerate(options):
                y = first_option_y + i * option_spacing
                col = (255,220,140) if i == idx else (200,200,200)

                num_text = f"{i+1}."
                label_text = opt

                # positions: numbers share same left, labels share same left
                num_x = block_left_x
                label_x = block_left_x + num_col_width

                num_surface = font.render(num_text, True, col)
                label_surface = font.render(label_text, True, col)

                num_rect = num_surface.get_rect(midleft=(num_x, y))
                label_rect = label_surface.get_rect(midleft=(label_x, y))

                self.screen.blit(num_surface, num_rect)
                self.screen.blit(label_surface, label_rect)

            # Summary line with current class and PCG status/seed
            from src.level.config_loader import load_pcg_runtime_config
            runtime = load_pcg_runtime_config()
            mode = "PCG" if runtime.use_pcg else "Legacy"
            
            # Display selected class prominently at the bottom with class-specific colors
            class_colors = {
                "Knight": (220, 72, 72),    # Red
                "Ranger": (80, 200, 120),   # Green
                "Wizard": (80, 150, 220)    # Blue
            }
            class_color = class_colors.get(self.game.selected_class, (255,220,140))
            class_text = f"Selected Class: {self.game.selected_class}"
            draw_centered_text(self.screen, class_text, (WIDTH // 2, bottom_summary_y - 28), class_color, size=22, bold=True)
            
            # Display mode and seed info below class
            summary = f"Mode: {mode} | Seed: {runtime.seed}"
            draw_centered_text(self.screen, summary, (WIDTH // 2, bottom_summary_y), (180,200,220), size=16)

            # bottom helper text
            draw_centered_text(self.screen,
                               "Use Up/Down, Enter to select  1-5 hotkeys",
                               (WIDTH // 2, bottom_hint_y),
                               (160,160,180),
                               size=16)

            pygame.display.flip()

    def game_over_screen(self):
        """
        Blocking game over / restart menu.

        Options:
          - Restart: restart run via Game.restart_run()
          - Main Menu: return to title_screen() and start a fresh run (same as pause menu "Main Menu")
          - Quit: exit the game

        Restart keeps the selected class; Main Menu allows reconfiguring via title screen.
        """
        options = ["Restart", "Main Menu", "Quit"]
        idx = 0

        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    # Direct hotkeys for convenience (preserve legacy behavior)
                    if ev.key in (pygame.K_r,):  # Remove Enter and Space keys
                        # Restart run via centralized logic so behavior is consistent.
                        self.game.restart_run()
                        return
                    elif ev.key in (pygame.K_q, pygame.K_ESCAPE):
                        pygame.quit(); sys.exit()

                    # Navigate options with Arrow keys and WASD
                    if ev.key in (pygame.K_UP, pygame.K_w):
                        idx = (idx - 1) % len(options)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_1,):
                        # Hotkey: 1 => Restart
                        self.game.restart_run()
                        return
                    elif ev.key in (pygame.K_2, pygame.K_e):
                        # Hotkey: 2 or E => Main Menu
                        # Go back to title_screen(), then reset game state properly
                        self.title_screen()
                        self.game.reset_game_state()
                        return
                    elif ev.key in (pygame.K_3,):
                        # Hotkey: 3 => Quit
                        pygame.quit(); sys.exit()
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        # Handle based on selected menu entry
                        choice = options[idx]
                        if choice == "Restart":
                            self.game.restart_run()
                            return
                        elif choice == "Main Menu":
                            self.title_screen()
                            self.game.reset_game_state()
                            return
                        elif choice == "Quit":
                            pygame.quit(); sys.exit()

            # draw overlay
            self.screen.fill((10, 10, 16))
            draw_text(self.screen, "YOU DIED", (WIDTH//2 - 120, HEIGHT//2 - 120), (220,80,80), size=48, bold=True)

            # Render options list
            for i, opt in enumerate(options):
                y = HEIGHT//2 - 10 + i * 40
                col = (255,220,140) if i == idx else (200,200,200)
                draw_text(self.screen, f"{i+1}. {opt}", (WIDTH//2 - 80, y), col, size=26)

            # Helper/legacy hints
            draw_text(self.screen, "Use Up/Down, Enter to select", (WIDTH//2 - 170, HEIGHT//2 + 120), (160,160,180), size=18)
            draw_text(self.screen, "R / Enter - Restart • E / 2 - Main Menu • Q / Esc / 3 - Quit", (WIDTH//2 - 260, HEIGHT//2 + 150), (140,140,160), size=16)

            pygame.display.flip()

    def pause_menu(self):
        """Blocking pause menu with Resume / Settings / Main Menu / Quit."""
        options = ["Resume", "Settings", "Main Menu", "Quit"]
        idx = 0
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_r):
                        return  # resume
                    # Navigation: Arrow keys and WASD
                    elif ev.key in (pygame.K_UP, pygame.K_w):
                        idx = (idx - 1) % len(options)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        choice = options[idx]
                        if choice == "Resume":
                            return
                        elif choice == "Settings":
                            self.settings_screen()
                        elif choice == "Main Menu":
                            # Go back to title menu, allow user to adjust options,
                            # then reset game state properly
                            self.title_screen()
                            self.game.reset_game_state()
                            return
                        elif choice == "Quit":
                            pygame.quit(); sys.exit()
                    elif ev.key == pygame.K_q:
                        pygame.quit(); sys.exit()

            # draw pause overlay
            self.screen.fill((12, 12, 18))
            draw_text(self.screen, "PAUSED", (WIDTH//2 - 80, 60), (255,200,140), size=48, bold=True)
            for i, opt in enumerate(options):
                y = 180 + i*48
                col = (255,220,140) if i == idx else (200,200,200)
                draw_text(self.screen, f"{i+1}. {opt}", (WIDTH//2 - 80, y), col, size=28)
            draw_text(self.screen, "Use Up/Down, Enter to select, Esc/R to resume", (WIDTH//2 - 220, HEIGHT-64), (160,160,180), size=16)
            pygame.display.flip()
 
    def generation_options_menu(self):
        """
        Legacy stub preserved for compatibility.
        Procedural generation has been removed; this now returns immediately.
        """
        return

    def pcg_options_menu(self):
        """PCG configuration menu.

        - Option 1: Toggle PCG ON/OFF
        - Option 2: Seed Mode (Fixed / Random)
        - Option 3: Context-aware:
            * If Fixed: Set Fixed Seed (manual input)
            * If Random: Random New Seed (regenerate & store)
        Always shows the currently effective seed at the bottom.
        """
        from src.level.config_loader import (
            load_pcg_runtime_config,
            save_pcg_runtime_config,
        )
        import random

        runtime = load_pcg_runtime_config()

        idx = 0
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        # Esc always leaves PCG menu
                        return

                    if ev.key in (pygame.K_UP, pygame.K_w):
                        idx = (idx - 1) % 4
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        idx = (idx + 1) % 4
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        # Activate selected option
                        if idx == 0:
                            # Toggle PCG
                            runtime = runtime._replace(use_pcg=not runtime.use_pcg)
                            save_pcg_runtime_config(runtime)
                        elif idx == 1:
                            # Toggle seed mode
                            new_mode = "random" if runtime.seed_mode == "fixed" else "fixed"
                            runtime = runtime._replace(seed_mode=new_mode)
                            save_pcg_runtime_config(runtime)
                        elif idx == 2:
                            if runtime.seed_mode == "fixed":
                                # Set fixed seed via simple numeric input
                                runtime = self._pcg_prompt_fixed_seed(runtime)
                                save_pcg_runtime_config(runtime)
                            else:
                                # Random new seed now (and persist)
                                new_seed = random.randint(1, 2**31 - 1)
                                runtime = runtime._replace(seed=new_seed)
                                save_pcg_runtime_config(runtime)

                                # Update game's seed but don't generate levels yet
                                # Levels will be generated when "Start Game" is selected
                                try:
                                    self.game.pcg_seed = new_seed
                                    # Clear any cached level set to force regeneration with new seed
                                    from src.level.level_loader import level_loader
                                    if hasattr(level_loader, '_level_set'):
                                        delattr(level_loader, '_level_set')
                                    if hasattr(level_loader, '_last_generated_seed'):
                                        delattr(level_loader, '_last_generated_seed')
                                except Exception:
                                    pass
                        elif idx == 3:
                            return

            # Draw menu
            self.screen.fill((10, 10, 16))
            draw_text(self.screen, "PCG OPTIONS", (WIDTH//2 - 120, 60), (255,220,140), size=40, bold=True)

            # Option labels
            labels = []
            labels.append(f"Use PCG: {'ON' if runtime.use_pcg else 'OFF'}")
            labels.append(f"Seed Mode: {runtime.seed_mode.upper()}")
            if runtime.seed_mode == "fixed":
                labels.append("Set Fixed Seed")
            else:
                labels.append("Random New Seed")
            labels.append("Back")

            base_y = 160
            for i, text in enumerate(labels):
                y = base_y + i * 40
                col = (255,220,140) if i == idx else (200,200,200)
                draw_text(self.screen, f"{i+1}. {text}", (WIDTH//2 - 160, y), col, size=26)

            # Show currently effective seed (always visible)
            draw_text(self.screen,
                      f"Current Seed: {runtime.seed}",
                      (WIDTH//2 - 160, base_y + 4 * 40 + 24),
                      (180,200,220), size=20)
            draw_text(self.screen,
                      "Esc/Enter on 'Back' to return",
                      (WIDTH//2 - 180, HEIGHT-64), (140,140,160), size=16)

            pygame.display.flip()

    def _pcg_prompt_fixed_seed(self, runtime):
        """Prompt user to enter a fixed seed (digits only)."""
        import pygame

        seed_str = str(runtime.seed)
        backspace_held = False
        backspace_timer = 0
        initial_delay = 250  # ms before repeat starts
        repeat_interval = 40  # ms between repeats

        while True:
            dt = self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE,):
                        return runtime
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        try:
                            new_seed = int(seed_str) if seed_str else runtime.seed
                        except ValueError:
                            new_seed = runtime.seed
                        return runtime._replace(seed=new_seed, seed_mode="fixed")
                    elif ev.key == pygame.K_BACKSPACE:
                        # start/trigger backspace repeat behavior
                        backspace_held = True
                        backspace_timer = 0
                        if seed_str:
                            seed_str = seed_str[:-1]
                    else:
                        if ev.unicode.isdigit():
                            if len(seed_str) < 10:
                                seed_str += ev.unicode
                elif ev.type == pygame.KEYUP:
                    if ev.key == pygame.K_BACKSPACE:
                        backspace_held = False
                        backspace_timer = 0

            # handle held-backspace auto-repeat
            if backspace_held and seed_str:
                backspace_timer += dt
                if backspace_timer >= initial_delay:
                    # delete at fixed interval while held
                    repeats = (backspace_timer - initial_delay) // repeat_interval
                    if repeats > 0:
                        # remove one char per interval
                        new_len = max(0, len(seed_str) - int(repeats))
                        if new_len != len(seed_str):
                            seed_str = seed_str[:new_len]
                        # keep residual time to avoid burst deletions
                        backspace_timer = initial_delay + (backspace_timer - initial_delay) % repeat_interval

            self.screen.fill((10, 10, 18))

            title_text = "SET FIXED SEED"
            title_width = get_font(36, bold=True).size(title_text)[0]
            draw_text(self.screen, title_text,
                      (WIDTH//2 - title_width // 2, 80),
                      (255,220,140), size=36, bold=True)

            current_text = f"Current Seed: {runtime.seed}"
            current_width = get_font(20).size(current_text)[0]
            draw_text(self.screen, current_text,
                      (WIDTH//2 - current_width // 2, 150),
                      (200,200,210), size=20)

            hint_text = "Type digits for new seed, Enter to confirm"
            hint_width = get_font(18).size(hint_text)[0]
            draw_text(self.screen, hint_text,
                      (WIDTH//2 - hint_width // 2, 190),
                      (200,200,210), size=18)

            # If user cleared input entirely, show empty after colon (no fallback)
            new_seed_display = seed_str if seed_str != "" else ""
            new_text = f"New Seed: {new_seed_display}"
            new_width = get_font(28).size(new_text)[0]
            draw_text(self.screen, new_text,
                      (WIDTH//2 - new_width // 2, 240),
                      (220,220,240), size=28)

            footer_text = "Esc to cancel (keeps current seed)"
            footer_width = get_font(18).size(footer_text)[0]
            draw_text(self.screen, footer_text,
                      (WIDTH//2 - footer_width // 2, HEIGHT-64),
                      (160,160,180), size=18)

            pygame.display.flip()

    def settings_screen(self):
        """Simple settings placeholder. Press Esc to go back."""
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        return

            self.screen.fill((10, 10, 14))
            draw_text(self.screen, "SETTINGS", (WIDTH//2 - 80, 60), (220,220,220), size=40, bold=True)
            draw_text(self.screen, "(No settings yet)", (WIDTH//2 - 120, HEIGHT//2 - 8), (180,180,180), size=22)
            draw_text(self.screen, "Press Esc or Enter to return", (WIDTH//2 - 160, HEIGHT-64), (140,140,140), size=16)
            pygame.display.flip()