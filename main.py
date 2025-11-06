import sys
import pygame
from config import WIDTH, HEIGHT, FPS, BG, WHITE, CYAN, GREEN
from utils import draw_text, get_font
from camera import Camera
from level import Level
from entities import Player, hitboxes, floating, DamageNumber

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        # Window caption — show game title
        pygame.display.set_caption("Haridd")
        self.clock = pygame.time.Clock()
        self.font_small = get_font(18)
        self.font_big = get_font(32, bold=True)
        self.camera = Camera()

        # Title flow first: How to Play -> Class Select -> Play Game
        self.selected_class = 'Knight'  # default if player skips class select
        # Developer cheat toggles
        self.cheat_infinite_mana = False
        self.cheat_zero_cooldown = False
        self.debug_enemy_rays = False
        self.consumable_hotkeys = [pygame.K_4, pygame.K_5, pygame.K_6]
        self.consumable_catalog = {
            'health': {
                'name': "Health Flask",
                'type': 'heal',
                'amount': 3,
                'color': (215, 110, 120),
            },
            'mana': {
                'name': "Mana Vial",
                'type': 'mana',
                'amount': 10,
                'color': (120, 180, 240),
            },
            'speed': {
                'name': "Speed Tonic",
                'type': 'speed',
                'amount': 0.05,
                'duration': 8.0,
                'color': (255, 200, 120),
            },
        }
        self.title_screen()

        self.level_index = 0
        self.level = Level(self.level_index)
        sx, sy = self.level.spawn
        # create player with chosen class
        self.player = Player(sx, sy, cls=self.selected_class)
        self.enemies = self.level.enemies
        self.inventory_open = False
        self.gear_slots = []
        self.consumable_slots = []
        self._refresh_inventory_defaults()

    def switch_room(self, delta):
        # wrap using Level.ROOM_COUNT so new rooms are handled
        self.level_index = (self.level_index + delta) % Level.ROOM_COUNT
        self.level = Level(self.level_index)
        sx, sy = self.level.spawn
        self.player.rect.topleft = (sx, sy)
        self.enemies = self.level.enemies
        hitboxes.clear(); floating.clear()

    def _refresh_inventory_defaults(self):
        defaults = {
            'Knight': ["Knight's Sword", "Tower Shield", "Stalwart Crest"],
            'Ranger': ["Recurve Bow", "Trick Quiver", "Hunter's Token"],
            'Wizard': ["Arcane Staff", "Spell Tome", "Sage's Charm"],
        }
        consumable_defaults = {
            'Knight': ['health', 'speed', 'mana'],
            'Ranger': ['health', 'mana', 'speed'],
            'Wizard': ['mana', 'speed', 'health'],
        }
        cls = getattr(self.player, 'cls', 'Knight')
        self.gear_slots = defaults.get(cls, ["Primary Gear", "Offhand Gear", "Utility Charm"])
        keys = consumable_defaults.get(cls, ['health', 'mana', None])
        slots = []
        for i in range(len(self.consumable_hotkeys)):
            key_id = keys[i] if i < len(keys) else None
            slots.append(self._make_consumable(key_id) if key_id else None)
        self.consumable_slots = slots
        self.inventory_open = False

    def _make_consumable(self, key):
        if not key:
            return None
        data = self.consumable_catalog.get(key)
        if not data:
            return None
        clone = data.copy()
        clone['key'] = key
        return clone

    def add_consumable(self, key):
        item = self._make_consumable(key)
        if not item:
            return
        for i in range(len(self.consumable_slots)):
            if self.consumable_slots[i] is None:
                self.consumable_slots[i] = item
                return
        # replace last slot if no room
        self.consumable_slots[-1] = item

    def add_all_consumables(self):
        keys = list(self.consumable_catalog.keys())
        slots = []
        for i in range(len(self.consumable_slots)):
            key = keys[i] if i < len(keys) else None
            slots.append(self._make_consumable(key))
        self.consumable_slots = slots

    def consume_slot(self, idx):
        if idx < 0 or idx >= len(self.consumable_slots):
            return
        item = self.consumable_slots[idx]
        if not item:
            return
        if self._apply_consumable_effect(item):
            self.consumable_slots[idx] = None
        else:
            floating.append(DamageNumber(self.player.rect.centerx, self.player.rect.top-12, "No effect", WHITE))

    def _apply_consumable_effect(self, item):
        typ = item.get('type')
        if typ == 'heal':
            before = self.player.hp
            self.player.hp = min(self.player.max_hp, self.player.hp + item.get('amount', 0))
            healed = self.player.hp - before
            if healed <= 0:
                return False
            floating.append(DamageNumber(self.player.rect.centerx, self.player.rect.top-12, f"+{healed} HP", GREEN))
            return True
        if typ == 'mana' and hasattr(self.player, 'mana'):
            before = self.player.mana
            self.player.mana = min(self.player.max_mana, self.player.mana + item.get('amount', 0))
            restored = self.player.mana - before
            if restored <= 0:
                return False
            floating.append(DamageNumber(self.player.rect.centerx, self.player.rect.top-12, f"+{restored:.0f} MP", CYAN))
            return True
        if typ == 'speed':
            duration = int(item.get('duration', 8.0) * FPS)
            bonus = item.get('amount', 0.05)
            current = getattr(self.player, 'speed_potion_timer', 0)
            self.player.speed_potion_timer = max(current, duration)
            self.player.speed_potion_bonus = max(getattr(self.player, 'speed_potion_bonus', 0.0), bonus)
            floating.append(DamageNumber(self.player.rect.centerx, self.player.rect.top-12, "Haste", WHITE))
            return True
        return False

    def _hotkey_label(self, idx):
        if idx < len(self.consumable_hotkeys):
            return pygame.key.name(self.consumable_hotkeys[idx]).upper()
        return str(idx + 4)

    def draw_consumable_hotbar(self):
        if not self.consumable_slots:
            return
        slot_w, slot_h = 74, 62
        spacing = 12
        count = len(self.consumable_slots)
        total_w = slot_w * count + spacing * (count - 1)
        start_x = WIDTH - total_w - 20
        start_y = HEIGHT - slot_h - 24
        title_font = get_font(18, bold=True)
        title_surface = title_font.render("Consumables (4 / 5 / 6)", True, (215, 210, 220))
        self.screen.blit(title_surface, (start_x, start_y - 24))
        for idx, item in enumerate(self.consumable_slots):
            rect = pygame.Rect(start_x + idx * (slot_w + spacing), start_y, slot_w, slot_h)
            pygame.draw.rect(self.screen, (40, 40, 50), rect, border_radius=8)
            pygame.draw.rect(self.screen, (90, 90, 120), rect, width=2, border_radius=8)
            key_label = self._hotkey_label(idx)
            draw_text(self.screen, key_label, (rect.x + 6, rect.y + 4), (200,200,210), size=16, bold=True)
            icon_rect = pygame.Rect(rect.x + 12, rect.y + 22, rect.w - 24, 18)
            if item:
                pygame.draw.rect(self.screen, item.get('color', (160, 180, 220)), icon_rect, border_radius=6)
                name = item.get('name', '???')
            else:
                pygame.draw.rect(self.screen, (60, 60, 80), icon_rect, width=2, border_radius=6)
                name = "Empty"
            name_font = get_font(14)
            name_surface = name_font.render(name, True, (220,220,230))
            name_rect = name_surface.get_rect(center=(rect.centerx, rect.bottom - 12))
            self.screen.blit(name_surface, name_rect)

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
                    elif ev.key == pygame.K_UP:
                        idx = (idx - 1) % len(options)
                    elif ev.key == pygame.K_DOWN:
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        return options[idx]
                    elif ev.key == pygame.K_1:
                        return options[0]
                    elif ev.key == pygame.K_2:
                        return options[1]
                    elif ev.key == pygame.K_3:
                        return options[2]

            # draw
            self.screen.fill(BG)
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
            "  F2: Teleport to Boss Room",
        ]
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
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
        """Blocking title menu: How to Play / Class Select / Play Game / Quit.
        Sets self.selected_class and returns when Play Game is chosen.
        """
        options = ["How to Play", "Class Select", "Play Game", "Quit"]
        idx = 0
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    elif ev.key == pygame.K_UP:
                        idx = (idx - 1) % len(options)
                    elif ev.key == pygame.K_DOWN:
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        choice = options[idx]
                        if choice == "How to Play":
                            self.how_to_play_screen()
                        elif choice == "Class Select":
                            self.selected_class = self.select_class()
                        elif choice == "Play Game":
                            return
                        elif choice == "Quit":
                            pygame.quit(); sys.exit()
                    elif ev.key in (pygame.K_1, pygame.K_h):
                        self.how_to_play_screen()
                    elif ev.key in (pygame.K_2, pygame.K_c):
                        self.selected_class = self.select_class()
                    elif ev.key in (pygame.K_3, pygame.K_p):
                        return
                    elif ev.key in (pygame.K_4, pygame.K_q):
                        pygame.quit(); sys.exit()

            # draw title menu
            self.screen.fill((8, 8, 12))
            draw_text(self.screen, "HARIDD", (WIDTH//2 - 120, 60), (255,220,140), size=60, bold=True)
            draw_text(self.screen, "A tiny action roguelite", (WIDTH//2 - 150, 112), (180,180,200), size=20)
            for i, opt in enumerate(options):
                y = 200 + i*52
                col = (255,220,140) if i == idx else (200,200,200)
                draw_text(self.screen, f"{i+1}. {opt}", (WIDTH//2 - 120, y), col, size=28)
            draw_text(self.screen, f"Selected Class: {self.selected_class}", (WIDTH//2 - 150, HEIGHT-96), (180,200,220), size=20)
            draw_text(self.screen, "Use Up/Down, Enter to select • 1-4 hotkeys", (WIDTH//2 - 210, HEIGHT-64), (160,160,180), size=16)
            pygame.display.flip()

    def goto_room(self, index):
        # go to an absolute room index (wrapped)
        self.level_index = index % Level.ROOM_COUNT
        self.level = Level(self.level_index)
        sx, sy = self.level.spawn
        self.player.rect.topleft = (sx, sy)
        self.enemies = self.level.enemies
        hitboxes.clear(); floating.clear()

    def update(self):
        self.player.input(self.level, self.camera)
        self.player.physics(self.level)

        # If player died, show restart menu
        if getattr(self.player, 'dead', False):
            self.game_over_screen()
            return

        # Apply developer cheats each frame
        if self.cheat_infinite_mana and hasattr(self.player, 'max_mana'):
            self.player.mana = getattr(self.player, 'max_mana', self.player.mana)
        if self.cheat_zero_cooldown:
            # Force cooldowns to zero if present
            for attr in ('skill_cd1', 'skill_cd2', 'skill_cd3'):
                if hasattr(self.player, attr):
                    setattr(self.player, attr, 0)

        for d in self.level.doors:
            if self.player.rect.colliderect(d):
                # Gate boss rooms: require boss defeat before door works
                if getattr(self.level, 'is_boss_room', False):
                    if any(getattr(e, 'alive', False) for e in self.enemies):
                        # door locked; stay in room
                        pass
                    else:
                        self.switch_room(+1)
                        break
                else:
                    self.switch_room(+1)
                    break

        for e in self.enemies:
            e.tick(self.level, self.player)

        for hb in list(hitboxes):
            hb.tick()
            # if projectile hits solids, explode or die
            collided_solid = False
            for s in self.level.solids:
                if hb.rect.colliderect(s):
                    collided_solid = True
                    break
            if collided_solid:
                if getattr(hb, 'aoe_radius', 0) > 0 and not getattr(hb, 'visual_only', False):
                    cx, cy = hb.rect.center
                    for e2 in self.enemies:
                        if getattr(e2, 'alive', False):
                            dx = e2.rect.centerx - cx
                            dy = e2.rect.centery - cy
                            if (dx*dx + dy*dy) ** 0.5 <= hb.aoe_radius:
                                e2.hit(hb, self.player)
                # remove visual-only hitboxes or projectiles
                if hb in hitboxes:
                    hitboxes.remove(hb)
                continue
            # enemy hitboxes can affect player (damage/stun). Ignore player's own.
            if getattr(hb, 'owner', None) is not self.player:
                # AOE against player
                if getattr(hb, 'aoe_radius', 0) > 0 and not getattr(hb, 'visual_only', False):
                    cx, cy = hb.rect.center
                    dx = self.player.rect.centerx - cx
                    dy = self.player.rect.centery - cy
                    if (dx*dx + dy*dy) ** 0.5 <= getattr(hb, 'aoe_radius', 0):
                        # apply stun tag if present
                        if getattr(hb, 'tag', None) == 'stun':
                            self.player.stunned = max(self.player.stunned, int(0.8 * FPS))
                        # apply damage if any
                        if getattr(hb, 'damage', 0) > 0:
                            kx, ky = hb.dir_vec if getattr(hb, 'dir_vec', None) else (0, -1)
                            self.player.damage(hb.damage, (int(kx*3), -6))
                        # consume the AOE
                        hb.alive = False
                # direct projectile/contact against player
                elif hb.rect.colliderect(self.player.rect) and not getattr(hb, 'visual_only', False):
                    if getattr(hb, 'tag', None) == 'stun':
                        self.player.stunned = max(self.player.stunned, int(0.8 * FPS))
                    if getattr(hb, 'damage', 0) > 0:
                        kx, ky = hb.dir_vec if getattr(hb, 'dir_vec', None) else (0, -1)
                        self.player.damage(hb.damage, (int(kx*3), -6))
                    # non-piercing projectiles disappear after hitting player
                    if (getattr(hb, 'vx', 0) or getattr(hb, 'vy', 0)) and not getattr(hb, 'pierce', False):
                        hb.alive = False
            # moving/projectile hitboxes may hit enemies; support AOE hitboxes
            # Only allow player-owned hitboxes to damage enemies (no enemy friendly-fire)
            if getattr(hb, 'aoe_radius', 0) > 0 and getattr(hb, 'owner', None) is self.player:
                # visual-only AOE (e.g., cold feet) should not apply instant damage
                if getattr(hb, 'visual_only', False):
                    if not hb.alive:
                        hitboxes.remove(hb)
                    continue
                # check collision with any enemy, explode on first hit
                exploded = False
                for e in self.enemies:
                    if getattr(e, 'alive', False) and hb.rect.colliderect(e.rect):
                        # explode: apply damage to all enemies within radius
                        cx, cy = hb.rect.center
                        for e2 in self.enemies:
                            if getattr(e2, 'alive', False):
                                dx = e2.rect.centerx - cx
                                dy = e2.rect.centery - cy
                                if (dx*dx + dy*dy) ** 0.5 <= hb.aoe_radius:
                                    e2.hit(hb, self.player)
                        exploded = True
                        hb.alive = False
                        break
                if not hb.alive:
                    hitboxes.remove(hb)
                continue

            # Only player-owned hitboxes damage enemies
            if getattr(hb, 'owner', None) is self.player:
                for e in self.enemies:
                    if getattr(e, 'alive', False) and hb.rect.colliderect(e.rect):
                        e.hit(hb, self.player)
                        # moving projectiles should disappear after first enemy hit unless they can pierce
                        if getattr(hb, 'vx', 0) or getattr(hb, 'vy', 0):
                            if not getattr(hb, 'pierce', False):
                                hb.alive = False
                                break
            if not hb.alive:
                hitboxes.remove(hb)

        for dn in list(floating):
            dn.tick()
            if dn.life <= 0:
                floating.remove(dn)

        self.camera.update(self.player.rect)

    def draw(self):
        self.screen.fill(BG)
        self.level.draw(self.screen, self.camera)
        for e in self.enemies:
            e.draw(self.screen, self.camera, show_los=self.debug_enemy_rays)
        for hb in hitboxes:
            hb.draw(self.screen, self.camera)
        self.player.draw(self.screen, self.camera)
        for dn in floating:
            dn.draw(self.screen, self.camera, self.font_small)

        # HUD
        x, y = 16, 16
        for i in range(self.player.max_hp):
            c = (80,200,120) if i < self.player.hp else (60,80,60)
            pygame.draw.rect(self.screen, c, pygame.Rect(x+i*18, y, 16, 10), border_radius=3)
        y += 16
        if self.player.dash_cd:
            pct = 1 - (self.player.dash_cd / 24)
            pygame.draw.rect(self.screen, (80,80,80), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(self.screen, CYAN, pygame.Rect(x, y, int(120*pct), 6), border_radius=3)
        # stamina bar (if player has stamina)
        y += 12
        if hasattr(self.player, 'stamina') and hasattr(self.player, 'max_stamina'):
            spct = max(0.0, min(1.0, self.player.stamina / max(1e-6, self.player.max_stamina)))
            pygame.draw.rect(self.screen, (60,60,60), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(self.screen, (200,180,60), pygame.Rect(x, y, int(120*spct), 6), border_radius=3)
            y += 12
        # mana bar
        if hasattr(self.player, 'mana') and hasattr(self.player, 'max_mana'):
            mpct = max(0.0, min(1.0, self.player.mana / max(1e-6, self.player.max_mana)))
            pygame.draw.rect(self.screen, (60,60,60), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(self.screen, CYAN, pygame.Rect(x, y, int(120*mpct), 6), border_radius=3)
            y += 12

        # show ranger charge bar when charging
        if getattr(self.player, 'cls', '') == 'Ranger' and getattr(self.player, 'charging', False):
            pct = max(0.0, min(1.0, self.player.charge_time / max(1, self.player.charge_threshold)))
            pygame.draw.rect(self.screen, (60,60,60), pygame.Rect(x, y, 120, 6), border_radius=3)
            pygame.draw.rect(self.screen, (200,180,60), pygame.Rect(x, y, int(120*pct), 6), border_radius=3)
            # show '!' when fully charged
            if pct >= 1.0:
                draw_text(self.screen, "!", (x + 124, y-6), (255,80,80), size=18, bold=True)
            y += 12

        # show selected class on HUD
        draw_text(self.screen, f"Class: {getattr(self.player, 'cls', 'Unknown')}", (WIDTH-220, 8), (200,200,200), size=16)

        # Skill bar (MOBA-style): show 1/2/3 cooldowns and active highlights
        sbx, sby = 16, HEIGHT - 80
        slot_w, slot_h = 46, 46
        # Names per class
        if self.player.cls == 'Knight':
            names = ['Shield', 'Power', 'Charge']
            actives = [self.player.shield_timer>0, self.player.power_timer>0, False]
        elif self.player.cls == 'Ranger':
            names = ['Triple', 'Sniper', 'Speed']
            actives = [self.player.triple_timer>0, self.player.sniper_ready, self.player.speed_timer>0]
        else:
            names = ['Fireball', 'Cold', 'Missile']
            actives = [False, False, False]
        cds = [self.player.skill_cd1, self.player.skill_cd2, self.player.skill_cd3]
        maxcds = [max(1,self.player.skill_cd1_max), max(1,self.player.skill_cd2_max), max(1,self.player.skill_cd3_max)]
        for i in range(3):
            rx = sbx + i*(slot_w+8)
            ry = sby
            # slot background
            pygame.draw.rect(self.screen, (40,40,50), pygame.Rect(rx, ry, slot_w, slot_h), border_radius=6)
            # active border glow
            if actives[i]:
                pygame.draw.rect(self.screen, (120,210,220), pygame.Rect(rx-2, ry-2, slot_w+4, slot_h+4), width=2, border_radius=8)
            # cooldown overlay
            if cds[i] > 0:
                pct = cds[i] / maxcds[i]
                h = int(slot_h * pct)
                overlay = pygame.Rect(rx, ry + (slot_h - h), slot_w, h)
                pygame.draw.rect(self.screen, (0,0,0,120), overlay)
                # remaining seconds text
                secs = max(0.0, cds[i]/FPS)
                draw_text(self.screen, f"{secs:.0f}", (rx + 12, ry + 12), (220,220,220), size=18, bold=True)
            # key label and name
            draw_text(self.screen, str(i+1), (rx+2, ry+2), (200,200,200), size=14)
            draw_text(self.screen, names[i], (rx+2, ry+slot_h-14), (180,180,200), size=12)

        self.draw_consumable_hotbar()

        if getattr(self.player, 'speed_potion_timer', 0) > 0:
            secs = max(0, int(self.player.speed_potion_timer / FPS))
            draw_text(self.screen, f"Haste {secs}s", (WIDTH-180, HEIGHT-120), (255,220,140), size=16, bold=True)

        draw_text(self.screen,
                  "Move A/D | Jump Space/K | Dash Shift/J | Attack L/Mouse | Up/Down+Attack for Up/Down slash (Down=Pogo)",
                  (12, HEIGHT-28), (180,180,200), size=16)
        draw_text(self.screen, f"Room {self.level_index+1}/{Level.ROOM_COUNT}", (12, 8), WHITE)
        if getattr(self.player, 'god', False):
            draw_text(self.screen, "GOD", (WIDTH-64, 8), (255,200,80), bold=True)
        # Boss room hint: lock door until boss defeated
        if getattr(self.level, 'is_boss_room', False) and any(getattr(e, 'alive', False) for e in self.enemies):
            draw_text(self.screen, "Defeat the boss to open the door", (WIDTH//2 - 160, 8), (255,120,120), size=16)

        if self.inventory_open:
            self.draw_inventory_overlay()

    def draw_inventory_overlay(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        panel_w, panel_h = 660, 520
        panel_rect = pygame.Rect(
            (WIDTH - panel_w) // 2,
            (HEIGHT - panel_h) // 2,
            panel_w,
            panel_h,
        )
        panel_bg = (30, 28, 40)
        panel_border = (210, 200, 170)
        pygame.draw.rect(self.screen, panel_bg, panel_rect, border_radius=12)
        pygame.draw.rect(self.screen, panel_border, panel_rect, width=2, border_radius=12)

        draw_text(self.screen, "Inventory", (panel_rect.x + 32, panel_rect.y + 20), (240,220,190), size=30, bold=True)
        footer_font = get_font(18)
        footer_surface = footer_font.render("Press I or Esc to close", True, (180,180,195))
        footer_rect = footer_surface.get_rect(center=(panel_rect.centerx, panel_rect.bottom - 28))
        self.screen.blit(footer_surface, footer_rect)

        left_x = panel_rect.x + 32
        left_y = panel_rect.y + 72
        left_column_width = panel_rect.centerx - left_x - 28
        status_lines = [
            f"Class: {getattr(self.player, 'cls', 'Unknown')}",
            f"HP: {self.player.hp}/{self.player.max_hp}",
            f"Room: {self.level_index+1}/{Level.ROOM_COUNT}",
        ]
        if hasattr(self.player, 'stamina') and hasattr(self.player, 'max_stamina'):
            status_lines.append(f"Stamina: {self.player.stamina:.1f}/{self.player.max_stamina:.1f}")
        if hasattr(self.player, 'mana') and hasattr(self.player, 'max_mana'):
            status_lines.append(f"Mana: {self.player.mana:.1f}/{self.player.max_mana:.1f}")
        status_lines.append(f"Attack Power: {getattr(self.player, 'attack_damage', '?')}")
        ground_speed = float(getattr(self.player, 'player_speed', 0.0) or 0.0)
        air_speed = float(getattr(self.player, 'player_air_speed', 0.0) or 0.0)
        status_lines.append(f"Move Speed: {ground_speed:.1f}/{air_speed:.1f} (ground/air)")

        status_spacing = 24
        for i, line in enumerate(status_lines):
            draw_text(self.screen, line, (left_x, left_y + i * status_spacing), (210,210,225), size=20)

        gear_title_y = left_y + len(status_lines) * status_spacing + 24
        draw_text(self.screen, "Armament Slots", (left_x, gear_title_y), (235,210,190), size=22, bold=True)

        slot_w, slot_h = left_column_width, 46
        slot_spacing = 16
        slot_start_y = gear_title_y + 34
        slot_bg = (46, 52, 72)
        slot_border = (110, 120, 150)
        for idx in range(3):
            label = self.gear_slots[idx] if idx < len(self.gear_slots) else "Empty"
            rect = pygame.Rect(left_x, slot_start_y + idx * (slot_h + slot_spacing), slot_w, slot_h)
            pygame.draw.rect(self.screen, slot_bg, rect, border_radius=8)
            pygame.draw.rect(self.screen, slot_border, rect, width=2, border_radius=8)
            draw_text(self.screen, f"{idx+1}. {label}", (rect.x + 12, rect.y + 12), (220,220,235), size=18)

        right_x = panel_rect.centerx + 36
        model_frame = pygame.Rect(right_x, left_y - 12, 192, 232)
        pygame.draw.rect(self.screen, (32, 36, 52), model_frame, border_radius=16)
        pygame.draw.rect(self.screen, (160, 180, 220), model_frame, width=2, border_radius=16)

        model_rect = pygame.Rect(0, 0, self.player.rect.width * 4, self.player.rect.height * 4)
        model_rect.center = model_frame.center
        pygame.draw.rect(self.screen, (120, 200, 235), model_rect, border_radius=12)

        label_font = get_font(20)
        label_surface = label_font.render("Player Model", True, (210,210,225))
        label_rect = label_surface.get_rect(center=(model_frame.centerx, model_frame.bottom + 24))
        self.screen.blit(label_surface, label_rect)

        cons_title_surface = get_font(24, bold=True).render("Consumables", True, (235,210,190))
        cons_title_rect = cons_title_surface.get_rect(center=(model_frame.centerx, label_rect.bottom + 34))
        self.screen.blit(cons_title_surface, cons_title_rect)

        slot_count = len(self.consumable_slots)
        if slot_count > 0:
            cons_size = 78
            cons_spacing = 24
            cons_total_width = cons_size * slot_count + cons_spacing * max(0, slot_count - 1)
            cons_start_x = model_frame.centerx - cons_total_width // 2
            cons_start_y = cons_title_rect.bottom + 30
            cons_bg = (50, 60, 84)
            cons_border = (130, 150, 180)
            name_font = get_font(18)
            for idx in range(slot_count):
                rect = pygame.Rect(cons_start_x + idx * (cons_size + cons_spacing), cons_start_y, cons_size, cons_size)
                pygame.draw.rect(self.screen, cons_bg, rect, border_radius=10)
                pygame.draw.rect(self.screen, cons_border, rect, width=2, border_radius=10)
                key_label = self._hotkey_label(idx)
                draw_text(self.screen, key_label, (rect.x + 8, rect.y + 6), (200,200,210), size=18, bold=True)
                item = self.consumable_slots[idx]
                icon_rect = rect.inflate(-rect.w * 0.4, -rect.h * 0.45)
                if item:
                    pygame.draw.rect(self.screen, item.get('color', (140, 160, 200)), icon_rect, border_radius=10)
                    name = item.get('name', '???')
                else:
                    pygame.draw.rect(self.screen, (70, 70, 88), icon_rect, width=2, border_radius=10)
                    name = "Empty"
                text_surface = name_font.render(name, True, (220,220,230))
                text_rect = text_surface.get_rect(center=(rect.centerx, rect.bottom - 18))
                self.screen.blit(text_surface, text_rect)

        draw_text(self.screen, "Use keys 4 / 5 / 6 during gameplay to consume items.", (panel_rect.x + 32, panel_rect.bottom - 76), (185,185,205), size=18)

    def run(self):
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_i:
                        self.inventory_open = not self.inventory_open
                        continue
                    if ev.key == pygame.K_F5:
                        self.inventory_open = False
                        self.debug_menu()
                        continue
                    if self.inventory_open:
                        if ev.key == pygame.K_ESCAPE:
                            self.inventory_open = False
                        continue
                    used_consumable = False
                    for idx, keycode in enumerate(self.consumable_hotkeys):
                        if ev.key == keycode:
                            self.consume_slot(idx)
                            used_consumable = True
                            break
                    if used_consumable:
                        continue
                    if ev.key == pygame.K_ESCAPE:
                        # open pause menu instead of quitting
                        self.pause_menu()
                    # Developer cheats
                    elif ev.key == pygame.K_F1:
                        # toggle god mode
                        self.player.god = not getattr(self.player, 'god', False)
                        print(f"God mode {'ON' if self.player.god else 'OFF'}")
                    elif ev.key == pygame.K_F2:
                        # teleport to boss room (last room)
                        self.goto_room(Level.ROOM_COUNT - 1)
                    elif ev.key == pygame.K_F3:
                        # toggle infinite mana
                        self.cheat_infinite_mana = not self.cheat_infinite_mana
                        state = 'ON' if self.cheat_infinite_mana else 'OFF'
                        print(f"Cheat: Infinite Mana {state}")
                    elif ev.key == pygame.K_F4:
                        # toggle zero cooldown
                        self.cheat_zero_cooldown = not self.cheat_zero_cooldown
                        state = 'ON' if self.cheat_zero_cooldown else 'OFF'
                        print(f"Cheat: Zero Cooldown {state}")
                    elif ev.key == pygame.K_F6:
                        self.goto_room(1)
                    elif ev.key == pygame.K_F7:
                        self.goto_room(2)
                    elif ev.key == pygame.K_F8:
                        self.goto_room(3)
                    elif ev.key == pygame.K_F9:
                        self.goto_room(4)
                    elif ev.key == pygame.K_F10:
                        self.goto_room(5)

            if not self.inventory_open:
                self.update()
            self.draw()
            pygame.display.flip()

    def game_over_screen(self):
        """Blocking game over / restart menu. Restart keeps the selected class."""
        font_big = get_font(48, bold=True)
        font_med = get_font(28)
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                        pygame.quit(); sys.exit()
                    if ev.key in (pygame.K_r, pygame.K_RETURN, pygame.K_KP_ENTER):
                        # restart: reset level, player and containers
                        self.level_index = 0
                        self.level = Level(self.level_index)
                        sx, sy = self.level.spawn
                        self.player = Player(sx, sy, cls=self.selected_class)
                        self.enemies = self.level.enemies
                        self._refresh_inventory_defaults()
                        hitboxes.clear(); floating.clear()
                        self.camera = Camera()
                        return

            # draw overlay
            self.screen.fill((10, 10, 16))
            draw_text(self.screen, "YOU DIED", (WIDTH//2 - 120, HEIGHT//2 - 80), (220,80,80), size=48, bold=True)
            draw_text(self.screen, "Press R or Enter to Restart", (WIDTH//2 - 160, HEIGHT//2 - 8), (200,200,200), size=24)
            draw_text(self.screen, "Press Q or Esc to Quit", (WIDTH//2 - 140, HEIGHT//2 + 36), (180,180,180), size=20)
            pygame.display.flip()

    def debug_menu(self):
        self.inventory_open = False
        options = [
            {'label': "God Mode (F1)", 'type': 'toggle',
             'getter': lambda: getattr(self.player, 'god', False),
             'setter': lambda v: setattr(self.player, 'god', v)},
            {'label': "Teleport to Boss Room (F2)", 'type': 'action',
             'action': lambda: self.goto_room(Level.ROOM_COUNT - 1)},
            {'label': "Infinite Mana (F3)", 'type': 'toggle',
             'getter': lambda: self.cheat_infinite_mana,
             'setter': lambda v: setattr(self, 'cheat_infinite_mana', v)},
            {'label': "Zero Cooldown (F4)", 'type': 'toggle',
             'getter': lambda: self.cheat_zero_cooldown,
             'setter': lambda v: setattr(self, 'cheat_zero_cooldown', v)},
            {'label': "Enemy Vision Rays", 'type': 'toggle',
             'getter': lambda: self.debug_enemy_rays,
             'setter': lambda v: setattr(self, 'debug_enemy_rays', v)},
            {'label': "Refill Consumables", 'type': 'action',
             'action': self.add_all_consumables},
            {'label': "Close", 'type': 'action',
             'action': None, 'close': True},
        ]
        idx = 0
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_F5):
                        return
                    elif ev.key == pygame.K_UP:
                        idx = (idx - 1) % len(options)
                    elif ev.key == pygame.K_DOWN:
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        opt = options[idx]
                        if opt['type'] == 'toggle':
                            opt['setter'](not opt['getter']())
                        elif opt['type'] == 'action' and opt['action']:
                            opt['action']()
                        if opt.get('close'):
                            return
            self.draw()
            self._draw_debug_overlay(options, idx)
            pygame.display.flip()

    def _draw_debug_overlay(self, options, selected):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(WIDTH//2 - 220, HEIGHT//2 - 200, 440, 360)
        pygame.draw.rect(self.screen, (32, 30, 42), panel, border_radius=12)
        pygame.draw.rect(self.screen, (210, 200, 170), panel, width=2, border_radius=12)
        draw_text(self.screen, "Debugger", (panel.x + 24, panel.y + 16), (240,220,190), size=28, bold=True)
        info = "Arrows = Navigate | Enter = Toggle | Esc/F5 = Close"
        draw_text(self.screen, info, (panel.x + 24, panel.bottom - 32), (180,180,200), size=16)
        line_h = 44
        for i, opt in enumerate(options):
            row = pygame.Rect(panel.x + 24, panel.y + 64 + i * line_h, panel.width - 48, 34)
            bg_col = (70, 70, 90) if i == selected else (50, 50, 68)
            pygame.draw.rect(self.screen, bg_col, row, border_radius=8)
            text = opt['label']
            if opt['type'] == 'toggle':
                text = f"{text}: {'ON' if opt['getter']() else 'OFF'}"
            elif opt['type'] == 'action' and not opt.get('close'):
                text = f"{text}"
            draw_text(self.screen, text, (row.x + 12, row.y + 8), (220,220,230), size=18)

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
                    elif ev.key == pygame.K_UP:
                        idx = (idx - 1) % len(options)
                    elif ev.key == pygame.K_DOWN:
                        idx = (idx + 1) % len(options)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        choice = options[idx]
                        if choice == "Resume":
                            return
                        elif choice == "Settings":
                            self.settings_screen()
                        elif choice == "Main Menu":
                            # go back to title menu (how-to/class select) and reset
                            self.selected_class = 'Knight'
                            self.title_screen()
                            self.level_index = 0
                            self.level = Level(self.level_index)
                            sx, sy = self.level.spawn
                            self.player = Player(sx, sy, cls=self.selected_class)
                            self.enemies = self.level.enemies
                            self._refresh_inventory_defaults()
                            hitboxes.clear(); floating.clear()
                            self.camera = Camera()
                            return
                        elif choice == "Quit":
                            pygame.quit(); sys.exit()
                        # Show cheats status
                        cheat_msgs = []
                        if getattr(self.player, 'god', False):
                            cheat_msgs.append('GOD')
                        if getattr(self, 'cheat_infinite_mana', False):
                            cheat_msgs.append('IM')
                        if getattr(self, 'cheat_zero_cooldown', False):
                            cheat_msgs.append('ZCD')
                        if cheat_msgs:
                            draw_text(self.screen, ' '.join(cheat_msgs), (WIDTH-120, 28), (255,200,80), size=16, bold=True)
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

    def settings_screen(self):
        """Simple settings placeholder. Press Esc to go back."""
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                        return

            self.screen.fill((10, 10, 14))
            draw_text(self.screen, "SETTINGS", (WIDTH//2 - 80, 60), (220,220,220), size=40, bold=True)
            draw_text(self.screen, "(No settings yet)", (WIDTH//2 - 120, HEIGHT//2 - 8), (180,180,180), size=22)
            draw_text(self.screen, "Press Esc or Enter to return", (WIDTH//2 - 160, HEIGHT-64), (140,140,140), size=16)
            pygame.display.flip()

if __name__ == '__main__':
    Game().run()
