import pygame
import random
from config import WIDTH, HEIGHT, WHITE, GREEN, CYAN
from ..core.utils import draw_text, get_font
from .items import build_consumable_catalog, build_armament_catalog
from ..entities.entities import floating, DamageNumber


class Shop:
    def __init__(self, game):
        self.game = game
        self.shop_open = False
        self.selection = 0
        self.shop_consumables = build_consumable_catalog()
        self.shop_equipment = build_armament_catalog()
        
        # Track stock amounts for consumables
        self.consumable_stock = {}  # {item_key: available_stock}
        
        # Track which equipment has been purchased this shop visit
        self.purchased_equipment = set()  # {item_key}
        
        # Create random shop inventory (3 consumables, 3 equipment)
        self.refresh_inventory()
        
        # UI regions for interaction
        self.regions = []
        self.hover_item = None
        self.hover_button = None  # Track which button is being hovered
        
    def refresh_inventory(self):
        """Create random selection of 3 consumables and 3 equipment"""
        # Clear previous stock and purchased equipment tracking
        self.consumable_stock = {}
        self.purchased_equipment = set()
        
        # Randomly select 3 consumables
        consumable_keys = list(self.shop_consumables.keys())
        random.shuffle(consumable_keys)
        self.selected_consumables = []
        
        for key in consumable_keys[:3]:
            item = self.shop_consumables[key]
            self.selected_consumables.append(item)
            
            # Generate random stock amount (1-3 common, 4-5 rare)
            if random.random() < 0.7:  # 70% chance for common stock (1-3)
                stock = random.randint(1, 3)
            else:  # 30% chance for rare stock (4-5)
                stock = random.randint(4, 5)
            
            self.consumable_stock[key] = stock
        
        # Randomly select 3 equipment
        equipment_keys = list(self.shop_equipment.keys())
        random.shuffle(equipment_keys)
        self.selected_equipment = [
            self.shop_equipment[key] for key in equipment_keys[:3]
        ]
        
        # Combine for easier iteration
        self.shop_items = self.selected_consumables + self.selected_equipment
    
    def open_shop(self):
        """Open the shop interface"""
        self.shop_open = True
        self.selection = 0
        self.refresh_inventory()
        
    def close_shop(self):
        """Close the shop interface"""
        self.shop_open = False
        self.selection = 0
        self.regions = []
        self.hover_item = None
    
    def can_afford(self, item):
        """Check if player can afford an item"""
        # Generate price based on item type and properties
        if hasattr(item, 'amount'):  # Heal consumable
            base_price = 10 * item.amount
        elif hasattr(item, 'modifiers'):  # Equipment
            # Price based on total modifier values
            total_mods = sum(abs(v) for v in item.modifiers.values())
            base_price = int(50 * total_mods)
        else:  # Other consumables
            base_price = 30
        
        # Add some randomness
        price = max(10, int(base_price * random.uniform(0.8, 1.2)))
        return self.game.player.money >= price
    
    def purchase_item(self, item):
        """Attempt to purchase an item"""
        # Calculate price
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
            # Add to inventory instead of using immediately
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
        """Add purchased equipment to inventory storage without equipping it"""
        # Add to inventory system storage instead of equipping
        if hasattr(self.game, 'inventory'):
            # Add to armament order if not already there
            if equipment.key not in self.game.inventory.armament_order:
                self.game.inventory.armament_order.append(equipment.key)
            # Don't equip - just add to the available stock
            # The player can equip it manually from the inventory
        else:
            # Fallback: apply modifiers directly to player
            player = self.game.player
            for stat, value in equipment.modifiers.items():
                if hasattr(player, stat):
                    setattr(player, stat, getattr(player, stat) + value)
    
    def handle_input(self):
        """Handle shop input - this method is deprecated, use handle_event instead"""
        # This method is kept for compatibility but should not be used
        pass
    
    def handle_event(self, event):
        """Handle shop events properly using event-based input"""
        if event.type == pygame.KEYDOWN:
            # Navigation - support both arrow keys and WASD
            if event.key in [pygame.K_UP, pygame.K_w]:
                self.selection = (self.selection - 1) % len(self.shop_items)
            elif event.key in [pygame.K_DOWN, pygame.K_s]:
                self.selection = (self.selection + 1) % len(self.shop_items)
            elif event.key in [pygame.K_LEFT, pygame.K_a]:
                self.selection = (self.selection - 1) % len(self.shop_items)
            elif event.key in [pygame.K_RIGHT, pygame.K_d]:
                self.selection = (self.selection + 1) % len(self.shop_items)
            
            # Purchase
            elif event.key in [pygame.K_RETURN, pygame.K_SPACE]:
                if self.selection < len(self.shop_items):
                    item = self.shop_items[self.selection]
                    self.purchase_item(item)
            
            # Close shop
            elif event.key in [pygame.K_ESCAPE, pygame.K_i]:
                self.close_shop()
    
    def _get_item_at_pos(self, pos):
        """Get shop item at mouse position"""
        for info in self.regions:
            if info['rect'].collidepoint(pos):
                return info.get('item')
        return None
    
    def _draw_shop_tooltip(self, screen, item, mouse_pos):
        """Draw tooltip for shop item"""
        if not item:
            return
        
        lines = item.tooltip_lines()
        if not lines:
            return
        
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
        
        font = get_font(16)
        icon_space = 34  # Space for icon
        width = max(font.size(line)[0] for line in lines) + 20 + icon_space
        height = len(lines) * 22 + 12
        
        tooltip_rect = pygame.Rect(mouse_pos[0] + 18, mouse_pos[1] + 18, width, height)
        
        # Adjust position if tooltip goes off screen
        if tooltip_rect.right > WIDTH - 8:
            tooltip_rect.x = WIDTH - width - 8
        if tooltip_rect.bottom > HEIGHT - 8:
            tooltip_rect.y = HEIGHT - height - 8
        
        # Draw tooltip background
        pygame.draw.rect(screen, (28, 28, 38), tooltip_rect, border_radius=8)
        pygame.draw.rect(screen, (180, 170, 200), tooltip_rect, width=1, border_radius=8)
        
        # Draw icon
        icon_rect = pygame.Rect(tooltip_rect.x + 10, tooltip_rect.y + 10, 24, 24)
        pygame.draw.rect(screen, item.color, icon_rect, border_radius=6)
        if hasattr(item, 'icon_letter'):
            icon_font = get_font(14, bold=True)
            icon_surf = icon_font.render(item.icon_letter, True, (10, 10, 20))
            screen.blit(icon_surf, icon_surf.get_rect(center=icon_rect.center))
        
        # Draw text
        text_x = tooltip_rect.x + 10 + icon_space
        for i, line in enumerate(lines):
            screen.blit(font.render(line, True, (230, 230, 245)),
                     (text_x, tooltip_rect.y + 6 + i * 22))
    
    def draw(self, screen):
        """Draw the shop interface"""
        if not self.shop_open:
            return
        
        # Darken background
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))
        
        # Shop panel - resized to fit screen better
        panel_width = min(700, WIDTH - 40)  # Ensure 20px margin on each side
        panel_height = min(500, HEIGHT - 60)  # Ensure 30px margin top/bottom
        panel_x = (WIDTH - panel_width) // 2
        panel_y = (HEIGHT - panel_height) // 2
        
        panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        pygame.draw.rect(screen, (30, 28, 40), panel_rect, border_radius=12)
        pygame.draw.rect(screen, (210, 200, 170), panel_rect, width=2, border_radius=12)
        
        # Clear regions for mouse interaction
        self.regions = []
        
        # Title
        title_font = get_font(28, bold=True)
        title_text = title_font.render("MYSTIC SHOP", True, (240, 220, 190))
        title_rect = title_text.get_rect(center=(panel_x + panel_width // 2, panel_y + 30))
        screen.blit(title_text, title_rect)
        
        # Item layout settings
        item_width = 280
        item_height = 80
        item_spacing = 20
        items_per_row = 2
        start_y = panel_y + 80
        start_x = panel_x + (panel_width - (items_per_row * item_width + (items_per_row - 1) * item_spacing)) // 2
        
        # Draw items
        item_font = get_font(16)
        price_font = get_font(14)
        button_font = get_font(12, bold=True)
        
        for i, item in enumerate(self.shop_items):
            row = i // items_per_row
            col = i % items_per_row
            
            item_x = start_x + col * (item_width + item_spacing)
            item_y = start_y + row * (item_height + item_spacing)
            
            # Item background
            item_rect = pygame.Rect(item_x, item_y, item_width, item_height)
            
            # Highlight selected item
            if i == self.selection:
                pygame.draw.rect(screen, (60, 60, 80), item_rect, border_radius=8)
                pygame.draw.rect(screen, (255, 210, 120), item_rect, width=2, border_radius=8)
            else:
                pygame.draw.rect(screen, (40, 40, 50), item_rect, border_radius=8)
                pygame.draw.rect(screen, (100, 100, 120), item_rect, width=1, border_radius=8)
            
            # Item icon (left side)
            icon_rect = pygame.Rect(item_x + 15, item_y + 15, 50, 50)
            pygame.draw.rect(screen, item.color, icon_rect, border_radius=6)
            
            # Item icon letter
            if hasattr(item, 'icon_letter'):
                icon_text = get_font(24, bold=True).render(item.icon_letter, True, (20, 20, 28))
                icon_text_rect = icon_text.get_rect(center=icon_rect.center)
                screen.blit(icon_text, icon_text_rect)
            
            # Display stock amount for consumables (bottom left of icon)
            if hasattr(item, 'use'):  # Consumable
                stock_amount = self.consumable_stock.get(item.key, 0)
                if stock_amount > 0:
                    stock_font = get_font(12, bold=True)
                    stock_text = stock_font.render(str(stock_amount), True, (255, 255, 255))
                    stock_rect = stock_text.get_rect(bottomleft=(icon_rect.left + 2, icon_rect.bottom - 2))
                    # Draw a small background for better visibility
                    pygame.draw.rect(screen, (0, 0, 0, 180), stock_rect.inflate(4, 2))
                    screen.blit(stock_text, stock_rect)
            
            # Item name (right side of icon)
            name_color = GREEN if self.game.player.money >= self._get_item_price(item) else (150, 150, 150)
            name_text = item_font.render(item.name, True, name_color)
            screen.blit(name_text, (item_x + 75, item_y + 15))
            
            # Price (below name)
            price = self._get_item_price(item)
            price_text = price_font.render(f"{price} coins", True, name_color)
            screen.blit(price_text, (item_x + 75, item_y + 35))
            
            # Buy button (on right side, beside price)
            button_rect = pygame.Rect(item_x + 165, item_y + 35, 90, 20)
            
            # Check if mouse is hovering over this button
            mouse_pos = pygame.mouse.get_pos()
            is_hovering = button_rect.collidepoint(mouse_pos)
            
            # Check if item is sold out or player owns max amount
            is_sold_out = False
            button_text = "BUY"
            
            if hasattr(item, 'use'):  # Consumable
                stock_amount = self.consumable_stock.get(item.key, 0)
                player_owned = 0
                if hasattr(self.game, 'inventory'):
                    player_owned = self.game.inventory._total_available_count(item.key)
                
                # Check if sold out or player owns max amount (20)
                if stock_amount <= 0 or player_owned >= 20:
                    is_sold_out = True
                    button_text = "SOLD OUT"
            elif hasattr(item, 'modifiers'):  # Equipment
                # Check if player already owns this equipment
                player_owns_item = False
                if hasattr(self.game, 'inventory'):
                    player_owns_item = item.key in self.game.inventory.armament_order
                
                # Check if equipment has been purchased this shop visit
                if item.key in self.purchased_equipment or player_owns_item:
                    is_sold_out = True
                    button_text = "SOLD"
                else:
                    is_sold_out = False
                    button_text = "BUY"
            
            # Determine button color based on state
            if is_sold_out:
                button_color = (60, 60, 60)  # Dark gray for sold out
            elif self.game.player.money >= price:
                # Player can afford - yellow normally, green on hover
                button_color = (255, 215, 0) if not is_hovering else (0, 200, 0)  # Yellow -> Green
            else:
                # Player cannot afford - gray
                button_color = (100, 80, 80)
            
            pygame.draw.rect(screen, button_color, button_rect, border_radius=4)
            pygame.draw.rect(screen, (150, 150, 170), button_rect, width=1, border_radius=4)
            
            button_text_color = (180, 180, 180) if is_sold_out else (255, 255, 255)
            button_surface = button_font.render(button_text, True, button_text_color)
            button_text_rect = button_surface.get_rect(center=button_rect.center)
            screen.blit(button_surface, button_text_rect)
            
            # Register button region FIRST (so it has priority over item region)
            buy_region = {'rect': button_rect, 'item': item, 'action': 'buy'}
            self.regions.append(buy_region)
            
            # Register item region LAST (so it has lower priority)
            self.regions.append({'rect': item_rect, 'item': item})
        
        # Exit button at bottom center
        exit_button_width = 120
        exit_button_height = 40
        exit_button_x = panel_x + (panel_width - exit_button_width) // 2
        exit_button_y = panel_y + panel_height - 60
        exit_button_rect = pygame.Rect(exit_button_x, exit_button_y, exit_button_width, exit_button_height)
        
        # Check if mouse is hovering over exit button
        mouse_pos = pygame.mouse.get_pos()
        is_exit_hovering = exit_button_rect.collidepoint(mouse_pos)
        
        # Exit button color: gray normally, red on hover
        exit_button_color = (150, 150, 150) if not is_exit_hovering else (200, 50, 50)  # Gray -> Red
        exit_border_color = (200, 150, 150) if not is_exit_hovering else (255, 100, 100)
        
        pygame.draw.rect(screen, exit_button_color, exit_button_rect, border_radius=6)
        pygame.draw.rect(screen, exit_border_color, exit_button_rect, width=2, border_radius=6)
        
        exit_text = get_font(16, bold=True).render("EXIT", True, (255, 255, 255))
        exit_text_rect = exit_text.get_rect(center=exit_button_rect.center)
        screen.blit(exit_text, exit_text_rect)
        
        # Register exit button region
        self.regions.append({'rect': exit_button_rect, 'action': 'exit'})
        
        # Instructions
        inst_font = get_font(12)
        instructions = [
            "WASD/Arrows: Navigate",
            "Space/Enter: Buy",
            "ESC: Exit Shop"
        ]
        
        for i, instruction in enumerate(instructions):
            inst_text = inst_font.render(instruction, True, (180, 180, 200))
            screen.blit(inst_text, (panel_x + 20, panel_y + panel_height - 40 + i * 12))
        
        # Handle mouse hover for tooltips
        mouse_pos = pygame.mouse.get_pos()
        hover_item = self._get_item_at_pos(mouse_pos)
        
        if hover_item:
            self._draw_shop_tooltip(screen, hover_item, mouse_pos)
    
    def handle_mouse_click(self, pos):
        """Handle mouse clicks in shop"""
        if not self.shop_open:
            return
        
        for info in self.regions:
            if info['rect'].collidepoint(pos):
                if info.get('action') == 'buy':
                    item = info.get('item')
                    if item:
                        self.purchase_item(item)
                elif info.get('action') == 'exit':
                    self.close_shop()
                elif info.get('item'):
                    # Click on item area - select it
                    item = info.get('item')
                    if item:
                        try:
                            self.selection = self.shop_items.index(item)
                        except ValueError:
                            pass
                break
    
    def _get_item_price(self, item):
        """Calculate price for an item based on its properties"""
        if hasattr(item, 'amount'):  # Heal consumable
            base_price = 10 * item.amount
        elif hasattr(item, 'modifiers'):  # Equipment
            # Price based on total modifier values
            total_mods = sum(abs(v) for v in item.modifiers.values())
            base_price = int(50 * total_mods)
        else:  # Other consumables
            base_price = 30
        
        # Add some randomness but keep it consistent for this shop session
        if not hasattr(self, '_price_cache'):
            self._price_cache = {}
        
        if item.key not in self._price_cache:
            self._price_cache[item.key] = max(10, int(base_price * random.uniform(0.8, 1.2)))
        
        return self._price_cache[item.key]