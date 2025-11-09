import pygame
import random
from config import WIDTH, HEIGHT, FPS, WHITE
from ..core.utils import draw_text, get_font
from .items import Consumable, HealConsumable, ManaConsumable, SpeedConsumable, JumpBoostConsumable, StaminaBoostConsumable, build_armament_catalog, build_consumable_catalog
from ..entities.entities import floating, DamageNumber

from dataclasses import dataclass
from typing import Optional

@dataclass
class ConsumableStack:
    key: str
    count: int = 1

    def add(self, amount: int, max_stack: int) -> int:
        """Increase the stack count up to max_stack. Returns how many were added."""
        if amount <= 0:
            return 0
        space = max(0, max_stack - self.count)
        added = min(space, amount)
        self.count += added
        return added

    def consume_one(self) -> bool:
        if self.count <= 0:
            return False
        self.count -= 1
        return True

    def is_empty(self) -> bool:
        return self.count <= 0


class Inventory:
    UNEQUIP_GEAR_KEY = "__inventory_clear_gear__"
    UNEQUIP_CONSUMABLE_KEY = "__inventory_clear_consumable__"
    MAX_CONSUMABLE_SLOT_STACK = 20

    _UNEQUIP_CELL_INFO = {
        'gear': {
            'color': (60, 60, 80),
            'border': (200, 120, 120),
            'letter': "X",
            'title': "Unequip Armament",
            'subtitle': "Clears selected armament slot.",
        },
        'consumable': {
            'color': (60, 65, 90),
            'border': (200, 120, 160),
            'letter': "X",
            'title': "Unequip Consumable",
            'subtitle': "Clears selected consumable slot.",
        },
    }
    def __init__(self, game):
        self.game = game
        self.inventory_open = False
        self.inventory_selection = None
        self.inventory_stock_mode = 'gear'
        self.inventory_regions = []
        self.inventory_drag = None
        self.gear_slots: list[Optional[str]] = []
        self.consumable_slots = []
        self.armament_scroll_offset = 0
        self.consumable_scroll_offset = 0
        self.consumable_storage: dict[str, int] = {}
        
        # Initialize inventory-related attributes
        self.consumable_hotkeys = [pygame.K_4, pygame.K_5, pygame.K_6]
        self.armament_catalog = build_armament_catalog()
        self.armament_order = list(self.armament_catalog.keys())
        self.consumable_catalog = build_consumable_catalog()
        self.consumable_order: list[str] = []

    def _refresh_inventory_defaults(self):
        consumable_defaults = {
            'Knight': ['health', 'stamina', 'mana'],
            'Ranger': ['health', 'skyroot', 'speed'],
            'Wizard': ['mana', 'skyroot', 'stamina'],
        }
        cls = getattr(self.game.player, 'cls', 'Knight')
        available_armaments = self.armament_order[:]
        random.shuffle(available_armaments)
        self.gear_slots = available_armaments[:3] + [None] * max(0, 3 - len(available_armaments[:3]))
        
        self.consumable_order = []
        self.consumable_storage.clear()
        keys = consumable_defaults.get(cls, ['health', 'mana', None])
        slots = []
        for i in range(len(self.consumable_hotkeys)):
            key_id = keys[i] if i < len(keys) else None
            if key_id:
                # Create stack directly without discovery to avoid duplicates
                stack = ConsumableStack(key=key_id, count=1)
                # Add to order list for starting items
                if key_id not in self.consumable_order:
                    self.consumable_order.append(key_id)
                slots.append(stack)
            else:
                slots.append(None)
        self.consumable_slots = slots
        self.inventory_open = False
        self.inventory_selection = None
        self.inventory_stock_mode = 'gear' # Reset to default
        self.recalculate_player_stats()

    def _register_inventory_region(self, rect, kind, **data):
        info = {'rect': rect.copy(), 'kind': kind}
        info.update(data)
        self.inventory_regions.append(info)

    def _clear_inventory_selection(self):
        self.inventory_selection = None
        self.inventory_stock_mode = None
        self.inventory_drag = None

    def _inventory_hit_test(self, pos):
        for info in reversed(self.inventory_regions):
            if info['rect'].collidepoint(pos):
                return info
        return None

    def _find_gear_slot_with_key(self, key):
        for idx, slot_key in enumerate(self.gear_slots):
            if slot_key == key:
                return idx
        return None

    def _start_inventory_drag(self, pos):
        if not self.inventory_open:
            return
        info = self._inventory_hit_test(pos)
        if not info:
            return
        if info['kind'] == 'gear_slot':
            idx = info.get('index', -1)
            if 0 <= idx < len(self.gear_slots):
                key = self.gear_slots[idx]
                if key:
                    self.inventory_drag = {'kind': 'gear', 'index': idx, 'key': key}
        elif info['kind'] == 'consumable_slot':
            idx = info.get('index', -1)
            if 0 <= idx < len(self.consumable_slots):
                stack = self.consumable_slots[idx]
                if stack:
                    self.inventory_drag = {'kind': 'consumable', 'index': idx, 'key': stack.key}

    def _finish_inventory_drag(self, pos):
        drag = self.inventory_drag
        if not drag:
            return
        self.inventory_drag = None
        info = self._inventory_hit_test(pos)
        if not info:
            return
        if drag['kind'] == 'gear' and info['kind'] == 'gear_slot':
            idx = info.get('index', -1)
            if 0 <= idx < len(self.gear_slots) and idx != drag['index']:
                self._swap_gear_slots(drag['index'], idx)
                self.inventory_selection = {'kind': 'gear_slot', 'index': idx}
                self.inventory_stock_mode = 'gear'
        elif drag['kind'] == 'consumable' and info['kind'] == 'consumable_slot':
            idx = info.get('index', -1)
            if 0 <= idx < len(self.consumable_slots) and idx != drag['index']:
                self._swap_consumable_slots(drag['index'], idx)
                self.inventory_selection = {'kind': 'consumable_slot', 'index': idx}
                self.inventory_stock_mode = 'consumable'

    def _handle_inventory_click(self, pos):
        if not self.inventory_open:
            return
        hit = self._inventory_hit_test(pos)
        if not hit:
            return
        kind = hit['kind']
        sel = self.inventory_selection

        scroll_amount = 50 # Pixels to scroll per click
        
        if kind == 'scroll_up' or kind == 'scroll_down':
            mode = hit.get('mode')
            stock_rect = hit.get('stock_rect')
            grid_start_y = hit.get('grid_start_y')
            grid_padding = hit.get('grid_padding', 10)
            slot_size = hit.get('slot_size', 56)
            slot_spacing = hit.get('slot_spacing', 12)
            cols = hit.get('cols')
            if not cols:
                usable_width = max(1, stock_rect.width - grid_padding * 2)
                cols = max(1, (usable_width + slot_spacing) // (slot_size + slot_spacing))
            row_height = slot_size + slot_spacing

            viewport_height = stock_rect.height - grid_start_y

            total_content_height = 0
            if mode == 'gear':
                num_rows = (len(self.armament_order) + cols - 1) // cols
                total_content_height = num_rows * row_height
            elif mode == 'consumable':
                num_rows = (len(self.consumable_order) + cols - 1) // cols
                total_content_height = num_rows * row_height

            if kind == 'scroll_up':
                if mode == 'gear':
                    self.armament_scroll_offset = max(0, self.armament_scroll_offset - scroll_amount)
                elif mode == 'consumable':
                    self.consumable_scroll_offset = max(0, self.consumable_scroll_offset - scroll_amount)
            elif kind == 'scroll_down':
                if mode == 'gear':
                    max_scroll = max(0, total_content_height - viewport_height)
                    self.armament_scroll_offset = min(max_scroll, self.armament_scroll_offset + scroll_amount)
                elif mode == 'consumable':
                    max_scroll = max(0, total_content_height - viewport_height)
                    self.consumable_scroll_offset = min(max_scroll, self.consumable_scroll_offset + scroll_amount)
            return

        if kind == 'gear_slot':
            idx = hit['index']
            self.inventory_stock_mode = 'gear' # Set mode when gear slot is clicked
            if sel and sel.get('kind') == 'gear_slot':
                if sel['index'] == idx:
                    self._clear_inventory_selection()
                else:
                    self.inventory_selection = {'kind': 'gear_slot', 'index': idx}
            elif sel and sel.get('kind') == 'gear_pool':
                self._equip_armament(idx, sel['key'])
                self.inventory_selection = {'kind': 'gear_slot', 'index': idx}
            else:
                self.inventory_selection = {'kind': 'gear_slot', 'index': idx}
        elif kind == 'gear_pool':
            key = hit['key']
            if key == self.UNEQUIP_GEAR_KEY:
                if sel and sel.get('kind') == 'gear_slot':
                    idx = sel.get('index', -1)
                    if 0 <= idx < len(self.gear_slots):
                        if self.gear_slots[idx] is not None:
                            self.gear_slots[idx] = None
                            self.recalculate_player_stats()
                return
            if sel and sel.get('kind') == 'gear_slot':
                self._equip_armament(sel['index'], key)
                self.inventory_selection = {'kind': 'gear_slot', 'index': sel['index']}
            elif sel and sel.get('kind') == 'gear_pool' and sel['key'] == key:
                self._clear_inventory_selection()
            else:
                self.inventory_selection = {'kind': 'gear_pool', 'key': key}
        elif kind == 'consumable_pool':
            key = hit['key']
            if key == self.UNEQUIP_CONSUMABLE_KEY:
                if sel and sel.get('kind') == 'consumable_slot':
                    idx = sel.get('index', -1)
                    if 0 <= idx < len(self.consumable_slots):
                        if self.consumable_slots[idx]:
                            self._unequip_consumable_slot(idx)
                return
            if sel and sel.get('kind') == 'consumable_slot':
                self._equip_consumable(sel['index'], key)
                self.inventory_selection = {'kind': 'consumable_slot', 'index': sel['index']}
            elif sel and sel.get('kind') == 'consumable_pool' and sel['key'] == key:
                self._clear_inventory_selection()
            else:
                self.inventory_selection = {'kind': 'consumable_pool', 'key': key}
        elif kind == 'consumable_slot':
            idx = hit['index']
            self.inventory_stock_mode = 'consumable' # Set mode when consumable slot is clicked
            if sel and sel.get('kind') == 'consumable_slot':
                if sel['index'] == idx:
                    self._clear_inventory_selection()
                else:
                    self.inventory_selection = {'kind': 'consumable_slot', 'index': idx}
            elif sel and sel.get('kind') == 'consumable_pool':
                self._equip_consumable(idx, sel['key'])
                self.inventory_selection = {'kind': 'consumable_slot', 'index': idx}
            else:
                self.inventory_selection = {'kind': 'consumable_slot', 'index': idx}
        elif kind == 'unequip_armament':
            # Unequip selected armament slot
            if sel and sel.get('kind') == 'gear_slot':
                idx = sel.get('index', -1)
                if 0 <= idx < len(self.gear_slots):
                    self.gear_slots[idx] = None
                    self.recalculate_player_stats()
                    self._clear_inventory_selection()
        elif kind == 'unequip_armament_stock':
            # Unequip selected armament from stock
            if sel and sel.get('kind') == 'gear_pool':
                key = sel.get('key')
                if key:
                    # Find and remove from gear slots
                    for i, slot_key in enumerate(self.gear_slots):
                        if slot_key == key:
                            self.gear_slots[i] = None
                            self.recalculate_player_stats()
                            self._clear_inventory_selection()
                            break
        elif kind == 'unequip_consumable':
            # Unequip selected consumable slot
            if sel and sel.get('kind') == 'consumable_slot':
                idx = sel.get('index', -1)
                if 0 <= idx < len(self.consumable_slots):
                    self._unequip_consumable_slot(idx)
                    self._clear_inventory_selection()
        elif kind == 'unequip_consumable_stock':
            # Unequip selected consumable from stock
            if sel and sel.get('kind') == 'consumable_pool':
                key = sel.get('key')
                if key:
                    # Find and remove from consumable slots
                    for i, stack in enumerate(self.consumable_slots):
                        if stack and stack.key == key:
                            self._unequip_consumable_slot(i)
                            self._clear_inventory_selection()
                            break

    def _format_modifier_lines(self, modifiers):
        if not modifiers:
            return []
        lines = []
        for stat, value in modifiers.items():
            if not value:
                continue
            if stat == 'max_hp':
                lines.append(f"+{value:+.0f} Max HP")
            elif stat == 'attack_damage':
                lines.append(f"+{value:+.0f} Attack")
            elif stat == 'max_mana':
                lines.append(f"+{value:+.0f} Max Mana")
            elif stat == 'max_stamina':
                lines.append(f"+{value:+.0f} Max Stamina")
            elif stat == 'player_speed':
                lines.append(f"+{value:+.2f} Ground Speed")
            elif stat == 'player_air_speed':
                lines.append(f"+{value:+.2f} Air Speed")
            elif stat == 'mana_regen':
                lines.append(f"+{value*FPS:+.2f} Mana / s")
            elif stat == 'stamina_regen':
                lines.append(f"+{value*FPS:+.2f} Stamina / s")
        return lines

    def _tooltip_payload(self, info):
        if not info:
            return None
        payload = {'lines': [], 'color': None, 'letter': ""}
        kind = info['kind']
        if kind in ('gear_slot', 'gear_pool'):
            key = info.get('key')
            if key is None and kind == 'gear_slot':
                idx = info.get('index', -1)
                key = self.gear_slots[idx] if 0 <= idx < len(self.gear_slots) else None
            if key == self.UNEQUIP_GEAR_KEY:
                cell_info = self._UNEQUIP_CELL_INFO['gear']
                payload['lines'] = [cell_info['title'], cell_info['subtitle']]
                payload['color'] = cell_info['border']
                payload['letter'] = cell_info['letter']
                return payload
            if not key:
                payload['lines'] = ["Empty Armament Slot"]
                return payload
            item = self.armament_catalog.get(key)
            if not item:
                payload['lines'] = ["Unknown Armament"]
                return payload
            lines = item.tooltip_lines()
            lines.extend(self._format_modifier_lines(item.modifiers))
            payload['lines'] = lines
            payload['color'] = item.color
            payload['letter'] = item.icon_letter
            return payload
        if kind in ('consumable_slot', 'consumable_pool'):
            if kind == 'consumable_slot':
                idx = info.get('index', -1)
                if idx < 0 or idx >= len(self.consumable_slots):
                    return payload
                stack = self.consumable_slots[idx]
                if not stack:
                    payload['lines'] = ["Empty Consumable Slot"]
                    return payload
                key = stack.key
                stack_count = stack.count
            else:
                key = info.get('key')
                stack_count = None
            if key == self.UNEQUIP_CONSUMABLE_KEY:
                cell_info = self._UNEQUIP_CELL_INFO['consumable']
                payload['lines'] = [cell_info['title'], cell_info['subtitle']]
                payload['color'] = cell_info['border']
                payload['letter'] = cell_info['letter']
                return payload
            entry = self.consumable_catalog.get(key) if key else None
            if not entry:
                payload['lines'] = ["Unknown Consumable"]
                return payload
            lines = entry.tooltip_lines()
            if stack_count is not None:
                lines.append(f"Stack: {stack_count}")
            storage_count = self._storage_count(key)
            if storage_count > 0:
                lines.append(f"Storage: {storage_count}")
            payload['lines'] = lines
            payload['color'] = entry.color
            payload['letter'] = entry.icon_letter
            return payload
        return payload

    def _draw_inventory_tooltip(self, hover_info):
        if not hover_info:
            return
        payload = self._tooltip_payload(hover_info)
        if not payload:
            return
        lines = payload.get('lines', [])
        if not lines:
            return
        font = get_font(16)
        icon_space = 0
        if payload.get('color'):
            icon_space = 34
        width = max(font.size(line)[0] for line in lines) + 20 + icon_space
        height = len(lines) * 22 + 12
        mx, my = pygame.mouse.get_pos()
        tooltip_rect = pygame.Rect(mx + 18, my + 18, width, height)
        if tooltip_rect.right > WIDTH - 8:
            tooltip_rect.x = WIDTH - width - 8
        if tooltip_rect.bottom > HEIGHT - 8:
            tooltip_rect.y = HEIGHT - height - 8
        pygame.draw.rect(self.game.screen, (28, 28, 38), tooltip_rect, border_radius=8)
        pygame.draw.rect(self.game.screen, (180, 170, 200), tooltip_rect, width=1, border_radius=8)
        text_x = tooltip_rect.x + 10
        if icon_space:
            icon_rect = pygame.Rect(tooltip_rect.x + 10, tooltip_rect.y + 10, 24, 24)
            pygame.draw.rect(self.game.screen, payload['color'], icon_rect, border_radius=6)
            if payload.get('letter'):
                icon_font = get_font(14, bold=True)
                icon_surf = icon_font.render(payload['letter'], True, (10,10,20))
                self.game.screen.blit(icon_surf, icon_surf.get_rect(center=icon_rect.center))
            text_x += icon_space
        for i, line in enumerate(lines):
            self.game.screen.blit(font.render(line, True, (230, 230, 245)),
                             (text_x, tooltip_rect.y + 6 + i * 22))

    def _draw_unequip_stock_cell(self, surface, rect, mode, icon_font, highlighted):
        info = self._UNEQUIP_CELL_INFO.get(mode)
        if not info:
            return
        pygame.draw.rect(surface, info['color'], rect, border_radius=8)
        border_col = info['border'] if highlighted else (150, 150, 170)
        pygame.draw.rect(surface, border_col, rect, width=2, border_radius=8)
        icon_surface = icon_font.render(info['letter'], True, (225, 225, 235))
        surface.blit(icon_surface, icon_surface.get_rect(center=rect.center))

    def _draw_stock_panel(self, rect, mode, selection):
        pygame.draw.rect(self.game.screen, (32, 30, 48), rect, border_radius=12)
        pygame.draw.rect(self.game.screen, (210, 200, 170), rect, width=1, border_radius=12)
        title = "Armory Stock" if mode == 'gear' else "Consumable Stock"
        title_font = get_font(18, bold=True)
        self.game.screen.blit(title_font.render(title, True, (235, 210, 190)), (rect.x + 16, rect.y + 12))
        subtext = "Select slot, then pick stock item."
        info_font = get_font(14)
        self.game.screen.blit(info_font.render(subtext, True, (180, 180, 200)), (rect.x + 16, rect.y + 36))
        close_label = "Close Armory" if mode == 'gear' else "Close Consumables"
        close_rect = pygame.Rect(rect.x + 16, rect.bottom - 40, 140, 26)
        pygame.draw.rect(self.game.screen, (60, 60, 80), close_rect, border_radius=6)
        pygame.draw.rect(self.game.screen, (200, 180, 150), close_rect, width=1, border_radius=6)
        self.game.screen.blit(info_font.render(close_label, True, (230, 230, 240)),
                         (close_rect.x + 10, close_rect.y + 4))
        self._register_inventory_region(close_rect, 'stock_close', mode=mode)
        grid_top = rect.y + 64
        cell_size = 56
        spacing = 12
        cols = 2
        icon_font = get_font(18, bold=True)
        count_font = get_font(16, bold=True)
        selection_key = None
        if selection and selection.get('kind') in (f"{mode}_pool", f"{mode}_slot"):
            selection_key = selection.get('key')
            if selection_key is None and selection.get('kind') == f"{mode}_slot":
                idx = selection.get('index', -1)
                if mode == 'gear' and 0 <= idx < len(self.gear_slots):
                    selection_key = self.gear_slots[idx]
                elif mode == 'consumable' and 0 <= idx < len(self.consumable_slots):
                    stack = self.consumable_slots[idx]
                    selection_key = stack.key if stack else None
        if mode == 'gear':
            keys = [*self.armament_order, self.UNEQUIP_GEAR_KEY]
        else:
            consumable_keys = [k for k in self.consumable_order if self._has_consumable_anywhere(k)]
            keys = [*consumable_keys, self.UNEQUIP_CONSUMABLE_KEY]
        for i, key in enumerate(keys):
            row = i // cols
            col = i % cols
            cell = pygame.Rect(
                rect.x + 16 + col * (cell_size + spacing),
                grid_top + row * (cell_size + spacing),
                cell_size,
                cell_size,
            )
            entry = self.armament_catalog.get(key) if mode == 'gear' else self.consumable_catalog.get(key)
            if mode == 'gear' and key == self.UNEQUIP_GEAR_KEY:
                highlighted = selection_key == key
                self._draw_unequip_stock_cell(self.game.screen, cell, 'gear', icon_font, highlighted)
            elif mode == 'consumable' and key == self.UNEQUIP_CONSUMABLE_KEY:
                highlighted = selection_key == key
                self._draw_unequip_stock_cell(self.game.screen, cell, 'consumable', icon_font, highlighted)
            else:
                if not entry:
                    continue
                pygame.draw.rect(self.game.screen, entry.color, cell, border_radius=8)
                border_col = (255, 210, 120) if selection_key == key else (160, 160, 190)
                pygame.draw.rect(self.game.screen, border_col, cell, width=2, border_radius=8)
                if mode == 'gear' and key in self.gear_slots:
                    pygame.draw.rect(self.game.screen, (120, 230, 180), cell.inflate(6, 6), width=2, border_radius=10)
                if mode == 'consumable':
                    equipped = self._total_equipped_count(key)
                    if equipped > 0:
                        pygame.draw.rect(self.game.screen, (120, 230, 180), cell.inflate(6, 6), width=2, border_radius=10)
                    total = self._total_available_count(key)
                    if total > 0:
                        count_surface = count_font.render(str(total), True, (250, 250, 255))
                        count_rect = count_surface.get_rect(bottomright=(cell.right - 4, cell.bottom - 4))
                        self.game.screen.blit(count_surface, count_rect)
                icon_surface = icon_font.render(entry.icon_letter, True, (20, 20, 28))
                self.game.screen.blit(icon_surface, icon_surface.get_rect(center=cell.center))
            region_kind = 'gear_pool' if mode == 'gear' else 'consumable_pool'
            self._register_inventory_region(cell, region_kind, key=key)
        


    def draw_inventory_overlay(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.game.screen.blit(overlay, (0, 0))

        # Calculate panel size to fit within screen with margins
        margin = 40
        max_panel_w = WIDTH - (margin * 2)
        max_panel_h = HEIGHT - (margin * 2)
        
        # Use responsive sizing that fits within screen - made smaller and moved down
        panel_w = min(800, max_panel_w)  # Reduced from 900
        panel_h = min(600, max_panel_h)  # Reduced from 680
        panel_rect = pygame.Rect(
            (WIDTH - panel_w) // 2,
            (HEIGHT - panel_h) // 2 + 20,  # Moved down by 20 pixels
            panel_w,
            panel_h,
        )
        
        panel_bg = (30, 28, 40)
        panel_border = (210, 200, 170)
        pygame.draw.rect(self.game.screen, panel_bg, panel_rect, border_radius=12)
        pygame.draw.rect(self.game.screen, panel_border, panel_rect, width=2, border_radius=12)
        self.inventory_regions = []
        selection = self.inventory_selection

        draw_text(self.game.screen, "Inventory", (panel_rect.x + 32, panel_rect.y + 20), (240,220,190), size=30, bold=True)
        footer_font = get_font(18)
        footer_surface = footer_font.render("Press I or Esc to close", True, (180,180,195))
        footer_rect = footer_surface.get_rect(midbottom=(panel_rect.centerx, panel_rect.bottom - 18))
        self.game.screen.blit(footer_surface, footer_rect)

        # Define main panes
        left_pane_width = 280
        right_pane_width = panel_w - left_pane_width - 60 # 60 for spacing
        left_pane_rect = pygame.Rect(panel_rect.x + 20, panel_rect.y + 70, left_pane_width, panel_h - 100)
        right_pane_rect = pygame.Rect(left_pane_rect.right + 20, panel_rect.y + 70, right_pane_width, panel_h - 100)

        # --- Left Pane: Player Info ---
        pygame.draw.rect(self.game.screen, (25, 25, 35), left_pane_rect, border_radius=10) # Outline for left pane
        pygame.draw.rect(self.game.screen, (100, 100, 120), left_pane_rect, width=1, border_radius=10)

        model_frame = pygame.Rect(left_pane_rect.x + 20, left_pane_rect.y + 20, left_pane_width - 40, 232)
        pygame.draw.rect(self.game.screen, (32, 36, 52), model_frame, border_radius=16)
        pygame.draw.rect(self.game.screen, (160, 180, 220), model_frame, width=1, border_radius=16)
        
        model_rect = pygame.Rect(0, 0, self.game.player.rect.width * 4, self.game.player.rect.height * 4)
        model_rect.center = model_frame.center
        pygame.draw.rect(self.game.screen, (120, 200, 235), model_rect, border_radius=12)
        
        draw_text(self.game.screen, self.game.player.cls, (model_frame.centerx - 40, model_frame.bottom - 30), (210,210,225), size=22, bold=True)

        stats_y = model_frame.bottom + 25  # Reduced spacing from 30 to 25
        status_lines = [
            f"HP: {self.game.player.hp}/{self.game.player.max_hp}",
            f"Attack: {getattr(self.game.player, 'attack_damage', '?')}",
        ]
        if hasattr(self.game.player, 'mana') and hasattr(self.game.player, 'max_mana'):
            status_lines.append(f"Mana: {self.game.player.mana:.1f}/{self.game.player.max_mana:.1f}")
        if hasattr(self.game.player, 'stamina') and hasattr(self.game.player, 'max_stamina'):
            status_lines.append(f"Stamina: {self.game.player.stamina:.1f}/{self.game.player.max_stamina:.1f}")
        
        status_spacing = 20  # Reduced spacing from 24 to 20
        
        for i, line in enumerate(status_lines):
            draw_text(self.game.screen, line, (left_pane_rect.x + 20, stats_y + i * status_spacing), (210,210,225), size=18)

        # --- Right Pane: Equipped Slots and Stock ---
        pygame.draw.rect(self.game.screen, (25, 25, 35), right_pane_rect, border_radius=10) # Outline for right pane
        pygame.draw.rect(self.game.screen, (100, 100, 120), right_pane_rect, width=1, border_radius=10)

        slot_w, slot_h = 56, 56
        slot_spacing = 12
        icon_font = get_font(18, bold=True)

        # Equipped Slots section header
        equipped_slots_x_start = right_pane_rect.x + 20
        consumable_slots_x_start = equipped_slots_x_start + 3 * (slot_w + slot_spacing) + 30 # Extra space between groups
        label_y = right_pane_rect.y + 20
        label_color = (205, 200, 215)
        draw_text(self.game.screen, "Armaments", (equipped_slots_x_start, label_y), label_color, size=16, bold=True)
        draw_text(self.game.screen, "Consumables", (consumable_slots_x_start, label_y), label_color, size=16, bold=True)
        equipped_slots_y = label_y + 26

        # Armament Slots
        for idx in range(3):
            rect = pygame.Rect(equipped_slots_x_start + idx * (slot_w + slot_spacing), equipped_slots_y, slot_w, slot_h)
            self._register_inventory_region(rect, 'gear_slot', index=idx)
            
            item_key = self.gear_slots[idx] if idx < len(self.gear_slots) else None
            item = self.armament_catalog.get(item_key) if item_key else None
            
            pygame.draw.rect(self.game.screen, (46, 52, 72), rect, border_radius=8)
            border_color = (110, 120, 150)
            if selection and selection.get('kind') == 'gear_slot' and selection.get('index') == idx:
                border_color = (255, 210, 120)
            
            if item:
                pygame.draw.rect(self.game.screen, item.color, rect.inflate(-8, -8), border_radius=6)
                icon_surf = icon_font.render(item.icon_letter, True, (20,20,28))
                self.game.screen.blit(icon_surf, icon_surf.get_rect(center=rect.center))
            else:
                 draw_text(self.game.screen, str(idx+1), (rect.centerx-4, rect.centery-8), (80,90,110), size=18)
            pygame.draw.rect(self.game.screen, border_color, rect, width=2, border_radius=8)



        # Consumable Slots (next to armament slots)
        for idx in range(len(self.consumable_slots)):
            rect = pygame.Rect(consumable_slots_x_start + idx * (slot_w + slot_spacing), equipped_slots_y, slot_w, slot_h)
            self._register_inventory_region(rect, 'consumable_slot', index=idx)
            
            stack = self.consumable_slots[idx]
            entry = self.consumable_catalog.get(stack.key) if stack else None

            pygame.draw.rect(self.game.screen, (46, 52, 72), rect, border_radius=8)
            border_color = (110, 120, 150)
            if selection and selection.get('kind') == 'consumable_slot' and selection.get('index') == idx:
                border_color = (255, 210, 120)

            if entry:
                pygame.draw.rect(self.game.screen, entry.color, rect.inflate(-8, -8), border_radius=6)
                icon_surf = icon_font.render(entry.icon_letter, True, (20,20,28))
                self.game.screen.blit(icon_surf, icon_surf.get_rect(center=rect.center))
                if stack:
                    total_count = self._total_available_count(stack.key)
                    if total_count > 1:
                        count_font = get_font(16, bold=True)
                        count_surf = count_font.render(str(total_count), True, (250, 250, 255))
                        self.game.screen.blit(count_surf, count_surf.get_rect(bottomright=(rect.right - 4, rect.bottom - 4)))
            else:
                key_label = self._hotkey_label(idx)
                draw_text(self.game.screen, key_label, (rect.centerx-4, rect.centery-8), (80,90,110), size=18)
            pygame.draw.rect(self.game.screen, border_color, rect, width=2, border_radius=8)



        # Stock Panels (Scrollable)
        stock_panel_y = equipped_slots_y + slot_h + 30
        stock_panel_height = right_pane_rect.bottom - stock_panel_y - 20
        stock_panel_rect = pygame.Rect(right_pane_rect.x + 20, stock_panel_y, right_pane_width - 40, stock_panel_height)
        
        pygame.draw.rect(self.game.screen, (35, 30, 45), stock_panel_rect, border_radius=10) # Outline for stock area
        pygame.draw.rect(self.game.screen, (100, 100, 120), stock_panel_rect, width=1, border_radius=10)

        # Clipping surface for scrolling
        stock_surface = pygame.Surface(stock_panel_rect.size, pygame.SRCALPHA)
        stock_surface.fill((0,0,0,0)) # Transparent background

        grid_padding = 10
        count_font = get_font(16, bold=True)

        current_scroll_offset = 0
        if self.inventory_stock_mode == 'gear':
            # Show all gear in armament order (including duplicates)
            available_gear = list(self.armament_order)
            keys_to_draw = [*available_gear, self.UNEQUIP_GEAR_KEY]
            current_scroll_offset = self.armament_scroll_offset
            draw_text(stock_surface, "Armory Stock", (10, 10), (210, 200, 170), size=18)
        elif self.inventory_stock_mode == 'consumable':
            # Only show consumables that have additional stock available beyond what's equipped
            available_consumables = []
            for key in self.consumable_order:
                # Check if this consumable is already equipped
                equipped_count = sum(1 for s in self.consumable_slots if s and s.key == key)
                storage_count = self._storage_count(key)
                # Only show if there's storage stock available (beyond what's equipped)
                if storage_count > 0:
                    available_consumables.append(key)
            keys_to_draw = [*available_consumables, self.UNEQUIP_CONSUMABLE_KEY]
            current_scroll_offset = self.consumable_scroll_offset
            draw_text(stock_surface, "Consumable Stock", (10, 10), (210, 200, 170), size=18)
        else:
            keys_to_draw = [] # Should not happen with default 'gear'

        grid_start_y_in_surface = 40 # Offset for title
        available_grid_width = max(1, stock_panel_rect.width - grid_padding * 2)
        cols = max(1, (available_grid_width + slot_spacing) // (slot_w + slot_spacing))
        
        total_content_height = 0
        if keys_to_draw:
            num_rows = (len(keys_to_draw) + cols - 1) // cols
            total_content_height = num_rows * (slot_w + slot_spacing)

        # Draw items onto the stock_surface
        y_offset_in_surface = grid_start_y_in_surface - current_scroll_offset
        
        for i, key in enumerate(keys_to_draw):
            row = i // cols
            col = i % cols
            
            cell_x = col * (slot_w + slot_spacing) + grid_padding
            cell_y = y_offset_in_surface + row * (slot_w + slot_spacing)
            
            cell = pygame.Rect(cell_x, cell_y, slot_w, slot_w)
            
            # Only draw if visible within the stock_surface
            if cell.bottom > grid_start_y_in_surface and cell.top < stock_panel_rect.height:
                if self.inventory_stock_mode == 'gear':
                    self._register_inventory_region(cell.move(stock_panel_rect.topleft), 'gear_pool', key=key)
                    if key == self.UNEQUIP_GEAR_KEY:
                        highlighted = bool(selection and selection.get('kind') == 'gear_pool' and selection.get('key') == key)
                        self._draw_unequip_stock_cell(stock_surface, cell, 'gear', icon_font, highlighted)
                        continue
                    entry = self.armament_catalog.get(key)
                    if not entry:
                        continue
                    pygame.draw.rect(stock_surface, entry.color, cell, border_radius=8)
                    border_col = (160, 160, 190)
                    if selection and selection.get('kind') in ('gear_pool', 'gear_slot') and selection.get('key') == key:
                        border_col = (255, 210, 120)
                    # Show equipped items with green border
                    equipped_count = self.gear_slots.count(key)
                    if equipped_count > 0:
                        border_col = (120, 230, 180)
                    pygame.draw.rect(stock_surface, border_col, cell, width=2, border_radius=8)
                    icon_surface = icon_font.render(entry.icon_letter, True, (20, 20, 28))
                    stock_surface.blit(icon_surface, icon_surface.get_rect(center=cell.center))
                elif self.inventory_stock_mode == 'consumable':
                    self._register_inventory_region(cell.move(stock_panel_rect.topleft), 'consumable_pool', key=key)
                    if key == self.UNEQUIP_CONSUMABLE_KEY:
                        highlighted = bool(selection and selection.get('kind') == 'consumable_pool' and selection.get('key') == key)
                        self._draw_unequip_stock_cell(stock_surface, cell, 'consumable', icon_font, highlighted)
                        continue
                    entry = self.consumable_catalog.get(key)
                    if not entry:
                        continue
                    pygame.draw.rect(stock_surface, entry.color, cell, border_radius=8)
                    border_col = (160, 160, 190)
                    if selection and selection.get('kind') in ('consumable_pool', 'consumable_slot') and selection.get('key') == key:
                        border_col = (255, 210, 120)
                    elif any(s and s.key == key for s in self.consumable_slots):
                        border_col = (120, 230, 180)
                    pygame.draw.rect(stock_surface, border_col, cell, width=2, border_radius=8)
                    icon_surface = icon_font.render(entry.icon_letter, True, (20, 20, 28))
                    stock_surface.blit(icon_surface, icon_surface.get_rect(center=cell.center))
                    
                    # Display the count for consumables in stock
                    total_count = self._total_available_count(key)
                    if total_count > 0:
                        count_surface = count_font.render(str(total_count), True, (250, 250, 255))
                        count_rect = count_surface.get_rect(bottomright=(cell.right - 4, cell.bottom - 4))
                        stock_surface.blit(count_surface, count_rect)
        

        
        self.game.screen.blit(stock_surface, stock_panel_rect.topleft)

        # Scrollbar (simple up/down arrows)
        viewport_height = stock_panel_rect.height - grid_start_y_in_surface
        if total_content_height > viewport_height:
            scrollbar_width = 20
            scrollbar_height_area = stock_panel_rect.height - grid_start_y_in_surface - 10 # 10 for padding
            scrollbar_x = stock_panel_rect.right - scrollbar_width - 5
            scrollbar_y = stock_panel_rect.y + grid_start_y_in_surface + 5

            # Scrollbar background
            pygame.draw.rect(self.game.screen, (60, 60, 80), (scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_height_area), border_radius=5)

            # Up arrow
            up_arrow_rect = pygame.Rect(scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_width)
            pygame.draw.rect(self.game.screen, (90, 90, 110), up_arrow_rect, border_radius=3)
            draw_text(self.game.screen, "^", (up_arrow_rect.centerx - 5, up_arrow_rect.centery - 10), WHITE, size=18)
            self._register_inventory_region(
                up_arrow_rect,
                'scroll_up',
                mode=self.inventory_stock_mode,
                stock_rect=stock_panel_rect,
                grid_start_y=grid_start_y_in_surface,
                grid_padding=grid_padding,
                slot_size=slot_w,
                slot_spacing=slot_spacing,
                cols=cols,
            )

            # Down arrow
            down_arrow_rect = pygame.Rect(scrollbar_x, scrollbar_y + scrollbar_height_area - scrollbar_width, scrollbar_width, scrollbar_width)
            pygame.draw.rect(self.game.screen, (90, 90, 110), down_arrow_rect, border_radius=3)
            draw_text(self.game.screen, "v", (down_arrow_rect.centerx - 5, down_arrow_rect.centery - 10), WHITE, size=18)
            self._register_inventory_region(
                down_arrow_rect,
                'scroll_down',
                mode=self.inventory_stock_mode,
                stock_rect=stock_panel_rect,
                grid_start_y=grid_start_y_in_surface,
                grid_padding=grid_padding,
                slot_size=slot_w,
                slot_spacing=slot_spacing,
                cols=cols,
            )

            # Scroll thumb
            scroll_range = total_content_height - viewport_height
            if scroll_range > 0:
                viewable_ratio = viewport_height / total_content_height
                thumb_height = max(20, int(scrollbar_height_area * viewable_ratio))
                current_scroll_val = self.armament_scroll_offset if self.inventory_stock_mode == 'gear' else self.consumable_scroll_offset
                thumb_pos_ratio = current_scroll_val / scroll_range
                thumb_y = scrollbar_y + scrollbar_width + int((scrollbar_height_area - 2 * scrollbar_width - thumb_height) * thumb_pos_ratio)
                thumb_rect = pygame.Rect(scrollbar_x + 2, thumb_y, scrollbar_width - 4, thumb_height)
                pygame.draw.rect(self.game.screen, (150, 150, 170), thumb_rect, border_radius=3)


        # Tooltip
        hover_info = self._inventory_hit_test(pygame.mouse.get_pos())
        self._draw_inventory_tooltip(hover_info)

    def draw_consumable_hotbar(self):
        """Draw the consumable hotbar in the HUD."""
        if not self.consumable_slots:
            return
        slot_size = 46
        slot_area_height = slot_size + 18
        spacing = 12
        count = len(self.consumable_slots)
        total_w = slot_size * count + spacing * (count - 1)
        start_x = WIDTH - total_w - 20
        start_y = HEIGHT - slot_area_height - 24
        title_font = get_font(18, bold=True)
        title_surface = title_font.render("Consumables (4 / 5 / 6)", True, (215, 210, 220))
        self.game.screen.blit(title_surface, (start_x, start_y - 24))
        name_font = get_font(12)
        count_font = get_font(16, bold=True)
        for idx, stack in enumerate(self.consumable_slots):
            rect = pygame.Rect(start_x + idx * (slot_size + spacing), start_y, slot_size, slot_size)
            pygame.draw.rect(self.game.screen, (40, 40, 50), rect, border_radius=8)
            pygame.draw.rect(self.game.screen, (90, 90, 120), rect, width=2, border_radius=8)
            key_label = self._hotkey_label(idx)
            draw_text(self.game.screen, key_label, (rect.x + 4, rect.y + 4), (200, 200, 210), size=14, bold=True)
            inner = rect.inflate(-10, -10)
            entry = self.consumable_catalog.get(stack.key) if stack else None
            if entry:
                pygame.draw.rect(self.game.screen, entry.color, inner, border_radius=6)
                if entry.icon_letter:
                    icon_font = get_font(18, bold=True)
                    icon_surface = icon_font.render(entry.icon_letter, True, (30, 30, 40))
                    icon_rect = icon_surface.get_rect(center=inner.center)
                    self.game.screen.blit(icon_surface, icon_rect)
            else:
                pygame.draw.rect(self.game.screen, (60, 60, 80), inner, width=2, border_radius=6)
            if stack:
                total_count = self._total_available_count(stack.key)
                if total_count > 1:
                    count_surface = count_font.render(str(total_count), True, (250, 250, 255))
                    count_rect = count_surface.get_rect(bottomright=(rect.right - 4, rect.bottom - 4))
                    self.game.screen.blit(count_surface, count_rect)
            name = entry.name if entry else "Empty"
            trimmed = self._shorten_text(name, name_font, slot_size + 8)
            name_surface = name_font.render(trimmed, True, (220, 220, 230))
            name_rect = name_surface.get_rect(center=(rect.centerx, rect.bottom + 8))
            self.game.screen.blit(name_surface, name_rect)

    def _hotkey_label(self, idx):
        """Get display label for a hotkey index."""
        if idx < len(self.consumable_hotkeys):
            return pygame.key.name(self.consumable_hotkeys[idx]).upper()
        return str(idx + 4)

    def _shorten_text(self, text, font, max_width):
        if not text:
            return ""
        if font.size(text)[0] <= max_width:
            return text
        ellipsis = "..."
        trimmed = text
        while trimmed and font.size(trimmed + ellipsis)[0] > max_width:
            trimmed = trimmed[:-1]
        return trimmed + ellipsis if trimmed else ellipsis

    def _inventory_message(self, text, color=WHITE):
        player = getattr(self.game, 'player', None)
        if not player:
            return
        floating.append(DamageNumber(player.rect.centerx,
                                     player.rect.top - 12,
                                     text,
                                     color))

    def _storage_count(self, key):
        return self.consumable_storage.get(key, 0)

    def _slot_stack_limit(self, key):
        item = self.consumable_catalog.get(key)
        if not item:
            return self.MAX_CONSUMABLE_SLOT_STACK
        return max(item.max_stack, self.MAX_CONSUMABLE_SLOT_STACK)

    def _discover_consumable_key(self, key):
        """Track consumables that actually exist so the stock list mirrors inventory."""
        if not key or key not in self.consumable_catalog:
            return
        if key not in self.consumable_order:
            self.consumable_order.append(key)

    def _has_consumable_anywhere(self, key):
        if not key:
            return False
        if any(stack and stack.key == key for stack in self.consumable_slots):
            return True
        return self._storage_count(key) > 0

    def _prune_consumable_key(self, key):
        """Remove depleted consumables from the stock list once no stacks remain."""
        if not key or key not in self.consumable_order:
            return
        if self._has_consumable_anywhere(key):
            return
        self.consumable_order.remove(key)

    def _storage_add(self, key, amount):
        if amount <= 0 or not key or key not in self.consumable_catalog:
            return 0
        amount = int(amount)
        if amount <= 0:
            return 0
        old_count = self._storage_count(key)
        equipped_count = self._total_equipped_count(key)
        new_total = equipped_count + old_count + amount
        
        # Check if adding this amount would exceed the total limit of 20
        if new_total > 20:
            # Calculate how much we can actually add
            max_addable = max(0, 20 - equipped_count - old_count)
            if max_addable <= 0:
                return 0
            amount = max_addable
        
        old_count = self._storage_count(key)
        self.consumable_storage[key] = old_count + amount
        self._discover_consumable_key(key)
        return amount

    def _storage_remove(self, key, amount):
        if amount <= 0 or not key or key not in self.consumable_catalog:
            return 0
        current = self._storage_count(key)
        take = min(current, int(amount))
        if take <= 0:
            return 0
        remaining = current - take
        if remaining > 0:
            self.consumable_storage[key] = remaining
        else:
            self.consumable_storage.pop(key, None)
            self._prune_consumable_key(key)
        return take

    def _storage_add_unequip(self, key, amount):
        """Special version of _storage_add for unequipping items that accounts for the fact
        that the items being unequipped are currently counted in equipped_count."""
        if amount <= 0 or not key or key not in self.consumable_catalog:
            return 0
        amount = int(amount)
        if amount <= 0:
            return 0
        old_count = self._storage_count(key)
        # For unequip, we need to subtract the amount being unequipped from equipped_count
        # since these items are being moved from equipped to storage
        equipped_count = max(0, self._total_equipped_count(key) - amount)
        new_total = equipped_count + old_count + amount
        
        # Check if adding this amount would exceed the total limit of 20
        if new_total > 20:
            # Calculate how much we can actually add
            max_addable = max(0, 20 - equipped_count - old_count)
            if max_addable <= 0:
                return 0
            amount = max_addable
        
        old_count = self._storage_count(key)
        self.consumable_storage[key] = old_count + amount
        self._discover_consumable_key(key)
        return amount

    def add_consumable_to_storage(self, key, count=1):
        """Public helper to stash consumables without equipping them."""
        return self._storage_add(key, count)

    def _total_equipped_count(self, key):
        return sum(stack.count for stack in self.consumable_slots if stack and stack.key == key)

    def _total_available_count(self, key):
        total = self._total_equipped_count(key) + self._storage_count(key)
        return total

    def _clear_consumable_slot(self, idx):
        """Clear a consumable slot when the stack is depleted or invalid."""
        if idx < 0 or idx >= len(self.consumable_slots):
            return
        stack = self.consumable_slots[idx]
        key = stack.key if stack else None
        self.consumable_slots[idx] = None
        if key:
            self._prune_consumable_key(key)

    def _unequip_consumable_slot(self, idx):
        """Move the slot stack back into storage."""
        if idx < 0 or idx >= len(self.consumable_slots):
            return
        stack = self.consumable_slots[idx]
        if not stack:
            return
        # Use a special version of storage_add that accounts for the fact we're unequipping
        self._storage_add_unequip(stack.key, stack.count)
        self.consumable_slots[idx] = None

    def consume_slot(self, idx):
        """Consume a consumable from the given slot index."""
        if idx < 0 or idx >= len(self.consumable_slots):
            return False
        stack = self.consumable_slots[idx]
        if not stack:
            return False
        entry = self.consumable_catalog.get(stack.key)
        if not entry:
            self._clear_consumable_slot(idx)
            return False
        consumed = entry.use(self.game)
        if consumed:
            stack.consume_one()
            if stack.is_empty():
                self._clear_consumable_slot(idx)
            return True
        if hasattr(self.game, 'player') and self.game.player:
            floating.append(DamageNumber(self.game.player.rect.centerx,
                                         self.game.player.rect.top - 12,
                                         "No effect",
                                         WHITE))
        return False

    def _make_consumable_stack(self, key_id, count=1):
        """Create a consumable stack for the given key."""
        if not key_id or key_id not in self.consumable_catalog:
            return None
        stack = ConsumableStack(key=key_id, count=max(1, count))
        # Don't discover during initial stack creation to avoid duplicates
        # Discovery will happen when items are actually added to storage
        return stack

    def _swap_gear_slots(self, idx1, idx2):
        """Swap two gear slots."""
        if 0 <= idx1 < len(self.gear_slots) and 0 <= idx2 < len(self.gear_slots):
            self.gear_slots[idx1], self.gear_slots[idx2] = self.gear_slots[idx2], self.gear_slots[idx1]
            self.recalculate_player_stats()

    def _swap_consumable_slots(self, idx1, idx2):
        """Swap two consumable slots."""
        if 0 <= idx1 < len(self.consumable_slots) and 0 <= idx2 < len(self.consumable_slots):
            self.consumable_slots[idx1], self.consumable_slots[idx2] = self.consumable_slots[idx2], self.consumable_slots[idx1]

    def _equip_armament(self, slot_idx, key):
        """Equip an armament to a specific slot, swapping duplicates when needed."""
        if slot_idx < 0 or slot_idx >= len(self.gear_slots):
            return
        if key not in self.armament_catalog:
            return
        
        # Ensure new discoveries appear in stock lists, but keep existing ordering stable
        if key not in self.armament_order:
            self.armament_order.append(key)
        
        existing_idx = self._find_gear_slot_with_key(key)
        if existing_idx is not None and existing_idx != slot_idx:
            self.gear_slots[existing_idx], self.gear_slots[slot_idx] = (
                self.gear_slots[slot_idx],
                self.gear_slots[existing_idx],
            )
        else:
            self.gear_slots[slot_idx] = key
        self.recalculate_player_stats()

    def _equip_consumable(self, slot_idx, key):
        """Equip a consumable to a specific slot, swapping duplicates when needed."""
        if slot_idx < 0 or slot_idx >= len(self.consumable_slots):
            return
        if key not in self.consumable_catalog:
            return
        
        # Ensure new discoveries appear in stock lists, but keep existing ordering stable
        self._discover_consumable_key(key)
        
        # Check if this consumable already exists in another slot and swap
        for i, stack in enumerate(self.consumable_slots):
            if stack and stack.key == key and i != slot_idx:
                # Swap the slots
                self.consumable_slots[slot_idx], self.consumable_slots[i] = (
                    self.consumable_slots[i],
                    self.consumable_slots[slot_idx],
                )
                return
        
        item_def = self.consumable_catalog[key]
        slot_limit = self._slot_stack_limit(key)
        existing = self.consumable_slots[slot_idx]
        if existing and existing.key != key:
            self._unequip_consumable_slot(slot_idx)
            existing = None
        if existing and existing.key == key:
            missing = max(0, slot_limit - existing.count)
            if missing <= 0:
                return
            pulled = self._storage_remove(key, missing)
            if pulled <= 0:
                self._inventory_message("No stock")
                return
            existing.count += pulled
            return
        pulled = self._storage_remove(key, slot_limit)
        if pulled <= 0:
            self._inventory_message("No stock")
            return
        self.consumable_slots[slot_idx] = ConsumableStack(key=key, count=pulled)

    def add_consumable(self, key, count=1):
        """Add consumables to the appropriate slot or create new stack."""
        item_def = self.consumable_catalog.get(key)
        if not item_def or count <= 0:
            return 0
        
        # Check current total before adding
        current_total = self._total_available_count(key)
        
        # Calculate how many more we can add before hitting the limit of 20
        space_available = max(0, 20 - current_total)
        if space_available <= 0:
            return 0
        
        # Limit the amount we can actually add
        amount_to_add = min(count, space_available)
        remaining = amount_to_add
        added_total = 0
        slot_limit = self._slot_stack_limit(key)
        
        # first try to add to existing stacks
        for stack in self.consumable_slots:
            if stack and stack.key == key:
                added = stack.add(remaining, slot_limit)
                if added > 0:
                    remaining -= added
                    added_total += added
                if remaining <= 0:
                    break
        # then fill empty slots
        if remaining > 0:
            for i, stack in enumerate(self.consumable_slots):
                if stack is None:
                    take = min(remaining, slot_limit)
                    if take <= 0:
                        continue
                    self.consumable_slots[i] = ConsumableStack(key=key, count=take)
                    remaining -= take
                    added_total += take
                    if remaining <= 0:
                        break
        stored = 0
        if remaining > 0:
            stored = self._storage_add(key, remaining)
            added_total += stored
            remaining = max(0, remaining - stored)
            
        if added_total > 0:
            self._discover_consumable_key(key)
        return added_total

    def add_all_consumables(self):
        """Developer helper: stack every known consumable into inventory."""
        for key in self.consumable_catalog.keys():
            self.add_consumable(key, 1)

    def _force_equip_armament(self, key):
        """Force equip an armament, finding first available slot."""
        if not self.gear_slots:
            return
        empty_idx = next((i for i, val in enumerate(self.gear_slots) if val is None), None)
        target = empty_idx if empty_idx is not None else 0
        self._equip_armament(target, key)

    def recalculate_player_stats(self):
        """Recalculate player stats based on equipped armaments."""
        player = getattr(self.game, 'player', None)
        if not player or not hasattr(player, '_base_stats'):
            return
        base = player._base_stats
        stats = {k: float(v) for k, v in base.items()}
        for key in self.gear_slots:
            if key is None:
                continue
            item = self.armament_catalog.get(key)
            if not item:
                continue
            for mod_key, value in item.modifiers.items():
                stats[mod_key] = stats.get(mod_key, 0.0) + value
        stamina_mult = getattr(player, 'stamina_buff_mult', 1.0)
        stats['max_stamina'] = stats.get('max_stamina', 0.0) * stamina_mult
        player.max_hp = max(1, int(round(stats.get('max_hp', player.max_hp) or player.max_hp)))
        player.hp = min(player.hp, player.max_hp)
        player.attack_damage = max(1, int(round(stats.get('attack_damage', player.attack_damage) or player.attack_damage)))
        player.player_speed = stats.get('player_speed', player.player_speed)
        player.player_air_speed = stats.get('player_air_speed', player.player_air_speed)
        if hasattr(player, 'max_mana'):
            player.max_mana = max(0.0, stats.get('max_mana', player.max_mana) or player.max_mana)
            player.mana = min(player.mana, player.max_mana)
        if hasattr(player, 'max_stamina'):
            player.max_stamina = max(0.0, stats.get('max_stamina', player.max_stamina) or player.max_stamina)
            player.stamina = min(player.stamina, player.max_stamina)
        if hasattr(player, '_stamina_regen'):
            player._stamina_regen = stats.get('stamina_regen', player._stamina_regen)
        if hasattr(player, '_mana_regen'):
            player._mana_regen = stats.get('mana_regen', player._mana_regen)
