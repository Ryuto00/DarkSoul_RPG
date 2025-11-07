import pygame
import random
from config import WIDTH, HEIGHT, WHITE, GREEN, CYAN
from utils import draw_text, get_font
from shop_items import build_shop_consumables, build_shop_equipment
from entities import floating, DamageNumber


class Shop:
    def __init__(self, game):
        self.game = game
        self.shop_open = False
        self.selection = 0
        self.shop_consumables = build_shop_consumables()
        self.shop_equipment = build_shop_equipment()
        
        # Create random shop inventory (3 consumables, 3 equipment)
        self.refresh_inventory()
        
        # UI regions for interaction
        self.regions = []
        self.hover_item = None
        
    def refresh_inventory(self):
        """Create random selection of 3 consumables and 3 equipment"""
        # Randomly select 3 consumables
        consumable_keys = list(self.shop_consumables.keys())
        random.shuffle(consumable_keys)
        self.selected_consumables = [
            self.shop_consumables[key] for key in consumable_keys[:3]
        ]
        
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
        return self.game.player.money >= item.price
    
    def purchase_item(self, item):
        """Attempt to purchase an item"""
        if not self.can_afford(item):
            floating.append(DamageNumber(
                self.game.player.rect.centerx,
                self.game.player.rect.top - 12,
                "Not enough coins!",
                (255, 100, 100)
            ))
            return False
        
        # Deduct money
        self.game.player.money -= item.price
        
        # Handle different item types
        if hasattr(item, 'use'):  # Consumable
            success = item.use(self.game)
            if success:
                floating.append(DamageNumber(
                    self.game.player.rect.centerx,
                    self.game.player.rect.top - 12,
                    f"Purchased {item.name}",
                    GREEN
                ))
            else:
                # Refund if item couldn't be used
                self.game.player.money += item.price
                return False
        else:  # Equipment
            self._equip_shop_item(item)
            floating.append(DamageNumber(
                self.game.player.rect.centerx,
                self.game.player.rect.top - 12,
                f"Equipped {item.name}",
                GREEN
            ))
        
        return True
    
    def _equip_shop_item(self, equipment):
        """Handle equipment purchase and equipping"""
        # Add to inventory system
        if hasattr(self.game, 'inventory'):
            # Find empty gear slot or replace existing
            for i in range(len(self.game.inventory.gear_slots)):
                if self.game.inventory.gear_slots[i] is None:
                    self.game.inventory.gear_slots[i] = equipment.key
                    self.game.inventory.recalculate_player_stats()
                    return
                elif self.game.inventory.gear_slots[i] == equipment.key:
                    # Already equipped, just refund
                    self.game.player.money += equipment.price
                    floating.append(DamageNumber(
                        self.game.player.rect.centerx,
                        self.game.player.rect.top - 12,
                        "Already equipped!",
                        (255, 200, 100)
                    ))
                    return
            
            # All slots full, replace first slot
            self.game.inventory.gear_slots[0] = equipment.key
            self.game.inventory.recalculate_player_stats()
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
            
            # Item name and price (right side of icon)
            name_color = GREEN if self.can_afford(item) else (150, 150, 150)
            name_text = item_font.render(item.name, True, name_color)
            screen.blit(name_text, (item_x + 75, item_y + 15))
            
            price_text = price_font.render(f"{item.price} coins", True, name_color)
            screen.blit(price_text, (item_x + 75, item_y + 35))
            
            # Buy button (below name)
            button_rect = pygame.Rect(item_x + 75, item_y + 55, 80, 20)
            button_color = (80, 150, 80) if self.can_afford(item) else (100, 80, 80)
            pygame.draw.rect(screen, button_color, button_rect, border_radius=4)
            pygame.draw.rect(screen, (150, 150, 170), button_rect, width=1, border_radius=4)
            
            button_text = button_font.render("BUY", True, (255, 255, 255))
            button_text_rect = button_text.get_rect(center=button_rect.center)
            screen.blit(button_text, button_text_rect)
            
            # Register button region FIRST (so it has priority over item region)
            buy_region = {'rect': button_rect, 'item': item, 'action': 'buy'}
            self.regions.append(buy_region)
            
            # Register item region LAST (so it has lower priority)
            self.regions.append({'rect': item_rect, 'item': item})
        
        # Exit button at bottom center
        exit_button_width = 100
        exit_button_height = 30
        exit_button_x = panel_x + (panel_width - exit_button_width) // 2
        exit_button_y = panel_y + panel_height - 50
        exit_button_rect = pygame.Rect(exit_button_x, exit_button_y, exit_button_width, exit_button_height)
        
        pygame.draw.rect(screen, (150, 80, 80), exit_button_rect, border_radius=6)
        pygame.draw.rect(screen, (200, 150, 150), exit_button_rect, width=2, border_radius=6)
        
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