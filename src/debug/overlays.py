import pygame
import logging
logger = logging.getLogger(__name__)

from config import TILE, WIDTH, HEIGHT
from src.core.utils import draw_text, get_font

class DebugOverlays:
    def __init__(self, game):
        self.game = game

    def draw_area_overlay(self):
        game = self.game
        if not getattr(game, 'debug_show_area_overlay', False):
            return
        try:
            lvl = getattr(game, 'level', None)
            if not lvl or not hasattr(lvl, 'level_id') or not hasattr(lvl, 'room_code'):

                return
            from src.level.level_loader import level_loader
            regions = level_loader.get_room_areas(lvl.level_id, lvl.room_code)
            if not regions:
                print(f"DEBUG: No regions found for {lvl.level_id}/{lvl.room_code}")
                return
            


            kind_colors = {
                'spawn': (50, 200, 50, 120),
                'player_spawn': (50, 120, 240, 160),
                'no_spawn': (200, 50, 50, 160),
                'hazard': (220, 80, 80, 160),
                'biome': (160, 220, 160, 110),
                'door_proximity': (200, 200, 80, 140),
                'safe_zone': (80, 200, 200, 110),
                'door_carve': (100, 150, 255, 140),  # Blue for door areas
            }

            overlay = pygame.Surface(game.screen.get_size(), pygame.SRCALPHA)

            for region in regions:
                base_color = kind_colors.get(region.kind, (180, 160, 220, 100))
                rcol = (base_color[0], base_color[1], base_color[2], int(base_color[3] * max(0.0, min(1.0, game.debug_area_overlay_opacity))))
                outline = (max(rcol[0]-40,0), max(rcol[1]-40,0), max(rcol[2]-40,0), min(255, 220))
                for r in region.rects:
                    wx = r.x * TILE
                    wy = r.y * TILE
                    ww = r.w * TILE
                    wh = r.h * TILE
                    sx = int((wx - game.camera.x) * game.camera.zoom)
                    sy = int((wy - game.camera.y) * game.camera.zoom)
                    sw = int(ww * game.camera.zoom)
                    sh = int(wh * game.camera.zoom)
                    if sw <= 0 or sh <= 0:
                        continue
                    rect_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
                    rect_surf.fill(rcol)
                    overlay.blit(rect_surf, (sx, sy))
                    try:
                        pygame.draw.rect(overlay, outline, pygame.Rect(sx, sy, sw, sh), width=2)
                    except Exception:
                        pass

                if region.rects:
                    r0 = region.rects[0]
                    wx = r0.x * TILE
                    wy = r0.y * TILE
                    sx = int((wx - game.camera.x) * game.camera.zoom)
                    sy = int((wy - game.camera.y) * game.camera.zoom)
                    label = f"{region.region_id} ({region.kind})"
                    try:
                        draw_text(overlay, label, (sx + 4, sy + 4), (235, 235, 235), size=14)
                    except Exception:
                        pass

            game.screen.blit(overlay, (0, 0))

            mx, my = pygame.mouse.get_pos()
            world_x = (mx / game.camera.zoom) + game.camera.x
            world_y = (my / game.camera.zoom) + game.camera.y
            tx = int(world_x // TILE)
            ty = int(world_y // TILE)

            hover_regions = [r for r in regions if r.contains_tile(tx, ty)]
            if hover_regions:
                hover_regions.sort(key=lambda r: r.priority, reverse=True)
                top = hover_regions[0]
                info_lines = [f"{top.region_id} ({top.kind})"]
                for k, v in top.properties.items():
                    info_lines.append(f"{k}: {v}")
                if top.allowed_enemy_types:
                    info_lines.append("allowed: " + ",".join(top.allowed_enemy_types))
                if top.banned_enemy_types:
                    info_lines.append("banned: " + ",".join(top.banned_enemy_types))
                if top.spawn_cap is not None:
                    info_lines.append(f"spawn_cap: {top.spawn_cap}")

                panel_w = 300
                font = get_font(14)
                line_h = font.get_linesize()
                panel_h = line_h * len(info_lines) + 10
                px = mx + 16
                py = my + 8
                if px + panel_w > WIDTH:
                    px = mx - panel_w - 16
                if py + panel_h > HEIGHT:
                    py = my - panel_h - 16
                panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
                panel.fill((8, 12, 18, 220))
                pygame.draw.rect(panel, (200, 200, 220, 200), panel.get_rect(), width=1)
                for i, line in enumerate(info_lines):
                    draw_text(panel, line, (8, 6 + i * line_h), (230, 230, 230), size=14)
                game.screen.blit(panel, (px, py))

        except Exception:
            return

    def get_player_area_labels(self):
        game = self.game
        areas = getattr(game.level, "areas", None)
        if not areas or not hasattr(areas, "areas_at"):
            return ""
        tx = game.player.rect.centerx // TILE
        ty = game.player.rect.centery // TILE
        here = areas.areas_at(tx, ty)
        if not here:
            return ""
        seen = set()
        types = []
        for a in here:
            if a.type not in seen:
                seen.add(a.type)
                types.append(a.type)
        return ", ".join(types)

    def get_grid_position(self, mouse_screen_pos):
        game = self.game
        world_x = (mouse_screen_pos[0] / game.camera.zoom) + game.camera.x
        world_y = (mouse_screen_pos[1] / game.camera.zoom) + game.camera.y
        grid_x = int(world_x // TILE)
        grid_y = int(world_y // TILE)
        collision_type = "Unknown"
        terrain_type = "Unknown"
        terrain_id = "N/A"
        level_grid = getattr(game.level, "grid", None)
        if level_grid:
            if 0 <= grid_y < len(level_grid) and 0 <= grid_x < len(level_grid[0]):
                grid_value = level_grid[grid_y][grid_x]
                from config import TILE_AIR, TILE_WALL
                if grid_value == TILE_AIR:
                    collision_type = "Air"
                elif grid_value == TILE_WALL:
                    collision_type = "Wall"
                else:
                    collision_type = f"Unknown({grid_value})"
                terrain_grid = getattr(game.level, "terrain_grid", None)
                if terrain_grid:
                    try:
                        terrain_id = terrain_grid[grid_y][grid_x]
                        if "platform" in terrain_id:
                            terrain_type = "Platform"
                        elif "wall" in terrain_id:
                            terrain_type = "Wall"
                        elif "water" in terrain_id:
                            terrain_type = "Water"
                        else:
                            terrain_type = terrain_id
                    except Exception as e:
                        terrain_type = f"Error: {str(e)[:20]}"
                else:
                    terrain_type = "No terrain data"
        if collision_type != "Unknown" and terrain_type != "Unknown":
            combined_info = f"Collision: {collision_type} | Terrain: {terrain_type}"
        elif collision_type != "Unknown":
            combined_info = f"Collision: {collision_type}"
        else:
            combined_info = "Out of bounds"
        return grid_x, grid_y, int(world_x), int(world_y), collision_type, terrain_type, combined_info, terrain_id

    def draw_grid_position_overlay(self):
        game = self.game
        if not getattr(game, 'debug_grid_position', False):
            return
        if not getattr(game.player, 'god', False):
            return
        mouse_screen_pos = pygame.mouse.get_pos()
        grid_x, grid_y, world_x, world_y, collision_type, terrain_type, combined_info, terrain_id = self.get_grid_position(mouse_screen_pos)
        game.mouse_grid_pos = (grid_x, grid_y)
        game.mouse_world_pos = (world_x, world_y)
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        grid_screen_x = (grid_x * TILE - game.camera.x) * game.camera.zoom
        grid_screen_y = (grid_y * TILE - game.camera.y) * game.camera.zoom
        tile_screen_size = TILE * game.camera.zoom
        highlight_rect = pygame.Rect(grid_screen_x, grid_screen_y, tile_screen_size, tile_screen_size)
        highlight_color = (255, 255, 255, 60)
        border_color = (255, 255, 255, 180)
        level_grid = getattr(game.level, "grid", None)
        if level_grid:
            if 0 <= grid_y < len(level_grid) and 0 <= grid_x < len(level_grid[0]):
                from config import TILE_AIR, TILE_WALL
                tile_value = level_grid[grid_y][grid_x]
                if tile_value == TILE_AIR:
                    highlight_color = (200, 200, 200, 30)
                    border_color = (200, 200, 200, 100)
                elif tile_value == TILE_WALL:
                    highlight_color = (255, 100, 100, 60)
                    border_color = (255, 100, 100, 180)
                else:
                    highlight_color = (255, 255, 255, 60)
                    border_color = (255, 255, 255, 180)
                terrain_grid = getattr(game.level, "terrain_grid", None)
                if terrain_grid:
                    if 0 <= grid_y < len(terrain_grid) and 0 <= grid_x < len(terrain_grid[0]):
                        terrain_id = terrain_grid[grid_y][grid_x]
                        if "water" in terrain_id:
                            highlight_color = (100, 100, 255, 60)
                            border_color = (100, 100, 255, 180)
        pygame.draw.rect(overlay, highlight_color, highlight_rect)
        pygame.draw.rect(overlay, border_color, highlight_rect, width=2)
        crosshair_x = grid_screen_x + tile_screen_size // 2
        crosshair_y = grid_screen_y + tile_screen_size // 2
        crosshair_size = max(8, int(tile_screen_size * 0.3))
        pygame.draw.line(overlay, (255, 255, 100, 200), (crosshair_x - crosshair_size, crosshair_y), (crosshair_x + crosshair_size, crosshair_y), 2)
        pygame.draw.line(overlay, (255, 255, 100, 200), (crosshair_x, crosshair_y - crosshair_size), (crosshair_x, crosshair_y + crosshair_size), 2)
        info_lines = [
            f"Grid: ({grid_x}, {grid_y})",
            f"World: ({world_x}, {world_y})",
            "Grid Value: N/A",
            f"Collision: {collision_type}",
            f"Terrain: {terrain_type}",
            f"Terrain ID: {terrain_id}"
        ]
        areas = getattr(game.level, "areas", None)
        if areas and hasattr(areas, "areas_at"):
            areas_here = areas.areas_at(grid_x, grid_y)
            if areas_here:
                area_names = [str(a.type) for a in areas_here]
                info_lines.append(f"Area: {', '.join(area_names)}")
        player_grid_x = game.player.rect.centerx // TILE
        player_grid_y = game.player.rect.centery // TILE
        distance = ((grid_x - player_grid_x) ** 2 + (grid_y - player_grid_y) ** 2) ** 0.5
        info_lines.append(f"Distance: {distance:.1f}")
        text_x = mouse_screen_pos[0] + 20
        text_y = mouse_screen_pos[1] - 40
        panel_width = 200
        panel_height = len(info_lines) * 18 + 10
        if text_x + panel_width > WIDTH:
            text_x = mouse_screen_pos[0] - panel_width - 20
        if text_y < 0:
            text_y = mouse_screen_pos[1] + 20
        if text_y + panel_height > HEIGHT:
            text_y = HEIGHT - panel_height - 10
        panel_rect = pygame.Rect(text_x - 5, text_y - 5, panel_width, panel_height)
        pygame.draw.rect(overlay, (20, 20, 30, 220), panel_rect, border_radius=5)
        pygame.draw.rect(overlay, (255, 255, 100, 180), panel_rect, width=1, border_radius=5)
        for i, line in enumerate(info_lines):
            color = (255, 255, 255) if i < 3 else (200, 200, 255)
            draw_text(overlay, line, (text_x, text_y + i * 18), color, size=14)
        game.screen.blit(overlay, (0, 0))

    def draw_tile_inspector(self):
        game = self.game
        try:
            from src.tiles.tile_types import TileType
            from src.tiles.tile_registry import tile_registry
            if getattr(game, 'level', None) is None:
                return
            grid = getattr(game.level, 'grid', None)
            if not grid:
                mx, my = pygame.mouse.get_pos()
                msg = "No tile grid"
                font = game.font_small
                surf = font.render(msg, True, (255, 180, 180))
                w, h = surf.get_size()
                bx = min(max(mx + 12, 0), max(0, WIDTH - w - 8))
                by = min(max(my - h - 12, 0), max(0, HEIGHT - h - 8))
                panel = pygame.Surface((w + 6, h + 6), pygame.SRCALPHA)
                panel.fill((20, 0, 0, 200))
                game.screen.blit(panel, (bx, by))
                game.screen.blit(surf, (bx + 3, by + 3))
                return
            if getattr(game.shop, "shop_open", False):
                return
            if getattr(game.inventory, "inventory_open", False):
                return
            mx, my = pygame.mouse.get_pos()
            world_x = (mx / game.camera.zoom) + game.camera.x
            world_y = (my / game.camera.zoom) + game.camera.y
            grid_x = int(world_x // TILE)
            grid_y = int(world_y // TILE)
            rows = len(grid)
            cols = len(grid[0]) if rows > 0 else 0
            def draw_panel(lines, title_color=(255,255,255)):
                font = game.font_small
                pad_x = 8
                pad_y = 6
                line_h = font.get_linesize()
                max_w = 0
                for line in lines:
                    w, _ = font.render(line, True, (255,255,255)).get_size()
                    max_w = max(max_w, w)
                panel_w = max_w + pad_x * 2
                panel_h = line_h * len(lines) + pad_y * 2
                text_x = mx + 20
                text_y = my - 40
                if text_x + panel_w > WIDTH:
                    text_x = mx - panel_w - 20
                if text_x < 0:
                    text_x = 4
                if text_y < 0:
                    text_y = my + 20
                if text_y + panel_h > HEIGHT:
                    text_y = max(4, HEIGHT - panel_h - 4)
                panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
                panel.fill((10, 10, 18, 210))
                pygame.draw.rect(panel, (200, 200, 240, 255), panel.get_rect(), 1)
                y = pad_y
                for i, line in enumerate(lines):
                    col = (255,255,255)
                    surf = font.render(line, True, col)
                    panel.blit(surf, (pad_x, y))
                    y += line_h
                game.screen.blit(panel, (text_x, text_y))
            if grid_y < 0 or grid_y >= rows or grid_x < 0 or grid_x >= cols:
                draw_panel([
                    f"Grid: ({grid_x}, {grid_y})",
                    f"World: ({int(world_x)}, {int(world_y)})",
                    "Out of bounds",
                ])
                return
            tile_value = grid[grid_y][grid_x]
            tile_screen_x = (grid_x * TILE - game.camera.x) * game.camera.zoom
            tile_screen_y = (grid_y * TILE - game.camera.y) * game.camera.zoom
            tile_screen_size = TILE * game.camera.zoom
            highlight = pygame.Surface((int(tile_screen_size), int(tile_screen_size)), pygame.SRCALPHA)
            highlight.fill((255, 255, 255, 40))
            game.screen.blit(highlight, (int(tile_screen_x), int(tile_screen_y)))
            pygame.draw.rect(game.screen, (255,255,255), pygame.Rect(int(tile_screen_x), int(tile_screen_y), int(tile_screen_size), int(tile_screen_size)), 1)
            if tile_value < 0:
                draw_panel([
                    f"Grid: ({grid_x}, {grid_y})",
                    f"World: ({int(world_x)}, {int(world_y)})",
                    "Empty (no tile)",
                ])
                return
            try:
                tile_type = TileType(tile_value)
            except ValueError:
                draw_panel([
                    f"Grid: ({grid_x}, {grid_y})",
                    f"World: ({int(world_x)}, {int(world_y)})",
                    f"Unknown tile id={tile_value}",
                ])
                return
            tile_data = tile_registry.get_tile(tile_type)
            if tile_data is None:
                draw_panel([
                    f"Grid: ({grid_x}, {grid_y})",
                    f"World: ({int(world_x)}, {int(world_y)})",
                    f"Unknown tile: ID={tile_value}, type={tile_type.name}, no TileData",
                ])
                return
            c = getattr(tile_data, "collision", None)
            p = getattr(tile_data, "physics", None)
            inter = getattr(tile_data, "interaction", None)
            vis = getattr(tile_data, "visual", None)
            lit = getattr(tile_data, "lighting", None)
            aud = getattr(tile_data, "audio", None)
            lines = []
            lines.append(f"Grid: ({grid_x}, {grid_y})")
            lines.append(f"World: ({int(world_x)}, {int(world_y)})")
            lines.append(f"Tile: {tile_data.name} ({tile_type.name}, id={tile_type.value})")
            if c:
                lines.append(f"collision_type={getattr(c, 'collision_type', 'unknown')}")
                lines.append(f"can_walk_on={getattr(c, 'can_walk_on', False)} pass_through={getattr(c, 'can_pass_through', False)} climb={getattr(c, 'can_climb', False)}")
                lines.append(f"damage={getattr(c, 'damage_on_contact', 0)} push={getattr(c, 'push_force', 0.0)}")
                lines.append(f"box_off={getattr(c, 'collision_box_offset', (0, 0))} box_size={getattr(c, 'collision_box_size', None)}")
            if p:
                lines.append(f"friction={getattr(p, 'friction', 1.0)} bounce={getattr(p, 'bounciness', 0.0)} move_speed_mul={getattr(p, 'movement_speed_modifier', 1.0)}")
                lines.append(f"sticky={getattr(p, 'is_sticky', False)} slippery={getattr(p, 'is_slippery', False)} density={getattr(p, 'density', 1.0)}")
            if inter:
                lines.append(
                    f"breakable={getattr(inter, 'breakable', False)} hp={getattr(inter, 'health_points', 0)} "
                    f"climbable={getattr(inter, 'climbable', False)} interact={getattr(inter, 'interactable', False)} "
                    f"collectible={getattr(inter, 'collectible', False)} trigger={getattr(inter, 'is_trigger', False)}"
                )
                lines.append(f"resistance={getattr(inter, 'resistance', 1.0)}")
            if vis:
                base_color = getattr(vis, "base_color", None)
                sprite_path = getattr(vis, "sprite_path", None)
                anim_frames = getattr(vis, "animation_frames", []) or []
                anim_speed = getattr(vis, "animation_speed", 0.0)
                border_radius = getattr(vis, "border_radius", 0)
                render_border = getattr(vis, "render_border", False)
                border_color = getattr(vis, "border_color", None)
                lines.append(f"base_color={base_color}")
                lines.append(f"sprite={sprite_path or 'None'} anim_frames={len(anim_frames)} speed={anim_speed}")
                lines.append(f"border_radius={border_radius} border={render_border} border_color={border_color}")
            if lit:
                lines.append(
                    f"emits_light={getattr(lit, 'emits_light', False)} "
                    f"color={getattr(lit, 'light_color', None)} radius={getattr(lit, 'light_radius', 0.0)}"
                )
                lines.append(
                    f"blocks_light={getattr(lit, 'blocks_light', False)} "
                    f"transparency={getattr(lit, 'transparency', 1.0)} casts_shadows={getattr(lit, 'casts_shadows', True)} "
                    f"reflection={getattr(lit, 'reflection_intensity', 0.0)}"
                )
            if aud:
                lines.append(
                    f"snd_foot={getattr(aud, 'footstep_sound', None)} "
                    f"snd_contact={getattr(aud, 'contact_sound', None)} "
                    f"snd_break={getattr(aud, 'break_sound', None)} "
                    f"snd_ambient={getattr(aud, 'ambient_sound', None)} "
                    f"vol={getattr(aud, 'sound_volume', 1.0)}"
                )
            try:
                lines.append(
                    f"is_walkable={getattr(tile_data, 'is_walkable', False)} "
                    f"has_collision={getattr(tile_data, 'has_collision', False)} "
                    f"is_destructible={getattr(tile_data, 'is_destructible', False)}"
                )
            except Exception:
                pass
            draw_panel(lines)
        except Exception:
            return

    def draw_collision_boxes(self):
        game = self.game
        try:
            from src.tiles.tile_types import TileType
            from src.tiles.tile_registry import tile_registry
            level = getattr(game, "level", None)
            if level is None:
                return
            grid = getattr(level, "grid", None)
            if not grid:
                return
            screen_w, screen_h = game.screen.get_size()
            zoom = getattr(game.camera, "zoom", 1.0) or 1.0
            world_left = game.camera.x
            world_top = game.camera.y
            world_right = game.camera.x + screen_w / zoom
            world_bottom = game.camera.y + screen_h / zoom
            rows = len(grid)
            cols = len(grid[0]) if rows > 0 else 0
            if rows == 0 or cols == 0:
                return
            start_tx = max(0, int(world_left // TILE) - 1)
            end_tx = min(cols, int(world_right // TILE) + 2)
            start_ty = max(0, int(world_top // TILE) - 1)
            end_ty = min(rows, int(world_bottom // TILE) + 2)
            for ty in range(start_ty, end_ty):
                row = grid[ty]
                for tx in range(start_tx, end_tx):
                    tile_value = row[tx]
                    if tile_value < 0:
                        continue
                    try:
                        tile_type = TileType(tile_value)
                    except ValueError:
                        continue
                    tile_data = tile_registry.get_tile(tile_type)
                    if not tile_data or not getattr(tile_data, "has_collision", False):
                        continue
                    c = getattr(tile_data, "collision", None)
                    if not c:
                        continue
                    off = getattr(c, "collision_box_offset", (0, 0))
                    size = getattr(c, "collision_box_size", None)
                    if not size:
                        continue
                    off_x, off_y = off
                    width, height = size
                    world_x = tx * TILE + off_x
                    world_y = ty * TILE + off_y
                    sx = int((world_x - game.camera.x) * zoom)
                    sy = int((world_y - game.camera.y) * zoom)
                    sw = int(width * zoom)
                    sh = int(height * zoom)
                    if sw <= 0 or sh <= 0:
                        continue
                    ct = getattr(c, "collision_type", "")
                    if ct == "full":
                        color = (255, 80, 80)
                    elif ct == "top_only":
                        color = (80, 255, 80)
                    elif ct == "one_way":
                        color = (80, 160, 255)
                    else:
                        color = (255, 255, 0)
                    pygame.draw.rect(game.screen, color, (sx, sy, sw, sh), width=1)
        except Exception:
            return

    def draw_collision_log_overlay(self):
        game = self.game
        try:
            if not getattr(game, "collision_events", None):
                return
            now = pygame.time.get_ticks()
            RECENT_MS = 120
            for ev in game.collision_events:
                if not isinstance(ev, dict):
                    continue
                t = ev.get("time")
                if t is None or now - t > RECENT_MS:
                    continue
                tx = ev.get("tile_x")
                ty = ev.get("tile_y")
                tile_data = ev.get("tile_data")
                if tx is None or ty is None:
                    continue
                wx = tx * TILE
                wy = ty * TILE
                ww = TILE
                wh = TILE
                tile_rect = ev.get("tile_rect")
                if tile_rect is not None and hasattr(tile_rect, "x"):
                    wx, wy, ww, wh = tile_rect.x, tile_rect.y, tile_rect.w, tile_rect.h
                zoom = getattr(game.camera, "zoom", 1.0) or 1.0
                sx = int((wx - game.camera.x) * zoom)
                sy = int((wy - game.camera.y) * zoom)
                sw = int(ww * zoom)
                sh = int(wh * zoom)
                if sw <= 0 or sh <= 0:
                    continue
                side = ev.get("side")
                col = (0, 255, 0)
                if side == "top":
                    col = (0, 255, 255)
                elif side == "bottom":
                    col = (255, 0, 255)
                elif side == "left":
                    col = (255, 255, 0)
                elif side == "right":
                    col = (255, 165, 0)
                pygame.draw.rect(game.screen, col, (sx, sy, sw, sh), width=1)
                if side == "top":
                    pygame.draw.line(game.screen, col, (sx, sy), (sx + sw, sy), 2)
                elif side == "bottom":
                    pygame.draw.line(game.screen, col, (sx, sy + sh), (sx + sw, sy + sh), 2)
                elif side == "left":
                    pygame.draw.line(game.screen, col, (sx, sy), (sx, sy + sh), 2)
                elif side == "right":
                    pygame.draw.line(game.screen, col, (sx + sw, sy), (sx + sw, sy + sh), 2)
            font = game.font_small
            lines = []
            max_events = 8
            for ev in reversed(game.collision_events[-40:]):
                if len(lines) >= max_events:
                    break
                if not isinstance(ev, dict):
                    continue
                tile_name = ev.get("tile_name", "Unknown")
                tx = ev.get("tile_x")
                ty = ev.get("tile_y")
                side = ev.get("side") or "-"
                pen = ev.get("penetration")
                if pen is None:
                    pen = "-"
                dmg = ev.get("damage")
                if dmg is None:
                    dmg = "-"
                line = f"P vs {tile_name} @({tx},{ty}) side={side} pen={pen} dmg={dmg}"
                lines.append(line)
            if not lines:
                return
            pad_x = 8
            pad_y = 6
            line_h = font.get_linesize()
            max_w = 0
            for s in lines:
                w, _ = font.render(s, True, (255, 255, 255)).get_size()
                max_w = max(max_w, w)
            panel_w = max_w + pad_x * 2
            panel_h = line_h * len(lines) + pad_y * 2
            x = 8
            y = HEIGHT - panel_h - 8
            panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel.fill((5, 5, 10, 200))
            pygame.draw.rect(panel, (120, 220, 255, 255), panel.get_rect(), 1)
            cy = pad_y
            for s in lines:
                surf = font.render(s, True, (220, 240, 255))
                panel.blit(surf, (pad_x, cy))
                cy += line_h
            game.screen.blit(panel, (x, y))
        except Exception:
            return

    def draw_pcg_level_select_overlay(self, room_tuple, idx, total):
        game = self.game
        from src.level.level_loader import level_loader
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((12, 14, 20, 200))
        game.screen.blit(overlay, (0, 0))
        panel_w, panel_h = 540, 300
        panel_x = (WIDTH - panel_w) // 2
        panel_y = (HEIGHT - panel_h) // 2
        shadow = pygame.Rect(panel_x + 6, panel_y + 8, panel_w, panel_h)
        pygame.draw.rect(game.screen, (0, 0, 0, 220), shadow, border_radius=14)
        panel = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        pygame.draw.rect(game.screen, (26, 28, 36), panel, border_radius=14)
        pygame.draw.rect(game.screen, (140, 140, 150), panel, width=1, border_radius=14)
        try:
            level_id, room_code = room_tuple
        except Exception:
            level_id, room_code = None, None
        try:
            lc = (120 + (int(level_id) * 47) % 100, 110, 170)
        except Exception:
            lc = (120, 110, 170)
        header = pygame.Rect(panel.x, panel.y, panel.width, 64)
        pygame.draw.rect(game.screen, lc, header, border_radius=12)
        draw_text(game.screen, "Teleport to PCG Room", (panel.x + 20, panel.y + 14), (245, 245, 250), size=22, bold=True)
        badge_w, badge_h = 88, 40
        badge = pygame.Rect(panel.x + 20, panel.y + 90 - 10, badge_w, badge_h)
        pygame.draw.rect(game.screen, lc, badge, border_radius=8)
        pygame.draw.rect(game.screen, (255,255,255,40), badge, width=1, border_radius=8)
        try:
            draw_text(game.screen, f"L{level_id}", (badge.x + 14, badge.y + 8), (245,245,245), size=20, bold=True)
        except Exception:
            pass
        room_name = f"Room {room_code}"
        draw_text(game.screen, room_name, (badge.right + 16, panel.y + 78), (230,230,235), size=28, bold=True)
        local_idx = None
        rcount = None
        try:
            rlist = level_loader.list_rooms_in_level(int(level_id))
            rcount = len(rlist)
            if room_code in rlist:
                local_idx = rlist.index(room_code) + 1
        except Exception:
            rlist = None
        sub_x = badge.right + 16
        sub_y = panel.y + 118
        if local_idx is not None and rcount is not None:
            draw_text(game.screen, f"{local_idx}/{rcount} in Level {level_id}", (sub_x, sub_y), (200,200,210), size=16)
        draw_text(game.screen, f"PCG: {idx+1}/{total}", (panel.right - 140, panel.y + 78), (200,200,210), size=18)
        draw_text(game.screen, "← / → to choose  •  Enter to teleport  •  Esc to cancel", (panel.x + 20, panel.bottom - 42), (170,180,200), size=14)
        try:
            room = level_loader.get_room(int(level_id), str(room_code))
            if room and getattr(room, 'spawn_tile', None):
                sx, sy = room.spawn_tile
                draw_text(game.screen, f"Spawn tile: ({sx}, {sy})", (panel.x + 20, panel.y + 148), (200,200,210), size=14)
        except Exception:
            pass

    def draw_level_select_overlay(self, idx):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.game.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 200)
        pygame.draw.rect(self.game.screen, (30, 28, 42), panel, border_radius=12)
        pygame.draw.rect(self.game.screen, (210, 200, 170), panel, width=2, border_radius=12)
        draw_text(self.game.screen, "Teleport to Level", (panel.x + 24, panel.y + 16), (240,220,190), size=26, bold=True)
        info = "Left/Right choose, Enter confirm, Esc to cancel"
        draw_text(self.game.screen, info, (panel.x + 24, panel.bottom - 36), (180,180,200), size=16)
        draw_text(self.game.screen, f"Room {idx+1}/{__import__('src.level.legacy_level', fromlist=['ROOM_COUNT']).ROOM_COUNT}", (panel.centerx - 80, panel.centery - 10), (220,220,240), size=32, bold=True)

