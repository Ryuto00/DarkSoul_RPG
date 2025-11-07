"""
Test script for the new enemy movement system
Run this to see how enemies move with different strategies
"""

import pygame
import sys
from enemy_entities import Bug, Frog, Archer, WizardCaster, Assassin, Bee, Golem, Boss
from terrain_system import terrain_system
from enemy_movement import MovementStrategyFactory
from config import FPS, TILE, WHITE


class MockLevel:
    """Mock level for testing"""
    def __init__(self, width=20, height=15):
        self.width = width
        self.height = height
        self.solids = []
        
        # Create some test platforms
        self.solids.append(pygame.Rect(0, height*TILE - 40, width*TILE, 40))  # Ground
        self.solids.append(pygame.Rect(5*TILE, height*TILE - 120, 4*TILE, 20))  # Platform
        self.solids.append(pygame.Rect(12*TILE, height*TILE - 160, 3*TILE, 20))  # Platform


class MockPlayer:
    """Mock player for testing"""
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 20, 30)
        self.inv = 0


def test_movement_strategies():
    """Test different movement strategies"""
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Enemy Movement System Test")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 24)
    
    # Create test level
    level = MockLevel()
    
    # Create test enemies
    enemies = [
        Bug(100, 400),
        Frog(200, 400),
        Archer(300, 400),
        WizardCaster(400, 400),
        Assassin(500, 400),
        Bee(600, 200),
        Golem(150, 300),
        Boss(400, 300)
    ]
    
    # Create mock player
    player = MockPlayer(400, 200)
    
    # Load terrain for level
    terrain_system.load_terrain_from_level(level)
    
    running = True
    show_terrain = False
    
    print("Enemy Movement System Test")
    print("Controls:")
    print("Arrow Keys: Move player")
    print("T: Toggle terrain overlay")
    print("ESC: Exit")
    print("\nEnemy Types:")
    for i, enemy in enumerate(enemies):
        strategy_name = enemy.movement_strategy.name if enemy.movement_strategy else "None"
        print(f"{i+1}. {enemy.__class__.__name__}: {strategy_name}")
    
    while running:
        dt = clock.tick(FPS) / 1000.0
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_t:
                    show_terrain = not show_terrain
        
        # Handle player input
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            player.rect.x -= 5
        if keys[pygame.K_RIGHT]:
            player.rect.x += 5
        if keys[pygame.K_UP]:
            player.rect.y -= 5
        if keys[pygame.K_DOWN]:
            player.rect.y += 5
        
        # Update enemies
        for enemy in enemies:
            enemy.tick(level, player)
        
        # Draw everything
        screen.fill((20, 20, 30))
        
        # Draw terrain
        if show_terrain:
            terrain_system.draw_terrain_overlay(screen, MockCamera(), True)
        
        # Draw level solids
        for solid in level.solids:
            pygame.draw.rect(screen, (100, 100, 100), solid)
        
        # Draw enemies
        for enemy in enemies:
            enemy.draw(screen, MockCamera(), show_los=False)
            
            # Draw enemy name and strategy
            strategy_name = enemy.movement_strategy.name if enemy.movement_strategy else "None"
            text = font.render(f"{enemy.__class__.__name__}: {strategy_name}", True, WHITE)
            screen.blit(text, (enemy.rect.x, enemy.rect.y - 25))
        
        # Draw player
        pygame.draw.rect(screen, (0, 255, 0), player.rect)
        
        # Draw instructions
        instructions = [
            "Arrow Keys: Move player",
            "T: Toggle terrain overlay",
            "ESC: Exit"
        ]
        for i, instruction in enumerate(instructions):
            text = font.render(instruction, True, WHITE)
            screen.blit(text, (10, 10 + i * 25))
        
        # Show terrain status
        if show_terrain:
            terrain_text = font.render("Terrain Overlay: ON", True, (255, 255, 0))
            screen.blit(terrain_text, (10, 100))
        
        pygame.display.flip()
    
    pygame.quit()
    sys.exit()


class MockCamera:
    """Mock camera for testing"""
    def to_screen(self, pos):
        return pos  # No camera transformation for test
    
    def to_screen_rect(self, rect):
        return rect


if __name__ == "__main__":
    test_movement_strategies()