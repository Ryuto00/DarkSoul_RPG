import pygame
import random
from config import WIDTH, HEIGHT, WHITE, GREEN, CYAN, FPS
from ..core.utils import draw_text, get_font
from .items import build_consumable_catalog, build_armament_catalog, load_icon, icon_has_transparency, load_icon_masked, rarity_border_color
from typing import Optional, List, Dict, Tuple
from ..entities.entities import floating, DamageNumber


def _safe_load_icon(path: str, size: tuple = (24,24)) -> Optional[pygame.Surface]:
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
        return None
    return None

import random as _rnd

# Enhanced rarity weights for better distribution
RARITY_WEIGHTS = {
    'Normal': 50,
    'Rare': 30,
    'Epic': 15,
    'Legendary': 5,
}

# Consumable rarity weights for stock determination
CONSUMABLE_RARITY_WEIGHTS = {
    'Normal': 60,
    'Rare': 25,
    'Epic': 10,
    'Legendary': 5,
}


class Shop:
    def __init__(self, game):
        self.game = game
        self.shop_open = False
        self.selection = 0
        self.selection_category = 'gear'  # 'gear' or 'consumable'
        self.shop_consumables = build_consumable_catalog()
        self.shop_equipment = build_armament_catalog()
        
        # Track stock amounts for consumables
        self.consumable_stock = {}  # {item_key: available_stock}
        
        # Track which equipment has been purchased this shop visit
        self.purchased_equipment = set()  # {item_key}
        
        # New shop inventory with 5 gear slots and 3 consumables
        self.selected_gear = []  # 5 items
        self.selected_consumables = []  # 3 items
        
        # Scrolling support
        self.gear_scroll_offset = 0
        self.consumable_scroll_offset = 0
        self.max_visible_gear = 5  # Maximum gear items visible at once
        self.max_visible_consumables = 3  # Maximum consumable items visible at once
        self.player_info_scroll_offset = 0  # Scroll offset for player stats
        
        # UI regions for interaction
        self.regions = []
        self.hover_item = None
        self.hover_button = None
        
        # Buy button feedback
        self.buy_button_clicked = False
        self.buy_button_click_time = 0
        
        # Slot selection state for viewing inventory stock
        self.selected_slot_type = None  # 'gear' or 'consumable'
        self.selected_slot_index = None  # Which slot (0-2)
        self.stock_scroll_offset = 0  # Scroll offset for stock view

        # Persisted rects for robust input handling
        self.panel_rect = None
        self.left_rect = None
        self.middle_rect = None
        self.right_rect = None
        self.left_grid_rect = None
        self.right_stock_grid_rect = None
        self.right_stats_area_rect = None
        
        # Create initial inventory
        self.refresh_inventory()

    
    def _get_max_visible(self):
        """Get max visible items for current category"""
        if self.selection_category == 'gear':
            return self.max_visible_gear
        else:
            return self.max_visible_consumables
        
    def refresh_inventory(self):
        """Create random selection of 5 gear items and 3 consumables with rarity-based spawn rates"""
        # Clear previous stock and purchased equipment tracking
        self.consumable_stock = {}
        self.purchased_equipment = set()
        
        # Generate 5 gear items with enhanced rarity system
        self.selected_gear = self._generate_gear_selection(5)
        
        # Generate 3 consumables with improved stock system
        self.selected_consumables = self._generate_consumable_selection(3)
        
        # Combine for easier iteration
        self.shop_items = self.selected_gear + self.selected_consumables
        
    def _generate_gear_selection(self, count: int) -> List:
        """Generate gear selection with enhanced rarity distribution"""
        pool = list(self.shop_equipment.values())
        weights = [RARITY_WEIGHTS.get(getattr(item, 'rarity', 'Normal'), 1) for item in pool]
        selected = []
        
        for _ in range(min(count, len(pool))):
            if not pool:
                break
                
            total = sum(weights)
            if total <= 0:
                break
                
            r = _rnd.random() * total
            cum = 0.0
            idx = 0
            
            for i, w in enumerate(weights):
                cum += w
                if r <= cum:
                    idx = i
                    break
                    
            selected.append(pool.pop(idx))
            weights.pop(idx)
            
        return selected
    
    def _generate_consumable_selection(self, count: int) -> List:
        """Generate consumable selection with rarity-based spawning"""
        pool = list(self.shop_consumables.values())
        weights = [CONSUMABLE_RARITY_WEIGHTS.get(getattr(item, 'rarity', 'Normal'), 1) for item in pool]
        selected = []
        
        for _ in range(min(count, len(pool))):
            if not pool:
                break
                
            total = sum(weights)
            if total <= 0:
                break
                
            r = _rnd.random() * total
            cum = 0.0
            idx = 0
            
            for i, w in enumerate(weights):
                cum += w
                if r <= cum:
                    idx = i
                    break
                    
            selected.append(pool.pop(idx))
            weights.pop(idx)
            
            # Generate stock based on rarity for selected consumable
            item = selected[-1]
            rarity = getattr(item, 'rarity', 'Normal') if hasattr(item, 'rarity') else 'Normal'
            stock = self._generate_consumable_stock(rarity)
            self.consumable_stock[item.key] = stock
            
        return selected
    
    def _generate_consumable_stock(self, rarity: str) -> int:
        """Generate stock amount based on consumable rarity"""
        if rarity == 'Normal':
            return random.randint(3, 5)  # Common items have more stock
        elif rarity == 'Rare':
            return random.randint(2, 4)
        elif rarity == 'Epic':
            return random.randint(1, 3)
        elif rarity == 'Legendary':
            return random.randint(1, 2)  # Legendary items are rare
        else:
            return random.randint(1, 3)  # Default
    

    
    def open_shop(self):
        """Open shop interface"""
        self.shop_open = True
        self.selection = 0
        self.selection_category = 'gear'
        self.refresh_inventory()
        
    def close_shop(self):
        """Close shop interface"""
        self.shop_open = False
        self.selection = 0
        self.selection_category = 'gear'
        self.regions = []
        self.hover_item = None
    
    def can_afford(self, item):
        """Check if player can afford an item"""
        price = self._get_item_price(item)
        return self.game.player.money >= price
    
    def purchase_item(self, item):
        """Attempt to purchase an item"""
        price = self._get_item_price(item)
        
        if self.game.player.money < price:
            floating.append(DamageNumber(
                self.game.player.rect.centerx,
                self.game.player.rect.top - 12,
                "Not enough coins!",
                (255, 100, 100)
            ))
            return False
        
        # Check if consumable has stock available
        if hasattr(item, 'use'):  # Consumable
            if item.key in self.consumable_stock:
                if self.consumable_stock[item.key] <= 0:
                    floating.append(DamageNumber(
                        self.game.player.rect.centerx,
                        self.game.player.rect.top - 12,
                        "Out of stock!",
                        (255, 100, 100)
                    ))
                    return False
        # Check if equipment has already been purchased this shop visit or already owned
        elif hasattr(item, 'modifiers'):  # Equipment
            player_owns_item = False
            if hasattr(self.game, 'inventory'):
                player_owns_item = item.key in self.game.inventory.armament_order
                
            if item.key in self.purchased_equipment:
                floating.append(DamageNumber(
                    self.game.player.rect.centerx,
                    self.game.player.rect.top - 12,
                    "Already purchased this visit!",
                    (255, 200, 100)
                ))
                return False
            elif player_owns_item:
                floating.append(DamageNumber(
                    self.game.player.rect.centerx,
                    self.game.player.rect.top - 12,
                    "Already owned!",
                    (255, 200, 100)
                ))
                return False
        
        # Deduct money
        self.game.player.money -= price
        
        # Handle different item types
        if hasattr(item, 'use'):  # Consumable
            # Add to inventory
            if hasattr(self.game, 'inventory'):
                added = self.game.inventory.add_consumable(item.key, 1)
                if added > 0:
                    # Decrease stock
                    if item.key in self.consumable_stock:
                        self.consumable_stock[item.key] -= 1
                    
                    floating.append(DamageNumber(
                        self.game.player.rect.centerx,
                        self.game.player.rect.top - 12,
                        f"Purchased {item.name}",
                        GREEN
                    ))
                else:
                    # Refund if couldn't add to inventory
                    self.game.player.money += price
                    floating.append(DamageNumber(
                        self.game.player.rect.centerx,
                        self.game.player.rect.top - 12,
                        "Inventory full!",
                        (255, 100, 100)
                    ))
                    return False
            else:
                # Fallback: use immediately if no inventory system
                success = item.use(self.game)
                if success:
                    # Decrease stock
                    if item.key in self.consumable_stock:
                        self.consumable_stock[item.key] -= 1
                    
                    floating.append(DamageNumber(
                        self.game.player.rect.centerx,
                        self.game.player.rect.top - 12,
                        f"Purchased {item.name}",
                        GREEN
                    ))
                else:
                    # Refund if item couldn't be used
                    self.game.player.money += price
                    return False
        else:  # Equipment
            self._add_shop_item_to_inventory(item)
            # Mark this equipment as purchased for this shop visit
            self.purchased_equipment.add(item.key)
            floating.append(DamageNumber(
                self.game.player.rect.centerx,
                self.game.player.rect.top - 12,
                f"Purchased {item.name}",
                GREEN
            ))
        
        return True
    
    def _add_shop_item_to_inventory(self, equipment):
        """Add purchased equipment to inventory storage"""
        if hasattr(self.game, 'inventory'):
            # Add to armament order if not already there
            if equipment.key not in self.game.inventory.armament_order:
                self.game.inventory.armament_order.append(equipment.key)
        else:
            # Fallback: apply modifiers directly to player
            player = self.game.player
            for stat, value in equipment.modifiers.items():
                if hasattr(player, stat):
                    setattr(player, stat, getattr(player, stat) + value)
    
    def handle_input(self):
        """Handle shop input - this method is deprecated, use handle_event instead"""
        pass
    
    def handle_event(self, event):
        """Handle shop events properly using event-based input"""
        if event.type == pygame.MOUSEWHEEL:
            # Detect which column the mouse is over for targeted scrolling
            mouse_pos = pygame.mouse.get_pos()
            # Return the result of the scroll handler.
            # This will be True if a column was scrolled, and False if not.
            return self._handle_mousewheel_scroll(mouse_pos, event.y)
        
        elif event.type == pygame.KEYDOWN:
            # Navigation - LEFT/RIGHT switch between categories (spatial navigation)
            if event.key in [pygame.K_LEFT, pygame.K_a]:
                if self.selection_category == 'consumable':
                    # Consumables are on the right, LEFT goes to gear (left neighbor)
                    self.selection_category = 'gear'
                    # Keep same index if possible, otherwise clamp to valid range
                    self.selection = min(self.selection, len(self.selected_gear) - 1) if self.selected_gear else 0
                    self.gear_scroll_offset = max(0, self.selection - self.max_visible_gear + 1)
                return True  # Event handled
            
            elif event.key in [pygame.K_RIGHT, pygame.K_d]:
                if self.selection_category == 'gear':
                    # Gear is on the left, RIGHT goes to consumables (right neighbor)
                    self.selection_category = 'consumable'
                    # Keep same index if possible, otherwise clamp to valid range
                    self.selection = min(self.selection, len(self.selected_consumables) - 1) if self.selected_consumables else 0
                    self.consumable_scroll_offset = max(0, self.selection - self.max_visible_consumables + 1)
                return True  # Event handled
            
            elif event.key in [pygame.K_UP, pygame.K_w]:
                # Move up in current category
                if self.selection > 0:
                    self.selection -= 1
                    # Adjust scroll offset if selection moves off-screen
                    if self.selection_category == 'gear':
                        if self.selection < self.gear_scroll_offset:
                            self.gear_scroll_offset = max(0, self.selection)
                    else:  # consumable
                        if self.selection < self.consumable_scroll_offset:
                            self.consumable_scroll_offset = max(0, self.selection)
                return True  # Event handled
            
            elif event.key in [pygame.K_DOWN, pygame.K_s]:
                # Move down in current category
                max_items = len(self.selected_gear) if self.selection_category == 'gear' else len(self.selected_consumables)
                if self.selection < max_items - 1:
                    self.selection += 1
                    # Adjust scroll offset if selection moves off-screen
                    if self.selection_category == 'gear':
                        last_visible_index = self.gear_scroll_offset + self.max_visible_gear - 1
                        if self.selection > last_visible_index:
                            self.gear_scroll_offset = self.selection - (self.max_visible_gear - 1)
                            # Ensure scroll offset doesn't exceed maximum
                            max_scroll = max(0, len(self.selected_gear) - self.max_visible_gear)
                            self.gear_scroll_offset = min(self.gear_scroll_offset, max_scroll)
                    else:  # consumable
                        last_visible_index = self.consumable_scroll_offset + self.max_visible_consumables - 1
                        if self.selection > last_visible_index:
                            self.consumable_scroll_offset = self.selection - (self.max_visible_consumables - 1)
                            # Ensure scroll offset doesn't exceed maximum
                            max_scroll = max(0, len(self.selected_consumables) - self.max_visible_consumables)
                            self.consumable_scroll_offset = min(self.consumable_scroll_offset, max_scroll)
                return True  # Event handled
            
            # Purchase/Select action
            elif event.key in [pygame.K_RETURN, pygame.K_SPACE]:
                self._handle_selection()
                return True  # Event handled
            
            # Scrolling
            elif event.key == pygame.K_PAGEUP:
                self._scroll_up()
                return True  # Event handled
            elif event.key == pygame.K_PAGEDOWN:
                self._scroll_down()
                return True  # Event handled
            elif event.key == pygame.K_HOME:
                self._scroll_to_top()
                return True  # Event handled
            elif event.key == pygame.K_END:
                self._scroll_to_bottom()
                return True  # Event handled
            
            # Close shop
            elif event.key in [pygame.K_ESCAPE, pygame.K_i]:
                self.close_shop()
                return True  # Event handled
        
        # If no event was handled, return False
        return False
    
    def _handle_selection(self):
        """Handle current selection"""
        if self.selection_category == 'gear':
            if 0 <= self.selection < len(self.selected_gear):
                item = self.selected_gear[self.selection]
                self.purchase_item(item)
        elif self.selection_category == 'consumable':
            if 0 <= self.selection < len(self.selected_consumables):
                item = self.selected_consumables[self.selection]
                self.purchase_item(item)
    
    def _get_item_at_pos(self, pos):
        """Get shop item at mouse position"""
        for info in self.regions:
            if info['rect'].collidepoint(pos):
                return info.get('item')
        return None
    
    def _get_player_stats_with_preview(self, preview_item=None) -> Dict[str, Tuple[str, str]]:
        """Get player stats with optional preview of item effects"""
        player = self.game.player
        stats = {}
        
        # Base stats
        base_hp = getattr(player, 'max_hp', 0)
        base_attack = getattr(player, 'attack_damage', 0)
        base_mana = getattr(player, 'max_mana', 0)
        base_stamina = getattr(player, 'max_stamina', 0)
        base_speed = getattr(player, 'player_speed', 0)
        
        # Current stats (with equipment)
        current_hp = base_hp
        current_attack = base_attack
        current_mana = base_mana
        current_stamina = base_stamina
        current_speed = base_speed
        
        # Add current equipment effects
        if hasattr(self.game, 'inventory'):
            for key in self.game.inventory.gear_slots:
                if key and key in self.game.inventory.armament_catalog:
                    item = self.game.inventory.armament_catalog[key]
                    for stat, value in item.modifiers.items():
                        if stat == 'max_hp':
                            current_hp += value
                        elif stat == 'attack_damage':
                            current_attack += value
                        elif stat == 'max_mana':
                            current_mana += value
                        elif stat == 'max_stamina':
                            current_stamina += value
                        elif stat == 'player_speed':
                            current_speed += value
        
        # Preview item effects
        preview_hp = current_hp
        preview_attack = current_attack
        preview_mana = current_mana
        preview_stamina = current_stamina
        preview_speed = current_speed
        
        if preview_item and hasattr(preview_item, 'modifiers'):
            for stat, value in preview_item.modifiers.items():
                if stat == 'max_hp':
                    preview_hp += value
                elif stat == 'attack_damage':
                    preview_attack += value
                elif stat == 'max_mana':
                    preview_mana += value
                elif stat == 'max_stamina':
                    preview_stamina += value
                elif stat == 'player_speed':
                    preview_speed += value
        
        # Format stats
        stats['hp'] = (f"{player.hp}/{current_hp}", f"→ {player.hp}/{preview_hp}" if preview_hp != current_hp else "")
        stats['attack'] = (str(current_attack), f"→ {preview_attack}" if preview_attack != current_attack else "")
        stats['mana'] = (f"{player.mana:.1f}/{current_mana:.1f}", f"→ {player.mana:.1f}/{preview_mana:.1f}" if preview_mana != current_mana else "")
        stats['stamina'] = (f"{player.stamina:.1f}/{current_stamina:.1f}", f"→ {player.stamina:.1f}/{preview_stamina:.1f}" if preview_stamina != current_stamina else "")
        stats['speed'] = (f"{current_speed:.1f}", f"→ {preview_speed:.1f}" if preview_speed != current_speed else "")
        
        return stats
    
    def _draw_shop_tooltip(self, screen, item, mouse_pos):
        """Draw enhanced tooltip for shop item with stat comparisons.

        Draw onto whatever surface is passed. Use `draw_tooltip_overlay` to
        render the tooltip last from the main draw loop so it appears on top
        of all UI elements.
        """
        if not item:
            return

        lines = item.tooltip_lines()
        if not lines:
            return
        # Insert rarity line after the effect text if present, otherwise after the name
        try:
            rarity = getattr(item, 'rarity', 'Normal')
            rarity_line = f"Rarity: {rarity}"
            insert_index = 1  # default after name
            if hasattr(item, 'effect_text') and item.effect_text:
                # find first occurrence of effect_text in lines
                for idx, l in enumerate(lines):
                    if l == item.effect_text:
                        insert_index = idx + 1
                        break
            lines.insert(insert_index, rarity_line)
        except Exception:
            pass

        # Add stock and ownership information for consumables
        if hasattr(item, 'use'):  # Consumable
            player_owned = 0
            if hasattr(self.game, 'inventory'):
                player_owned = self.game.inventory._total_available_count(item.key)

            available_stock = self.consumable_stock.get(item.key, 0)
            lines.append(f"You own: {player_owned}")
            lines.append(f"Available: {available_stock}")
        # Add purchase status information for equipment
        elif hasattr(item, 'modifiers'):  # Equipment
            player_owns_item = False
            if hasattr(self.game, 'inventory'):
                player_owns_item = item.key in self.game.inventory.armament_order

            if item.key in self.purchased_equipment:
                lines.append("Already purchased this visit")
            elif player_owns_item:
                lines.append("Already owned")
            else:
                # Add stat preview for equipment
                stats = self._get_player_stats_with_preview(item)
                if stats['attack'][1]:  # If attack would change
                    lines.append(f"Attack: {stats['attack'][0]} {stats['attack'][1]}")
                if stats['hp'][1]:  # If HP would change
                    lines.append(f"HP: {stats['hp'][0]} {stats['hp'][1]}")
                if stats['speed'][1]:  # If speed would change
                    lines.append(f"Speed: {stats['speed'][0]} {stats['speed'][1]}")

        font = get_font(16)
        name_font = get_font(18, bold=True)
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

        tooltip_rect = pygame.Rect(mouse_pos[0] + 18, mouse_pos[1] + 18, width, height)

        # Ensure tooltip is fully on-screen (clamp to margins)
        min_margin = 8
        if tooltip_rect.right > WIDTH - min_margin:
            tooltip_rect.x = WIDTH - width - min_margin
        if tooltip_rect.bottom > HEIGHT - min_margin:
            tooltip_rect.y = HEIGHT - height - min_margin
        if tooltip_rect.x < min_margin:
            tooltip_rect.x = min_margin
        if tooltip_rect.y < min_margin:
            tooltip_rect.y = min_margin

        # Draw tooltip background
        pygame.draw.rect(screen, (28, 28, 38), tooltip_rect, border_radius=8)
        pygame.draw.rect(screen, (180, 170, 200), tooltip_rect, width=1, border_radius=8)

        # Draw rarity border accent around tooltip
        try:
            border_col = rarity_border_color(item)
            # Draw a thin accent border inset so it doesn't overlap the outer border
            inner = tooltip_rect.inflate(-4, -4)
            pygame.draw.rect(screen, border_col, inner, width=2, border_radius=6)
        except Exception:
            pass

        # Draw icon
        icon_rect = pygame.Rect(tooltip_rect.x + 10, tooltip_rect.y + 10, 24, 24)
        icon_surf = None
        if hasattr(item, 'icon_path') and item.icon_path:
            surf = _safe_load_icon(item.icon_path, (24,24))
            if surf:
                icon_surf = surf
            else:
                try:
                    icon_surf = load_icon_masked(item.icon_path, (24,24), radius=6)
                except Exception:
                    icon_surf = None
        if icon_surf:
            screen.blit(icon_surf, icon_rect)
        else:
            pygame.draw.rect(screen, item.color, icon_rect, border_radius=6)
            if hasattr(item, 'icon_letter'):
                icon_font = get_font(14, bold=True)
                icon_surf2 = icon_font.render(item.icon_letter, True, (10, 10, 20))
                screen.blit(icon_surf2, icon_surf2.get_rect(center=icon_rect.center))

        # Draw text
        text_x = tooltip_rect.x + 10 + icon_space
        for i, line in enumerate(lines):
            # Different colors and sizes for different tooltip parts
            if i == 0:  # Name line (bigger and gold)
                text_font = get_font(18, bold=True)
                text_color = (255, 215, 0)  # Gold color for name
            # Rarity line detection (we insert as 'Rarity: <Name>')
            if isinstance(line, str) and line.startswith("Rarity:"):
                text_font = get_font(16, bold=True)
                # Parse rarity name and get the border color
                try:
                    rarity_name = line.split(':', 1)[1].strip()
                except Exception:
                    rarity_name = getattr(item, 'rarity', 'Normal') if item else 'Normal'
                try:
                    rarity_col = rarity_border_color(rarity_name)
                except Exception:
                    rarity_col = (200, 200, 200)
                text_color = rarity_col
                # Draw a small swatch before the text
                swatch_size = 10
                sw_x = text_x
                sw_y = tooltip_rect.y + 6 + i * 22 + (16 - swatch_size) // 2
                try:
                    pygame.draw.rect(screen, rarity_col, (sw_x, sw_y, swatch_size, swatch_size), border_radius=2)
                    pygame.draw.rect(screen, (10,10,10), (sw_x, sw_y, swatch_size, swatch_size), width=1, border_radius=2)
                except Exception:
                    pass
                # Shift text_x to account for swatch + gap
                text_to_draw_x = text_x + swatch_size + 6
                screen.blit(text_font.render(line, True, text_color), (text_to_draw_x, tooltip_rect.y + 6 + i * 22))
            elif i == 1 and hasattr(item, 'effect_text') and item.effect_text:  # Effect text (cyan and normal size)
                text_font = get_font(16)
                text_color = (100, 200, 255)  # Cyan color for effect
                screen.blit(text_font.render(line, True, text_color), (text_x, tooltip_rect.y + 6 + i * 22))
            else:  # Description and flavor (white and normal size)
                text_font = get_font(16)
                text_color = (230, 230, 245)  # Light gray/white for description
                screen.blit(text_font.render(line, True, text_color), (text_x, tooltip_rect.y + 6 + i * 22))
    
    def draw(self, screen):
        """Draw 3-column shop interface (inventory-style)"""
        if not self.shop_open:
            return

        # Clear any clipping state to ensure UI renders fully
        try:
            screen.set_clip(None)
        except Exception:
            pass

        # Clear regions FIRST before any drawing to ensure fresh state
        self.regions = []
        
        # Darken background
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))
        
        # Calculate panel dimensions
        margin = 40
        panel_width = WIDTH - (margin * 2)
        panel_height = HEIGHT - (margin * 2)
        panel_x = margin
        panel_y = margin
        
        panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        pygame.draw.rect(screen, (30, 28, 40), panel_rect, border_radius=12)
        pygame.draw.rect(screen, (210, 200, 170), panel_rect, width=2, border_radius=12)
        
        # Decorative header block (old RPG style)
        header_height = 60
        header_rect = pygame.Rect(panel_x + 10, panel_y + 10, panel_width - 20, header_height)
        # Ornate header background
        pygame.draw.rect(screen, (50, 45, 60), header_rect, border_radius=8)
        pygame.draw.rect(screen, (180, 160, 120), header_rect, width=3, border_radius=8)
        # Inner decorative border
        inner_header = header_rect.inflate(-10, -10)
        pygame.draw.rect(screen, (160, 140, 100), inner_header, width=1, border_radius=6)
        
        # Title with shadow effect
        title_font = get_font(28, bold=True)
        # Shadow
        shadow_text = title_font.render("MYSTIC SHOP", True, (20, 20, 30))
        shadow_rect = shadow_text.get_rect(center=(header_rect.centerx + 2, header_rect.centery + 2))
        screen.blit(shadow_text, shadow_rect)
        # Main title
        title_text = title_font.render("MYSTIC SHOP", True, (255, 235, 180))
        title_rect = title_text.get_rect(center=(header_rect.centerx, header_rect.centery))
        screen.blit(title_text, title_rect)
        
        # 3-column layout
        column_margin = 12
        content_y = panel_y + header_height + 20
        content_height = panel_height - header_height - 80  # Leave space for footer
        
        # Left column: Shop items list (40% width) - FULL HEIGHT NOW
        left_width = int(panel_width * 0.40)
        left_rect = pygame.Rect(panel_x + 10, content_y, left_width, content_height)
        
        # Middle column: Player slots (30% width)
        middle_width = int(panel_width * 0.28)
        middle_rect = pygame.Rect(left_rect.right + column_margin, content_y, middle_width, content_height)
        
        # Right column: Player status (30% width)
        right_width = panel_width - left_width - middle_width - column_margin * 3 - 20
        right_rect = pygame.Rect(middle_rect.right + column_margin, content_y, right_width, content_height)

        # Persist column rects - used for hit testing in input handling and scrolling
        try:
            self.panel_rect = panel_rect
            self.left_rect = left_rect
            self.middle_rect = middle_rect
            self.right_rect = right_rect
        except Exception:
            pass

        # Draw columns
        self._draw_shop_items_column(screen, left_rect)
        self._draw_player_slots_column(screen, middle_rect)
        self._draw_player_info_column(screen, right_rect)


        
        # Footer area - Coin box and Exit button
        # Exit button back in center
        exit_button_width = 120
        exit_button_height = 36
        exit_button_x = panel_x + (panel_width - exit_button_width) // 2
        exit_button_y = panel_y + panel_height - 50
        exit_button_rect = pygame.Rect(exit_button_x, exit_button_y, exit_button_width, exit_button_height)
        
        # Coin box on the left side of footer - SMALLER and LOWER
        coin_box_width = 140  # Reduced from 250
        coin_box_height = 44
        coin_box_x = panel_x + 20
        coin_box_y = panel_y + panel_height - 54  # Lower to avoid overlap
        coin_box_rect = pygame.Rect(coin_box_x, coin_box_y, coin_box_width, coin_box_height)
        
        mouse_pos = pygame.mouse.get_pos()
        is_exit_hovering = exit_button_rect.collidepoint(mouse_pos)
        
        exit_button_color = (180, 60, 60) if is_exit_hovering else (120, 50, 50)
        pygame.draw.rect(screen, exit_button_color, exit_button_rect, border_radius=6)
        pygame.draw.rect(screen, (200, 150, 150), exit_button_rect, width=2, border_radius=6)
        
        exit_text = get_font(14, bold=True).render("EXIT (ESC)", True, (255, 255, 255))
        exit_text_rect = exit_text.get_rect(center=exit_button_rect.center)
        screen.blit(exit_text, exit_text_rect)
        
        # Draw coin box in footer
        self._draw_coin_display_box(screen, coin_box_rect)
        
        # Register exit button region
        self.regions.append({'rect': exit_button_rect, 'action': 'exit'})

        # Note: tooltip is drawn later by the main draw routine to ensure it
        # appears above all shop UI layers. Call `shop.draw_tooltip_overlay(screen)`
        # from `Game.draw` after `shop.draw` when shop is open.

    
    def _draw_shop_items_column(self, screen, rect):
        """Draw left column with shop items as a vertical list and a bottom buy button.

        This presents items similar to a shop/list (image 2), with an icon on the
        left, name in the middle, and price on the right. Clicking an item selects
        it (updates `self.selection` and `self.selection_category`). A single Buy
        button at the bottom of this column purchases the currently selected item.
        """
        # Column background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=10)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=10)

        # Header
        header_height = 36
        header_rect = pygame.Rect(rect.x + 4, rect.y + 4, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), header_rect, width=2, border_radius=6)

        title_font = get_font(16, bold=True)
        total_items = len(self.selected_gear) + len(self.selected_consumables)
        title_text = title_font.render(f"Shop Items ({total_items})", True, (255, 235, 180))
        screen.blit(title_text, (header_rect.x + 10, header_rect.y + 10))

        # Combine gear and consumables into one ordered list
        all_items = []
        for item in self.selected_gear:
            all_items.append(('gear', item))
        for item in self.selected_consumables:
            all_items.append(('consumable', item))

        # Scrollable area (leave space at bottom for buy button)
        grid_y = rect.y + header_height + 8
        buy_button_height = 36
        bottom_padding = 18
        # compute buy button Y first then derive grid height so they never overlap
        buy_y = rect.y + rect.height - buy_button_height - bottom_padding
        grid_height = max(0, buy_y - grid_y - 8)
        # Add a bit more left padding to avoid clipping against the panel edge
        # (previously this could cause the leftmost content to be partially
        # obscured by the outer panel border). 16 px provides a consistent
        # inner margin that matches other column spacing.
        grid_rect = pygame.Rect(rect.x + 16, grid_y, rect.width - 32, grid_height)
        try:
            self.left_grid_rect = grid_rect
        except Exception:
            self.left_grid_rect = None

        # List layout (single column list with category headers)
        item_h = 64
        item_spacing = 8
        category_header_h = 28
        
        # Calculate total content height including category headers
        # One header for gear, one for consumables (if both exist)
        num_headers = 0
        if len(self.selected_gear) > 0:
            num_headers += 1
        if len(self.selected_consumables) > 0:
            num_headers += 1
        
        total_content_height = len(all_items) * (item_h + item_spacing) + num_headers * (category_header_h + item_spacing)

        # Scrolling: reuse gear_scroll_offset as pixel offset
        scroll_offset = getattr(self, 'gear_scroll_offset', 0)
        # Clamp scroll_offset (if content fits, keep at 0)
        max_scroll = max(0, total_content_height - grid_rect.height)
        if total_content_height <= grid_rect.height:
            scroll_offset = 0
        else:
            scroll_offset = max(0, min(scroll_offset, max_scroll))
        self.gear_scroll_offset = scroll_offset

        mouse_pos = pygame.mouse.get_pos()
        name_font = get_font(14, bold=True)
        small_font = get_font(10, bold=True)
        header_font = get_font(13, bold=True)

        # Set clipping rect to prevent items from drawing over header and buy button
        # This ensures scrolled content is clipped to the visible grid area
        old_clip = screen.get_clip()
        screen.set_clip(grid_rect)

        # Draw items with category headers
        y_start = grid_rect.y - scroll_offset
        current_y = y_start
        
        # Track which category we're in
        last_category = None
        
        for idx, (item_type, item) in enumerate(all_items):
            # Draw category header when category changes
            if item_type != last_category:
                header_rect = pygame.Rect(grid_rect.x, current_y, grid_rect.width, category_header_h)
                
                # Check if header is visible
                if not (header_rect.bottom < grid_rect.y or header_rect.top > grid_rect.bottom):
                    # Header background
                    pygame.draw.rect(screen, (50, 45, 60), header_rect, border_radius=6)
                    pygame.draw.rect(screen, (120, 100, 80), header_rect, width=2, border_radius=6)
                    
                    # Header text
                    header_text = "GEAR" if item_type == 'gear' else "CONSUMABLES"
                    header_color = (220, 180, 100) if item_type == 'gear' else (100, 200, 150)
                    header_surf = header_font.render(header_text, True, header_color)
                    screen.blit(header_surf, (header_rect.x + 10, header_rect.y + 7))
                    
                    # Item count
                    count = len(self.selected_gear) if item_type == 'gear' else len(self.selected_consumables)
                    count_surf = small_font.render(f"({count})", True, (180, 180, 200))
                    screen.blit(count_surf, (header_rect.right - 35, header_rect.y + 9))
                
                current_y += category_header_h + item_spacing
                last_category = item_type
            
            # Position item after any headers
            y = current_y
            item_rect = pygame.Rect(grid_rect.x, y, grid_rect.width, item_h)
            current_y += item_h + item_spacing

            # Check if item is visible for drawing, but always register regions
            is_visible = not (item_rect.bottom < grid_rect.y or item_rect.top > grid_rect.bottom)
            
            if not is_visible:
                # Still register clickable region for items outside visible area
                self.regions.append({'rect': item_rect, 'item': item})
                continue

            # Determine if this is the currently selected item
            is_selected = False
            if self.selection_category == 'gear' and item_type == 'gear' and 0 <= self.selection < len(self.selected_gear):
                try:
                    is_selected = (item is self.selected_gear[self.selection])
                except Exception:
                    is_selected = False
            if self.selection_category == 'consumable' and item_type == 'consumable' and 0 <= self.selection < len(self.selected_consumables):
                try:
                    is_selected = (item is self.selected_consumables[self.selection])
                except Exception:
                    is_selected = False

            # Background and border
            bg_col = (55, 50, 70) if is_selected else (40, 38, 48)
            pygame.draw.rect(screen, bg_col, item_rect, border_radius=8)
            border_col = rarity_border_color(item)
            pygame.draw.rect(screen, border_col, item_rect, width=2 if is_selected else 1, border_radius=8)

            # Icon area
            icon_area = pygame.Rect(item_rect.x + 8, item_rect.y + 8, item_h - 16, item_h - 16)
            icon_img = None
            if hasattr(item, 'icon_path') and item.icon_path:
                icon_img = _safe_load_icon(item.icon_path, (icon_area.width, icon_area.height))
                if not icon_img:
                    try:
                        icon_img = load_icon_masked(item.icon_path, (icon_area.width, icon_area.height), radius=6)
                    except Exception:
                        icon_img = None
            if icon_img:
                screen.blit(icon_img, icon_img.get_rect(center=icon_area.center))
            else:
                pygame.draw.rect(screen, item.color, icon_area, border_radius=6)
                if hasattr(item, 'icon_letter'):
                    letter_surf = get_font(18, bold=True).render(item.icon_letter, True, (20,20,28))
                    screen.blit(letter_surf, letter_surf.get_rect(center=icon_area.center))

            # Name - centered vertically in the item box
            text_x = icon_area.right + 10
            name_surf = name_font.render(item.name, True, (230, 230, 245))
            text_y = item_rect.centery - name_surf.get_height() // 2
            screen.blit(name_surf, (text_x, text_y))

            # Price box on the right
            price = self._get_item_price(item)
            price_can_afford = self.game.player.money >= price
            price_w = 72
            price_h = 26
            price_rect = pygame.Rect(item_rect.right - price_w - 10, item_rect.y + (item_h - price_h)//2, price_w, price_h)
            price_bg = (90, 50, 50) if not price_can_afford else (90, 80, 60)
            pygame.draw.rect(screen, price_bg, price_rect, border_radius=6)
            pygame.draw.rect(screen, (150,150,170), price_rect, width=1, border_radius=6)
            price_text = small_font.render(f"{price}c", True, (255,255,255))
            screen.blit(price_text, price_text.get_rect(center=price_rect.center))

            # Stock count for consumables (in a mini box)
            if item_type == 'consumable':
                stock = self.consumable_stock.get(item.key, 0)
                if stock > 0:
                    # Create mini box for stock count
                    stock_font = get_font(13, bold=True)  # Larger font
                    stock_surf = stock_font.render(f"x{stock}", True, (255, 255, 255))
                    
                    # Mini box dimensions
                    stock_box_w = 36
                    stock_box_h = 24
                    stock_box_x = price_rect.left - stock_box_w - 8
                    stock_box_y = item_rect.centery - stock_box_h // 2  # Vertically centered
                    stock_box_rect = pygame.Rect(stock_box_x, stock_box_y, stock_box_w, stock_box_h)
                    
                    # Draw mini box
                    pygame.draw.rect(screen, (60, 55, 70), stock_box_rect, border_radius=4)
                    pygame.draw.rect(screen, (120, 180, 140), stock_box_rect, width=1, border_radius=4)
                    
                    # Draw text centered in the box
                    stock_text_rect = stock_surf.get_rect(center=stock_box_rect.center)
                    screen.blit(stock_surf, stock_text_rect)

            # Register clickable region for selecting item (not immediate buy) - only for visible items
            # We store the item and its index so selection logic can find it
            if is_visible:
                self.regions.append({'rect': item_rect, 'item': item})

        # Restore previous clipping state before drawing scrollbar and buy button
        screen.set_clip(old_clip)

        # If content taller than viewport, draw simple scrollbar on right side of column
        if total_content_height > grid_rect.height:
            scrollbar_x = rect.right - 12
            scrollbar_y = grid_rect.y + 4
            scrollbar_h = grid_rect.height - 8
            pygame.draw.rect(screen, (60,60,80), (scrollbar_x, scrollbar_y, 8, scrollbar_h), border_radius=4)
            # Thumb
            scroll_ratio = scroll_offset / max(1, total_content_height - grid_rect.height)
            thumb_h = max(20, int((grid_rect.height / total_content_height) * scrollbar_h))
            thumb_y = scrollbar_y + int(scroll_ratio * (scrollbar_h - thumb_h))
            pygame.draw.rect(screen, (150,150,170), (scrollbar_x+2, thumb_y, 4, thumb_h), border_radius=3)

        # Draw Buy button at bottom of column that applies to the selected item
        # Match buy button left offset to the list padding so it lines up
        # visually with the items above it.
        buy_x = rect.x + 16
        buy_w = rect.width - 24
        buy_rect = pygame.Rect(buy_x, buy_y, buy_w, buy_button_height)

        # Determine selected item for the button
        selected_item = None
        if self.selection_category == 'gear' and 0 <= self.selection < len(self.selected_gear):
            selected_item = self.selected_gear[self.selection]
        elif self.selection_category == 'consumable' and 0 <= self.selection < len(self.selected_consumables):
            selected_item = self.selected_consumables[self.selection]

        # Button appearance with hover detection
        mouse_pos = pygame.mouse.get_pos()
        is_hovering = buy_rect.collidepoint(mouse_pos)
        
        # Check click feedback timing
        current_time = pygame.time.get_ticks()
        is_click_feedback_active = (current_time - self.buy_button_click_time) < 150  # 150ms feedback
        
        if selected_item is None:
            btn_col = (80, 80, 90)
            label = "Buy (no item)"
        else:
            price = self._get_item_price(selected_item)
            affordable = self.game.player.money >= price
            has_stock = True
            
            # Check stock for consumables
            if hasattr(selected_item, 'use') and self.consumable_stock.get(selected_item.key, 0) <= 0:
                affordable = False
                has_stock = False
            
            # Check if already purchased for gear
            if hasattr(selected_item, 'modifiers') and (selected_item.key in self.purchased_equipment or (hasattr(self.game, 'inventory') and selected_item.key in self.game.inventory.armament_order)):
                affordable = False
            
            # Button color logic:
            # - Click feedback (white flash): When just clicked
            # - Green: Hovering + can afford + has stock
            # - Yellow: Can afford + has stock (not hovering)
            # - Red: Cannot afford or no stock
            if is_click_feedback_active:
                btn_col = (200, 200, 200)  # White flash on click
            elif not affordable or not has_stock:
                btn_col = (120, 50, 50)  # Red (can't buy)
            elif is_hovering:
                btn_col = (50, 180, 80)  # Bright green (hovering + can buy)
            else:
                btn_col = (180, 160, 40)  # Yellow (can buy, not hovering)
            
            # Button label like "Buy x1: 20c"
            label = f"Buy x1: {price}c"

        pygame.draw.rect(screen, btn_col, buy_rect, border_radius=6)
        pygame.draw.rect(screen, (200, 170, 150), buy_rect, width=2 if is_hovering else 1, border_radius=6)
        lbl = get_font(14, bold=True).render(label, True, (255, 255, 255))
        screen.blit(lbl, lbl.get_rect(center=buy_rect.center))

        # Register buy button region
        self.regions.append({'rect': buy_rect, 'action': 'buy_selected'})
    
    def _draw_coin_display_box(self, screen, rect):
        """Draw compact coin/money display box in footer"""
        # Box background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=8)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=8)
        
        # Inner decorative border with gold accent
        inner_rect = rect.inflate(-6, -6)
        pygame.draw.rect(screen, (60, 50, 30), inner_rect, border_radius=6)
        pygame.draw.rect(screen, (255, 215, 0), inner_rect, width=2, border_radius=6)
        
        # Coin icon/symbol on the left
        coin_size = 28  # Slightly smaller
        coin_x = rect.x + 12
        coin_y = rect.centery - coin_size // 2
        coin_rect = pygame.Rect(coin_x, coin_y, coin_size, coin_size)
        
        # Draw coin (golden circle)
        pygame.draw.circle(screen, (255, 215, 0), coin_rect.center, coin_size // 2)
        pygame.draw.circle(screen, (218, 165, 32), coin_rect.center, coin_size // 2, width=2)
        pygame.draw.circle(screen, (255, 235, 100), coin_rect.center, coin_size // 2 - 3, width=1)
        
        # Coin symbol/letter
        coin_font = get_font(16, bold=True)
        coin_symbol = coin_font.render("C", True, (139, 90, 0))
        coin_symbol_rect = coin_symbol.get_rect(center=coin_rect.center)
        screen.blit(coin_symbol, coin_symbol_rect)
        
        # Coin amount (large and prominent) - NO LABEL, just the number
        amount_font = get_font(22, bold=True)
        amount_text = amount_font.render(str(self.game.player.money), True, (255, 215, 0))
        amount_x = coin_rect.right + 12
        amount_y = rect.centery - amount_text.get_height() // 2
        screen.blit(amount_text, (amount_x, amount_y))
    
    def _draw_player_slots_column(self, screen, rect):
        """Draw middle column with player equipment and consumable slots (two-row horizontal layout)

        Layout: Armaments on the top row, Consumables on the bottom row. Uses inventory data
        so equipped items and counts are shown correctly.
        """
        if not hasattr(self.game, 'inventory'):
            return

        inventory = self.game.inventory

        # Column background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=10)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=10)

        # Header block (shared style)
        header_height = 36
        header_rect = pygame.Rect(rect.x + 4, rect.y + 4, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), header_rect, width=2, border_radius=6)

        title_font = get_font(15, bold=True)
        title_text = title_font.render("Armaments", True, (255, 235, 180))
        screen.blit(title_text, (header_rect.x + 10, header_rect.y + 10))

        # Slot geometry
        slot_size = 64
        slot_spacing = 10
        slots_per_row = 3
        total_row_width = slots_per_row * slot_size + (slots_per_row - 1) * slot_spacing
        start_x = rect.x + (rect.width - total_row_width) // 2
        arm_row_y = header_rect.bottom + 12

        mouse_pos = pygame.mouse.get_pos()
        icon_font = get_font(18, bold=True)

        # Draw Armament slots in a horizontal row
        for i in range(3):
            item_x = start_x + i * (slot_size + slot_spacing)
            slot_rect = pygame.Rect(item_x, arm_row_y, slot_size, slot_size)

            is_hovering = slot_rect.collidepoint(mouse_pos)
            is_selected = (self.selected_slot_type == 'gear' and self.selected_slot_index == i)

            # Slot background
            if is_selected:
                bg_color = (70, 90, 110)  # Highlighted when selected
            elif is_hovering:
                bg_color = (50, 50, 65)
            else:
                bg_color = (46, 52, 72)
            pygame.draw.rect(screen, bg_color, slot_rect, border_radius=8)

            # Get equipped item
            item_key = inventory.gear_slots[i] if i < len(inventory.gear_slots) else None
            item = inventory.armament_catalog.get(item_key) if item_key else None

            if item:
                # Draw item background and rarity border
                pygame.draw.rect(screen, item.color, slot_rect.inflate(-8, -8), border_radius=6)
                border_color = rarity_border_color(item)
                border_width = 3 if is_selected else (2 if is_hovering else 1)
                pygame.draw.rect(screen, border_color, slot_rect, width=border_width, border_radius=8)

                # Icon (try true-alpha, then masked)
                icon_surf = None
                if hasattr(item, 'icon_path') and item.icon_path:
                    surf = _safe_load_icon(item.icon_path, (slot_size - 12, slot_size - 12))
                    if surf:
                        icon_surf = surf
                    else:
                        try:
                            icon_surf = load_icon_masked(item.icon_path, (slot_size - 12, slot_size - 12), radius=6)
                        except Exception:
                            icon_surf = None

                if icon_surf:
                    screen.blit(icon_surf, icon_surf.get_rect(center=slot_rect.center))
                else:
                    if hasattr(item, 'icon_letter'):
                        icon_text = icon_font.render(item.icon_letter, True, (20, 20, 28))
                        screen.blit(icon_text, icon_text.get_rect(center=slot_rect.center))
            else:
                # Empty slot
                border_color = (120, 120, 140) if is_hovering else (80, 80, 100)
                pygame.draw.rect(screen, border_color, slot_rect, width=2, border_radius=8)
                # Slot number
                num_font = get_font(20)
                num_text = num_font.render(str(i + 1), True, (100, 100, 120))
                screen.blit(num_text, num_text.get_rect(center=slot_rect.center))

            # Register clickable region for slot selection
            self.regions.append({'rect': slot_rect, 'action': 'select_gear_slot', 'slot_index': i, 'item': item})

        # Consumables header (placed under armament row)
        cons_header_rect = pygame.Rect(rect.x + 4, arm_row_y + slot_size + 12, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), cons_header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), cons_header_rect, width=2, border_radius=6)
        title_text = title_font.render("Consumables", True, (255, 235, 180))
        screen.blit(title_text, (cons_header_rect.x + 10, cons_header_rect.y + 10))

        cons_row_y = cons_header_rect.bottom + 12

        # Draw Consumable slots in a horizontal row
        for i in range(min(3, len(inventory.consumable_slots))):
            item_x = start_x + i * (slot_size + slot_spacing)
            slot_rect = pygame.Rect(item_x, cons_row_y, slot_size, slot_size)

            is_hovering = slot_rect.collidepoint(mouse_pos)
            is_selected = (self.selected_slot_type == 'consumable' and self.selected_slot_index == i)

            # Slot background
            if is_selected:
                bg_color = (70, 90, 110)  # Highlighted when selected
            elif is_hovering:
                bg_color = (50, 50, 65)
            else:
                bg_color = (46, 52, 72)
            pygame.draw.rect(screen, bg_color, slot_rect, border_radius=8)

            # Get equipped consumable
            stack = inventory.consumable_slots[i]
            item = inventory.consumable_catalog.get(stack.key) if stack else None

            if item:
                # Draw item background and rarity border
                pygame.draw.rect(screen, item.color, slot_rect.inflate(-8, -8), border_radius=6)
                border_color = rarity_border_color(item)
                border_width = 3 if is_selected else (2 if is_hovering else 1)
                pygame.draw.rect(screen, border_color, slot_rect, width=border_width, border_radius=8)

                # Icon
                icon_surf = None
                if hasattr(item, 'icon_path') and item.icon_path:
                    surf = _safe_load_icon(item.icon_path, (slot_size - 12, slot_size - 12))
                    if surf:
                        icon_surf = surf
                    else:
                        try:
                            icon_surf = load_icon_masked(item.icon_path, (slot_size - 12, slot_size - 12), radius=6)
                        except Exception:
                            icon_surf = None

                if icon_surf:
                    screen.blit(icon_surf, icon_surf.get_rect(center=slot_rect.center))
                else:
                    if hasattr(item, 'icon_letter'):
                        icon_text = icon_font.render(item.icon_letter, True, (20, 20, 28))
                        screen.blit(icon_text, icon_text.get_rect(center=slot_rect.center))

                # Count
                if stack:
                    total_count = inventory._total_available_count(stack.key)
                    if total_count > 0:
                        count_font = get_font(14, bold=True)
                        count_text = count_font.render(str(total_count), True, (255, 255, 255))
                        screen.blit(count_text, count_text.get_rect(bottomright=(slot_rect.right - 4, slot_rect.bottom - 4)))
            else:
                # Empty slot
                border_color = (120, 120, 140) if is_hovering else (80, 80, 100)
                pygame.draw.rect(screen, border_color, slot_rect, width=2, border_radius=8)
                # Hotkey
                hotkey = inventory._hotkey_label(i)
                hotkey_font = get_font(16)
                hotkey_text = hotkey_font.render(hotkey, True, (100, 100, 120))
                screen.blit(hotkey_text, hotkey_text.get_rect(center=slot_rect.center))

            # Register clickable region for slot selection
            self.regions.append({'rect': slot_rect, 'action': 'select_consumable_slot', 'slot_index': i, 'item': item})
    
    def _draw_inventory_stock_view(self, screen, rect):
        """Draw inventory stock view when a slot is selected (like in inventory system)"""
        if not hasattr(self.game, 'inventory'):
            return
        
        inventory = self.game.inventory
        
        # Header
        header_height = 50
        header_rect = pygame.Rect(rect.x + 4, rect.y + 4, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), header_rect, border_radius=8)
        pygame.draw.rect(screen, (180, 160, 140), header_rect, width=2, border_radius=8)
        
        title_font = get_font(18, bold=True)
        if self.selected_slot_type == 'gear':
            title_text = title_font.render("Armory Stock", True, (240, 220, 190))
        else:
            title_text = title_font.render("Consumable Stock", True, (240, 220, 190))
        screen.blit(title_text, (header_rect.x + 10, header_rect.y + 15))
        
        # Get items to display
        if self.selected_slot_type == 'gear':
            # Only show gear that is not already equipped (same as inventory)
            items_to_show = [(key, inventory.armament_catalog.get(key)) 
                           for key in inventory.armament_order
                           if key not in inventory.gear_slots]
        else:
            # Only show consumables with stock
            items_to_show = [(key, inventory.consumable_catalog.get(key)) 
                           for key in inventory.consumable_order 
                           if inventory._storage_count(key) > 0]
        
        # Unequip button
        unequip_button_height = 36
        unequip_button_y = header_rect.bottom + 8
        unequip_button_rect = pygame.Rect(rect.x + 10, unequip_button_y, rect.width - 20, unequip_button_height)
        
        # Check if currently equipped slot has an item
        has_equipped_item = False
        if self.selected_slot_type == 'gear' and hasattr(self.game, 'inventory') and self.selected_slot_index is not None:
            item_key = inventory.gear_slots[self.selected_slot_index] if self.selected_slot_index < len(inventory.gear_slots) else None
            has_equipped_item = item_key is not None
        elif self.selected_slot_type == 'consumable' and hasattr(self.game, 'inventory') and self.selected_slot_index is not None:
            stack = inventory.consumable_slots[self.selected_slot_index] if self.selected_slot_index < len(inventory.consumable_slots) else None
            has_equipped_item = stack is not None
        
        # Draw unequip button
        mouse_pos = pygame.mouse.get_pos()
        is_unequip_hovering = unequip_button_rect.collidepoint(mouse_pos)
        
        if has_equipped_item:
            unequip_color = (180, 80, 60) if is_unequip_hovering else (120, 60, 50)
        else:
            unequip_color = (60, 60, 70)  # Disabled
        
        pygame.draw.rect(screen, unequip_color, unequip_button_rect, border_radius=6)
        pygame.draw.rect(screen, (200, 150, 150), unequip_button_rect, width=2 if is_unequip_hovering else 1, border_radius=6)
        
        unequip_font = get_font(13, bold=True)
        unequip_text = unequip_font.render("UNEQUIP", True, (255, 255, 255) if has_equipped_item else (100, 100, 110))
        screen.blit(unequip_text, unequip_text.get_rect(center=unequip_button_rect.center))
        
        if has_equipped_item:
            self.regions.append({'rect': unequip_button_rect, 'action': 'unequip_slot'})
        
        # Scrollable grid area
        grid_y = unequip_button_rect.bottom + 8
        grid_height = rect.bottom - grid_y - 10
        grid_rect = pygame.Rect(rect.x + 10, grid_y, rect.width - 20, grid_height)
        try:
            self.right_stock_grid_rect = grid_rect
        except Exception:
            self.right_stock_grid_rect = None
        
        # Item grid settings - FIT TO COLUMN WIDTH
        item_spacing = 6
        available_width = grid_rect.width - 10  # Leave space for scrollbar
        items_per_row = 3  # Changed from 4 to 3 to fit better
        item_size = (available_width - (items_per_row - 1) * item_spacing) // items_per_row
        
        # Calculate scrolling
        total_rows = (len(items_to_show) + items_per_row - 1) // items_per_row
        total_height = total_rows * (item_size + item_spacing)
        max_scroll = max(0, total_height - grid_height)
        self.stock_scroll_offset = max(0, min(self.stock_scroll_offset, max_scroll))
        
        # Set clipping
        old_clip = screen.get_clip()
        screen.set_clip(grid_rect)
        
        mouse_pos = pygame.mouse.get_pos()
        icon_font = get_font(18, bold=True)
        
        # Draw items
        for idx, (key, item) in enumerate(items_to_show):
            if not item:
                continue
            
            row = idx // items_per_row
            col = idx % items_per_row
            
            item_x = grid_rect.x + col * (item_size + item_spacing)
            item_y = grid_rect.y + row * (item_size + item_spacing) - self.stock_scroll_offset
            item_rect = pygame.Rect(item_x, item_y, item_size, item_size)
            
            # Skip if not visible
            if item_rect.bottom < grid_rect.y or item_rect.top > grid_rect.bottom:
                continue
            
            # Check if equipped
            is_equipped = False
            if self.selected_slot_type == 'gear':
                is_equipped = key in inventory.gear_slots
            else:
                is_equipped = any(s and s.key == key for s in inventory.consumable_slots)
            
            # Draw item
            pygame.draw.rect(screen, item.color, item_rect.inflate(-8, -8), border_radius=6)
            border_color = rarity_border_color(item)
            pygame.draw.rect(screen, border_color, item_rect, width=2, border_radius=8)
            
            # Green glow if equipped
            if is_equipped:
                pygame.draw.rect(screen, (120, 230, 180), item_rect.inflate(4, 4), width=2, border_radius=10)
            
            # Icon
            icon_surf = None
            if hasattr(item, 'icon_path') and item.icon_path:
                surf = _safe_load_icon(item.icon_path, (item_size - 12, item_size - 12))
                if surf:
                    icon_surf = surf
                else:
                    try:
                        icon_surf = load_icon_masked(item.icon_path, (item_size - 12, item_size - 12), radius=6)
                    except Exception:
                        icon_surf = None
            if icon_surf:
                screen.blit(icon_surf, icon_surf.get_rect(center=item_rect.center))
            else:
                if hasattr(item, 'icon_letter'):
                    icon_text = icon_font.render(item.icon_letter, True, (20, 20, 28))
                    screen.blit(icon_text, icon_text.get_rect(center=item_rect.center))
            
            # Show count for consumables
            if self.selected_slot_type == 'consumable':
                count = inventory._total_available_count(key)
                if count > 0:
                    count_font = get_font(12, bold=True)
                    count_text = count_font.render(str(count), True, (255, 255, 255))
                    screen.blit(count_text, count_text.get_rect(bottomright=(item_rect.right - 3, item_rect.bottom - 3)))
            
            # Register clickable region for equip/unequip
            self.regions.append({'rect': item_rect, 'action': 'toggle_equip_item', 'item_key': key, 'item': item})
        
        # Restore clip
        screen.set_clip(old_clip)
        
        # Scrollbar if needed
        if total_height > grid_height:
            scrollbar_x = rect.right - 12
            scrollbar_y = grid_rect.y
            scrollbar_h = grid_rect.height
            
            pygame.draw.rect(screen, (60, 60, 80), (scrollbar_x, scrollbar_y, 6, scrollbar_h), border_radius=3)
            
            scroll_ratio = self.stock_scroll_offset / max(1, max_scroll)
            thumb_h = max(20, int((grid_height / total_height) * scrollbar_h))
            thumb_y = scrollbar_y + int(scroll_ratio * (scrollbar_h - thumb_h))
            pygame.draw.rect(screen, (150, 150, 170), (scrollbar_x + 1, thumb_y, 4, thumb_h), border_radius=2)
    
    def _draw_player_info_column(self, screen, rect):
        """Draw right column with player status or inventory stock view"""
        # Column background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=10)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=10)
        
        # If a slot is selected, show inventory stock view
        if self.selected_slot_type is not None:
            self._draw_inventory_stock_view(screen, rect)
            return
        
        # Otherwise, show player model frame - REDUCED HEIGHT
        model_height = 120  # Reduced from 200 to 120
        model_rect = pygame.Rect(rect.x + 10, rect.y + 10, rect.width - 20, model_height)
        pygame.draw.rect(screen, (32, 36, 52), model_rect, border_radius=12)
        pygame.draw.rect(screen, (160, 180, 220), model_rect, width=1, border_radius=12)
        
        # Player class display (smaller)
        player_frame = pygame.Rect(0, 0, self.game.player.rect.width * 2, self.game.player.rect.height * 2)
        player_frame.center = (model_rect.centerx, model_rect.centery - 10)
        pygame.draw.rect(screen, (120, 200, 235), player_frame, border_radius=8)
        
        class_font = get_font(16, bold=True)  # Reduced from 20 to 16
        class_text = class_font.render(self.game.player.cls, True, (240, 230, 250))
        screen.blit(class_text, class_text.get_rect(center=(model_rect.centerx, model_rect.bottom - 15)))
        
        # Stats section with header and scrollable area
        stats_header_y = model_rect.bottom + 10
        stats_header_height = 30
        stats_header_rect = pygame.Rect(rect.x + 4, stats_header_y, rect.width - 8, stats_header_height)
        pygame.draw.rect(screen, (45, 40, 55), stats_header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), stats_header_rect, width=2, border_radius=6)
        
        header_font = get_font(14, bold=True)
        header_text = header_font.render("Player Stats", True, (255, 235, 180))
        screen.blit(header_text, (stats_header_rect.x + 10, stats_header_rect.y + 8))
        
        # Scrollable stats area
        stats_area_y = stats_header_rect.bottom + 8
        stats_area_height = rect.bottom - stats_area_y - 10
        stats_area_rect = pygame.Rect(rect.x + 10, stats_area_y, rect.width - 20, stats_area_height)
        try:
            self.right_stats_area_rect = stats_area_rect
        except Exception:
            self.right_stats_area_rect = None
        
        stats_font = get_font(14)  # Reduced from 16 to 14
        line_height = 22  # Reduced from 24 to 22
        
        stats_lines = [
            (f"HP: {self.game.player.hp}/{self.game.player.max_hp}", (255, 150, 150)),
            (f"Attack: {getattr(self.game.player, 'attack_damage', '?')}", (255, 200, 100)),
        ]
        
        if hasattr(self.game.player, 'mana'):
            stats_lines.append((f"Mana: {self.game.player.mana:.0f}/{self.game.player.max_mana:.0f}", (100, 150, 255)))
        
        if hasattr(self.game.player, 'stamina'):
            stats_lines.append((f"Stamina: {self.game.player.stamina:.0f}/{self.game.player.max_stamina:.0f}", (150, 255, 150)))
        
        stats_lines.append((f"Speed: {self.game.player.player_speed:.1f}", (200, 200, 255)))
        # Coins removed - now displayed in dedicated coin box under shop items
        
        # Calculate total content height
        total_stats_height = len(stats_lines) * line_height
        
        # Clamp scroll offset
        max_scroll = max(0, total_stats_height - stats_area_height)
        if total_stats_height <= stats_area_height:
            self.player_info_scroll_offset = 0
        else:
            self.player_info_scroll_offset = max(0, min(self.player_info_scroll_offset, max_scroll))
        
        # Set clipping for stats area
        old_clip = screen.get_clip()
        screen.set_clip(stats_area_rect)
        
        # Draw stats with scroll offset
        for i, (text, color) in enumerate(stats_lines):
            stat_y = stats_area_rect.y + (i * line_height) - self.player_info_scroll_offset
            # Only draw if visible in the clipped area
            if stat_y + line_height >= stats_area_rect.y and stat_y <= stats_area_rect.bottom:
                stat_text = stats_font.render(text, True, color)
                screen.blit(stat_text, (stats_area_rect.x + 5, stat_y))
        
        # Restore clip
        screen.set_clip(old_clip)
        
        # Draw scrollbar if needed
        if total_stats_height > stats_area_height:
            scrollbar_x = rect.right - 10
            scrollbar_y = stats_area_rect.y
            scrollbar_h = stats_area_rect.height
            
            # Track
            pygame.draw.rect(screen, (60, 60, 80), (scrollbar_x, scrollbar_y, 6, scrollbar_h), border_radius=3)
            
            # Thumb
            scroll_ratio = self.player_info_scroll_offset / max(1, max_scroll)
            thumb_h = max(20, int((stats_area_height / total_stats_height) * scrollbar_h))
            thumb_y = scrollbar_y + int(scroll_ratio * (scrollbar_h - thumb_h))
            pygame.draw.rect(screen, (150, 150, 170), (scrollbar_x + 1, thumb_y, 4, thumb_h), border_radius=2)
    
    def _draw_shop_gear_cell(self, screen, rect):
        """Draw shop gear items cell with a list view"""
        # Cell background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=10)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=10)
        
        # Decorative header block
        header_height = 32
        header_rect = pygame.Rect(rect.x + 4, rect.y + 4, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), header_rect, width=2, border_radius=6)
        
        # Title with scroll hint
        title_font = get_font(16, bold=True)
        total_gear = len(self.selected_gear)
        title_text = title_font.render(f"Shop Gear ({total_gear})", True, (255, 235, 180))
        screen.blit(title_text, (header_rect.x + 8, header_rect.y + 8))
        
        # Show scroll hint if there are more items than can be displayed
        if total_gear > self.max_visible_gear:
            hint_font = get_font(9)
            hint_text = hint_font.render("↑↓", True, (200, 180, 150))
            screen.blit(hint_text, (header_rect.right - 20, header_rect.y + 10))
        
        # Draw list view with details and buy buttons - maximize space
        list_y = rect.y + header_height + 8
        list_height = rect.height - header_height - 12
        list_rect = pygame.Rect(rect.x + 4, list_y, rect.width - 8, list_height)
        self._draw_gear_list(screen, list_rect, self.selected_gear)
    
    def _draw_shop_consumables_cell(self, screen, rect):
        """Draw shop consumables cell with a list view"""
        # Cell background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=10)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=10)
        
        # Decorative header block
        header_height = 32
        header_rect = pygame.Rect(rect.x + 4, rect.y + 4, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), header_rect, width=2, border_radius=6)
        
        # Title with scroll hint
        title_font = get_font(16, bold=True)
        total_consumables = len(self.selected_consumables)
        title_text = title_font.render(f"Shop Consumables ({total_consumables})", True, (255, 235, 180))
        screen.blit(title_text, (header_rect.x + 8, header_rect.y + 8))
        
        # Show scroll hint if there are more items than can be displayed
        if total_consumables > self.max_visible_consumables:
            hint_font = get_font(9)
            hint_text = hint_font.render("↑↓", True, (200, 180, 150))
            screen.blit(hint_text, (header_rect.right - 20, header_rect.y + 10))
        
        # Draw list view with details and buy buttons - maximize space
        list_y = rect.y + header_height + 8
        list_height = rect.height - header_height - 12
        list_rect = pygame.Rect(rect.x + 4, list_y, rect.width - 8, list_height)
        self._draw_consumable_list(screen, list_rect, self.selected_consumables)
    
    def _draw_player_status_cell(self, screen, rect):
        """Draw player status cell"""
        # Cell background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=10)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=10)
        
        # Decorative header block
        header_height = 32
        header_rect = pygame.Rect(rect.x + 4, rect.y + 4, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), header_rect, width=2, border_radius=6)
        
        # Title
        title_font = get_font(16, bold=True)
        title_text = title_font.render("Player Status", True, (255, 235, 180))
        screen.blit(title_text, (header_rect.x + 8, header_rect.y + 8))
        
        # Get current hover item for preview
        mouse_pos = pygame.mouse.get_pos()
        hover_item = self._get_item_at_pos(mouse_pos)
        
        # Get stats with preview
        stats = self._get_player_stats_with_preview(hover_item)
        
        # Draw stats - start below header
        stats_font = get_font(14)
        stats_y = rect.y + header_height + 16
        line_height = 20
        
        # Player class
        class_text = stats_font.render(f"Class: {self.game.player.cls}", True, (200, 200, 215))
        screen.blit(class_text, (rect.x + 10, stats_y))
        stats_y += line_height + 5
        
        # HP
        hp_text = stats_font.render(f"HP: {stats['hp'][0]}", True, (255, 150, 150))
        screen.blit(hp_text, (rect.x + 10, stats_y))
        if stats['hp'][1]:
            preview_text = stats_font.render(stats['hp'][1], True, (100, 255, 100))
            screen.blit(preview_text, (rect.x + 120, stats_y))
        stats_y += line_height
        
        # Attack
        attack_text = stats_font.render(f"Attack: {stats['attack'][0]}", True, (255, 200, 100))
        screen.blit(attack_text, (rect.x + 10, stats_y))
        if stats['attack'][1]:
            preview_text = stats_font.render(stats['attack'][1], True, (100, 255, 100))
            screen.blit(preview_text, (rect.x + 120, stats_y))
        stats_y += line_height
        
        # Mana
        mana_text = stats_font.render(f"Mana: {stats['mana'][0]}", True, (100, 150, 255))
        screen.blit(mana_text, (rect.x + 10, stats_y))
        if stats['mana'][1]:
            preview_text = stats_font.render(stats['mana'][1], True, (100, 255, 100))
            screen.blit(preview_text, (rect.x + 120, stats_y))
        stats_y += line_height
        
        # Stamina
        stamina_text = stats_font.render(f"Stamina: {stats['stamina'][0]}", True, (150, 255, 150))
        screen.blit(stamina_text, (rect.x + 10, stats_y))
        if stats['stamina'][1]:
            preview_text = stats_font.render(stats['stamina'][1], True, (100, 255, 100))
            screen.blit(preview_text, (rect.x + 120, stats_y))
        stats_y += line_height
        
        # Speed
        speed_text = stats_font.render(f"Speed: {stats['speed'][0]}", True, (200, 200, 255))
        screen.blit(speed_text, (rect.x + 10, stats_y))
        if stats['speed'][1]:
            preview_text = stats_font.render(stats['speed'][1], True, (100, 255, 100))
            screen.blit(preview_text, (rect.x + 120, stats_y))
        stats_y += line_height
        
        # Money
        money_text = stats_font.render(f"Coins: {self.game.player.money}", True, (255, 215, 0))
        screen.blit(money_text, (rect.x + 10, stats_y))
    
    def _draw_player_gear_slots_cell(self, screen, rect):
        """Draw player gear slots cell (display only)"""
        # Cell background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=10)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=10)
        
        # Decorative header block
        header_height = 32
        header_rect = pygame.Rect(rect.x + 4, rect.y + 4, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), header_rect, width=2, border_radius=6)
        
        # Title with hint
        title_font = get_font(15, bold=True)
        title_text = title_font.render("Your Gear (Click to Change)", True, (255, 235, 180))
        screen.blit(title_text, (header_rect.x + 8, header_rect.y + 9))
        
        if not hasattr(self.game, 'inventory'):
            # No inventory system
            no_inv_text = get_font(12).render("No inventory system", True, (180, 180, 200))
            screen.blit(no_inv_text, (rect.x + 10, rect.y + 50))
            return
        
        inventory = self.game.inventory
        
        # Draw 3 gear slots horizontally - maximize size
        item_size = 70
        item_spacing = 12
        start_x = rect.x + 10
        start_y = rect.y + header_height + 16
        
        mouse_pos = pygame.mouse.get_pos()
        
        for i in range(3):  # 3 gear slots for player
            item_x = start_x + i * (item_size + item_spacing)
            item_y = start_y
            
            item_rect = pygame.Rect(item_x, item_y, item_size, item_size)
            
            # Check hover state
            is_hovering = item_rect.collidepoint(mouse_pos)
            
            # Draw slot background with hover effect
            bg_color = (50, 50, 65) if is_hovering else (40, 40, 50)
            border_color = (150, 150, 180) if is_hovering else (80, 80, 100)
            pygame.draw.rect(screen, bg_color, item_rect, border_radius=8)
            pygame.draw.rect(screen, border_color, item_rect, width=2 if is_hovering else 1, border_radius=8)
            
            # Draw equipped item if any
            if i < len(inventory.gear_slots) and inventory.gear_slots[i]:
                item_key = inventory.gear_slots[i]
                item = inventory.armament_catalog.get(item_key)
                if item:
                    self._draw_equipped_item(screen, item, item_rect)
            
            # Slot number
            slot_text = get_font(12).render(str(i + 1), True, (120, 120, 140))
            screen.blit(slot_text, (item_rect.x + 3, item_rect.y + 3))
            
            # Clickable region removed - no swap popup functionality
            # Register hover-only region so tooltips show for equipped gear
            if i < len(inventory.gear_slots) and inventory.gear_slots[i]:
                item_key = inventory.gear_slots[i]
                hover_item = inventory.armament_catalog.get(item_key)
            else:
                hover_item = None
            self.regions.append({'rect': item_rect, 'item': hover_item})
    
    def _draw_player_consumable_slots_cell(self, screen, rect):
        """Draw player consumable slots cell (display only)"""
        # Cell background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=10)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=10)
        
        # Decorative header block
        header_height = 32
        header_rect = pygame.Rect(rect.x + 4, rect.y + 4, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), header_rect, width=2, border_radius=6)
        
        # Title with hint
        title_font = get_font(14, bold=True)
        title_text = title_font.render("Your Consumables (Click to Change)", True, (255, 235, 180))
        screen.blit(title_text, (header_rect.x + 8, header_rect.y + 9))
        
        if not hasattr(self.game, 'inventory'):
            # No inventory system
            no_inv_text = get_font(12).render("No inventory system", True, (180, 180, 200))
            screen.blit(no_inv_text, (rect.x + 10, rect.y + 50))
            return
        
        inventory = self.game.inventory
        
        # Draw consumable slots horizontally - maximize size
        item_size = 70
        item_spacing = 12
        start_x = rect.x + 10
        start_y = rect.y + header_height + 16
        
        mouse_pos = pygame.mouse.get_pos()
        
        for i, stack in enumerate(inventory.consumable_slots):
            if i >= 3:  # Only show first 3 slots
                break
                
            item_x = start_x + i * (item_size + item_spacing)
            item_y = start_y
            
            item_rect = pygame.Rect(item_x, item_y, item_size, item_size)
            
            # Check hover state
            is_hovering = item_rect.collidepoint(mouse_pos)
            
            # Draw slot background with hover effect
            bg_color = (50, 50, 65) if is_hovering else (40, 40, 50)
            border_color = (150, 150, 180) if is_hovering else (80, 80, 100)
            pygame.draw.rect(screen, bg_color, item_rect, border_radius=8)
            pygame.draw.rect(screen, border_color, item_rect, width=2 if is_hovering else 1, border_radius=8)
            
            # Draw equipped consumable if any
            if stack:
                item = inventory.consumable_catalog.get(stack.key)
                if item:
                    self._draw_equipped_item(screen, item, item_rect)
                    
                    # Draw count
                    count_text = get_font(12, bold=True).render(str(stack.count), True, (255, 255, 255))
                    count_rect = count_text.get_rect(bottomright=(item_rect.right - 4, item_rect.bottom - 4))
                    screen.blit(count_text, count_rect)
            
            # Hotkey label
            hotkey = inventory._hotkey_label(i)
            hotkey_text = get_font(10).render(hotkey, True, (120, 120, 140))
            screen.blit(hotkey_text, (item_rect.x + 3, item_rect.y + 3))
            
            # Register clickable region
            # Clickable region removed - no swap popup functionality
            # Add hover-only region for tooltips on equipped consumables
            hover_item = None
            if stack:
                hover_item = inventory.consumable_catalog.get(stack.key)
            self.regions.append({'rect': item_rect, 'item': hover_item})
    
    def _draw_dynamic_inventory_panel(self, screen, rect):
        """Draw dynamic inventory panel that changes based on selection"""
        # Cell background
        pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=10)
        pygame.draw.rect(screen, (100, 100, 120), rect, width=2, border_radius=10)
        
        # Decorative header block
        header_height = 32
        header_rect = pygame.Rect(rect.x + 4, rect.y + 4, rect.width - 8, header_height)
        pygame.draw.rect(screen, (45, 40, 55), header_rect, border_radius=6)
        pygame.draw.rect(screen, (160, 140, 100), header_rect, width=2, border_radius=6)
        
        # Title
        title_font = get_font(16, bold=True)
        
        # Get current selection to determine what to show
        mouse_pos = pygame.mouse.get_pos()
        hover_item = self._get_item_at_pos(mouse_pos)
        
        if hover_item:
            if hasattr(hover_item, 'modifiers'):  # Gear item
                title_text = title_font.render("Gear Details", True, (255, 235, 180))
                screen.blit(title_text, (header_rect.x + 8, header_rect.y + 8))
                self._draw_gear_details(screen, hover_item, rect, header_height)
            elif hasattr(hover_item, 'use'):  # Consumable item
                title_text = title_font.render("Consumable Details", True, (255, 235, 180))
                screen.blit(title_text, (header_rect.x + 8, header_rect.y + 8))
                self._draw_consumable_details(screen, hover_item, rect, header_height)
        else:
            # Show equipment effects when no item is hovered
            title_text = title_font.render("Equipment Effects", True, (255, 235, 180))
            screen.blit(title_text, (header_rect.x + 8, header_rect.y + 8))
            self._draw_equipment_effects(screen, rect, header_height)
    
    def _draw_gear_details(self, screen, item, rect, header_height=32):
        """Draw detailed gear information"""
        if not hasattr(item, 'modifiers'):
            return
            
        # Draw modifiers
        details_font = get_font(12)
        details_y = rect.y + header_height + 16
        
        for stat, value in item.modifiers.items():
            if stat == 'max_hp':
                mod_text = f"HP +{value}"
                color = (255, 150, 150)
            elif stat == 'attack_damage':
                mod_text = f"Attack +{value}"
                color = (255, 200, 100)
            elif stat == 'max_mana':
                mod_text = f"Mana +{value}"
                color = (100, 150, 255)
            elif stat == 'max_stamina':
                mod_text = f"Stamina +{value}"
                color = (150, 255, 150)
            elif stat == 'player_speed':
                mod_text = f"Speed +{value:.1f}"
                color = (200, 200, 255)
            else:
                mod_text = f"{stat} +{value}"
                color = (200, 200, 200)
            
            mod_surface = details_font.render(mod_text, True, color)
            screen.blit(mod_surface, (rect.x + 15, details_y))
            details_y += 18
        
        # Draw price
        price = self._get_item_price(item)
        price_text = details_font.render(f"Price: {price} coins", True, (255, 215, 0))
        screen.blit(price_text, (rect.x + 15, details_y + 10))
    
    def _draw_consumable_details(self, screen, item, rect, header_height=32):
        """Draw detailed consumable information"""
        details_font = get_font(12)
        details_y = rect.y + header_height + 16
        
        # Draw effect text
        if hasattr(item, 'effect_text') and item.effect_text:
            effect_lines = item.effect_text.split('\n') if '\n' in item.effect_text else [item.effect_text]
            for line in effect_lines:
                effect_surface = details_font.render(line, True, (200, 200, 215))
                screen.blit(effect_surface, (rect.x + 15, details_y))
                details_y += 18
        
        # Draw stock and price
        stock = self.consumable_stock.get(item.key, 0)
        price = self._get_item_price(item)
        
        stock_text = details_font.render(f"Available: {stock}", True, (150, 255, 150))
        screen.blit(stock_text, (rect.x + 15, details_y + 10))
        
        price_text = details_font.render(f"Price: {price} coins", True, (255, 215, 0))
        screen.blit(price_text, (rect.x + 15, details_y + 30))
    
    def _draw_equipment_effects(self, screen, rect, header_height=32):
        """Draw current equipment effects"""
        if not hasattr(self.game, 'inventory') or not self.game.inventory.gear_slots:
            no_effects_text = get_font(12).render("No equipment equipped", True, (180, 180, 200))
            screen.blit(no_effects_text, (rect.x + 15, rect.y + header_height + 16))
            return
        
        details_font = get_font(11)
        details_y = rect.y + header_height + 16
        
        for i, key in enumerate(self.game.inventory.gear_slots):
            if key and key in self.game.inventory.armament_catalog:
                item = self.game.inventory.armament_catalog[key]
                
                # Item name
                item_name = details_font.render(f"• {item.name}", True, (200, 200, 215))
                screen.blit(item_name, (rect.x + 15, details_y))
                details_y += 15
                
                # Show modifiers
                for stat, value in item.modifiers.items():
                    if stat == 'max_hp':
                        mod_text = f"  HP +{value}"
                        color = (255, 150, 150)
                    elif stat == 'attack_damage':
                        mod_text = f"  Attack +{value}"
                        color = (255, 200, 100)
                    elif stat == 'max_mana':
                        mod_text = f"  Mana +{value}"
                        color = (100, 150, 255)
                    elif stat == 'max_stamina':
                        mod_text = f"  Stamina +{value}"
                        color = (150, 255, 150)
                    elif stat == 'player_speed':
                        mod_text = f"  Speed +{value:.1f}"
                        color = (200, 200, 255)
                    else:
                        mod_text = f"  {stat} +{value}"
                        color = (180, 180, 180)
                    
                    mod_surface = details_font.render(mod_text, True, color)
                    screen.blit(mod_surface, (rect.x + 20, details_y))
                    details_y += 12
                
                details_y += 8  # Extra spacing between items
    
    def _draw_equipped_item(self, screen, item, rect):
        """Draw an equipped item"""
        # Draw item background
        pygame.draw.rect(screen, item.color, rect.inflate(-8, -8), border_radius=6)
        
        # Draw rarity border
        border_color = rarity_border_color(item)
        pygame.draw.rect(screen, border_color, rect, width=2, border_radius=8)
        
        # Draw icon
        icon_rect = pygame.Rect(rect.x + 5, rect.y + 5, rect.width - 10, rect.height - 10)
        icon_surf = None
        if hasattr(item, 'icon_path') and item.icon_path:
            surf = _safe_load_icon(item.icon_path, (icon_rect.width, icon_rect.height))
            if surf:
                icon_surf = surf
            else:
                try:
                    icon_surf = load_icon_masked(item.icon_path, (icon_rect.width, icon_rect.height), radius=6)
                except Exception:
                    icon_surf = None
        if icon_surf:
            screen.blit(icon_surf, icon_rect)
        else:
            if hasattr(item, 'icon_letter'):
                icon_text = get_font(16, bold=True).render(item.icon_letter, True, (20, 20, 28))
                icon_text_rect = icon_text.get_rect(center=icon_rect.center)
                screen.blit(icon_text, icon_text_rect)
    
    def _draw_gear_list(self, screen, rect, gear_items):
        """Draw gear list with details and buy buttons - maximized"""
        # List items - maximize space usage
        item_height = 76  # Increased for better visibility
        item_spacing = 6
        start_y = rect.y + 2  # Minimal top padding
        
        # Calculate visible range with scrolling
        start_index = self.gear_scroll_offset
        end_index = min(start_index + self.max_visible_gear, len(gear_items))
        
        for i in range(start_index, end_index):
            item = gear_items[i]
            visible_index = i - start_index  # Index for positioning within visible area
                
            item_rect = pygame.Rect(rect.x + 10, start_y + visible_index * (item_height + item_spacing), rect.width - 20, item_height)
            
            if item_rect.bottom > rect.bottom:
                break
            
            # Highlight selected item
            if i == self.selection and self.selection_category == 'gear':
                pygame.draw.rect(screen, (60, 60, 80), item_rect, border_radius=4)
                pygame.draw.rect(screen, (255, 210, 120), item_rect, width=2, border_radius=4)
            else:
                pygame.draw.rect(screen, (40, 40, 50), item_rect, border_radius=4)
                border_color = rarity_border_color(item)
                pygame.draw.rect(screen, border_color, item_rect, width=1, border_radius=4)
            
            # Item icon - maximized for better visibility
            icon_rect = pygame.Rect(item_rect.x + 6, item_rect.y + 5, 64, 64)  # Increased size
            icon_surf = None
            if hasattr(item, 'icon_path') and item.icon_path:
                surf = _safe_load_icon(item.icon_path, (icon_rect.width, icon_rect.height))
                if surf:
                    icon_surf = surf
                else:
                    try:
                        icon_surf = load_icon_masked(item.icon_path, (icon_rect.width, icon_rect.height), radius=6)
                    except Exception:
                        icon_surf = None
            # Draw rarity border around icon
            border_color = rarity_border_color(item)
            pygame.draw.rect(screen, border_color, icon_rect.inflate(4, 4), width=2, border_radius=8)
            
            if icon_surf:
                screen.blit(icon_surf, icon_rect)
            else:
                pygame.draw.rect(screen, item.color, icon_rect, border_radius=6)
                if hasattr(item, 'icon_letter'):
                    icon_text = get_font(20, bold=True).render(item.icon_letter, True, (20, 20, 28))
                    icon_text_rect = icon_text.get_rect(center=icon_rect.center)
                    screen.blit(icon_text, icon_text_rect)
            
            # Item name
            name_font = get_font(14, bold=True)
            name_text = name_font.render(item.name, True, (220, 220, 235))
            screen.blit(name_text, (item_rect.x + 78, item_rect.y + 8))
            
            # Price and buy button
            price = self._get_item_price(item)
            price_font = get_font(12, bold=True)
            button_font = get_font(11, bold=True)
            
            # Price
            price_color = GREEN if self.game.player.money >= price else (150, 150, 150)
            price_text = price_font.render(f"{price}c", True, price_color)
            screen.blit(price_text, (item_rect.x + 78, item_rect.y + 30))
            
            # Check if player owns this item
            player_owns_item = False
            if hasattr(self.game, 'inventory'):
                player_owns_item = item.key in self.game.inventory.armament_order
            
            # Draw "OWNED" badge if player has this item
            if player_owns_item:
                badge_rect = pygame.Rect(item_rect.right - 68, item_rect.y + 4, 64, 16)
                pygame.draw.rect(screen, (80, 180, 120), badge_rect, border_radius=3)
                pygame.draw.rect(screen, (120, 255, 180), badge_rect, width=1, border_radius=3)
                badge_font = get_font(9, bold=True)
                badge_text = badge_font.render("OWNED", True, (255, 255, 255))
                badge_text_rect = badge_text.get_rect(center=badge_rect.center)
                screen.blit(badge_text, badge_text_rect)
            
            # Buy button
            button_rect = pygame.Rect(item_rect.right - 62, item_rect.y + 22, 58, 24)  # Adjusted for new height
            
            # Check if sold out or owned
            is_sold_out = False
            button_text = "BUY"
                
            if item.key in self.purchased_equipment or player_owns_item:
                is_sold_out = True
                button_text = "SOLD"
            
            # Button color
            if is_sold_out:
                button_color = (60, 60, 60)
            elif self.game.player.money >= price:
                button_color = (0, 150, 0)
            else:
                button_color = (100, 80, 80)
            
            pygame.draw.rect(screen, button_color, button_rect, border_radius=2)
            pygame.draw.rect(screen, (150, 150, 170), button_rect, width=1, border_radius=2)
            
            button_text_color = (180, 180, 180) if is_sold_out else (255, 255, 255)
            button_surface = button_font.render(button_text, True, button_text_color)
            button_text_rect = button_surface.get_rect(center=button_rect.center)
            screen.blit(button_surface, button_text_rect)
            
            # Register regions
            self.regions.append({'rect': button_rect, 'item': item, 'action': 'buy'})
            self.regions.append({'rect': item_rect, 'item': item})
        
        # Draw scroll indicators for gear
        total_gear_items = len(gear_items)
        if total_gear_items > self.max_visible_gear:
            self._draw_scroll_indicators(screen, rect, total_gear_items, self.gear_scroll_offset, 'gear', self.max_visible_gear)
    
    def _draw_consumable_list(self, screen, rect, consumable_items):
        """Draw consumable list with details and buy buttons - maximized"""
        # List items - maximize space usage
        item_height = 76  # Increased for better visibility
        item_spacing = 6
        start_y = rect.y + 2  # Minimal top padding
        
        # Calculate visible range with scrolling
        start_index = self.consumable_scroll_offset
        end_index = min(start_index + self.max_visible_consumables, len(consumable_items))
        
        for i in range(start_index, end_index):
            item = consumable_items[i]
            visible_index = i - start_index  # Index for positioning within visible area
                
            item_rect = pygame.Rect(rect.x + 10, start_y + visible_index * (item_height + item_spacing), rect.width - 20, item_height)
            
            if item_rect.bottom > rect.bottom:
                break
            
            # Highlight selected item
            if i == self.selection and self.selection_category == 'consumable':
                pygame.draw.rect(screen, (60, 60, 80), item_rect, border_radius=4)
                pygame.draw.rect(screen, (255, 210, 120), item_rect, width=2, border_radius=4)
            else:
                pygame.draw.rect(screen, (40, 40, 50), item_rect, border_radius=4)
                border_color = rarity_border_color(item)
                pygame.draw.rect(screen, border_color, item_rect, width=1, border_radius=4)
            
            # Item icon - maximized for better visibility
            icon_rect = pygame.Rect(item_rect.x + 6, item_rect.y + 5, 64, 64)  # Increased size
            icon_surf = None
            if hasattr(item, 'icon_path') and item.icon_path:
                surf = _safe_load_icon(item.icon_path, (icon_rect.width, icon_rect.height))
                if surf:
                    icon_surf = surf
                else:
                    try:
                        icon_surf = load_icon_masked(item.icon_path, (icon_rect.width, icon_rect.height), radius=6)
                    except Exception:
                        icon_surf = None
            
            # Draw rarity border around icon
            border_color = rarity_border_color(item)
            pygame.draw.rect(screen, border_color, icon_rect.inflate(4, 4), width=2, border_radius=8)
            
            if icon_surf:
                screen.blit(icon_surf, icon_rect)
            else:
                pygame.draw.rect(screen, item.color, icon_rect, border_radius=6)
                if hasattr(item, 'icon_letter'):
                    icon_text = get_font(20, bold=True).render(item.icon_letter, True, (20, 20, 28))
                    icon_text_rect = icon_text.get_rect(center=icon_rect.center)
                    screen.blit(icon_text, icon_text_rect)
            
            # Item name
            name_font = get_font(14, bold=True)
            name_text = name_font.render(item.name, True, (220, 220, 235))
            screen.blit(name_text, (item_rect.x + 78, item_rect.y + 8))
            
            # Stock count
            stock = self.consumable_stock.get(item.key, 0)
            stock_font = get_font(12)
            stock_text = stock_font.render(f"Stock: {stock}", True, (150, 255, 150))
            screen.blit(stock_text, (item_rect.x + 78, item_rect.y + 26))
            
            # Price and buy button
            price = self._get_item_price(item)
            price_font = get_font(12, bold=True)
            button_font = get_font(11, bold=True)
            
            # Price
            price_color = GREEN if self.game.player.money >= price else (150, 150, 150)
            price_text = price_font.render(f"{price}c", True, price_color)
            screen.blit(price_text, (item_rect.x + 78, item_rect.y + 44))
            
            # Buy button
            button_rect = pygame.Rect(item_rect.right - 62, item_rect.y + 22, 58, 24)  # Adjusted for new height
            
            # Check if sold out
            is_sold_out = stock <= 0
            button_text = "BUY" if not is_sold_out else "SOLD"
            
            # Button color
            if is_sold_out:
                button_color = (60, 60, 60)
            elif self.game.player.money >= price:
                button_color = (0, 150, 0)
            else:
                button_color = (100, 80, 80)
            
            pygame.draw.rect(screen, button_color, button_rect, border_radius=2)
            pygame.draw.rect(screen, (150, 150, 170), button_rect, width=1, border_radius=2)
            
            button_text_color = (180, 180, 180) if is_sold_out else (255, 255, 255)
            button_surface = button_font.render(button_text, True, button_text_color)
            button_text_rect = button_surface.get_rect(center=button_rect.center)
            screen.blit(button_surface, button_text_rect)
            
            # Register regions
            self.regions.append({'rect': button_rect, 'item': item, 'action': 'buy'})
            self.regions.append({'rect': item_rect, 'item': item})
        
        # Draw scroll indicators for consumables
        total_consumable_items = len(consumable_items)
        if total_consumable_items > self.max_visible_consumables:
            self._draw_scroll_indicators(screen, rect, total_consumable_items, self.consumable_scroll_offset, 'consumable', self.max_visible_consumables)
    
    
    def _draw_scroll_indicators(self, screen, rect, total_items, scroll_offset, list_type, max_visible):
        """Draw scroll indicators for lists with enhanced clickable buttons"""
        if total_items <= max_visible:
            return  # No scrolling needed
        
        # Get mouse position for hover effects
        mouse_pos = pygame.mouse.get_pos()
        
        # Draw scroll up arrow button (larger and more visible)
        if scroll_offset > 0:
            arrow_up_rect = pygame.Rect(rect.right - 30, rect.y + 5, 25, 20)
            is_hovering = arrow_up_rect.collidepoint(mouse_pos)
            
            # Button background
            bg_color = (80, 80, 100) if is_hovering else (60, 60, 80)
            pygame.draw.rect(screen, bg_color, arrow_up_rect, border_radius=4)
            pygame.draw.rect(screen, (150, 150, 170), arrow_up_rect, width=1, border_radius=4)
            
            # Arrow
            arrow_color = (255, 255, 255) if is_hovering else (200, 200, 220)
            pygame.draw.polygon(screen, arrow_color, [
                (arrow_up_rect.centerx, arrow_up_rect.y + 5),
                (arrow_up_rect.x + 5, arrow_up_rect.bottom - 5),
                (arrow_up_rect.right - 5, arrow_up_rect.bottom - 5)
            ])
            self.regions.append({'rect': arrow_up_rect, 'action': f'scroll_up_{list_type}'})
        
        # Draw scroll down arrow button (larger and more visible)
        if scroll_offset + max_visible < total_items:
            arrow_down_rect = pygame.Rect(rect.right - 30, rect.bottom - 25, 25, 20)
            is_hovering = arrow_down_rect.collidepoint(mouse_pos)
            
            # Button background
            bg_color = (80, 80, 100) if is_hovering else (60, 60, 80)
            pygame.draw.rect(screen, bg_color, arrow_down_rect, border_radius=4)
            pygame.draw.rect(screen, (150, 150, 170), arrow_down_rect, width=1, border_radius=4)
            
            # Arrow
            arrow_color = (255, 255, 255) if is_hovering else (200, 200, 220)
            pygame.draw.polygon(screen, arrow_color, [
                (arrow_down_rect.centerx, arrow_down_rect.bottom - 5),
                (arrow_down_rect.x + 5, arrow_down_rect.y + 5),
                (arrow_down_rect.right - 5, arrow_down_rect.y + 5)
            ])
            self.regions.append({'rect': arrow_down_rect, 'action': f'scroll_down_{list_type}'})
        
        # Draw scroll position indicator bar
        if total_items > 0:
            scroll_progress = scroll_offset / max(1, total_items - max_visible)
            indicator_height = max(20, int((max_visible / total_items) * (rect.height - 50)))
            indicator_y = rect.y + 30 + int(scroll_progress * (rect.height - 60 - indicator_height))
            indicator_rect = pygame.Rect(rect.right - 10, indicator_y, 6, indicator_height)
            
            # Track background
            track_rect = pygame.Rect(rect.right - 10, rect.y + 30, 6, rect.height - 60)
            pygame.draw.rect(screen, (40, 40, 50), track_rect, border_radius=3)
            
            # Indicator
            pygame.draw.rect(screen, (120, 120, 140), indicator_rect, border_radius=3)
            pygame.draw.rect(screen, (180, 180, 200), indicator_rect, width=1, border_radius=3)
    
    def _handle_mousewheel_scroll(self, mouse_pos, scroll_direction):
        """Handle mouse wheel scrolling based on which column is over.

        Returns True if scroll was handled by a specific column, False otherwise.
        """
        # Calculate column bounds (same as in draw method)
        margin = 40
        panel_width = WIDTH - (margin * 2)
        panel_height = HEIGHT - (margin * 2)
        panel_x = margin
        panel_y = margin

        column_margin = 12
        header_height = 60
        content_y = panel_y + header_height + 20
        content_height = panel_height - header_height - 80  # Leave space for footer

        # First check if mouse is within shop panel at all
        panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        if not panel_rect.collidepoint(mouse_pos):
            return False  # Mouse is outside the shop panel entirely

        # Left column: Shop items list (40% width) - more precise calculation
        left_width = int(panel_width * 0.40)
        left_rect = pygame.Rect(panel_x + 10, content_y, left_width, content_height)

        # Middle column: Player slots (30% width) - ensure no overlap
        middle_width = int(panel_width * 0.28)
        middle_rect = pygame.Rect(left_rect.right + column_margin, content_y, middle_width, content_height)

        # Right column: Player info (remaining width) - ensure no overlap
        right_width = panel_width - left_width - middle_width - column_margin * 3 - 20
        right_rect = pygame.Rect(middle_rect.right + column_margin, content_y, right_width, content_height)

        # If we have persisted grid rectangles from drawing code, check those first
        # They are more accurate and guarantee consistency with what is drawn to screen.
        try:
            # Right stock grid
            if hasattr(self, 'right_stock_grid_rect') and self.right_stock_grid_rect and self.right_stock_grid_rect.collidepoint(mouse_pos):
                # Scroll the inventory stock view
                scroll_amount = 50
                if scroll_direction > 0:
                    self.stock_scroll_offset = max(0, self.stock_scroll_offset - scroll_amount)
                else:
                    self.stock_scroll_offset += scroll_amount
                return True

            # Right stats area
            if hasattr(self, 'right_stats_area_rect') and self.right_stats_area_rect and self.right_stats_area_rect.collidepoint(mouse_pos):
                if scroll_direction > 0:
                    self.player_info_scroll_offset = max(0, self.player_info_scroll_offset - 22)
                else:
                    self.player_info_scroll_offset += 22
                return True

            # Middle rect (slots) - consume so left pane doesn't receive wheel events while cursor in this column
            if hasattr(self, 'middle_rect') and self.middle_rect and self.middle_rect.collidepoint(mouse_pos):
                return True

            # Left grid - scroll if within left grid
            if hasattr(self, 'left_grid_rect') and self.left_grid_rect and self.left_grid_rect.collidepoint(mouse_pos):
                if scroll_direction > 0:
                    self._scroll_up()
                else:
                    self._scroll_down()
                return True
        except Exception:
            # Fall back to recompute approach below if persisted rects are not available
            pass

        # No persisted rects or persisted rects didn't match: fall back
        # Use horizontal x coordinate to determine which column should receive the scroll
        mx, my = mouse_pos

        # Check Right column scrollable areas first (to avoid left column capturing events)
        if right_rect.collidepoint(mouse_pos):
            # If stock view is open (selected_slot_type set), compute the stock grid rect and only scroll if over grid
            if self.selected_slot_type is not None:
                # Compute unequip button and grid area exactly like _draw_inventory_stock_view
                header_height = 50
                unequip_button_height = 36
                unequip_button_y = right_rect.y + header_height + 8
                grid_y = unequip_button_y + unequip_button_height + 8
                grid_height = right_rect.bottom - grid_y - 10
                grid_rect = pygame.Rect(right_rect.x + 10, grid_y, right_rect.width - 20, max(0, grid_height))

                if grid_rect.collidepoint(mouse_pos):
                    scroll_amount = 50  # Pixel scroll
                    if scroll_direction > 0:
                        self.stock_scroll_offset = max(0, self.stock_scroll_offset - scroll_amount)
                    else:
                        self.stock_scroll_offset += scroll_amount
                    return True
                # If mouse is in right column but not over the stock grid area, prevent other scrolling
                return True
            else:
                # Compute the player stats area
                model_height = 120
                model_rect = pygame.Rect(right_rect.x + 10, right_rect.y + 10, right_rect.width - 20, model_height)
                stats_header_y = model_rect.bottom + 10
                stats_header_height = 30
                stats_area_y = stats_header_y + stats_header_height + 8
                stats_area_height = right_rect.bottom - stats_area_y - 10
                stats_area_rect = pygame.Rect(right_rect.x + 10, stats_area_y, right_rect.width - 20, max(0, stats_area_height))

                if stats_area_rect.collidepoint(mouse_pos):
                    # Scroll player info stats by line height
                    if scroll_direction > 0:
                        self.player_info_scroll_offset = max(0, self.player_info_scroll_offset - 22)  # line height
                    else:
                        self.player_info_scroll_offset += 22
                    return True
                # Mouse in right column but not over stats area -> consume event to prevent left scroll
                return True

        # If mouse is over middle column area -> consume but don't scroll
        if middle_rect.collidepoint(mouse_pos):
            return True

        # If mouse is over left column area (shop items) -> check the actual scrollable grid rectangle
        if left_rect.collidepoint(mouse_pos):
            header_h = 36
            buy_button_height = 36
            bottom_padding = 18

            grid_y = left_rect.y + header_h + 8
            grid_height = left_rect.height - header_h - buy_button_height - bottom_padding - 8
            grid_rect = pygame.Rect(left_rect.x + 16, grid_y, left_rect.width - 32, max(0, grid_height))

            # Only scroll if mouse is actually within the scrollable list area (not header/buy button)
            if grid_rect.collidepoint(mouse_pos):
                if scroll_direction > 0:
                    self._scroll_up()
                else:
                    self._scroll_down()
                return True
            # Mouse over left column but not in scrollable grid: consume event to prevent other lists from scrolling
            return True

        # Mouse is in gaps between columns or outside content area
        return False
    
    def _scroll_up(self):
        """Scroll up in shop list"""
        if self.gear_scroll_offset > 0:
            self.gear_scroll_offset -= 50  # Scroll by pixels
            self.gear_scroll_offset = max(0, self.gear_scroll_offset)
    
    def _scroll_down(self):
        """Scroll down in shop list"""
        # Calculate max scroll based on grid layout
        total_items = len(self.selected_gear) + len(self.selected_consumables)
        if total_items > 0:
            self.gear_scroll_offset += 50  # Scroll by pixels
            # Max scroll will be calculated in draw method
    
    def _scroll_to_top(self):
        """Scroll to top of current list"""
        if self.selection_category == 'gear':
            self.gear_scroll_offset = 0
            self.selection = 0
        else:  # consumable
            self.consumable_scroll_offset = 0
            self.selection = 0
    
    def _scroll_to_bottom(self):
        """Scroll to bottom of current list"""
        if self.selection_category == 'gear':
            self.gear_scroll_offset = max(0, len(self.selected_gear) - self.max_visible_gear)
            self.selection = len(self.selected_gear) - 1
        else:  # consumable
            self.consumable_scroll_offset = max(0, len(self.selected_consumables) - self.max_visible_consumables)
            self.selection = len(self.selected_consumables) - 1

    def draw_tooltip_overlay(self, screen):
        """Draw any shop tooltip overlay last so it appears above all UI."""
        if not self.shop_open:
            return
        mouse_pos = pygame.mouse.get_pos()
        hover_item = self._get_item_at_pos(mouse_pos)
        if not hover_item:
            return
        # Ensure no clip
        try:
            screen.set_clip(None)
        except Exception:
            pass
        self._draw_shop_tooltip(screen, hover_item, mouse_pos)
    
    def handle_mouse_click(self, pos):
        """Handle mouse clicks in shop"""
        if not self.shop_open:
            return
        
        for info in self.regions:
            if info['rect'].collidepoint(pos):
                action = info.get('action')
                if action == 'buy':
                    # legacy per-item buy button - allow it as before
                    item = info.get('item')
                    if item:
                        self.purchase_item(item)
                elif action == 'buy_selected':
                    # Buy currently selected item from the left column
                    selected_item = None
                    if self.selection_category == 'gear' and 0 <= self.selection < len(self.selected_gear):
                        selected_item = self.selected_gear[self.selection]
                    elif self.selection_category == 'consumable' and 0 <= self.selection < len(self.selected_consumables):
                        selected_item = self.selected_consumables[self.selection]
                    if selected_item:
                        # Trigger click feedback
                        self.buy_button_click_time = pygame.time.get_ticks()
                        self.purchase_item(selected_item)
                elif action == 'exit':
                    self.close_shop()
                elif action == 'select_gear_slot':
                    # Select gear slot to view inventory
                    slot_idx = info.get('slot_index')
                    if slot_idx is not None:
                        if self.selected_slot_type == 'gear' and self.selected_slot_index == slot_idx:
                            # Deselect if clicking the same slot
                            self.selected_slot_type = None
                            self.selected_slot_index = None
                        else:
                            self.selected_slot_type = 'gear'
                            self.selected_slot_index = slot_idx
                            self.stock_scroll_offset = 0
                elif action == 'select_consumable_slot':
                    # Select consumable slot to view inventory
                    slot_idx = info.get('slot_index')
                    if slot_idx is not None:
                        if self.selected_slot_type == 'consumable' and self.selected_slot_index == slot_idx:
                            # Deselect if clicking the same slot
                            self.selected_slot_type = None
                            self.selected_slot_index = None
                        else:
                            self.selected_slot_type = 'consumable'
                            self.selected_slot_index = slot_idx
                            self.stock_scroll_offset = 0
                elif action == 'toggle_equip_item':
                    # Equip or unequip item from stock view
                    item_key = info.get('item_key')
                    if item_key and self.selected_slot_index is not None and hasattr(self.game, 'inventory'):
                        inventory = self.game.inventory
                        idx = self.selected_slot_index
                        
                        if self.selected_slot_type == 'gear':
                            inventory._equip_armament(idx, item_key)
                            # Move selection to next free slot after equipping
                            if idx < len(inventory.gear_slots) and inventory.gear_slots[idx] is not None:
                                next_free = None
                                for offset in range(1, len(inventory.gear_slots)):
                                    cand = (idx + offset) % len(inventory.gear_slots)
                                    if inventory.gear_slots[cand] is None:
                                        next_free = cand
                                        break
                                if next_free is not None:
                                    # Move to next free slot
                                    self.selected_slot_index = next_free
                                # If all slots full, selection stays on current slot (no change needed)
                                
                        elif self.selected_slot_type == 'consumable':
                            inventory._equip_consumable(idx, item_key)
                            # Move selection to next free slot after equipping
                            if idx < len(inventory.consumable_slots) and inventory.consumable_slots[idx] is not None:
                                next_free = None
                                for offset in range(1, len(inventory.consumable_slots)):
                                    cand = (idx + offset) % len(inventory.consumable_slots)
                                    if inventory.consumable_slots[cand] is None:
                                        next_free = cand
                                        break
                                if next_free is not None:
                                    # Move to next free slot
                                    self.selected_slot_index = next_free
                                # If all slots full, selection stays on current slot (no change needed)
                elif action == 'unequip_slot':
                    # Unequip item from selected slot by directly clearing it
                    if self.selected_slot_index is not None and hasattr(self.game, 'inventory'):
                        inventory = self.game.inventory
                        idx = self.selected_slot_index
                        
                        if self.selected_slot_type == 'gear':
                            # Clear gear slot and recalculate stats
                            if idx < len(inventory.gear_slots):
                                inventory.gear_slots[idx] = None
                                inventory.recalculate_player_stats()
                                
                                # Move selection to next equipped slot, or close stock view if all empty
                                next_equipped = None
                                for offset in range(1, len(inventory.gear_slots)):
                                    cand = (idx + offset) % len(inventory.gear_slots)
                                    if inventory.gear_slots[cand] is not None:
                                        next_equipped = cand
                                        break
                                
                                if next_equipped is not None:
                                    # Move to next equipped slot
                                    self.selected_slot_index = next_equipped
                                else:
                                    # All slots empty, close stock view
                                    self.selected_slot_type = None
                                    self.selected_slot_index = None
                                    
                        elif self.selected_slot_type == 'consumable':
                            # Unequip consumable slot (returns items to storage)
                            inventory._unequip_consumable_slot(idx)
                            
                            # Move selection to next equipped slot, or close stock view if all empty
                            next_equipped = None
                            for offset in range(1, len(inventory.consumable_slots)):
                                cand = (idx + offset) % len(inventory.consumable_slots)
                                if inventory.consumable_slots[cand] is not None:
                                    next_equipped = cand
                                    break
                            
                            if next_equipped is not None:
                                # Move to next equipped slot
                                self.selected_slot_index = next_equipped
                            else:
                                # All slots empty, close stock view
                                self.selected_slot_type = None
                                self.selected_slot_index = None
                elif action == 'scroll_up_gear':
                    if self.gear_scroll_offset > 0:
                        self.gear_scroll_offset = max(0, self.gear_scroll_offset - 50)
                        if self.selection < self.gear_scroll_offset:
                            self.selection = self.gear_scroll_offset
                elif action == 'scroll_down_gear':
                    # Scroll down by a fixed amount; scrolling clamp is enforced when drawing
                    self.gear_scroll_offset = self.gear_scroll_offset + 50
                elif action == 'scroll_up_consumable':
                    if self.consumable_scroll_offset > 0:
                        self.consumable_scroll_offset = max(0, self.consumable_scroll_offset - 50)
                        if self.selection < self.consumable_scroll_offset:
                            self.selection = self.consumable_scroll_offset
                elif action == 'scroll_down_consumable':
                    self.consumable_scroll_offset = self.consumable_scroll_offset + 50
                elif info.get('item'):
                    # Click on item area - select it (no immediate purchase)
                    item = info.get('item')
                    if item:
                        if hasattr(item, 'modifiers'):
                            self.selection_category = 'gear'
                            try:
                                self.selection = self.selected_gear.index(item)
                            except ValueError:
                                pass
                        elif hasattr(item, 'use'):
                            self.selection_category = 'consumable'
                            try:
                                self.selection = self.selected_consumables.index(item)
                            except ValueError:
                                pass
                break
    
    def _get_item_price(self, item):
        """Calculate price for an item based on its rarity and properties"""
        # Rarity-based pricing for both consumables and equipment
        rarity = getattr(item, 'rarity', 'Normal')
        
        if hasattr(item, 'use'):  # Consumable
            # Base prices by rarity for consumables
            rarity_base_prices = {
                'Normal': 30,
                'Rare': 150,
                'Epic': 320,
                'Legendary': 720,
            }
            base_price = rarity_base_prices.get(rarity, 30)
        elif hasattr(item, 'modifiers'):  # Equipment
            # Base prices by rarity for equipment
            rarity_base_prices = {
                'Normal': 100,
                'Rare': 300,
                'Epic': 750,
                'Legendary': 1900,
            }
            base_price = rarity_base_prices.get(rarity, 100)
        else:  # Other items
            base_price = 30
        
        # Add some randomness but keep it consistent for this shop session
        if not hasattr(self, '_price_cache'):
            self._price_cache = {}
        
        if item.key not in self._price_cache:
            self._price_cache[item.key] = max(10, int(base_price * random.uniform(0.8, 1.2)))
        
        return self._price_cache[item.key]
