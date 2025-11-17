import logging
import pygame
import random
from config import WIDTH, HEIGHT, FPS, WHITE

logger = logging.getLogger(__name__)
from ..core.utils import draw_text, get_font
from .items import Consumable, HealConsumable, ManaConsumable, SpeedConsumable, JumpBoostConsumable, StaminaBoostConsumable, build_armament_catalog, build_consumable_catalog, load_icon, icon_has_transparency, load_icon_masked, rarity_border_color
from ..entities.entities import floating, DamageNumber

from dataclasses import dataclass
from typing import Optional, Any
from typing import Optional as _Optional
from typing import Tuple

# ============================================================================
# PLAYER MODEL DISPLAY CONFIGURATION
# ============================================================================
# Adjust these values to fine-tune how player sprites appear in inventory

# Scale factors for each class (multiplier applied to sprite size)
PLAYER_MODEL_SCALES = {
    'Knight': 1.8,      # Knight sprites: 93x64
    'Ranger': 1.6,      # Ranger sprites: 48x64
    'Wizard': 1.2,      # Default for future classe
    'Assassin': 2.0,    # Default for future classes
}

# Offset from center position (x, y) in pixels
# Positive X = move right, Positive Y = move down
PLAYER_MODEL_OFFSETS = {
    'Knight': (-20, -15),      # Centered
    'Ranger': (-10, -10),      # Centered
    'Wizard': (0, -5),      # Centered (placeholder)
    'Assassin': (0, 0),    # Centered (placeholder)
}

# ============================================================================


def _safe_load_icon(path: str, size: tuple = (24,24)) -> _Optional[pygame.Surface]:
    """Return loaded surface only if the image contains transparent pixels."""
    if not path:
        return None
    try:
        surf = load_icon(path, size)
    except Exception:
        return None
    if not surf:
        return None
    try:
        if icon_has_transparency(path, size):
            return surf
    except Exception:
        # Conservative: if transparency check fails, treat as opaque
        return None
    return None


def _draw_icon_in_rect(surface: pygame.Surface, rect: pygame.Rect, obj: Any, font: pygame.font.Font, radius: int = 6) -> None:
    """Draw an icon (true-alpha, masked placeholder, or letter) centered in `rect`.

    `obj` may be an item-like object with attributes `icon_path` and `icon_letter`.
    """
    size = (max(4, rect.width - 8), max(4, rect.height - 8))
    icon_img = None
    try:
        path = getattr(obj, 'icon_path', None)
        if path:
            icon_img = _safe_load_icon(path, size)
            if not icon_img:
                icon_img = load_icon_masked(path, size, radius=radius)
    except Exception:
        icon_img = None
    if icon_img:
        surface.blit(icon_img, icon_img.get_rect(center=rect.center))
        return
    # fallback to letter
    letter = getattr(obj, 'icon_letter', None) or ''
    if letter:
        try:
            letter_surf = font.render(letter, True, (20, 20, 28))
            surface.blit(letter_surf, letter_surf.get_rect(center=rect.center))
        except Exception:
            return
    return

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
        self.stats_scroll_offset = 0  # Add scroll for stats display
        self.consumable_storage: dict[str, int] = {}
        
        # Initialize inventory-related attributes
        self.consumable_hotkeys = [pygame.K_4, pygame.K_5, pygame.K_6]
        self.armament_catalog = build_armament_catalog()
        self.armament_order = list(self.armament_catalog.keys())
        self.consumable_catalog = build_consumable_catalog()
        self.consumable_order: list[str] = []
        
        # Player model animation state
        self._model_anim_timer = 0
        self._model_attack_cooldown = 0
        self._model_is_attacking = False

    def _draw_player_model(self, model_frame):
        """Draw animated player sprite in the inventory model frame with idle animation and random attacks."""
        player = self.game.player
        
        # Update animation timer
        self._model_anim_timer += 1
        
        # Update run animation cooldown (renamed from attack cooldown)
        if self._model_attack_cooldown > 0:
            self._model_attack_cooldown -= 1
            if self._model_attack_cooldown == 0:
                self._model_is_attacking = False
        
        # Random chance to trigger run animation when not on cooldown
        if not self._model_is_attacking and self._model_attack_cooldown == 0:
            if random.random() < 0.008:  # ~0.8% chance per frame = run roughly every 2-3 seconds
                self._model_is_attacking = True
                self._model_attack_cooldown = 90  # 1.5 second cooldown at 60 FPS
        
        # If player has animation manager and sprite rendering, use it
        if hasattr(player, 'anim_manager') and player.anim_manager and player.anim_manager.animations:
            # Decide which animation to show based on model state
            from ..entities.animation_system import AnimationState
            
            # Use RUN animation for action, IDLE for rest
            if self._model_is_attacking:
                target_state = AnimationState.RUN
            else:
                target_state = AnimationState.IDLE
            
            # Get the animation for the target state
            anim_data = player.anim_manager.animations.get(target_state)
            if anim_data and anim_data.frames:
                # Calculate which frame to show based on timer
                frame_duration = anim_data.frame_duration
                total_frames = len(anim_data.frames)
                
                # For run animation, progress through once then reset
                if self._model_is_attacking:
                    run_progress = 90 - self._model_attack_cooldown  # 0 to 90
                    frame_index = min(int(run_progress / frame_duration), total_frames - 1)
                else:
                    # For idle, loop continuously
                    frame_index = (self._model_anim_timer // frame_duration) % total_frames
                
                # Get the current frame surface
                current_frame = anim_data.frames[frame_index]
                
                if current_frame:
                    sprite_size = current_frame.get_size()
                    
                    # Get scale factor from configuration (or use default)
                    scale_factor = PLAYER_MODEL_SCALES.get(player.cls, 2.0)
                    
                    # Get offset from configuration (or use default)
                    offset_x, offset_y = PLAYER_MODEL_OFFSETS.get(player.cls, (0, 0))
                    
                    scaled_w = int(sprite_size[0] * scale_factor)
                    scaled_h = int(sprite_size[1] * scale_factor)
                    scaled_sprite = pygame.transform.scale(current_frame, (scaled_w, scaled_h))
                    
                    # Flip sprite to face right
                    scaled_sprite = pygame.transform.flip(scaled_sprite, True, False)
                    
                    # Center the sprite in the model frame with offset
                    sprite_rect = scaled_sprite.get_rect()
                    sprite_rect.center = (model_frame.centerx + offset_x, model_frame.centery + offset_y)
                    
                    # Draw the sprite
                    self.game.screen.blit(scaled_sprite, sprite_rect)
                    return  # Successfully drew sprite
            
        # Fallback to colored rectangle for classes without animation or if sprite fails
        model_rect = pygame.Rect(0, 0, player.rect.width * 3.5, player.rect.height * 3.5)
        model_rect.center = model_frame.center
        pygame.draw.rect(self.game.screen, (120, 200, 235), model_rect, border_radius=12)
    
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

    def _scroll_stock(self, delta: int) -> None:
        """Scroll current stock panel by delta pixels (positive = down, negative = up)."""
        if not self.inventory_open or self.inventory_stock_mode not in ("gear", "consumable"):
            return

        # Reconstruct the same geometry used in draw_inventory_overlay for the stock panel
        margin = 40
        max_panel_w = WIDTH - (margin * 2)
        max_panel_h = HEIGHT - (margin * 2)
        panel_w = min(800, max_panel_w)
        panel_h = min(600, max_panel_h)
        panel_rect = pygame.Rect(
            (WIDTH - panel_w) // 2,
            (HEIGHT - panel_h) // 2 + 20,
            panel_w,
            panel_h,
        )

        left_pane_width = 280
        right_pane_width = panel_w - left_pane_width - 60
        right_pane_rect = pygame.Rect(
            panel_rect.x + 20 + left_pane_width + 20,
            panel_rect.y + 70,
            right_pane_width,
            panel_h - 100,
        )

        slot_w, slot_spacing = 56, 12
        grid_padding = 10

        # Match stock_panel_y / height from draw_inventory_overlay
        equipped_slots_y = right_pane_rect.y + 20 + 26
        stock_panel_y = equipped_slots_y + slot_w + 30
        stock_panel_height = right_pane_rect.bottom - stock_panel_y - 20
        stock_panel_rect = pygame.Rect(
            right_pane_rect.x + 20,
            stock_panel_y,
            right_pane_width - 40,
            stock_panel_height,
        )

        header_height = 40
        grid_start_y = 10  # Must match grid_start_y_in_surface in draw_inventory_overlay
        max_grid_width = stock_panel_rect.width - grid_padding * 2 - 25
        cols = max(1, max_grid_width // (slot_w + slot_spacing))
        row_height = slot_w + slot_spacing
        # viewport is the scrollable body height minus top padding
        viewport_height = stock_panel_rect.height - header_height - grid_start_y

        if self.inventory_stock_mode == "gear":
            keys = [self.UNEQUIP_GEAR_KEY, *self.armament_order]
        else:
            available_consumables = []
            for key in self.consumable_order:
                if self._storage_count(key) > 0:
                    available_consumables.append(key)
            keys = [self.UNEQUIP_CONSUMABLE_KEY, *available_consumables]

        if not keys:
            return

        num_rows = (len(keys) + cols - 1) // cols
        total_content_height = num_rows * row_height
        max_scroll = max(0, total_content_height - viewport_height)
        # Always keep scroll within [0, max_scroll]; if content shorter than viewport,
        # clamp to 0 so items never overlap the fixed header text.

        if self.inventory_stock_mode == "gear":
            self.armament_scroll_offset = max(0, min(max_scroll, self.armament_scroll_offset + delta))
        else:
            self.consumable_scroll_offset = max(0, min(max_scroll, self.consumable_scroll_offset + delta))
    
    def scroll_stats(self, delta):
        """Scroll the player stats display by delta pixels."""
        # Just increment/decrement, clamping happens in draw
        self.stats_scroll_offset += delta

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
        
        # Handle exit button click
        if kind == 'exit_button':
            self.inventory_open = False
            self._clear_inventory_selection()
            return

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
            self.inventory_stock_mode = 'gear'

            if sel and sel.get('kind') == 'gear_slot':
                # Clicking another gear slot while one is selected: toggle or move selection
                if sel['index'] == idx:
                    self._clear_inventory_selection()
                else:
                    self.inventory_selection = {'kind': 'gear_slot', 'index': idx}

            elif sel and sel.get('kind') == 'gear_pool':
                key = sel.get('key')
                # Equip selected stock item into this slot
                self._equip_armament(idx, key)

                # If this slot now has an item, move to next free slot if any
                if self.gear_slots[idx] is not None:
                    next_free = None
                    for offset in range(1, len(self.gear_slots)):
                        cand = (idx + offset) % len(self.gear_slots)
                        if self.gear_slots[cand] is None:
                            next_free = cand
                            break
                    if next_free is not None:
                        # Move selection to next free slot to speed equipping
                        self.inventory_selection = {'kind': 'gear_slot', 'index': next_free}
                    else:
                        # All slots filled, stay on the recently equipped slot
                        self.inventory_selection = {'kind': 'gear_slot', 'index': idx}
                else:
                    # Equip failed; just select this slot
                    self.inventory_selection = {'kind': 'gear_slot', 'index': idx}

            else:
                # No stock selection: just select exactly the clicked slot
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
                            # Select next equipped gear slot, or clear if none
                            next_idx = None
                            for offset in range(1, len(self.gear_slots)):
                                cand = (idx + offset) % len(self.gear_slots)
                                if self.gear_slots[cand] is not None:
                                    next_idx = cand
                                    break
                            if next_idx is not None:
                                self.inventory_selection = {'kind': 'gear_slot', 'index': next_idx}
                            else:
                                self._clear_inventory_selection()
                return
            if sel and sel.get('kind') == 'gear_slot':
                self._equip_armament(sel['index'], key)
                
                # If this slot now has an item, move to next free slot if any
                if self.gear_slots[sel['index']] is not None:
                    next_free = None
                    for offset in range(1, len(self.gear_slots)):
                        cand = (sel['index'] + offset) % len(self.gear_slots)
                        if self.gear_slots[cand] is None:
                            next_free = cand
                            break
                    if next_free is not None:
                        # Move selection to next free slot to speed equipping
                        self.inventory_selection = {'kind': 'gear_slot', 'index': next_free}
                    else:
                        # All slots filled, stay on the recently equipped slot
                        self.inventory_selection = {'kind': 'gear_slot', 'index': sel['index']}
                else:
                    # Equip failed; just select this slot
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
                            # Select next slot that still has a consumable, or clear if none
                            next_idx = None
                            for offset in range(1, len(self.consumable_slots)):
                                cand = (idx + offset) % len(self.consumable_slots)
                                if self.consumable_slots[cand] is not None:
                                    next_idx = cand
                                    break
                            if next_idx is not None:
                                self.inventory_selection = {'kind': 'consumable_slot', 'index': next_idx}
                            else:
                                self._clear_inventory_selection()
                return
            if sel and sel.get('kind') == 'consumable_slot':
                self._equip_consumable(sel['index'], key)
                
                # If this slot now has an item, move to next free consumable slot if any
                if self.consumable_slots[sel['index']]:
                    next_free = None
                    for offset in range(1, len(self.consumable_slots)):
                        cand = (sel['index'] + offset) % len(self.consumable_slots)
                        if self.consumable_slots[cand] is None:
                            next_free = cand
                            break
                    if next_free is not None:
                        self.inventory_selection = {'kind': 'consumable_slot', 'index': next_free}
                    else:
                        # All slots filled, stay on the recently equipped slot
                        self.inventory_selection = {'kind': 'consumable_slot', 'index': sel['index']}
                else:
                    # Equip failed; just select this slot
                    self.inventory_selection = {'kind': 'consumable_slot', 'index': sel['index']}
            elif sel and sel.get('kind') == 'consumable_pool' and sel['key'] == key:
                self._clear_inventory_selection()
            else:
                self.inventory_selection = {'kind': 'consumable_pool', 'key': key}
        elif kind == 'consumable_slot':
            idx = hit['index']
            self.inventory_stock_mode = 'consumable'

            if sel and sel.get('kind') == 'consumable_slot':
                # Clicking same slot toggles, different moves selection
                if sel['index'] == idx:
                    self._clear_inventory_selection()
                else:
                    self.inventory_selection = {'kind': 'consumable_slot', 'index': idx}

            elif sel and sel.get('kind') == 'consumable_pool':
                key = sel.get('key')
                # Equip selected consumable from stock into this slot
                self._equip_consumable(idx, key)

                # If this slot now has an item, move to next free consumable slot if any
                if self.consumable_slots[idx]:
                    next_free = None
                    for offset in range(1, len(self.consumable_slots)):
                        cand = (idx + offset) % len(self.consumable_slots)
                        if self.consumable_slots[cand] is None:
                            next_free = cand
                            break
                    if next_free is not None:
                        self.inventory_selection = {'kind': 'consumable_slot', 'index': next_free}
                    else:
                        # All slots filled, stay on the recently equipped slot
                        self.inventory_selection = {'kind': 'consumable_slot', 'index': idx}
                else:
                    # Equip failed; just select this slot
                    self.inventory_selection = {'kind': 'consumable_slot', 'index': idx}

            else:
                # No stock selection: just select exactly the clicked slot
                self.inventory_selection = {'kind': 'consumable_slot', 'index': idx}
        elif kind == 'unequip_armament':
            # Unequip selected armament slot
            if sel and sel.get('kind') == 'gear_slot':
                idx = sel.get('index', -1)
                if 0 <= idx < len(self.gear_slots):
                    self.gear_slots[idx] = None
                    self.recalculate_player_stats()
                    # Select next equipped gear slot, or clear if none
                    next_idx = None
                    for offset in range(1, len(self.gear_slots)):
                        cand = (idx + offset) % len(self.gear_slots)
                        if self.gear_slots[cand] is not None:
                            next_idx = cand
                            break
                    if next_idx is not None:
                        self.inventory_selection = {'kind': 'gear_slot', 'index': next_idx}
                    else:
                        self._clear_inventory_selection()
        elif kind == 'unequip_armament_stock':
            # Unequip selected armament from stock
            if sel and sel.get('kind') == 'gear_pool':
                key = sel.get('key')
                if key:
                    # Find and remove from gear slots (from last to first)
                    for i in range(len(self.gear_slots) - 1, -1, -1):
                        slot_key = self.gear_slots[i]
                        if slot_key == key:
                            self.gear_slots[i] = None
                            self.recalculate_player_stats()
                            # Select next equipped gear slot, or clear if none
                            next_idx = None
                            for offset in range(1, len(self.gear_slots)):
                                cand = (i + offset) % len(self.gear_slots)
                                if self.gear_slots[cand] is not None:
                                    next_idx = cand
                                    break
                            if next_idx is not None:
                                self.inventory_selection = {'kind': 'gear_slot', 'index': next_idx}
                            else:
                                self._clear_inventory_selection()
                            break
        elif kind == 'unequip_consumable':
            # Unequip selected consumable slot
            if sel and sel.get('kind') == 'consumable_slot':
                idx = sel.get('index', -1)
                if 0 <= idx < len(self.consumable_slots):
                    self._unequip_consumable_slot(idx)
                    # Select next slot that still has a consumable, or clear if none
                    next_idx = None
                    for offset in range(1, len(self.consumable_slots)):
                        cand = (idx + offset) % len(self.consumable_slots)
                        if self.consumable_slots[cand] is not None:
                            next_idx = cand
                            break
                    if next_idx is not None:
                        self.inventory_selection = {'kind': 'consumable_slot', 'index': next_idx}
                    else:
                        self._clear_inventory_selection()
        elif kind == 'unequip_consumable_stock':
            # Unequip selected consumable from stock
            if sel and sel.get('kind') == 'consumable_pool':
                key = sel.get('key')
                if key:
                    # Find and remove from consumable slots (from last to first)
                    for i in range(len(self.consumable_slots) - 1, -1, -1):
                        stack = self.consumable_slots[i]
                        if stack and stack.key == key:
                            self._unequip_consumable_slot(i)
                            # Select next slot that still has a consumable, or clear if none
                            next_idx = None
                            for offset in range(1, len(self.consumable_slots)):
                                cand = (i + offset) % len(self.consumable_slots)
                                if self.consumable_slots[cand] is not None:
                                    next_idx = cand
                                    break
                            if next_idx is not None:
                                self.inventory_selection = {'kind': 'consumable_slot', 'index': next_idx}
                            else:
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
        payload = {'lines': [], 'item': None, 'color': None, 'letter': ""}
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
            # Insert rarity after effect_text if present, otherwise after the name
            try:
                rarity = getattr(item, 'rarity', 'Normal')
                rarity_line = f"Rarity: {rarity}"
                insert_index = 1
                if hasattr(item, 'effect_text') and item.effect_text:
                    for idx, l in enumerate(lines):
                        if l == item.effect_text:
                            insert_index = idx + 1
                            break
                lines.insert(insert_index, rarity_line)
            except Exception:
                pass
            lines.extend(self._format_modifier_lines(item.modifiers))
            payload['lines'] = lines
            payload['item'] = item
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
            # Insert rarity after effect_text if present, otherwise after the name
            try:
                rarity = getattr(entry, 'rarity', 'Normal')
                rarity_line = f"Rarity: {rarity}"
                insert_index = 1
                if hasattr(entry, 'effect_text') and entry.effect_text:
                    for idx, l in enumerate(lines):
                        if l == entry.effect_text:
                            insert_index = idx + 1
                            break
                lines.insert(insert_index, rarity_line)
            except Exception:
                pass
            if stack_count is not None:
                lines.append(f"Stack: {stack_count}")
            storage_count = self._storage_count(key)
            if storage_count > 0:
                lines.append(f"Storage: {storage_count}")
            payload['lines'] = lines
            payload['item'] = entry
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
        name_font = get_font(18, bold=True)
        icon_space = 0
        # Use new icon system if item is available
        if payload.get('item'):
            icon_space = 34
        
        # Calculate width using appropriate font for each line
        widths = []
        for i, line in enumerate(lines):
            if i == 0:  # Name line uses bigger font
                widths.append(name_font.size(line)[0])
            else:  # Other lines use normal font
                widths.append(font.size(line)[0])
        
        width = max(widths) + 20 + icon_space
        height = len(lines) * 22 + 12
        mx, my = pygame.mouse.get_pos()
        tooltip_rect = pygame.Rect(mx + 18, my + 18, width, height)
        if tooltip_rect.right > WIDTH - 8:
            tooltip_rect.x = WIDTH - width - 8
        if tooltip_rect.bottom > HEIGHT - 8:
            tooltip_rect.y = HEIGHT - height - 8
        pygame.draw.rect(self.game.screen, (28, 28, 38), tooltip_rect, border_radius=8)
        pygame.draw.rect(self.game.screen, (180, 170, 200), tooltip_rect, width=1, border_radius=8)

        # Draw rarity border accent around tooltip if we have an item
        try:
            item_obj = payload.get('item')
            if item_obj:
                border_col = rarity_border_color(item_obj)
                inner = tooltip_rect.inflate(-4, -4)
                pygame.draw.rect(self.game.screen, border_col, inner, width=2, border_radius=6)
        except Exception:
            pass

        text_x = tooltip_rect.x + 10
        if icon_space:
            icon_rect = pygame.Rect(tooltip_rect.x + 10, tooltip_rect.y + 10, 24, 24)
            item = payload['item']
            # Draw icon using new system (same as inventory slots)
            icon_img = None
            if hasattr(item, 'icon_path') and item.icon_path:
                icon_img = _safe_load_icon(item.icon_path, (24, 24))
                if not icon_img:
                    icon_img = load_icon_masked(item.icon_path, (24, 24), radius=4)
            if icon_img:
                self.game.screen.blit(icon_img, icon_img.get_rect(center=icon_rect.center))
            else:
                # Fallback to old system for items without icons
                if payload.get('color'):
                    pygame.draw.rect(self.game.screen, payload['color'], icon_rect, border_radius=6)
                if payload.get('letter'):
                    icon_font = get_font(14, bold=True)
                    icon_surf = icon_font.render(payload['letter'], True, (10,10,20))
                    self.game.screen.blit(icon_surf, icon_surf.get_rect(center=icon_rect.center))
            text_x += icon_space
        for i, line in enumerate(lines):
            # Different colors and sizes for different tooltip parts
            item = payload.get('item')
            # Rarity line detection (we insert as 'Rarity: <Name>')
            if isinstance(line, str) and line.startswith("Rarity:"):
                text_font = get_font(16, bold=True)
                try:
                    rarity_name = line.split(':', 1)[1].strip()
                except Exception:
                    rarity_name = getattr(item, 'rarity', 'Normal') if item else 'Normal'
                try:
                    rarity_col = rarity_border_color(rarity_name)
                except Exception:
                    rarity_col = (200, 200, 200)
                text_color = rarity_col
                # Draw small swatch
                swatch_size = 10
                sw_x = text_x
                sw_y = tooltip_rect.y + 6 + i * 22 + (16 - swatch_size) // 2
                try:
                    pygame.draw.rect(self.game.screen, rarity_col, (sw_x, sw_y, swatch_size, swatch_size), border_radius=2)
                    pygame.draw.rect(self.game.screen, (10,10,10), (sw_x, sw_y, swatch_size, swatch_size), width=1, border_radius=2)
                except Exception:
                    pass
                text_to_draw_x = text_x + swatch_size + 6
                self.game.screen.blit(text_font.render(line, True, text_color), (text_to_draw_x, tooltip_rect.y + 6 + i * 22))
            elif i == 1 and item and hasattr(item, 'effect_text') and item.effect_text:  # Effect text (cyan and normal size)
                text_font = get_font(16)
                text_color = (100, 200, 255)  # Cyan color for effect
                self.game.screen.blit(text_font.render(line, True, text_color), (text_x, tooltip_rect.y + 6 + i * 22))
            else:  # Description and flavor (white and normal size)
                text_font = get_font(16)
                text_color = (230, 230, 245)  # Light gray/white for description
                self.game.screen.blit(text_font.render(line, True, text_color), (text_x, tooltip_rect.y + 6 + i * 22))

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
            keys = [self.UNEQUIP_GEAR_KEY, *self.armament_order]
        else:
            consumable_keys = [k for k in self.consumable_order if self._has_consumable_anywhere(k)]
            keys = [self.UNEQUIP_CONSUMABLE_KEY, *consumable_keys]
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
                # Default border color; override with rarity color for items
                border_col = (110, 120, 150)
                try:
                    border_col = rarity_border_color(entry)
                except Exception:
                    border_col = (110, 120, 150)
                is_selected = selection_key == key
                # Draw rarity border first
                pygame.draw.rect(self.game.screen, border_col, cell, width=2, border_radius=8)
                # Draw white selection border inside rarity border if selected (thinner, smaller)
                if is_selected:
                    pygame.draw.rect(self.game.screen, (255, 255, 255), cell.inflate(-4, -4), width=2, border_radius=6)
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
                # Prefer true-alpha icon, else masked placeholder, else letter
                icon_img = None
                if hasattr(entry, 'icon_path') and entry.icon_path:
                    icon_img = _safe_load_icon(entry.icon_path, (cell_size, cell_size))
                    if not icon_img:
                        icon_img = load_icon_masked(entry.icon_path, (cell_size, cell_size), radius=8)
                if icon_img:
                    self.game.screen.blit(icon_img, icon_img.get_rect(center=cell.center))
                else:
                    icon_surface = icon_font.render(entry.icon_letter, True, (20, 20, 28))
                    self.game.screen.blit(icon_surface, icon_surface.get_rect(center=cell.center))
            region_kind = 'gear_pool' if mode == 'gear' else 'consumable_pool'
            self._register_inventory_region(cell, region_kind, key=key)
        


    def _build_player_stats_display(self):
        """Build comprehensive player stats display with modifiers shown in color."""
        player = self.game.player
        base = getattr(player, '_base_stats', {})
        stats_lines = []
        
        # HP with max HP modifier
        current_hp = player.hp
        max_hp = getattr(player.combat, 'max_hp', 0) if hasattr(player, 'combat') else 0
        base_max_hp = base.get('max_hp', max_hp)
        hp_mod = max_hp - base_max_hp
        if hp_mod != 0:
            mod_text = f" {'+' if hp_mod > 0 else ''}{int(hp_mod)}"
            mod_color = (100, 255, 100) if hp_mod > 0 else (255, 100, 100)
            stats_lines.append((f"HP: {current_hp}/{int(max_hp)}", (255, 150, 150), mod_text, mod_color))
        else:
            stats_lines.append((f"HP: {current_hp}/{int(max_hp)}", (255, 150, 150)))
        
        # Attack with damage modifier
        attack = getattr(player, 'attack_damage', 0)
        atk_bonus = getattr(player.combat, 'atk_bonus', 0) if hasattr(player, 'combat') else 0
        base_attack = base.get('attack_damage', attack - atk_bonus)
        total_atk_mod = attack - base_attack
        if total_atk_mod != 0:
            mod_text = f" {'+' if total_atk_mod > 0 else ''}{int(total_atk_mod)}"
            mod_color = (100, 255, 100) if total_atk_mod > 0 else (255, 100, 100)
            stats_lines.append((f"Attack: {int(attack)}", (255, 200, 100), mod_text, mod_color))
        else:
            stats_lines.append((f"Attack: {int(attack)}", (255, 200, 100)))
        
        # Mana
        if hasattr(player, 'mana'):
            current_mana = player.mana
            max_mana = player.max_mana
            base_max_mana = base.get('max_mana', max_mana)
            mana_mod = max_mana - base_max_mana
            if mana_mod != 0:
                mod_text = f" {'+' if mana_mod > 0 else ''}{mana_mod:.0f}"
                mod_color = (100, 255, 255) if mana_mod > 0 else (255, 100, 100)
                stats_lines.append((f"Mana: {current_mana:.0f}/{max_mana:.0f}", (100, 150, 255), mod_text, mod_color))
            else:
                stats_lines.append((f"Mana: {current_mana:.0f}/{max_mana:.0f}", (100, 150, 255)))
        
        # Stamina
        if hasattr(player, 'stamina'):
            current_stamina = player.stamina
            max_stamina = player.max_stamina
            base_max_stamina = base.get('max_stamina', max_stamina)
            stamina_mod = max_stamina - base_max_stamina
            if stamina_mod != 0:
                mod_text = f" {'+' if stamina_mod > 0 else ''}{stamina_mod:.1f}"
                mod_color = (100, 255, 100) if stamina_mod > 0 else (255, 100, 100)
                stats_lines.append((f"Stamina: {current_stamina:.1f}/{max_stamina:.1f}", (150, 255, 150), mod_text, mod_color))
            else:
                stats_lines.append((f"Stamina: {current_stamina:.1f}/{max_stamina:.1f}", (150, 255, 150)))
        
        # Speed
        speed = player.player_speed
        base_speed = base.get('player_speed', speed)
        speed_mod = speed - base_speed
        if speed_mod != 0:
            mod_text = f" {'+' if speed_mod > 0 else ''}{speed_mod:.1f}"
            mod_color = (100, 255, 255) if speed_mod > 0 else (255, 100, 100)
            stats_lines.append((f"Speed: {speed:.1f}", (200, 200, 255), mod_text, mod_color))
        else:
            stats_lines.append((f"Speed: {speed:.1f}", (200, 200, 255)))
        
        # Lifesteal (melee) - special effect, not a base attribute
        if hasattr(player, 'combat'):
            ls_pct = getattr(player.combat, 'lifesteal_pct', 0.0)
            if ls_pct > 0.0:
                stats_lines.append((f"+Lifesteal: {ls_pct*100:.1f}%", (160, 220, 180)))
            
            # Spell Lifesteal - special effect
            spell_ls = getattr(player.combat, 'spell_lifesteal_pct', getattr(player.combat, 'spell_lifesteal', 0.0))
            if spell_ls > 0.0:
                stats_lines.append((f"+Spell Lifesteal: {spell_ls*100:.1f}%", (120, 180, 255)))
        
        # Additional stats from items (multipliers, special effects)
        # Attack Speed - special effect
        attack_speed_mult = getattr(player, 'attack_speed_mult', 1.0)
        if attack_speed_mult != 1.0:
            bonus_pct = (attack_speed_mult - 1.0) * 100
            color = (100, 255, 100) if bonus_pct > 0 else (255, 100, 100)
            stats_lines.append((f"+Attack Speed: {'+' if bonus_pct > 0 else ''}{bonus_pct:.0f}%", color))
        
        # Skill Cooldown Reduction - special effect
        skill_cdr_mult = getattr(player, 'skill_cooldown_mult', 1.0)
        if skill_cdr_mult != 1.0:
            cdr_pct = (1.0 - skill_cdr_mult) * 100
            color = (150, 200, 255)
            stats_lines.append((f"+CDR: {cdr_pct:.0f}%", color))
        
        # Skill Damage - special effect
        skill_dmg_mult = getattr(player, 'skill_damage_mult', 1.0)
        if skill_dmg_mult != 1.0:
            bonus_pct = (skill_dmg_mult - 1.0) * 100
            color = (200, 150, 255)
            stats_lines.append((f"+Skill Dmg: {'+' if bonus_pct > 0 else ''}{bonus_pct:.0f}%", color))
        
        # Dash Stamina Cost - special effect
        dash_stamina_mult = getattr(player, 'dash_stamina_mult', 1.0)
        if dash_stamina_mult != 1.0:
            reduction_pct = (1.0 - dash_stamina_mult) * 100
            color = (100, 255, 200)
            stats_lines.append((f"+Dash Cost: {'-' if reduction_pct > 0 else '+'}{abs(reduction_pct):.0f}%", color))
        
        # Extra Dash/Jump Charges - special effects
        extra_dash = getattr(player, 'extra_dash_charges', 0)
        if extra_dash > 0:
            stats_lines.append((f"+Dash Charges: {extra_dash}", (100, 255, 200)))
        
        extra_jumps = getattr(player, 'extra_jump_charges', 0)
        if extra_jumps > 0:
            stats_lines.append((f"+Air Jumps: {extra_jumps}", (200, 220, 255)))
        
        # Critical Hit - special effect
        crit_chance = getattr(player, 'crit_chance', 0.0)
        if crit_chance > 0:
            stats_lines.append((f"+Crit Chance: {crit_chance*100:.1f}%", (255, 200, 100)))
        
        # Critical Damage Multiplier - special effect
        crit_mult = getattr(player, 'crit_multiplier', 0.0)
        if crit_mult > 0 and crit_mult != 2.0:  # Only show if not default 2.0x
            stats_lines.append((f"+Crit Damage: {crit_mult:.1f}x", (255, 180, 80)))
        
        # Dodge Chance - special effect
        dodge_chance = getattr(player, 'dodge_chance', 0.0)
        if dodge_chance > 0:
            stats_lines.append((f"+Dodge: {dodge_chance*100:.1f}%", (180, 220, 255)))
        
        # Check equipped items for on-hit effects
        # Poison from equipped items
        poison_stacks = 0
        for gear_key in self.gear_slots:
            if gear_key:
                item = self.armament_catalog.get(gear_key)
                if item and hasattr(item, 'modifiers'):
                    poison_stacks += item.modifiers.get('on_hit_poison_stacks', 0)
        if poison_stacks > 0:
            stats_lines.append((f"+Poison: {poison_stacks} stacks", (150, 255, 120)))
        
        # Burn from equipped items
        burn_dps = 0
        burn_duration = 0
        burn_always = False
        for gear_key in self.gear_slots:
            if gear_key:
                item = self.armament_catalog.get(gear_key)
                if item and hasattr(item, 'modifiers'):
                    item_burn_dps = item.modifiers.get('on_hit_burn_dps', 0)
                    if item_burn_dps > 0:
                        burn_dps = max(burn_dps, item_burn_dps)  # Use highest DPS
                        burn_duration = max(burn_duration, item.modifiers.get('on_hit_burn_duration', 0))
                        if item.modifiers.get('on_hit_burn_always', False):
                            burn_always = True
        if burn_dps > 0:
            burn_text = f"+Burn: {burn_dps}/s for {burn_duration:.0f}s"
            if burn_always:
                burn_text += " (always)"
            stats_lines.append((burn_text, (255, 150, 80)))
        
        # Bleed from equipped items
        bleed_dmg = 0
        bleed_duration = 0
        for gear_key in self.gear_slots:
            if gear_key:
                item = self.armament_catalog.get(gear_key)
                if item and hasattr(item, 'modifiers'):
                    item_bleed_dur = item.modifiers.get('on_hit_bleed_duration', 0)
                    if item_bleed_dur > 0:
                        bleed_dmg = max(bleed_dmg, item.modifiers.get('on_hit_bleed_dps', 0))
                        bleed_duration = max(bleed_duration, item_bleed_dur)
        if bleed_dmg > 0:
            stats_lines.append((f"+Bleed: {bleed_dmg}/s for {bleed_duration:.0f}s", (200, 80, 80)))
        
        # Freeze from equipped items
        freeze_chance = 0
        freeze_duration = 0
        for gear_key in self.gear_slots:
            if gear_key:
                item = self.armament_catalog.get(gear_key)
                if item and hasattr(item, 'modifiers'):
                    item_freeze_chance = item.modifiers.get('on_hit_freeze_chance', 0)
                    if item_freeze_chance > 0:
                        freeze_chance += item_freeze_chance  # Stack chances
                        freeze_duration = max(freeze_duration, item.modifiers.get('on_hit_freeze_duration', 0))
        if freeze_chance > 0:
            stats_lines.append((f"+Freeze: {freeze_chance*100:.0f}% for {freeze_duration:.1f}s", (150, 200, 255)))
        
        # Double Attack from equipped items
        double_attack_chance = 0
        for gear_key in self.gear_slots:
            if gear_key:
                item = self.armament_catalog.get(gear_key)
                if item and hasattr(item, 'modifiers'):
                    double_attack_chance += item.modifiers.get('double_attack', 0)
        if double_attack_chance > 0:
            stats_lines.append((f"+Double Attack: {double_attack_chance*100:.0f}%", (255, 220, 120)))
        
        return stats_lines

    def draw_inventory_overlay(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.game.screen.blit(overlay, (0, 0))

        # Calculate panel size to fit within screen with margins
        margin = 30  # Reduced margin from 40 to 30
        max_panel_w = WIDTH - (margin * 2)
        max_panel_h = HEIGHT - (margin * 2)
        
        # Make panel taller to use more screen space
        panel_w = min(800, max_panel_w)
        panel_h = min(700, max_panel_h)  # Increased from 600 to 700
        panel_rect = pygame.Rect(
            (WIDTH - panel_w) // 2,
            (HEIGHT - panel_h) // 2,  # Centered vertically (removed +20 offset)
            panel_w,
            panel_h,
        )
        
        panel_bg = (30, 28, 40)
        panel_border = (210, 200, 170)
        pygame.draw.rect(self.game.screen, panel_bg, panel_rect, border_radius=12)
        pygame.draw.rect(self.game.screen, panel_border, panel_rect, width=2, border_radius=12)
        self.inventory_regions = []
        selection = self.inventory_selection

        # Draw "Inventory" title in its own header box - moved to very top
        header_box_height = 45  # Slightly reduced from 50
        header_box_rect = pygame.Rect(panel_rect.x + 15, panel_rect.y + 10, panel_rect.width - 30, header_box_height)
        pygame.draw.rect(self.game.screen, (40, 35, 55), header_box_rect, border_radius=8)
        pygame.draw.rect(self.game.screen, (210, 200, 170), header_box_rect, width=2, border_radius=8)
        draw_text(self.game.screen, "Inventory", (header_box_rect.x + 15, header_box_rect.y + 8), (240,220,190), size=28, bold=True)
        
        # Draw footer area with red exit button
        footer_box_height = 45  # Taller footer box
        footer_box_y = panel_rect.bottom - footer_box_height - 10
        footer_box_rect = pygame.Rect(panel_rect.x + 15, footer_box_y, panel_rect.width - 30, footer_box_height)
        pygame.draw.rect(self.game.screen, (40, 35, 55), footer_box_rect, border_radius=8)
        pygame.draw.rect(self.game.screen, (100, 100, 120), footer_box_rect, width=1, border_radius=8)
        
        # Red exit button centered in footer - matching shop exactly
        button_width = 140  # Wider to fit "EXIT (ESC)"
        button_height = 34
        exit_button_rect = pygame.Rect(
            footer_box_rect.centerx - button_width // 2,
            footer_box_rect.centery - button_height // 2,
            button_width,
            button_height
        )
        
        # Check if mouse is hovering over exit button
        mouse_pos = pygame.mouse.get_pos()
        is_hovering = exit_button_rect.collidepoint(mouse_pos)
        
        # Draw button with hover feedback - exact shop colors
        exit_button_color = (180, 60, 60) if is_hovering else (120, 50, 50)
        pygame.draw.rect(self.game.screen, exit_button_color, exit_button_rect, border_radius=6)
        pygame.draw.rect(self.game.screen, (200, 150, 150), exit_button_rect, width=2, border_radius=6)
        
        # Draw "EXIT (ESC)" text on button - matching shop format
        exit_font = get_font(14, bold=True)
        exit_text = exit_font.render("EXIT (ESC)", True, (255, 255, 255))
        exit_text_rect = exit_text.get_rect(center=exit_button_rect.center)
        self.game.screen.blit(exit_text, exit_text_rect)
        
        # Register exit button as clickable region
        self._register_inventory_region(exit_button_rect, 'exit_button')

        # Define main panes - start right below header with minimal gap
        left_pane_width = 280
        right_pane_width = panel_w - left_pane_width - 50  # Reduced spacing from 60 to 50
        panes_y = header_box_rect.bottom + 8  # Start 8px below header
        panes_height = footer_box_y - panes_y - 8  # End 8px above footer box
        left_pane_rect = pygame.Rect(panel_rect.x + 15, panes_y, left_pane_width, panes_height)
        right_pane_rect = pygame.Rect(left_pane_rect.right + 20, panes_y, right_pane_width, panes_height)

        # --- Left Pane: Player Info ---
        pygame.draw.rect(self.game.screen, (25, 25, 35), left_pane_rect, border_radius=10) # Outline for left pane
        pygame.draw.rect(self.game.screen, (100, 100, 120), left_pane_rect, width=1, border_radius=10)

        model_frame = pygame.Rect(left_pane_rect.x + 20, left_pane_rect.y + 20, left_pane_width - 40, 150)
        pygame.draw.rect(self.game.screen, (32, 36, 52), model_frame, border_radius=16)
        pygame.draw.rect(self.game.screen, (160, 180, 220), model_frame, width=1, border_radius=16)
        
        # Draw animated player sprite in the model frame
        self._draw_player_model(model_frame)
        
        draw_text(self.game.screen, self.game.player.cls, (model_frame.centerx - 40, model_frame.bottom - 25), (210,210,225), size=20, bold=True)

        # Stats section - draw background box for entire stats area
        stats_section_y = model_frame.bottom + 10
        stats_section_height = left_pane_rect.bottom - stats_section_y - 10
        stats_section_rect = pygame.Rect(left_pane_rect.x + 10, stats_section_y, left_pane_rect.width - 20, stats_section_height)
        
        # Draw stats section background
        pygame.draw.rect(self.game.screen, (32, 36, 52), stats_section_rect, border_radius=8)
        pygame.draw.rect(self.game.screen, (80, 80, 100), stats_section_rect, width=1, border_radius=8)
        
        # Player Stats Header - matching Armory Stock style
        stats_header_height = 30
        stats_header_rect = pygame.Rect(stats_section_rect.x + 4, stats_section_rect.y + 4, stats_section_rect.width - 8, stats_header_height)
        pygame.draw.rect(self.game.screen, (25, 25, 35), stats_header_rect, border_radius=6)
        pygame.draw.rect(self.game.screen, (100, 100, 120), stats_header_rect, width=1, border_radius=6)
        
        header_font = get_font(14, bold=True)
        header_text = header_font.render("Player Stats", True, (205, 200, 215))
        self.game.screen.blit(header_text, (stats_header_rect.x + 10, stats_header_rect.y + 7))
        
        # Stats area starts below header with proper spacing
        stats_y = stats_header_rect.bottom + 12  # Reduced padding from 18 to 12
        status_lines = self._build_player_stats_display()
        
        status_spacing = 22  # Line height - increased for better readability
        
        # Define scrollable stats area - use remaining space in the section box
        stats_area_y = stats_y
        stats_area_height = stats_section_rect.bottom - stats_area_y - 10
        stats_area_rect = pygame.Rect(stats_section_rect.x + 10, stats_y, stats_section_rect.width - 20, stats_area_height)
        self.stats_area_rect = stats_area_rect  # Store for mouse wheel handling
        
        # Calculate total content height
        total_stats_height = len(status_lines) * status_spacing
        
        # Clamp scroll offset
        max_scroll = max(0, total_stats_height - stats_area_height)
        self.stats_scroll_offset = max(0, min(self.stats_scroll_offset, max_scroll))
        
        # Set clipping for stats area - add some padding at top to avoid harsh clipping
        old_clip = self.game.screen.get_clip()
        clip_rect = pygame.Rect(stats_section_rect.x, stats_area_y - 5, stats_section_rect.width, stats_area_height + 5)
        self.game.screen.set_clip(clip_rect)
        
        # Draw stats with scroll offset
        for i, item in enumerate(status_lines):
            y_pos = stats_area_y + (i * status_spacing) - self.stats_scroll_offset
            # Only draw if visible in clipped area
            if y_pos + status_spacing >= stats_area_y and y_pos <= stats_area_rect.bottom:
                # Handle both old format (text, color) and new format (text, color, mod_text, mod_color)
                text_x = stats_area_rect.x + 8  # Good padding from stats area edge
                
                if len(item) == 4:
                    line, color, mod_text, mod_color = item
                    # Draw the base stat
                    draw_text(self.game.screen, line, (text_x, y_pos), color, size=16)
                    # Draw the modifier next to it
                    if mod_text:
                        try:
                            font = get_font(16)
                            main_surface = font.render(line, True, color)
                            main_width = main_surface.get_width()
                            draw_text(self.game.screen, mod_text, (text_x + main_width + 5, y_pos), mod_color, size=16)
                        except:
                            # Fallback
                            draw_text(self.game.screen, mod_text, (text_x + len(line) * 9 + 5, y_pos), mod_color, size=16)
                else:
                    line, color = item
                    draw_text(self.game.screen, line, (text_x, y_pos), color, size=16)
        
        # Restore clip
        self.game.screen.set_clip(old_clip)
        
        # Draw scrollbar only if needed
        if total_stats_height > stats_area_height:
            scrollbar_x = stats_area_rect.right - 10
            scrollbar_y = stats_area_rect.y  
            scrollbar_h = stats_area_height
            
            # Track
            pygame.draw.rect(self.game.screen, (40, 40, 50), (scrollbar_x, scrollbar_y, 8, scrollbar_h), border_radius=4)
            
            # Thumb
            scroll_ratio = self.stats_scroll_offset / max(1, max_scroll)
            thumb_h = max(20, int((stats_area_height / total_stats_height) * scrollbar_h))
            thumb_y = scrollbar_y + int(scroll_ratio * (scrollbar_h - thumb_h))
            pygame.draw.rect(self.game.screen, (180, 180, 200), (scrollbar_x + 1, thumb_y, 6, thumb_h), border_radius=3)

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
            # Default border color; override with rarity color for items
            border_color = (110, 120, 150)
            if item:
                try:
                    border_color = rarity_border_color(item)
                except Exception:
                    border_color = (110, 120, 150)
            is_selected = selection and selection.get('kind') == 'gear_slot' and selection.get('index') == idx
            
            if item:
                pygame.draw.rect(self.game.screen, item.color, rect.inflate(-8, -8), border_radius=6)
                # Draw an inner outline using rarity color to match stock styling
                try:
                    inner_col = rarity_border_color(item)
                except Exception:
                    inner_col = (110, 120, 150)
                try:
                    pygame.draw.rect(self.game.screen, inner_col, rect.inflate(-6, -6), width=3, border_radius=6)
                except Exception:
                    pass
                # Prefer true-alpha icon, else masked placeholder, else letter
                icon_img = None
                if hasattr(item, 'icon_path') and item.icon_path:
                    icon_img = _safe_load_icon(item.icon_path, (rect.width-8, rect.height-8))
                    if not icon_img:
                        icon_img = load_icon_masked(item.icon_path, (rect.width-8, rect.height-8), radius=6)
                if icon_img:
                    self.game.screen.blit(icon_img, icon_img.get_rect(center=rect.center))
                else:
                    icon_surf = icon_font.render(item.icon_letter, True, (20,20,28))
                    self.game.screen.blit(icon_surf, icon_surf.get_rect(center=rect.center))
            else:
                draw_text(self.game.screen, str(idx+1), (rect.centerx-4, rect.centery-8), (80,90,110), size=18)
            # Draw rarity border first
            pygame.draw.rect(self.game.screen, border_color, rect, width=2, border_radius=8)
            # Draw white selection border inside rarity border if selected (thinner, smaller)
            if is_selected:
                pygame.draw.rect(self.game.screen, (255, 255, 255), rect.inflate(-4, -4), width=2, border_radius=6)



        # Consumable Slots (next to armament slots)
        for idx in range(len(self.consumable_slots)):
            rect = pygame.Rect(consumable_slots_x_start + idx * (slot_w + slot_spacing), equipped_slots_y, slot_w, slot_h)
            self._register_inventory_region(rect, 'consumable_slot', index=idx)
            
            stack = self.consumable_slots[idx]
            entry = self.consumable_catalog.get(stack.key) if stack else None

            pygame.draw.rect(self.game.screen, (46, 52, 72), rect, border_radius=8)
            is_selected = selection and selection.get('kind') == 'consumable_slot' and selection.get('index') == idx

            # Draw entry contents regardless of selection; selection only affects border
            if entry:
                pygame.draw.rect(self.game.screen, entry.color, rect.inflate(-8, -8), border_radius=6)
                # Determine border color from rarity (fallback to default)
                try:
                    border_color = rarity_border_color(entry)
                except Exception:
                    border_color = (110, 120, 150)
                # Draw inner rarity outline to match stock styling
                try:
                    inner_col = rarity_border_color(entry)
                except Exception:
                    inner_col = (110, 120, 150)
                try:
                    pygame.draw.rect(self.game.screen, inner_col, rect.inflate(-6, -6), width=3, border_radius=6)
                except Exception:
                    pass
                # Prefer true-alpha icon, else masked placeholder, else letter
                _draw_icon_in_rect(self.game.screen, rect, entry, icon_font, radius=6)
                if stack:
                    total_count = self._total_available_count(stack.key)
                    if total_count > 1:
                        count_font = get_font(16, bold=True)
                        count_surf = count_font.render(str(total_count), True, (250, 250, 255))
                        self.game.screen.blit(count_surf, count_surf.get_rect(bottomright=(rect.right - 4, rect.bottom - 4)))
            else:
                key_label = self._hotkey_label(idx)
                draw_text(self.game.screen, key_label, (rect.centerx-4, rect.centery-8), (80,90,110), size=18)
                border_color = (110, 120, 150)
            # Draw rarity border first
            pygame.draw.rect(self.game.screen, border_color, rect, width=2, border_radius=8)
            # Draw white selection border inside rarity border if selected (thinner, smaller)
            if is_selected:
                pygame.draw.rect(self.game.screen, (255, 255, 255), rect.inflate(-4, -4), width=2, border_radius=6)



        # Stock Panels (Scrollable) - increased height by reducing top spacing
        stock_panel_y = equipped_slots_y + slot_h + 20  # Reduced from 30 to 20
        stock_panel_height = right_pane_rect.bottom - stock_panel_y - 10  # Reduced bottom margin from 20 to 10
        stock_panel_rect = pygame.Rect(right_pane_rect.x + 20, stock_panel_y, right_pane_width - 40, stock_panel_height)
        
        # Split stock area into fixed header and scrollable body
        header_height = 35  # Reduced from 40 to 35
        header_rect = pygame.Rect(stock_panel_rect.x, stock_panel_rect.y, stock_panel_rect.width, header_height)
        body_rect = pygame.Rect(stock_panel_rect.x, stock_panel_rect.y + header_height, stock_panel_rect.width, stock_panel_rect.height - header_height)

        # Header box (title area)
        pygame.draw.rect(self.game.screen, (40, 35, 55), header_rect, border_radius=8)
        pygame.draw.rect(self.game.screen, (120, 110, 150), header_rect, width=1, border_radius=8)

        header_title = "Armory Stock" if self.inventory_stock_mode == 'gear' else "Consumable Stock" if self.inventory_stock_mode == 'consumable' else "Stock"
        header_font = get_font(18, bold=True)
        header_surf = header_font.render(header_title, True, (235, 220, 210))
        self.game.screen.blit(header_surf, (header_rect.x + 12, header_rect.y + 10))

        # Scrollable body box
        pygame.draw.rect(self.game.screen, (35, 30, 45), body_rect, border_radius=10)
        pygame.draw.rect(self.game.screen, (100, 100, 120), body_rect, width=1, border_radius=10)

        # Clipping surface for scrolling (only for body area, header is fixed)
        stock_surface = pygame.Surface(body_rect.size, pygame.SRCALPHA)
        stock_surface.fill((0,0,0,0)) # Transparent background

        grid_padding = 10
        count_font = get_font(16, bold=True)

        current_scroll_offset = 0
        if self.inventory_stock_mode == 'gear':
            # Only show gear that is not already equipped
            available_gear = []
            for key in self.armament_order:
                # Check if this gear is already equipped
                if key not in self.gear_slots:
                    available_gear.append(key)
            keys_to_draw = [self.UNEQUIP_GEAR_KEY, *available_gear]
            current_scroll_offset = self.armament_scroll_offset
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
            keys_to_draw = [self.UNEQUIP_CONSUMABLE_KEY, *available_consumables]
            current_scroll_offset = self.consumable_scroll_offset
        else:
            keys_to_draw = [] # Should not happen with default 'gear'

        # Start grid directly under header inside body surface
        grid_start_y_in_surface = 10
        # Compute columns so the stock grid ends exactly at the scrollbar track.
        # Scrollbar is 20px wide and starts 5px from the right edge of stock_panel_rect.
        # We pack whole cells from left padding up to (right - 25) with no overlap.
        max_grid_width = stock_panel_rect.width - grid_padding * 2 - 25
        cols = max(1, max_grid_width // (slot_w + slot_spacing))
        # Left-align grid within the reserved area before the scrollbar track for predictable hitboxes.
        grid_offset_x = grid_padding
        
        total_content_height = 0
        if keys_to_draw:
            num_rows = (len(keys_to_draw) + cols - 1) // cols
            total_content_height = num_rows * (slot_w + slot_spacing)

        # Clamp scroll so items never overlap the fixed header band
        viewport_height = body_rect.height - grid_start_y_in_surface
        max_scroll = max(0, total_content_height - viewport_height)
        if self.inventory_stock_mode == 'gear':
            current_scroll_offset = max(0, min(max_scroll, self.armament_scroll_offset))
            self.armament_scroll_offset = current_scroll_offset
        elif self.inventory_stock_mode == 'consumable':
            current_scroll_offset = max(0, min(max_scroll, self.consumable_scroll_offset))
            self.consumable_scroll_offset = current_scroll_offset

        # Draw items onto the stock_surface (header stays fixed at top)
        y_offset_in_surface = grid_start_y_in_surface - current_scroll_offset
        
        for i, key in enumerate(keys_to_draw):
            row = i // cols
            col = i % cols
            
            cell_x = col * (slot_w + slot_spacing) + grid_offset_x
            cell_y = y_offset_in_surface + row * (slot_w + slot_spacing)
            
            cell = pygame.Rect(cell_x, cell_y, slot_w, slot_w)
            
            # Only draw if visible within the stock_surface
            if cell.bottom > grid_start_y_in_surface and cell.top < stock_panel_rect.height:
                # Map from body surface to screen coords
                screen_cell = cell.move(body_rect.topleft)
                
                if self.inventory_stock_mode == 'gear':
                    # Only register hit region if not overlapping with footer (to prevent tooltip issues)
                    if screen_cell.bottom < footer_box_y:
                        self._register_inventory_region(screen_cell, 'gear_pool', key=key)
                    if key == self.UNEQUIP_GEAR_KEY:
                        highlighted = bool(selection and selection.get('kind') == 'gear_pool' and selection.get('key') == key)
                        self._draw_unequip_stock_cell(stock_surface, cell, 'gear', icon_font, highlighted)
                        continue
                    entry = self.armament_catalog.get(key)
                    if not entry:
                        continue
                    # Draw inner panel (match slot behavior) and inner rarity outline
                    inner_panel = cell.inflate(-8, -8)
                    pygame.draw.rect(stock_surface, entry.color, inner_panel, border_radius=6)
                    # Default border color; override with rarity color for items (like equipped slots)
                    border_col = (110, 120, 150)
                    try:
                        border_col = rarity_border_color(entry)
                    except Exception:
                        border_col = (110, 120, 150)
                    is_selected = selection and selection.get('kind') in ('gear_pool', 'gear_slot') and selection.get('key') == key
                    # Show equipped items with green border
                    equipped_count = self.gear_slots.count(key)
                    if equipped_count > 0:
                        border_col = (120, 230, 180)
                    # Draw inner rarity outline so stock items show rarity like slots
                    try:
                        inner_col = rarity_border_color(entry)
                    except Exception:
                        inner_col = (110, 120, 150)
                    try:
                        pygame.draw.rect(stock_surface, inner_col, inner_panel.inflate(-2, -2), width=3, border_radius=6)
                    except Exception:
                        pass
                    # Draw the icon at the same size as equipped slots (48x48)
                    icon_img = None
                    if hasattr(entry, 'icon_path') and entry.icon_path:
                        icon_img = _safe_load_icon(entry.icon_path, (inner_panel.width, inner_panel.height))
                        if not icon_img:
                            icon_img = load_icon_masked(entry.icon_path, (inner_panel.width, inner_panel.height), radius=6)
                    if icon_img:
                        stock_surface.blit(icon_img, icon_img.get_rect(center=inner_panel.center))
                    else:
                        icon_surf = icon_font.render(entry.icon_letter, True, (20,20,28))
                        stock_surface.blit(icon_surf, icon_surf.get_rect(center=inner_panel.center))
                    # Draw rarity border first
                    pygame.draw.rect(stock_surface, border_col, cell, width=2, border_radius=8)
                    # Draw white selection border inside rarity border if selected (thinner, smaller)
                    if is_selected:
                        pygame.draw.rect(stock_surface, (255, 255, 255), cell.inflate(-4, -4), width=2, border_radius=6)
                elif self.inventory_stock_mode == 'consumable':
                    # Only register hit region if not overlapping with footer (to prevent tooltip issues)
                    if screen_cell.bottom < footer_box_y:
                        self._register_inventory_region(screen_cell, 'consumable_pool', key=key)
                    if key == self.UNEQUIP_CONSUMABLE_KEY:
                        highlighted = bool(selection and selection.get('kind') == 'consumable_pool' and selection.get('key') == key)
                        self._draw_unequip_stock_cell(stock_surface, cell, 'consumable', icon_font, highlighted)
                        continue
                    entry = self.consumable_catalog.get(key)
                    if not entry:
                        continue
                    # Draw inner panel (match slot behavior) and inner rarity outline
                    inner_panel = cell.inflate(-8, -8)
                    pygame.draw.rect(stock_surface, entry.color, inner_panel, border_radius=6)
                    # Default border color; override with rarity color for items (like equipped slots)
                    border_col = (110, 120, 150)
                    try:
                        border_col = rarity_border_color(entry)
                    except Exception:
                        border_col = (110, 120, 150)
                    is_selected = selection and selection.get('kind') in ('consumable_pool', 'consumable_slot') and selection.get('key') == key
                    if any(s and s.key == key for s in self.consumable_slots):
                        border_col = (120, 230, 180)
                    # Draw inner rarity outline so stock items show rarity like slots
                    try:
                        inner_col = rarity_border_color(entry)
                    except Exception:
                        inner_col = (110, 120, 150)
                    try:
                        pygame.draw.rect(stock_surface, inner_col, inner_panel.inflate(-2, -2), width=3, border_radius=6)
                    except Exception:
                        pass
                    # Draw the icon at the same size as equipped slots (48x48)
                    icon_img = None
                    if hasattr(entry, 'icon_path') and entry.icon_path:
                        icon_img = _safe_load_icon(entry.icon_path, (inner_panel.width, inner_panel.height))
                        if not icon_img:
                            icon_img = load_icon_masked(entry.icon_path, (inner_panel.width, inner_panel.height), radius=6)
                    if icon_img:
                        stock_surface.blit(icon_img, icon_img.get_rect(center=inner_panel.center))
                    else:
                        icon_surf = icon_font.render(entry.icon_letter, True, (20,20,28))
                        stock_surface.blit(icon_surf, icon_surf.get_rect(center=inner_panel.center))
                    
                    # Display the count for consumables in stock
                    total_count = self._total_available_count(key)
                    if total_count > 0:
                        count_surface = count_font.render(str(total_count), True, (250, 250, 255))
                        count_rect = count_surface.get_rect(bottomright=(cell.right - 4, cell.bottom - 4))
                        stock_surface.blit(count_surface, count_rect)
                    # Draw rarity border first
                    pygame.draw.rect(stock_surface, border_col, cell, width=2, border_radius=8)
                    # Draw white selection border inside rarity border if selected (thinner, smaller)
                    if is_selected:
                        pygame.draw.rect(stock_surface, (255, 255, 255), cell.inflate(-4, -4), width=2, border_radius=6)
        

        
        # Blit scrollable content just under the fixed header
        self.game.screen.blit(stock_surface, body_rect.topleft)

        # Scrollbar (simple up/down arrows) inside item body only
        # Use body_rect height for viewport since header is fixed
        viewport_height = body_rect.height - grid_start_y_in_surface
        if total_content_height > viewport_height:
            scrollbar_width = 20
            scrollbar_height_area = body_rect.height - grid_start_y_in_surface - 10  # 10 for padding
            scrollbar_x = body_rect.right - scrollbar_width - 5
            scrollbar_y = body_rect.y + grid_start_y_in_surface + 5

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
                stock_rect=body_rect,
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
                stock_rect=body_rect,
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


        # Tooltip - don't show for exit button or scroll buttons
        hover_info = self._inventory_hit_test(pygame.mouse.get_pos())
        if hover_info and hover_info.get('kind') not in ('exit_button', 'scroll_up', 'scroll_down'):
            self._draw_inventory_tooltip(hover_info)

    def draw_consumable_hotbar(self):
        """Draw the consumable hotbar in the HUD."""
        if not self.consumable_slots:
            return
        slot_size = 40  # Reduced from 56 to 40 to match skill bar
        slot_area_height = slot_size + 18
        spacing = 6  # Match skill bar spacing
        count = len(self.consumable_slots)
        # Calculate position to continue after skill bar
        total_slots = 6  # 3 skills + 3 consumables
        total_w = slot_size * total_slots + spacing * (total_slots - 1)
        start_x = (WIDTH - total_w) // 2 + (slot_size * 3 + spacing * 3)  # Continue after 3 skill slots
        start_y = 16  # Same height as skill bar
        name_font = get_font(10)  # Reduced from 12
        count_font = get_font(14, bold=True)  # Reduced from 16
        for idx, stack in enumerate(self.consumable_slots):
            rect = pygame.Rect(start_x + idx * (slot_size + spacing), start_y, slot_size, slot_size)
            pygame.draw.rect(self.game.screen, (40, 40, 50), rect, border_radius=8)
            inner = rect.inflate(-10, -10)
            entry = self.consumable_catalog.get(stack.key) if stack else None
            # Use rarity-based border color for items
            border_color = (90, 90, 120)  # Default border color
            if entry:
                try:
                    border_color = rarity_border_color(entry)
                except Exception:
                    border_color = (90, 90, 120)
            pygame.draw.rect(self.game.screen, border_color, rect, width=2, border_radius=8)
            if entry:
                # Draw icon using new system (same as inventory slots)
                icon_img = None
                if hasattr(entry, 'icon_path') and entry.icon_path:
                    icon_img = _safe_load_icon(entry.icon_path, (inner.width, inner.height))
                    if not icon_img:
                        icon_img = load_icon_masked(entry.icon_path, (inner.width, inner.height), radius=6)
                if icon_img:
                    self.game.screen.blit(icon_img, icon_img.get_rect(center=inner.center))
                else:
                    # Fallback to old system for items without icons
                    pygame.draw.rect(self.game.screen, entry.color, inner, border_radius=6)
                    if entry.icon_letter:
                        icon_font = get_font(14, bold=True)  # Reduced from 18
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
            
            # Draw key number in top-left corner LAST (so it's on top of everything)
            key_label = self._hotkey_label(idx)
            draw_text(self.game.screen, key_label, (rect.x + 3, rect.y + 2), (220, 230, 255), size=11, bold=True)

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
                # Deep-merge modifiers into stats dict. Some modifiers are fractional (percentages).
                if mod_key in ('lifesteal_pct', 'spell_lifesteal', 'spell_lifesteal_pct'):
                    # Normalize 'spell_lifesteal' variant
                    if mod_key == 'spell_lifesteal':
                        mod_key_norm = 'spell_lifesteal'
                    elif mod_key == 'spell_lifesteal_pct':
                        mod_key_norm = 'spell_lifesteal'
                    else:
                        mod_key_norm = mod_key
                    stats[mod_key_norm] = stats.get(mod_key_norm, 0.0) + float(value)
                else:
                    stats[mod_key] = stats.get(mod_key, 0.0) + value
        stamina_mult = getattr(player, 'stamina_buff_mult', 1.0)
        stats['max_stamina'] = stats.get('max_stamina', 0.0) * stamina_mult
        default_max_hp = getattr(player, 'max_hp', base.get('max_hp', 1))
        player.max_hp = max(1, int(round(stats.get('max_hp', default_max_hp) or default_max_hp)))
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
        
        # Update percentage lifesteal values on the player's combat component
        try:
            if hasattr(player, 'combat') and player.combat:
                # Base lifesteal from equipment + base stats
                base_lifesteal_pct = stats.get('lifesteal_pct', getattr(player.combat, 'lifesteal_pct', 0.0) or 0.0)
                # Support both 'spell_lifesteal' and 'spell_lifesteal_pct' modifier keys
                base_spell_lifesteal = stats.get('spell_lifesteal', stats.get('spell_lifesteal_pct', getattr(player.combat, 'spell_lifesteal_pct', 0.0) or 0.0))
                # Preserve temporary buffs from power skill - _power_buff_lifesteal_add may be set
                power_add = getattr(player.combat, '_power_buff_lifesteal_add', 0.0)
                power_spell_add = getattr(player.combat, '_power_buff_spell_lifesteal_add', 0.0)
                player.combat.lifesteal_pct = float(base_lifesteal_pct) + float(power_add)
                player.combat.spell_lifesteal_pct = float(base_spell_lifesteal) + float(power_spell_add)
                try:
                    logger.debug("recalculate_player_stats: base_lifesteal=%s base_spell_lifesteal=%s power_add=%s power_spell_add=%s final_lifesteal=%s final_spell_lifesteal=%s gear_slots=%s",
                                 base_lifesteal_pct, base_spell_lifesteal, power_add, power_spell_add, player.combat.lifesteal_pct, player.combat.spell_lifesteal_pct, self.gear_slots)
                except Exception:
                    pass
        except Exception:
            pass

        # Apply attack speed modifier (reduces attack cooldown)
        attack_speed_bonus = stats.get('attack_speed', 0.0)
        player.attack_speed_mult = 1.0 + attack_speed_bonus  # 0.15 = 15% faster = 1.15x multiplier
        
        # Apply skill cooldown reduction
        skill_cdr = stats.get('skill_cooldown_reduction', 0.0)
        player.skill_cooldown_mult = 1.0 - skill_cdr  # 0.20 = 20% reduction = 0.8x multiplier
        
        # Apply dash stamina cost multiplier
        player.dash_stamina_mult = stats.get('dash_stamina_cost_mult', 1.0)
        
        # Apply extra dash charges
        player.extra_dash_charges = int(stats.get('extra_dash_charges', 0))
        
        # Apply poison damage boost
        player.poison_damage_mult = 1.0 + stats.get('poison_damage_pct', 0.0)
        
        # Apply skill damage boost
        player.skill_damage_mult = 1.0 + stats.get('skill_damage_mult', 0.0)
        
        # Clear on-hit effects cache when equipment changes
        try:
            from src.systems.on_hit_effects import clear_on_hit_cache
            clear_on_hit_cache()
        except Exception:
            pass  # Fail silently if on-hit effects system has issues
