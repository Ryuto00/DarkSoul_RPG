import pygame
from config import WIDTH, HEIGHT

class Camera:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.lerp = 0.12
        # >1.0 zooms in (larger = more zoomed); adjust to taste
        self.zoom = 1.5

    def update(self, target_rect: pygame.Rect):
        # center target in world coordinates taking zoom into account
        tx = target_rect.centerx - (WIDTH / (2 * self.zoom))
        ty = target_rect.centery - (HEIGHT / (2 * self.zoom))
        self.x += (tx - self.x) * self.lerp
        self.y += (ty - self.y) * self.lerp

    def to_screen(self, p):
        return (int((p[0] - self.x) * self.zoom), int((p[1] - self.y) * self.zoom))

    def to_screen_rect(self, r: pygame.Rect):
        return pygame.Rect(
            int((r.x - self.x) * self.zoom),
            int((r.y - self.y) * self.zoom),
            int(r.w * self.zoom),
            int(r.h * self.zoom)
        )
