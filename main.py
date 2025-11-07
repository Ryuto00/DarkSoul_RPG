import sys

import pygame
from config import WIDTH, HEIGHT, FPS, BG, WHITE, CYAN, GREEN
from utils import draw_text, get_font
from camera import Camera
from level import Level, ROOM_COUNT
from entities import Player, hitboxes, floating
from inventory import Inventory
from menu import Menu




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

        # Initialize menu system
        self.menu = Menu(self)

        # Title flow first: How to Play -> Class Select -> Play Game
        self.selected_class = 'Knight'  # default if player skips class select
        # Developer cheat toggles
        self.cheat_infinite_mana = False
        self.cheat_zero_cooldown = False
        self.debug_enemy_rays = False
        self.debug_enemy_nametags = False
        self.menu.title_screen()

        self.level_index = 0
        self.level = Level(self.level_index)
        
        # DEBUG: Initialize terrain system
        from terrain_system import terrain_system
        terrain_system.load_terrain_from_level(self.level)
        print(f"[DEBUG] Terrain system initialized for level {self.level_index}")
        
        sx, sy = self.level.spawn
        # create player with chosen class
        self.player = Player(sx, sy, cls=self.selected_class)
        self.enemies = self.level.enemies
        self.inventory = Inventory(self)
        self.inventory._refresh_inventory_defaults()

    def switch_room(self, delta):
        # wrap using Level.ROOM_COUNT so new rooms are handled
        self.level_index = (self.level_index + delta) % ROOM_COUNT
        self.level = Level(self.level_index)
        
        # DEBUG: Reinitialize terrain system for new level
        from terrain_system import terrain_system
        terrain_system.load_terrain_from_level(self.level)
        print(f"[DEBUG] Terrain system reinitialized for level {self.level_index}")
        
        sx, sy = self.level.spawn
        self.player.rect.topleft = (sx, sy)
        self.enemies = self.level.enemies
        hitboxes.clear(); floating.clear()

    def goto_room(self, index):
        # go to an absolute room index (wrapped)
        self.level_index = index % ROOM_COUNT
        self.level = Level(self.level_index)
        sx, sy = self.level.spawn
        self.player.rect.topleft = (sx, sy)
        self.enemies = self.level.enemies
        hitboxes.clear(); floating.clear()

    def update(self):
        self.player.input(self.level, self.camera)
        self.player.physics(self.level)
        self.inventory.recalculate_player_stats()

        # If player died, show restart menu
        if getattr(self.player, 'dead', False):
            self.menu.game_over_screen()
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
            e.draw(self.screen, self.camera, show_los=self.debug_enemy_rays, show_nametags=self.debug_enemy_nametags)
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
            stamina_col = (120, 230, 160) if getattr(self.player, 'stamina_boost_timer', 0) > 0 else (200,180,60)
            pygame.draw.rect(self.screen, stamina_col, pygame.Rect(x, y, int(120*spct), 6), border_radius=3)
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

        self.inventory.draw_consumable_hotbar()

        if getattr(self.player, 'speed_potion_timer', 0) > 0:
            secs = max(0, int(self.player.speed_potion_timer / FPS))
            draw_text(self.screen, f"Haste {secs}s", (WIDTH-180, HEIGHT-120), (255,220,140), size=16, bold=True)
        if getattr(self.player, 'jump_boost_timer', 0) > 0:
            secs = max(0, int(self.player.jump_boost_timer / FPS))
            draw_text(self.screen, f"Skybound {secs}s", (WIDTH-180, HEIGHT-140), (200,220,255), size=16, bold=True)
        if getattr(self.player, 'stamina_boost_timer', 0) > 0:
            secs = max(0, int(self.player.stamina_boost_timer / FPS))
            draw_text(self.screen, f"Cavern Brew {secs}s", (WIDTH-180, HEIGHT-160), (150,255,180), size=16, bold=True)

        draw_text(self.screen,
                  "Move A/D | Jump Space/K | Dash Shift/J | Attack L/Mouse | Up/Down+Attack for Up/Down slash (Down=Pogo)",
                  (12, HEIGHT-28), (180,180,200), size=16)
        draw_text(self.screen, f"Room {self.level_index+1}/{ROOM_COUNT}", (12, 8), WHITE)
        if getattr(self.player, 'god', False):
            draw_text(self.screen, "GOD", (WIDTH-64, 8), (255,200,80), bold=True)
        # Boss room hint: lock door until boss defeated
        if getattr(self.level, 'is_boss_room', False) and any(getattr(e, 'alive', False) for e in self.enemies):
            draw_text(self.screen, "Defeat the boss to open the door", (WIDTH//2 - 160, 8), (255,120,120), size=16)

        if self.inventory.inventory_open:
            self.inventory.draw_inventory_overlay()



    def run(self):
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    if self.inventory.inventory_open and ev.button == 1:
                        self.inventory._handle_inventory_click(ev.pos)
                    continue
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_i:
                        self.inventory.inventory_open = not self.inventory.inventory_open
                        if not self.inventory.inventory_open:
                            self.inventory._clear_inventory_selection()
                        continue
                    if ev.key == pygame.K_F5:
                        self.inventory.inventory_open = False
                        self.inventory._clear_inventory_selection()
                        self.debug_menu()
                        continue
                    if self.inventory.inventory_open:
                        if ev.key == pygame.K_ESCAPE:
                            self.inventory.inventory_open = False
                            self.inventory._clear_inventory_selection()
                        continue
                    used_consumable = False
                    for idx, keycode in enumerate(self.inventory.consumable_hotkeys):
                        if ev.key == keycode:
                            self.inventory.consume_slot(idx)
                            used_consumable = True
                            break
                    if used_consumable:
                        continue
                    if ev.key == pygame.K_ESCAPE:
                        # open pause menu instead of quitting
                        self.menu.pause_menu()
                    # Developer cheats
                    elif ev.key == pygame.K_F1:
                        # toggle god mode
                        self.player.god = not getattr(self.player, 'god', False)
                    elif ev.key == pygame.K_F2:
                        # refill consumables
                        self.inventory.add_all_consumables()
                    elif ev.key == pygame.K_F3:
                        # toggle enemy vision rays
                        self.debug_enemy_rays = not self.debug_enemy_rays
                    elif ev.key == pygame.K_F4:
                        # toggle enemy nametags
                        self.debug_enemy_nametags = not self.debug_enemy_nametags
                    elif ev.key == pygame.K_F5:
                        # open debugger menu
                        self.debug_menu()
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

            if not self.inventory.inventory_open:
                self.update()
            self.draw()
            pygame.display.flip()


    def debug_menu(self):
        self.inventory.inventory_open = False
        self.inventory._clear_inventory_selection()
        options = [
            {'label': "God Mode (F1)", 'type': 'toggle',
             'getter': lambda: getattr(self.player, 'god', False),
             'setter': lambda v: setattr(self.player, 'god', v)},
            {'label': "Refill Consumables (F2)", 'type': 'action',
             'action': self.inventory.add_all_consumables},
            {'label': "Enemy Vision Rays (F3)", 'type': 'toggle',
             'getter': lambda: self.debug_enemy_rays,
             'setter': lambda v: setattr(self, 'debug_enemy_rays', v)},
            {'label': "Enemy Nametags (F4)", 'type': 'toggle',
             'getter': lambda: self.debug_enemy_nametags,
             'setter': lambda v: setattr(self, 'debug_enemy_nametags', v)},
            {'label': "Infinite Mana", 'type': 'toggle',
             'getter': lambda: self.cheat_infinite_mana,
             'setter': lambda v: setattr(self, 'cheat_infinite_mana', v)},
            {'label': "Zero Cooldown", 'type': 'toggle',
             'getter': lambda: self.cheat_zero_cooldown,
             'setter': lambda v: setattr(self, 'cheat_zero_cooldown', v)},
            {'label': "Teleport to Level...", 'type': 'action',
             'action': self.debug_teleport_menu},
            {'label': "Refill Consumables", 'type': 'action',
             'action': self.inventory.add_all_consumables},
            {'label': "Give Items...", 'type': 'action',
             'action': self.debug_item_menu},
            {'label': "Close", 'type': 'action',
             'action': None, 'close': True},
        ]
        self._run_debug_option_menu(options, title="Debugger")

    def debug_item_menu(self):
        self.inventory.inventory_open = False
        self.inventory._clear_inventory_selection()
        options = []
        for key, item in self.inventory.consumable_catalog.items():
            options.append({
                'label': f"Add {item.name}",
                'type': 'action',
                'action': (lambda k=key: self.inventory.add_consumable(k, 1))
            })
        for key, item in self.inventory.armament_catalog.items():
            options.append({
                'label': f"Equip {item.name}",
                'type': 'action',
                'action': (lambda k=key: self.inventory._force_equip_armament(k))
            })
        options.append({'label': "Back", 'type': 'action', 'action': None, 'close': True})
        self._run_debug_option_menu(options, title="Item Spawner")

    def _draw_debug_overlay(self, options, selected, title="Debugger", offset=0, visible=9):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(WIDTH//2 - 220, HEIGHT//2 - 200, 440, 360)
        pygame.draw.rect(self.screen, (32, 30, 42), panel, border_radius=12)
        pygame.draw.rect(self.screen, (210, 200, 170), panel, width=2, border_radius=12)
        draw_text(self.screen, title, (panel.x + 24, panel.y + 16), (240,220,190), size=28, bold=True)
        info = "Arrows = Navigate | Enter = Toggle | Esc/F5 = Close"
        draw_text(self.screen, info, (panel.x + 24, panel.bottom - 32), (180,180,200), size=16)
        line_h = 34
        visible = max(1, visible)
        subset = options[offset:offset+visible]
        for i, opt in enumerate(subset):
            row = pygame.Rect(panel.x + 24, panel.y + 64 + i * line_h, panel.width - 48, 30)
            bg_col = (70, 70, 90) if (offset + i) == selected else (50, 50, 68)
            pygame.draw.rect(self.screen, bg_col, row, border_radius=8)
            text = opt['label']
            if opt['type'] == 'toggle':
                text = f"{text}: {'ON' if opt['getter']() else 'OFF'}"
            elif opt['type'] == 'action' and not opt.get('close'):
                text = f"{text}"
            draw_text(self.screen, text, (row.x + 12, row.y + 8), (220,220,230), size=18)

    def _run_debug_option_menu(self, options, title="Debugger"):
        idx = 0
        offset = 0
        visible = min(9, len(options)) or 1
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
            if idx < offset:
                offset = idx
            elif idx >= offset + visible:
                offset = idx - visible + 1
            self.draw()
            self._draw_debug_overlay(options, idx, title=title, offset=offset, visible=visible)
            pygame.display.flip()

    def debug_teleport_menu(self):
        idx = self.level_index
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_F5):
                        return
                    elif ev.key == pygame.K_LEFT:
                        idx = (idx - 1) % ROOM_COUNT
                    elif ev.key == pygame.K_RIGHT:
                        idx = (idx + 1) % ROOM_COUNT
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        self.goto_room(idx)
                        return
            self.draw()
            self._draw_level_select_overlay(idx)
            pygame.display.flip()

    def _draw_level_select_overlay(self, idx):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 200)
        pygame.draw.rect(self.screen, (30, 28, 42), panel, border_radius=12)
        pygame.draw.rect(self.screen, (210, 200, 170), panel, width=2, border_radius=12)
        draw_text(self.screen, "Teleport to Level", (panel.x + 24, panel.y + 16), (240,220,190), size=26, bold=True)
        info = "Left/Right choose, Enter confirm, Esc to cancel"
        draw_text(self.screen, info, (panel.x + 24, panel.bottom - 36), (180,180,200), size=16)
        draw_text(self.screen, f"Room {idx+1}/{ROOM_COUNT}", (panel.centerx - 80, panel.centery - 10), (220,220,240), size=32, bold=True)


if __name__ == '__main__':
    Game().run()
