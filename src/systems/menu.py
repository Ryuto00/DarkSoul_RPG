import sys
import os

# Add the root directory to Python path so we can import config
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, root_dir)

import pygame
from config import WIDTH, HEIGHT, FPS
from src.core.utils import draw_text, get_font
from src.level.level import Level, ROOM_COUNT
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
                        return options[idx]
                    # Direct hotkeys
                    elif ev.key == pygame.K_1:
                        return options[0]
                    elif ev.key == pygame.K_2:
                        return options[1]
                    elif ev.key == pygame.K_3:
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

    def how_to_play_screen(self):
        """Blocking help/instructions screen. Return to caller on Esc/Enter."""
        lines = [
            "Goal: Clear rooms and defeat the boss to progress.",
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
            "  - Doors in boss rooms stay locked until the boss is defeated.",
            "  - Enemies don't hurt each other; watch telegraphs (! / !!).",
            "",
            "Dev Cheats:",
            "  F1: Toggle God Mode",
            "  F2: Refill Consumables",
            "  F3: Toggle Enemy Vision Rays",
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
        # 1. Start Game, 2. Class Select, 3. How to Play, 4. Quit
        options = ["Start Game", "Class Select", "How to Play", "Procedural Generation Options", "Quit"]
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
                        elif choice == "How to Play":
                            self.how_to_play_screen()
                        elif choice == "Procedural Generation Options":
                            self.procedural_generation_menu()
                        elif choice == "Quit":
                            pygame.quit(); sys.exit()
                    # Hotkeys (unchanged behavior)
                    elif ev.key in (pygame.K_1, pygame.K_s):
                        return
                    elif ev.key in (pygame.K_2, pygame.K_c):
                        self.game.selected_class = self.select_class()
                    elif ev.key in (pygame.K_3, pygame.K_h):
                        self.how_to_play_screen()
                    elif ev.key == pygame.K_4: # Hotkey for Procedural Generation Options
                        self.procedural_generation_menu()
                    elif ev.key in (pygame.K_5, pygame.K_q): # Hotkey for Quit
                        pygame.quit(); sys.exit()

            # draw title menu
            self.screen.fill((8, 8, 12))
            draw_text(self.screen, "HARIDD", (WIDTH//2 - 120, 60), (255,220,140), size=60, bold=True)
            draw_text(self.screen, "A tiny action roguelite", (WIDTH//2 - 150, 112), (180,180,200), size=20)
            for i, opt in enumerate(options):
                y = 200 + i*52
                col = (255,220,140) if i == idx else (200,200,200)
                draw_text(self.screen, f"{i+1}. {opt}", (WIDTH//2 - 160, y), col, size=28)
            # Summary line with current class only (procedural generation removed)
            draw_text(self.screen,
                      f"Class: {self.game.selected_class}",
                      (WIDTH//2 - 140, HEIGHT-96), (180,200,220), size=18)
            draw_text(self.screen,
                      "Use Up/Down, Enter to select • 1-4 hotkeys",
                      (WIDTH//2 - 210, HEIGHT-64), (160,160,180), size=16)
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
                    if ev.key in (pygame.K_r, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        # Restart run via centralized logic so behavior is consistent.
                        print(f"[DEBUG GAME_OVER] Restart selected via hotkey")
                        print(f"[DEBUG GAME_OVER] Before restart: level_index={self.game.level_index}, current_level_number={self.game.current_level_number}")
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
                        print(f"[DEBUG GAME_OVER] Restart selected via hotkey 1")
                        print(f"[DEBUG GAME_OVER] Before restart: level_index={self.game.level_index}, current_level_number={self.game.current_level_number}")
                        self.game.restart_run()
                        return
                    elif ev.key in (pygame.K_2, pygame.K_e):
                        # Hotkey: 2 or E => Main Menu
                        # Mirror pause_menu "Main Menu" behavior:
                        # - Go back to title_screen()
                        # - Then reset to level 0 and recreate player/inventory/camera.
                        self.title_screen()
                        # After returning from title screen, reset to level 0 respecting current PCG setting
                        initial_level = 0 if not self.game.use_procedural else 1
                        self.game._load_level(initial_level, initial=True)
                        sx, sy = self.game.level.spawn
                        self.game.player = Player(sx, sy, cls=self.game.selected_class)
                        self.game.enemies = self.game.level.enemies
                        self.game.inventory._refresh_inventory_defaults()
                        hitboxes.clear()
                        floating.clear()
                        self.game.camera = Camera()
                        return
                    elif ev.key in (pygame.K_3,):
                        # Hotkey: 3 => Quit
                        pygame.quit(); sys.exit()
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        # Handle based on selected menu entry
                        choice = options[idx]
                        if choice == "Restart":
                            print(f"[DEBUG GAME_OVER] Restart selected via menu")
                            print(f"[DEBUG GAME_OVER] Before restart: level_index={self.game.level_index}, current_level_number={self.game.current_level_number}")
                            self.game.restart_run()
                            return
                        elif choice == "Main Menu":
                            self.title_screen()
                            # After returning from title screen, reset to level 0 respecting current PCG setting
                            initial_level = 0 if not self.game.use_procedural else 1
                            self.game._load_level(initial_level, initial=True)
                            sx, sy = self.game.level.spawn
                            self.game.player = Player(sx, sy, cls=self.game.selected_class)
                            self.game.enemies = self.game.level.enemies
                            self.game.inventory._refresh_inventory_defaults()
                            hitboxes.clear()
                            floating.clear()
                            self.game.camera = Camera()
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
                            # then start fresh level 0 respecting user_wants_procedural.
                            self.title_screen()
                            # After returning from title screen, reset to level 0 respecting current PCG setting
                            initial_level = 0 if not self.game.use_procedural else 1
                            self.game._load_level(initial_level, initial=True)
                            sx, sy = self.game.level.spawn
                            self.game.player = Player(sx, sy, cls=self.game.selected_class)
                            self.game.enemies = self.game.level.enemies
                            self.game.inventory._refresh_inventory_defaults()
                            hitboxes.clear(); floating.clear()
                            self.game.camera = Camera()
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
 
    def procedural_generation_menu(self):
        """Blocking menu for procedural generation options."""
        options = ["Toggle PCG", "Set Custom Seed", "Generate Random Seed", "Back"]
        idx = 0
        input_text = ""
        input_active = False

        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        if input_active:
                            input_active = False
                            input_text = ""
                        else:
                            return
                    elif input_active:
                        if ev.key == pygame.K_RETURN:
                            try:
                                seed_value = int(input_text)
                                self.game.set_custom_seed(seed_value)
                                input_active = False
                                input_text = ""
                                # Force a level reload to apply new seed (only when explicitly setting a seed)
                                self.game._load_level(self.game.current_level_number, initial=True)
                            except ValueError:
                                # Handle invalid input (non-integer)
                                input_text = "Invalid!"
                        elif ev.key == pygame.K_BACKSPACE:
                            input_text = input_text[:-1]
                        else:
                            input_text += ev.unicode
                    else: # Menu navigation
                        if ev.key in (pygame.K_UP, pygame.K_w):
                            idx = (idx - 1) % len(options)
                        elif ev.key in (pygame.K_DOWN, pygame.K_s):
                            idx = (idx + 1) % len(options)
                        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                            choice = options[idx]
                            if choice == "Toggle PCG":
                                print(f"[DEBUG MENU] Toggle PCG selected")
                                print(f"[DEBUG MENU] Before toggle: use_procedural={self.game.use_procedural}")
                                self.game.toggle_procedural_generation()
                                print(f"[DEBUG MENU] After toggle: use_procedural={self.game.use_procedural}")
                                print(f"[DEBUG MENU] PCG toggle will apply when starting a new run from the main menu.")
                            elif choice == "Set Custom Seed":
                                input_active = True
                                input_text = str(self.game.get_current_seed() or "") # Pre-fill with current seed
                            elif choice == "Generate Random Seed":
                                self.game.generate_random_seed()
                                # Force a level reload to apply new random seed (only when explicitly generating a new seed)
                                self.game._load_level(self.game.current_level_number, initial=True)
                            elif choice == "Back":
                                return

            # Draw menu
            self.screen.fill((8, 8, 12))
            draw_text(self.screen, "PROCEDURAL GENERATION", (WIDTH//2 - 200, 60), (255,220,140), size=40, bold=True)

            # Display current PCG state and seed
            pcg_status = "ON" if self.game.use_procedural else "OFF"
            current_seed = self.game.get_current_seed()
            seed_display = f"Current Seed: {current_seed if current_seed is not None else 'Random'}"
            draw_text(self.screen, f"PCG: {pcg_status}", (WIDTH//2 - 160, 140), (200,200,220), size=22)
            draw_text(self.screen, seed_display, (WIDTH//2 - 160, 170), (200,200,220), size=22)


            for i, opt in enumerate(options):
                y = 240 + i*52
                col = (255,220,140) if i == idx else (200,200,200)
                display_text = opt
                if opt == "Toggle PCG":
                    display_text = f"Toggle PCG ({pcg_status})"
                draw_text(self.screen, display_text, (WIDTH//2 - 160, y), col, size=28)

            if input_active:
                input_rect = pygame.Rect(WIDTH//2 - 150, 300 + options.index("Set Custom Seed")*52, 300, 40)
                pygame.draw.rect(self.screen, (50,50,70), input_rect)
                pygame.draw.rect(self.screen, (200,200,220), input_rect, 2)
                draw_text(self.screen, input_text, (input_rect.x + 10, input_rect.y + 10), (255,255,255), size=20)
                draw_text(self.screen, "Enter seed (integer)", (WIDTH//2 - 150, input_rect.y - 30), (180,180,200), size=16)


            draw_text(self.screen, "Use Up/Down, Enter to select, Esc to return", (WIDTH//2 - 210, HEIGHT-64), (160,160,180), size=16)
            pygame.display.flip()

    # Remove duplicate method - keeping the first one above

    def generation_options_menu(self):
        """
        Legacy stub preserved for compatibility.
        Procedural generation has been removed; this now returns immediately.
        """
        return

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