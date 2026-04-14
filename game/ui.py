"""UI systems: HUD, station UI, ship builder, sector map, menus."""
import pygame
import math
from typing import Optional, Tuple
from game.core import *
from game.ship import Ship, MODULE_DEFS, PlacedModule, EXPAND_COST
from game.sector import SectorManager, Station


# ═════════════════════════════════════════════════════════════════════════════
#  HUD (in-game overlay)
# ═════════════════════════════════════════════════════════════════════════════
class HUD:
    def __init__(self):
        self.notification_text = ""
        self.notification_timer = 0.0
        self.notification_color = WHITE
        self.low_fuel_flash = 0.0

    def notify(self, text, color=WHITE, duration=3.0):
        self.notification_text = text
        self.notification_timer = duration
        self.notification_color = color

    def update(self, dt):
        if self.notification_timer > 0:
            self.notification_timer -= dt
        self.low_fuel_flash += dt

    def draw(self, surface, ship: Ship, world, time, camera=None, mp_players=None):
        # ── Top-left: Resources ────────────────────────────────────
        x, y = 15, 15

        # HP
        draw_text(surface, "HULL", x, y, DIM_CYAN, 11)
        draw_bar(surface, x + 40, y + 1, 120, 10,
                ship.core_hp / max(1, ship.core_max_hp),
                NEON_RED if ship.core_hp < ship.core_max_hp * 0.3 else NEON_GREEN,
                (15, 15, 25), DIM_CYAN)
        hp_text = f"{int(ship.core_hp)}/{int(ship.core_max_hp)}"
        if ship.total_hull_regen > 0:
            hp_text += f" +{ship.total_hull_regen:.0f}/s"
        draw_text(surface, hp_text, x + 165, y, WHITE, 11)
        y += 18

        # Shield
        if ship.max_shield > 0:
            draw_text(surface, "SHLD", x, y, DIM_CYAN, 11)
            draw_bar(surface, x + 40, y + 1, 120, 10,
                    ship.shield / max(1, ship.max_shield),
                    NEON_BLUE, (15, 15, 25), DIM_CYAN)
            draw_text(surface, f"{int(ship.shield)}/{int(ship.max_shield)}", x + 165, y, WHITE, 11)
            y += 18

        # Fuel
        fuel_ratio = ship.fuel / max(1, ship.fuel_capacity)
        fuel_color = NEON_ORANGE
        if fuel_ratio < 0.2:
            fuel_color = NEON_RED if math.sin(self.low_fuel_flash * 6) > 0 else NEON_ORANGE
        draw_text(surface, "FUEL", x, y, DIM_CYAN, 11)
        draw_bar(surface, x + 40, y + 1, 120, 10,
                fuel_ratio, fuel_color, (15, 15, 25), DIM_CYAN)
        draw_text(surface, f"{int(ship.fuel)}/{int(ship.fuel_capacity)}", x + 165, y, WHITE, 11)
        y += 18

        # Ore
        ore_ratio = ship.ore / max(1, ship.ore_capacity) if ship.ore_capacity > 0 else 0
        draw_text(surface, "ORE ", x, y, DIM_CYAN, 11)
        draw_bar(surface, x + 40, y + 1, 120, 10,
                ore_ratio, ORE_COLOR, (15, 15, 25), DIM_CYAN)
        draw_text(surface, f"{int(ship.ore)}/{int(ship.ore_capacity)}", x + 165, y, WHITE, 11)
        y += 18

        # Refinery status
        if ship.refinery_rate > 0:
            if ship.refinery_enabled:
                if ship.ore > 0:
                    draw_text(surface, f"REFINING: {ship.refinery_rate:.0f}/s [R]", x, y, NEON_GREEN, 11)
                else:
                    draw_text(surface, f"Refinery idle [R]", x, y, DIM_GREEN, 11)
            else:
                draw_text(surface, f"Refinery OFF [R] (sell ore!)", x, y, NEON_ORANGE, 11)
            y += 18

        # Fuel range
        range_sectors = ship.fuel_range_sectors
        range_color = NEON_ORANGE if range_sectors > 2 else NEON_RED
        draw_text(surface, f"Range: ~{range_sectors:.1f} sectors", x, y, range_color, 11)
        y += 18

        # ── Top-right: Sector info ────────────────────────────────
        rx = SCREEN_W - 15
        ry = 15
        draw_text(surface, f"${ship.credits}", rx - 100, ry, NEON_YELLOW, 18)
        ry += 24

        current = world.sectors.get_current_sector()
        coord = current.coord
        draw_text(surface, f"SECTOR [{coord[0]}, {coord[1]}]", rx - 100, ry, NEON_CYAN, 13)
        ry += 18

        # Sector type
        type_colors = {
            'empty': DIM_CYAN,
            'asteroid_field': ORE_COLOR,
            'nebula': NEON_PURPLE,
            'pirate_territory': NEON_RED,
            'station': NEON_CYAN,
            'derelict_field': (120, 100, 60),
        }
        stype = current.sector_type.replace('_', ' ').title()
        draw_text(surface, stype, rx - 100, ry,
                 type_colors.get(current.sector_type, DIM_CYAN), 11)
        ry += 18

        # Threat level
        threat = current.threat_level
        threat_str = "|" * threat + "." * (5 - threat)
        threat_color = NEON_GREEN if threat <= 1 else (NEON_YELLOW if threat <= 3 else NEON_RED)
        draw_text(surface, f"THREAT: {threat_str}", rx - 100, ry, threat_color, 11)
        ry += 18

        # Sectors discovered
        draw_text(surface, f"Discovered: {len(world.sectors.discovered)}", rx - 100, ry, DIM_CYAN, 11)
        ry += 18

        # Goal
        if not world.void_titan_killed:
            titan_dx = 6 - current.coord[0]
            titan_dy = -4 - current.coord[1]
            titan_dist = abs(titan_dx) + abs(titan_dy)
            if titan_dist <= 3:
                draw_text(surface, f"VOID TITAN NEARBY [{titan_dx:+d},{titan_dy:+d}]",
                         rx - 100, ry, NEON_PINK, 11)
            else:
                draw_text(surface, f"Titan: sector [6,-4]", rx - 100, ry, (60, 40, 50), 10)
            ry += 18
        else:
            draw_text(surface, "TITAN SLAIN!", rx - 100, ry, NEON_GREEN, 11)
            ry += 18

        # Enemies nearby
        n_enemies = len(world.enemies)
        if n_enemies > 0:
            draw_text(surface, f"Hostiles: {n_enemies}", rx - 100, ry, NEON_RED, 11)
            ry += 18

        # Active mission
        if world.active_mission and not world.active_mission.completed:
            m = world.active_mission
            draw_text(surface, f"MISSION: {m.name}", rx - 100, ry, NEON_YELLOW, 11)
            ry += 15
            color = NEON_GREEN if m.is_done else NEON_ORANGE
            draw_text(surface, f"  {m.progress_text} — ${m.reward}", rx - 100, ry, color, 10)
            ry += 15
            if m.is_done:
                draw_text(surface, "  Dock to turn in!", rx - 100, ry, NEON_GREEN, 10)
                ry += 15

        # ── Bottom: Controls hint ─────────────────────────────────
        draw_text(surface, "LMB:Gun  RMB:Laser  MMB:Missile  E:Mine  R:Refinery  F:Dock  TAB:Map",
                 SCREEN_W // 2, SCREEN_H - 18, (60, 70, 90), 11, center=True)

        # ── Bottom-left: Probes ───────────────────────────────────
        bx = 15
        by = SCREEN_H - 50
        draw_text(surface, f"Probes: {ship.max_probes - ship.active_probes}/{ship.max_probes}",
                 bx, by, NEON_GREEN, 12)

        # ── Center notifications ──────────────────────────────────
        if self.notification_timer > 0:
            alpha = min(1.0, self.notification_timer)
            c = self.notification_color
            draw_text(surface, self.notification_text,
                     SCREEN_W // 2, SCREEN_H // 2 - 60,
                     safe_color(c[0] * alpha, c[1] * alpha, c[2] * alpha),
                     20, center=True)

        # Low fuel warning + emergency hint
        if fuel_ratio <= 0:
            draw_text(surface, "! NO FUEL - EMERGENCY THRUSTERS ONLY !",
                     SCREEN_W // 2, SCREEN_H // 2 + 40, NEON_RED, 16, center=True)
            draw_text(surface, "Hold H for distress warp to station",
                     SCREEN_W // 2, SCREEN_H // 2 + 60, NEON_YELLOW, 12, center=True)
        elif fuel_ratio < 0.15:
            if math.sin(time * 6) > 0:
                draw_text(surface, "! LOW FUEL !",
                         SCREEN_W // 2, SCREEN_H // 2 + 40, NEON_RED, 16, center=True)

        # Distress beacon charging bar
        if ship.distress_charging:
            charge = ship.distress_timer / 3.0
            bar_w = 200
            bx = SCREEN_W // 2 - bar_w // 2
            by = SCREEN_H // 2 + 80
            draw_bar(surface, bx, by, bar_w, 14, charge, NEON_YELLOW, (20, 20, 30), NEON_YELLOW)
            draw_text(surface, "DISTRESS WARP CHARGING...", SCREEN_W // 2, by - 14,
                     NEON_YELLOW, 14, center=True)
            cost = ship.credits // 2
            draw_text(surface, f"Cost: ${cost}", SCREEN_W // 2, by + 20,
                     NEON_ORANGE, 11, center=True)

        # Station direction indicator
        station_info = world.sectors.find_nearest_station_direction(ship.x, ship.y)
        if station_info and not ship.docked and camera:
            angle, d, name = station_info
            if d > 200:
                sx, sy = camera.world_to_screen(ship.x, ship.y)
                indicator_dist = 90
                ix = sx + math.cos(angle) * indicator_dist
                iy = sy + math.sin(angle) * indicator_dist
                # Arrow
                arrow_pts = [
                    (ix + math.cos(angle) * 8, iy + math.sin(angle) * 8),
                    (ix + math.cos(angle + 2.5) * 5, iy + math.sin(angle + 2.5) * 5),
                    (ix + math.cos(angle - 2.5) * 5, iy + math.sin(angle - 2.5) * 5),
                ]
                pygame.draw.polygon(surface, NEON_CYAN, arrow_pts)
                draw_text(surface, f"{name} ({int(d)}m)", int(ix + 12), int(iy - 8),
                         NEON_CYAN, 9)

        # Minimap
        self._draw_minimap(surface, ship, world, camera, mp_players)

    def _draw_minimap(self, surface, ship: Ship, world, camera, mp_players=None):
        mm_size = 130
        mm_x = SCREEN_W - mm_size - 15
        mm_y = SCREEN_H - mm_size - 15
        # Show local area (2 sectors wide)
        view_range = SECTOR_SIZE * 2

        mm_surf = pygame.Surface((mm_size, mm_size), pygame.SRCALPHA)
        mm_surf.fill((5, 5, 15, 160))
        pygame.draw.rect(mm_surf, DIM_CYAN, (0, 0, mm_size, mm_size), 1)

        def w2m(wx, wy):
            rx = (wx - ship.x) / view_range * mm_size / 2 + mm_size / 2
            ry = (wy - ship.y) / view_range * mm_size / 2 + mm_size / 2
            return int(rx), int(ry)

        # Sector grid lines on minimap
        sc = world.sectors.current_coord
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                sx_w = (sc[0] + dx) * SECTOR_SIZE
                sy_w = (sc[1] + dy) * SECTOR_SIZE
                mx1, my1 = w2m(sx_w, sy_w)
                mx2, my2 = w2m(sx_w + SECTOR_SIZE, sy_w + SECTOR_SIZE)
                if 0 <= mx1 <= mm_size or 0 <= mx2 <= mm_size:
                    pygame.draw.line(mm_surf, (20, 25, 35), (mx1, 0), (mx1, mm_size))
                if 0 <= my1 <= mm_size or 0 <= my2 <= mm_size:
                    pygame.draw.line(mm_surf, (20, 25, 35), (0, my1), (mm_size, my1))

        # Asteroids
        for a in world.asteroids:
            if a.depleted:
                continue
            ax, ay = w2m(a.x, a.y)
            if 0 <= ax < mm_size and 0 <= ay < mm_size:
                mm_surf.set_at((ax, ay), ORE_COLOR)

        # Stations
        for sector in world.sectors.get_loaded_sectors():
            if sector.station:
                sx2, sy2 = w2m(sector.station.x, sector.station.y)
                if 0 <= sx2 < mm_size and 0 <= sy2 < mm_size:
                    pygame.draw.circle(mm_surf, NEON_CYAN, (sx2, sy2), 3)

        # Enemies
        for e in world.enemies:
            if not e.alive:
                continue
            ex, ey = w2m(e.x, e.y)
            if 0 <= ex < mm_size and 0 <= ey < mm_size:
                c = NEON_PINK if e.is_boss else NEON_RED
                pygame.draw.circle(mm_surf, c, (ex, ey), 2 if e.is_boss else 1)

        # POIs
        for sector in world.sectors.get_loaded_sectors():
            for poi in sector.pois:
                if not poi.discovered or poi.looted:
                    continue
                px, py = w2m(poi.x, poi.y)
                if 0 <= px < mm_size and 0 <= py < mm_size:
                    pygame.draw.circle(mm_surf, poi.color, (px, py), 2)

        # Buildings (beacons + turrets)
        for b in world.buildings:
            if not b.alive:
                continue
            bx2, by2 = w2m(b.x, b.y)
            if 0 <= bx2 < mm_size and 0 <= by2 < mm_size:
                if b.defn.id == 'beacon':
                    pygame.draw.circle(mm_surf, NEON_CYAN, (bx2, by2), 3)
                    pygame.draw.circle(mm_surf, NEON_CYAN, (bx2, by2), 6, 1)
                elif b.defn.id == 'base_turret':
                    pygame.draw.circle(mm_surf, NEON_GREEN, (bx2, by2), 2)
                elif b.defn.id == 'chest':
                    pygame.draw.circle(mm_surf, NEON_YELLOW, (bx2, by2), 2)
                else:
                    mm_surf.set_at((bx2, by2), b.defn.glow)

        # Remote players
        if mp_players:
            for pid, pdata in mp_players.items():
                if not pdata.get('alive', True):
                    continue
                rpx, rpy = w2m(pdata.get('x', 0), pdata.get('y', 0))
                if 0 <= rpx < mm_size and 0 <= rpy < mm_size:
                    pc2 = tuple(pdata.get('color', [100, 255, 100]))
                    pygame.draw.circle(mm_surf, pc2, (rpx, rpy), 3)
                    # Name label
                    name = pdata.get('name', '?')
                    font = pygame.font.SysFont("consolas", 8)
                    label = font.render(name[:6], True, pc2)
                    mm_surf.blit(label, (max(0, min(rpx - 10, mm_size - 25)), max(0, rpy - 10)))

        # Player — bright pulsing dot so you can always see yourself
        pc = mm_size // 2
        pygame.draw.circle(mm_surf, WHITE, (pc, pc), 4)
        pygame.draw.circle(mm_surf, NEON_CYAN, (pc, pc), 3)
        # Direction indicator
        aim_dx = int(math.cos(ship.angle) * 8)
        aim_dy = int(math.sin(ship.angle) * 8)
        pygame.draw.line(mm_surf, NEON_CYAN, (pc, pc), (pc + aim_dx, pc + aim_dy), 1)

        surface.blit(mm_surf, (mm_x, mm_y))


# ═════════════════════════════════════════════════════════════════════════════
#  SECTOR MAP (discovery map)
# ═════════════════════════════════════════════════════════════════════════════
class SectorMap:
    def __init__(self):
        self.active = False
        self.cell_size = 40
        self.scroll_x = 0
        self.scroll_y = 0

    def toggle(self):
        self.active = not self.active

    def handle_event(self, event, sectors: SectorManager):
        if not self.active:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_TAB, pygame.K_m, pygame.K_ESCAPE):
                self.active = False
                return True
        if event.type == pygame.MOUSEWHEEL:
            self.cell_size = clamp(self.cell_size + event.y * 5, 20, 80)
            return True
        return False

    def draw(self, surface, sectors: SectorManager, ship: Ship, time, mp_players=None, buildings=None):
        if not self.active:
            return

        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        surface.blit(overlay, (0, 0))

        draw_text(surface, "SECTOR MAP", SCREEN_W // 2, 20, NEON_CYAN, 24, center=True)
        draw_text(surface, "TAB/M to close | Scroll to zoom", SCREEN_W // 2, SCREEN_H - 20,
                 (60, 70, 90), 11, center=True)

        cs = self.cell_size
        center_x = SCREEN_W // 2
        center_y = SCREEN_H // 2
        player_coord = sectors.current_coord

        type_colors = {
            'empty': (25, 30, 40),
            'asteroid_field': (50, 40, 20),
            'nebula': (40, 20, 60),
            'pirate_territory': (60, 20, 20),
            'station': (20, 50, 60),
            'derelict_field': (40, 35, 20),
        }

        # Draw discovered sectors
        for coord in sectors.discovered:
            dx = coord[0] - player_coord[0]
            dy = coord[1] - player_coord[1]
            sx = center_x + dx * cs - cs // 2
            sy = center_y + dy * cs - cs // 2

            if sx > SCREEN_W + cs or sx < -cs or sy > SCREEN_H + cs or sy < -cs:
                continue

            # Get sector info
            sector = sectors.loaded.get(coord)
            if sector:
                bg = type_colors.get(sector.sector_type, (25, 30, 40))
                threat = sector.threat_level
            else:
                bg = (20, 20, 30)
                threat = 0

            rect = pygame.Rect(sx, sy, cs - 2, cs - 2)
            pygame.draw.rect(surface, bg, rect)

            # Threat border color
            if threat == 0:
                border_c = (30, 40, 50)
            elif threat <= 2:
                border_c = (50, 80, 40)
            elif threat <= 3:
                border_c = (80, 80, 30)
            else:
                border_c = (100, 30, 30)
            pygame.draw.rect(surface, border_c, rect, 1)

            # Station marker
            if sector and sector.station:
                pygame.draw.circle(surface, NEON_CYAN,
                                 (int(sx + cs // 2), int(sy + cs // 2)), max(3, cs // 8))

            # Coord label
            if cs >= 35:
                draw_text(surface, f"{coord[0]},{coord[1]}",
                         int(sx + cs // 2), int(sy + cs - 10),
                         (50, 60, 70), 8, center=True)

        # Beacons on sector map
        if buildings:
            for b in buildings:
                if not b.alive or b.defn.id != 'beacon':
                    continue
                b_coord = (int(math.floor(b.x / SECTOR_SIZE)),
                          int(math.floor(b.y / SECTOR_SIZE)))
                bdx = b_coord[0] - player_coord[0]
                bdy = b_coord[1] - player_coord[1]
                bsx = center_x + bdx * cs
                bsy = center_y + bdy * cs
                pulse2 = 0.5 + 0.5 * math.sin(time * 3)
                pygame.draw.circle(surface, NEON_CYAN, (bsx, bsy), max(2, cs // 8))
                pygame.draw.circle(surface, safe_color(0, 255 * pulse2, 255 * pulse2),
                                 (bsx, bsy), max(4, cs // 5), 1)
                if b.label:
                    draw_text(surface, b.label, bsx, bsy - cs // 3 - 4,
                             NEON_CYAN, 8, center=True)

        # Remote players on sector map
        if mp_players:
            for pid, pdata in mp_players.items():
                if not pdata.get('alive', True):
                    continue
                rp_coord = (int(math.floor(pdata.get('x', 0) / SECTOR_SIZE)),
                           int(math.floor(pdata.get('y', 0) / SECTOR_SIZE)))
                rdx = rp_coord[0] - player_coord[0]
                rdy = rp_coord[1] - player_coord[1]
                rpx = center_x + rdx * cs
                rpy = center_y + rdy * cs
                pc2 = tuple(pdata.get('color', [100, 255, 100]))
                pygame.draw.circle(surface, pc2, (rpx, rpy), max(3, cs // 6))
                draw_text(surface, pdata.get('name', '?')[:8],
                         rpx, rpy - cs // 3, pc2, 9, center=True)

        # Player position
        px = center_x - cs // 2
        py = center_y - cs // 2
        pygame.draw.rect(surface, NEON_CYAN, (px, py, cs - 2, cs - 2), 2)

        # Fuel range circle
        fuel_range_sectors = ship.fuel_range_sectors
        fuel_r = int(fuel_range_sectors * cs)
        if fuel_r > 10:
            range_surf = pygame.Surface((fuel_r * 2 + 4, fuel_r * 2 + 4), pygame.SRCALPHA)
            range_color = NEON_ORANGE if fuel_range_sectors > 2 else NEON_RED
            pygame.draw.circle(range_surf, (*range_color[:3], 30),
                             (fuel_r + 2, fuel_r + 2), fuel_r, 2)
            surface.blit(range_surf, (center_x - fuel_r - 2, center_y - fuel_r - 2),
                        special_flags=pygame.BLEND_ADD)

        # Legend
        lx, ly = 20, SCREEN_H - 160
        draw_text(surface, "LEGEND", lx, ly, NEON_CYAN, 12)
        ly += 18
        legends = [
            (NEON_CYAN, "Station"),
            ((50, 40, 20), "Asteroid Field"),
            ((40, 20, 60), "Nebula"),
            ((60, 20, 20), "Pirate Territory"),
            ((40, 35, 20), "Derelict Field"),
        ]
        for color, label in legends:
            pygame.draw.rect(surface, color, (lx, ly, 12, 12))
            draw_text(surface, label, lx + 18, ly, (150, 160, 170), 10)
            ly += 16

        # Stats
        lx2 = SCREEN_W - 200
        ly2 = SCREEN_H - 100
        draw_text(surface, f"Fuel Range: ~{fuel_range_sectors:.1f} sectors", lx2, ly2,
                 NEON_ORANGE, 11)
        ly2 += 16
        draw_text(surface, f"Discovered: {len(sectors.discovered)} sectors", lx2, ly2,
                 DIM_CYAN, 11)
        ly2 += 16
        draw_text(surface, f"Farthest: {sectors.farthest_distance} from origin", lx2, ly2,
                 DIM_CYAN, 11)


# ═════════════════════════════════════════════════════════════════════════════
#  STATION UI (dock screen with shop, fuel, repair)
# ═════════════════════════════════════════════════════════════════════════════
class StationUI:
    def __init__(self):
        self.active = False
        self.station: Optional[Station] = None
        self.world_ref = None  # set when opened
        self.current_tab = 'services'  # 'services', 'modules'
        self.builder = ShipBuilder()

    def open(self, station: Station, world=None):
        self.active = True
        self.station = station
        self.world_ref = world
        self.current_tab = 'services'
        self.builder.active = False
        self.builder.shop_items = list(station.shop_inventory)
        self.builder.station_ref = station
        self.builder.selected_module_id = None
        self.builder.remove_mode = False
        self.builder.scroll_offset = 0

    def close(self):
        self.active = False
        self.station = None
        self.builder.active = False
        self.builder.station_ref = None

    def handle_event(self, event, ship: Ship, audio) -> Optional[str]:
        """Returns 'undock' signal or None."""
        if not self.active or not self.station:
            return None

        if self.current_tab == 'modules' and self.builder.active:
            self.builder.handle_event(event, ship, audio)
            # Still check tab clicks even in builder mode
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx2, my2 = event.pos
                tab_y = 70
                tabs = [('services', 'SERVICES'), ('modules', 'MODULES')]
                tx = SCREEN_W // 2 - 120
                for tab_id, tab_label in tabs:
                    tab_rect = pygame.Rect(tx, tab_y, 110, 30)
                    if tab_rect.collidepoint(mx2, my2):
                        self.current_tab = tab_id
                        self.builder.active = (tab_id == 'modules')
                        return None
                    tx += 130
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.current_tab = 'services'
                self.builder.active = False
                return None
            return None

        mx, my = pygame.mouse.get_pos()

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_f, pygame.K_ESCAPE):
                return 'undock'

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Tab buttons
            tab_y = 70
            tabs = [('services', 'SERVICES'), ('modules', 'MODULES')]
            tx = SCREEN_W // 2 - 120
            for tab_id, tab_label in tabs:
                tab_rect = pygame.Rect(tx, tab_y, 110, 30)
                if tab_rect.collidepoint(mx, my):
                    self.current_tab = tab_id
                    self.builder.active = (tab_id == 'modules')
                    if tab_id == 'modules':
                        self.builder.shop_items = list(self.station.shop_inventory)
                        self.builder.station_ref = self.station
                    return None
                tx += 130

            if self.current_tab == 'services':
                # Refuel button
                btn_y = 180
                btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 35)
                if btn_rect.collidepoint(mx, my):
                    space = ship.fuel_capacity - ship.fuel
                    if space > 0 and ship.credits > 0:
                        buy = min(space, ship.credits / self.station.fuel_price)
                        cost = int(buy * self.station.fuel_price)
                        ship.fuel += buy
                        ship.credits -= cost
                        audio.play('buy', 0.4)
                    return None

                # Repair button
                btn_y += 50
                btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 35)
                if btn_rect.collidepoint(mx, my):
                    core = next((m for m in ship.modules if m.defn.id == "core"), None)
                    if core and core.hp < core.max_hp:
                        repair_needed = core.max_hp - core.hp
                        affordable = ship.credits / self.station.repair_price
                        repair = min(repair_needed, affordable)
                        cost = int(repair * self.station.repair_price)
                        core.hp += repair
                        ship.credits -= cost
                        audio.play('buy', 0.4)
                    return None

                # Sell ore button
                btn_y += 50
                btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 35)
                if btn_rect.collidepoint(mx, my):
                    if ship.ore > 0:
                        credits_gain = int(ship.ore * ORE_SELL_PRICE)
                        ship.credits += credits_gain
                        ship.ore = 0
                        audio.play('pickup', 0.4)
                    return None

                # Mission buttons
                if self.world_ref:
                    # Turn in completed mission
                    if self.world_ref.active_mission and self.world_ref.active_mission.is_done:
                        btn_y += 50
                        btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 35)
                        if btn_rect.collidepoint(mx, my):
                            msg = self.world_ref.complete_mission(ship)
                            if msg:
                                audio.play('buy', 0.6)
                            return None
                    # Accept new mission (only if no active)
                    elif not self.world_ref.active_mission:
                        for mi, mission in enumerate(self.world_ref.available_missions):
                            btn_y += 38
                            btn_rect = pygame.Rect(SCREEN_W // 2 - 120, btn_y, 240, 34)
                            if btn_rect.collidepoint(mx, my):
                                self.world_ref.accept_mission(mi)
                                audio.play('buy', 0.4)
                                return None
                    # Abandon active mission
                    elif self.world_ref.active_mission and not self.world_ref.active_mission.is_done:
                        btn_y += 50
                        btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 35)
                        if btn_rect.collidepoint(mx, my):
                            self.world_ref.abandon_mission()
                            audio.play('hit', 0.3)
                            return None

                # Undock button
                btn_y += 60
                btn_rect = pygame.Rect(SCREEN_W // 2 - 80, btn_y, 160, 40)
                if btn_rect.collidepoint(mx, my):
                    return 'undock'

        return None

    def draw(self, surface, ship: Ship, time):
        if not self.active or not self.station:
            return

        # Modules tab — draw builder but overlay tabs on top
        if self.current_tab == 'modules' and self.builder.active:
            self.builder.draw(surface, ship, time)
            # Draw tab bar on top of builder
            self._draw_tabs(surface, time)
            return

        # Station overlay
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        surface.blit(overlay, (0, 0))

        # Header
        draw_text(surface, f"DOCKED: {self.station.name}", SCREEN_W // 2, 25,
                 NEON_CYAN, 22, center=True)
        draw_text(surface, f"[{self.station.station_type.replace('_', ' ').upper()}]",
                 SCREEN_W // 2, 50, DIM_CYAN, 12, center=True)

        # Tab buttons
        self._draw_tabs(surface, time)

        # Credits
        mx, my = pygame.mouse.get_pos()
        draw_text(surface, f"Credits: ${ship.credits}", SCREEN_W // 2, 120,
                 NEON_YELLOW, 16, center=True)

        if self.current_tab == 'services':
            self._draw_overview(surface, ship, time, mx, my)

    def _draw_tabs(self, surface, time):
        """Draw the tab bar at the top — visible on all station screens."""
        # Background strip
        tab_bg = pygame.Surface((SCREEN_W, 40), pygame.SRCALPHA)
        tab_bg.fill((5, 5, 15, 200))
        surface.blit(tab_bg, (0, 60))

        mx, my = pygame.mouse.get_pos()
        tabs = [('services', 'SERVICES'), ('modules', 'MODULES')]
        tx = SCREEN_W // 2 - 120
        for tab_id, tab_label in tabs:
            tab_rect = pygame.Rect(tx, 65, 110, 30)
            active = self.current_tab == tab_id
            hover = tab_rect.collidepoint(mx, my)
            color = NEON_CYAN if active else (NEON_BLUE if hover else DIM_CYAN)
            draw_neon_rect(surface, color, tab_rect, 2 if active else 1)
            draw_text(surface, tab_label, tab_rect.centerx, tab_rect.centery,
                     color, 13, center=True)
            tx += 130

        # Undock hint
        draw_text(surface, "[F] Undock  [ESC] Undock", SCREEN_W // 2, SCREEN_H - 20,
                 (50, 60, 70), 10, center=True)

    def _draw_overview(self, surface, ship, time, mx, my):
        btn_y = 180

        # Refuel
        space = ship.fuel_capacity - ship.fuel
        cost = int(space * self.station.fuel_price)
        btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 35)
        hover = btn_rect.collidepoint(mx, my)
        color = NEON_ORANGE if hover else DIM_CYAN
        can_buy = space > 0 and ship.credits > 0
        if not can_buy:
            color = (40, 40, 40)
        draw_neon_rect(surface, color, btn_rect, 2)
        draw_text(surface, "REFUEL", btn_rect.centerx, btn_rect.centery - 6, color, 14, center=True)
        draw_text(surface, f"${self.station.fuel_price}/unit | Need: {int(space)} (${cost})",
                 btn_rect.centerx, btn_rect.centery + 10, (100, 110, 120), 9, center=True)
        draw_bar(surface, btn_rect.x + 10, btn_rect.y - 8, btn_rect.w - 20, 4,
                ship.fuel / max(1, ship.fuel_capacity), NEON_ORANGE, (20, 20, 30))
        btn_y += 50

        # Repair
        core = next((m for m in ship.modules if m.defn.id == "core"), None)
        repair_needed = (core.max_hp - core.hp) if core else 0
        repair_cost = int(repair_needed * self.station.repair_price)
        btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 35)
        hover = btn_rect.collidepoint(mx, my)
        color = NEON_GREEN if hover else DIM_CYAN
        can_repair = repair_needed > 0 and ship.credits > 0
        if not can_repair:
            color = (40, 40, 40)
        draw_neon_rect(surface, color, btn_rect, 2)
        draw_text(surface, "REPAIR HULL", btn_rect.centerx, btn_rect.centery - 6, color, 14, center=True)
        draw_text(surface, f"${self.station.repair_price}/HP | Damage: {int(repair_needed)} (${repair_cost})",
                 btn_rect.centerx, btn_rect.centery + 10, (100, 110, 120), 9, center=True)
        btn_y += 50

        # Sell ore
        ore_value = int(ship.ore * ORE_SELL_PRICE)
        btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 35)
        hover = btn_rect.collidepoint(mx, my)
        color = ORE_COLOR if hover else DIM_CYAN
        can_sell = ship.ore > 0
        if not can_sell:
            color = (40, 40, 40)
        draw_neon_rect(surface, color, btn_rect, 2)
        draw_text(surface, "SELL ORE", btn_rect.centerx, btn_rect.centery - 6, color, 14, center=True)
        draw_text(surface, f"{int(ship.ore)} ore -> ${ore_value}",
                 btn_rect.centerx, btn_rect.centery + 10, (100, 110, 120), 9, center=True)
        # ── MISSIONS ──────────────────────────────────────────
        if self.world_ref:
            btn_y += 20
            draw_text(surface, f"MISSIONS (Lv.{self.world_ref.missions_completed + 1})",
                     SCREEN_W // 2, btn_y, NEON_YELLOW, 13, center=True)
            btn_y += 18

            if self.world_ref.active_mission and self.world_ref.active_mission.is_done:
                # Turn in button
                m = self.world_ref.active_mission
                btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 35)
                hover = btn_rect.collidepoint(mx, my)
                draw_neon_rect(surface, NEON_GREEN if hover else DIM_GREEN, btn_rect, 2)
                draw_text(surface, f"TURN IN: +${m.reward}", btn_rect.centerx, btn_rect.centery,
                         NEON_GREEN, 14, center=True)
                btn_y += 40
            elif self.world_ref.active_mission and not self.world_ref.active_mission.is_done:
                # Show active mission + abandon
                m = self.world_ref.active_mission
                draw_text(surface, f"Active: {m.name}", SCREEN_W // 2, btn_y, NEON_ORANGE, 11, center=True)
                btn_y += 14
                draw_text(surface, f"{m.description}", SCREEN_W // 2, btn_y, (140, 150, 160), 9, center=True)
                btn_y += 14
                draw_text(surface, f"Progress: {m.progress_text}", SCREEN_W // 2, btn_y, NEON_YELLOW, 10, center=True)
                btn_y += 18
                btn_rect = pygame.Rect(SCREEN_W // 2 - 100, btn_y, 200, 28)
                hover = btn_rect.collidepoint(mx, my)
                draw_neon_rect(surface, NEON_RED if hover else DIM_PINK, btn_rect, 1)
                draw_text(surface, "ABANDON MISSION", btn_rect.centerx, btn_rect.centery,
                         NEON_RED if hover else DIM_PINK, 11, center=True)
                btn_y += 35
            else:
                # Show available missions
                for mi, mission in enumerate(self.world_ref.available_missions):
                    btn_rect = pygame.Rect(SCREEN_W // 2 - 120, btn_y, 240, 34)
                    hover = btn_rect.collidepoint(mx, my)
                    draw_neon_rect(surface, NEON_YELLOW if hover else (60, 60, 30), btn_rect, 1 + hover)
                    draw_text(surface, mission.name, btn_rect.x + 8, btn_rect.y + 3,
                             NEON_YELLOW if hover else (180, 170, 100), 11)
                    draw_text(surface, f"${mission.reward} — {mission.description[:40]}",
                             btn_rect.x + 8, btn_rect.y + 18, (120, 120, 100), 9)
                    btn_y += 38

        # Undock
        btn_y += 15
        btn_rect = pygame.Rect(SCREEN_W // 2 - 80, btn_y, 160, 40)
        hover = btn_rect.collidepoint(mx, my)
        pulse = 0.7 + 0.3 * math.sin(time * 3)
        color = NEON_CYAN if hover else safe_color(DIM_CYAN[0] * pulse, DIM_CYAN[1] * pulse, DIM_CYAN[2] * pulse)
        draw_neon_rect(surface, color, btn_rect, 2)
        draw_text(surface, "UNDOCK [F]", btn_rect.centerx, btn_rect.centery, color, 16, center=True)

        # Ship stats summary
        sy = btn_y + 50
        draw_text(surface, "SHIP STATUS", SCREEN_W // 2, sy, NEON_CYAN, 13, center=True)
        sy += 20
        stats = [
            f"Hull: {int(ship.core_hp)}/{int(ship.core_max_hp)}",
            f"Fuel: {int(ship.fuel)}/{int(ship.fuel_capacity)} | Range: ~{ship.fuel_range_sectors:.1f} sectors",
            f"Ore: {int(ship.ore)}/{int(ship.ore_capacity)} | Refinery: {ship.refinery_rate:.0f}/s",
            f"Thrust: {ship.total_thrust:.0f} | Weapons: {len(ship.weapon_modules)} | Probes: {ship.max_probes}",
            f"Shield: {int(ship.max_shield)} (+{ship.shield_regen:.0f}/s) | Armor: {ship.total_armor:.0f}",
        ]
        for text in stats:
            draw_text(surface, text, SCREEN_W // 2, sy, (140, 150, 170), 11, center=True)
            sy += 16


# ═════════════════════════════════════════════════════════════════════════════
#  SHIP BUILDER (reused from station, slightly modified)
# ═════════════════════════════════════════════════════════════════════════════
class ShipBuilder:
    def __init__(self):
        self.active = False
        self.cell_size = 48
        self.selected_module_id: Optional[str] = None
        self.moving_module: Optional[PlacedModule] = None  # module being moved
        self.hover_gx = -1
        self.hover_gy = -1
        self.scroll_offset = 0
        self.shop_items = [mid for mid in MODULE_DEFS.keys() if mid != 'core']
        self.tooltip_module: Optional[str] = None
        self.remove_mode = False
        self.upgrade_mode = False
        self.station_ref: Optional[Station] = None

    def toggle(self):
        self.active = not self.active
        self.selected_module_id = None
        self.remove_mode = False
        self.upgrade_mode = False

    def _get_stock(self, mid: str) -> int:
        if self.station_ref and hasattr(self.station_ref, 'stock'):
            return self.station_ref.stock.get(mid, 0)
        return 99  # unlimited if not at a station

    def _use_stock(self, mid: str):
        if self.station_ref and hasattr(self.station_ref, 'stock'):
            self.station_ref.stock[mid] = max(0, self.station_ref.stock.get(mid, 0) - 1)

    def _add_stock(self, mid: str):
        if self.station_ref and hasattr(self.station_ref, 'stock'):
            self.station_ref.stock[mid] = self.station_ref.stock.get(mid, 0) + 1

    def _grid_origin(self, ship: Ship) -> Tuple[int, int]:
        total_w = ship.grid_w * self.cell_size
        total_h = ship.grid_h * self.cell_size
        ox = SCREEN_W // 2 - total_w // 2 - 80
        oy = SCREEN_H // 2 - total_h // 2
        return ox, oy

    def handle_event(self, event, ship: Ship, audio) -> bool:
        if not self.active:
            return False

        mx, my = pygame.mouse.get_pos()
        ox, oy = self._grid_origin(ship)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                gx = (mx - ox) // self.cell_size
                gy = (my - oy) // self.cell_size
                if 0 <= gx < ship.grid_w and 0 <= gy < ship.grid_h:
                    # Placing a module from shop
                    if self.selected_module_id:
                        if ship.can_place(self.selected_module_id, gx, gy):
                            cost = MODULE_DEFS[self.selected_module_id].cost
                            in_stock = self._get_stock(self.selected_module_id) > 0
                            if ship.credits >= cost and in_stock:
                                ship.credits -= cost
                                ship.place_module(self.selected_module_id, gx, gy)
                                self._use_stock(self.selected_module_id)
                                audio.play('buy', 0.5)
                        return True
                    # Placing a module being moved
                    elif self.moving_module:
                        m = self.moving_module
                        if ship.can_place(m.defn.id, gx, gy, exclude=m):
                            m.gx = gx
                            m.gy = gy
                            ship._recalc_stats()
                            audio.play('buy', 0.3)
                        self.moving_module = None
                        return True
                    # Sell mode
                    elif self.remove_mode:
                        m = ship.cell_occupied(gx, gy)
                        if m and m.defn.id != 'core':
                            refund = m.defn.cost // 2 + (m.level - 1) * 30
                            self._add_stock(m.defn.id)
                            ship.remove_module(m)
                            ship.credits += refund
                            audio.play('pickup', 0.4)
                        return True
                    # Upgrade mode
                    elif self.upgrade_mode:
                        m = ship.cell_occupied(gx, gy)
                        if m:
                            if m.level >= 5:
                                audio.play('hit', 0.2)
                            else:
                                cost = m.upgrade_cost()
                                if ship.credits >= cost:
                                    ship.credits -= cost
                                    m.level += 1
                                    ship._recalc_stats()
                                    audio.play('buy', 0.5)
                        return True
                    # Pick up module to move it
                    else:
                        m = ship.cell_occupied(gx, gy)
                        if m and m.defn.id != 'core':
                            self.moving_module = m
                            return True

                shop_x = ox + ship.grid_w * self.cell_size + 60
                shop_y = oy
                for i, mid in enumerate(self.shop_items):
                    item_y = shop_y + i * 36 - self.scroll_offset
                    if item_y < oy - 10 or item_y > oy + ship.grid_h * self.cell_size:
                        continue
                    item_rect = pygame.Rect(shop_x, item_y, 240, 32)
                    if item_rect.collidepoint(mx, my):
                        self.selected_module_id = mid
                        self.remove_mode = False
                        return True

                expand_btns = self._expand_button_rects(ship, ox, oy)
                for direction, rect in expand_btns.items():
                    if rect.collidepoint(mx, my):
                        if ship.expand_grid(direction):
                            audio.play('buy', 0.5)
                        return True

                shrink_btns = self._shrink_button_rects(ship, ox, oy)
                for direction, rect in shrink_btns.items():
                    if rect.collidepoint(mx, my):
                        if ship.shrink_grid(direction):
                            audio.play('pickup', 0.4)
                        return True

                remove_rect = pygame.Rect(ox, oy + ship.grid_h * self.cell_size + 10, 100, 30)
                if remove_rect.collidepoint(mx, my):
                    self.remove_mode = not self.remove_mode
                    self.upgrade_mode = False
                    self.selected_module_id = None
                    return True

                upg_rect = pygame.Rect(ox + 110, oy + ship.grid_h * self.cell_size + 10, 100, 30)
                if upg_rect.collidepoint(mx, my):
                    self.upgrade_mode = not self.upgrade_mode
                    self.remove_mode = False
                    self.selected_module_id = None
                    return True

                self.selected_module_id = None
                self.remove_mode = False
                self.upgrade_mode = False

            elif event.button == 3:
                self.selected_module_id = None
                self.moving_module = None
                self.remove_mode = False
                return True

        elif event.type == pygame.MOUSEWHEEL:
            max_scroll = max(0, len(self.shop_items) * 36 - ship.grid_h * self.cell_size)
            self.scroll_offset = clamp(self.scroll_offset - event.y * 36, 0, max_scroll)
            return True

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.selected_module_id = None
                self.remove_mode = False
                return True

        return False

    def _expand_button_rects(self, ship, ox, oy):
        cs = self.cell_size
        tw = ship.grid_w * cs
        th = ship.grid_h * cs
        btn_size = 22
        return {
            'up': pygame.Rect(ox + tw // 2 - btn_size - 2, oy - btn_size - 5, btn_size, btn_size),
            'down': pygame.Rect(ox + tw // 2 - btn_size - 2, oy + th + 5, btn_size, btn_size),
            'left': pygame.Rect(ox - btn_size - 5, oy + th // 2 - btn_size - 2, btn_size, btn_size),
            'right': pygame.Rect(ox + tw + 5, oy + th // 2 - btn_size - 2, btn_size, btn_size),
        }

    def _shrink_button_rects(self, ship, ox, oy):
        cs = self.cell_size
        tw = ship.grid_w * cs
        th = ship.grid_h * cs
        btn_size = 22
        return {
            'up': pygame.Rect(ox + tw // 2 + 2, oy - btn_size - 5, btn_size, btn_size),
            'down': pygame.Rect(ox + tw // 2 + 2, oy + th + 5, btn_size, btn_size),
            'left': pygame.Rect(ox - btn_size - 5, oy + th // 2 + 2, btn_size, btn_size),
            'right': pygame.Rect(ox + tw + 5, oy + th // 2 + 2, btn_size, btn_size),
        }

    def draw(self, surface, ship: Ship, time):
        if not self.active:
            return

        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        mx, my = pygame.mouse.get_pos()
        ox, oy = self._grid_origin(ship)
        cs = self.cell_size

        draw_text(surface, "SHIP BUILDER", SCREEN_W // 2, 15, NEON_CYAN, 24, center=True)
        draw_text(surface, f"Credits: ${ship.credits}", SCREEN_W // 2, 42, NEON_YELLOW, 16, center=True)
        if self.moving_module:
            draw_text(surface, f"Moving: {self.moving_module.defn.name} — Click grid to place, right-click cancel",
                     SCREEN_W // 2, 62, NEON_BLUE, 12, center=True)
        elif self.selected_module_id:
            defn = MODULE_DEFS[self.selected_module_id]
            draw_text(surface, f"Selected: {defn.name} (${defn.cost}) — Click grid to place",
                     SCREEN_W // 2, 62, NEON_GREEN, 12, center=True)
        elif self.remove_mode:
            draw_text(surface, "SELL MODE — Click a module to sell it",
                     SCREEN_W // 2, 62, NEON_RED, 12, center=True)
        elif self.upgrade_mode:
            draw_text(surface, "UPGRADE MODE — Click a module to level it up (max Lv.5)",
                     SCREEN_W // 2, 62, NEON_GREEN, 12, center=True)
        else:
            draw_text(surface, "Click module to MOVE | Shop to BUY | SELL / UPGRADE buttons below",
                     SCREEN_W // 2, 62, DIM_CYAN, 11, center=True)

        # Grid
        grid_rect = pygame.Rect(ox - 2, oy - 2, ship.grid_w * cs + 4, ship.grid_h * cs + 4)
        pygame.draw.rect(surface, GRID_COLOR, grid_rect)
        pygame.draw.rect(surface, DIM_CYAN, grid_rect, 2)

        for gx in range(ship.grid_w):
            for gy in range(ship.grid_h):
                cell_rect = pygame.Rect(ox + gx * cs, oy + gy * cs, cs, cs)
                pygame.draw.rect(surface, GRID_LINE, cell_rect, 1)

        # Placed modules
        for m in ship.modules:
            mx2 = ox + m.gx * cs
            my2 = oy + m.gy * cs
            mw = m.defn.width * cs
            mh = m.defn.height * cs
            mod_rect = pygame.Rect(mx2 + 2, my2 + 2, mw - 4, mh - 4)
            pygame.draw.rect(surface, m.defn.color, mod_rect)
            pygame.draw.rect(surface, m.defn.glow_color, mod_rect, 2)
            name = m.defn.name[:9] + "." if len(m.defn.name) > 10 else m.defn.name
            draw_text(surface, name, mx2 + mw // 2, my2 + mh // 2 - 6, WHITE, 9, center=True)
            # Level stars
            if m.level > 1:
                stars = "*" * (m.level - 1)
                draw_text(surface, stars, mx2 + mw // 2, my2 + mh // 2 + 8, NEON_YELLOW, 10, center=True)
            if m.hp < m.max_hp:
                draw_bar(surface, mx2 + 4, my2 + mh - 10, mw - 8, 4, m.hp / m.max_hp, NEON_GREEN, (20, 20, 30))
            # Mode-specific highlights on hover
            mouse_gx = (mx - ox) // cs
            mouse_gy = (my - oy) // cs
            hovering = any(cx == mouse_gx and cy == mouse_gy for cx, cy in m.cells())
            if self.remove_mode and m.defn.id != 'core' and hovering:
                pygame.draw.rect(surface, NEON_RED, mod_rect, 3)
                refund = m.defn.cost // 2 + (m.level - 1) * 30
                draw_text(surface, f"Sell: +${refund}", mx2 + mw // 2, my2 - 12,
                         NEON_YELLOW, 10, center=True)
            elif self.upgrade_mode and hovering:
                if m.level >= 5:
                    pygame.draw.rect(surface, (100, 100, 100), mod_rect, 3)
                    draw_text(surface, "MAX", mx2 + mw // 2, my2 - 12,
                             (150, 150, 150), 10, center=True)
                else:
                    pygame.draw.rect(surface, NEON_GREEN, mod_rect, 3)
                    cost = m.upgrade_cost()
                    can_afford = ship.credits >= cost
                    c = NEON_GREEN if can_afford else NEON_RED
                    draw_text(surface, f"Lv{m.level} -> Lv{m.level+1}: ${cost}",
                             mx2 + mw // 2, my2 - 12, c, 10, center=True)

        # Placement preview (new module from shop)
        if self.selected_module_id:
            defn = MODULE_DEFS[self.selected_module_id]
            gx = (mx - ox) // cs
            gy = (my - oy) // cs
            if 0 <= gx <= ship.grid_w - defn.width and 0 <= gy <= ship.grid_h - defn.height:
                can = ship.can_place(self.selected_module_id, gx, gy)
                color = (*NEON_GREEN[:3], 80) if can else (*NEON_RED[:3], 80)
                preview = pygame.Surface((defn.width * cs, defn.height * cs), pygame.SRCALPHA)
                preview.fill(color)
                surface.blit(preview, (ox + gx * cs, oy + gy * cs))
                border_color = NEON_GREEN if can else NEON_RED
                pygame.draw.rect(surface, border_color,
                               (ox + gx * cs, oy + gy * cs, defn.width * cs, defn.height * cs), 2)

        # Moving module preview (drag existing module)
        if self.moving_module:
            m = self.moving_module
            defn = m.defn
            gx = (mx - ox) // cs
            gy = (my - oy) // cs
            if 0 <= gx <= ship.grid_w - defn.width and 0 <= gy <= ship.grid_h - defn.height:
                can = ship.can_place(defn.id, gx, gy, exclude=m)
                color = (*NEON_BLUE[:3], 80) if can else (*NEON_RED[:3], 80)
                preview = pygame.Surface((defn.width * cs, defn.height * cs), pygame.SRCALPHA)
                preview.fill(color)
                surface.blit(preview, (ox + gx * cs, oy + gy * cs))
                border_color = NEON_BLUE if can else NEON_RED
                pygame.draw.rect(surface, border_color,
                               (ox + gx * cs, oy + gy * cs, defn.width * cs, defn.height * cs), 2)
            # Highlight the module's current position
            cur_rect = pygame.Rect(ox + m.gx * cs + 2, oy + m.gy * cs + 2,
                                  defn.width * cs - 4, defn.height * cs - 4)
            pygame.draw.rect(surface, NEON_BLUE, cur_rect, 2)

        # Expand buttons (+)
        expand_btns = self._expand_button_rects(ship, ox, oy)
        arrows = {'up': '^', 'down': 'v', 'left': '<', 'right': '>'}
        for direction, rect in expand_btns.items():
            hover = rect.collidepoint(mx, my)
            color = NEON_CYAN if hover else DIM_CYAN
            if ship.credits < EXPAND_COST:
                color = (40, 40, 40)
            pygame.draw.rect(surface, color, rect, 2)
            draw_text(surface, "+", rect.centerx, rect.centery, color, 16, center=True)

        # Shrink buttons (-)
        shrink_btns = self._shrink_button_rects(ship, ox, oy)
        for direction, rect in shrink_btns.items():
            hover = rect.collidepoint(mx, my)
            can = ship.can_shrink(direction)
            color = NEON_ORANGE if hover and can else (DIM_PINK if can else (40, 40, 40))
            pygame.draw.rect(surface, color, rect, 2)
            draw_text(surface, "-", rect.centerx, rect.centery, color, 16, center=True)

        draw_text(surface, f"Expand: ${EXPAND_COST} | Shrink: refund ${EXPAND_COST // 2}",
                 ox + ship.grid_w * cs // 2, oy - 50, DIM_CYAN, 10, center=True)

        # Remove button
        remove_rect = pygame.Rect(ox, oy + ship.grid_h * cs + 10, 100, 30)
        rm_color = NEON_RED if self.remove_mode else DIM_PINK
        pygame.draw.rect(surface, rm_color, remove_rect, 2)
        draw_text(surface, "SELL MODE" if self.remove_mode else "SELL",
                 remove_rect.centerx, remove_rect.centery, rm_color, 12, center=True)

        # Upgrade button
        upg_rect = pygame.Rect(ox + 110, oy + ship.grid_h * cs + 10, 100, 30)
        up_color = NEON_GREEN if self.upgrade_mode else DIM_GREEN
        pygame.draw.rect(surface, up_color, upg_rect, 2)
        draw_text(surface, "UPGRADE MODE" if self.upgrade_mode else "UPGRADE",
                 upg_rect.centerx, upg_rect.centery, up_color, 11, center=True)

        # Shop panel
        shop_x = ox + ship.grid_w * cs + 60
        shop_y = oy
        shop_w = 240
        shop_h = ship.grid_h * cs

        shop_rect = pygame.Rect(shop_x - 5, shop_y - 5, shop_w + 10, shop_h + 10)
        pygame.draw.rect(surface, (8, 8, 20), shop_rect)
        pygame.draw.rect(surface, DIM_CYAN, shop_rect, 1)
        draw_text(surface, "MODULES", shop_x + shop_w // 2, shop_y - 20, NEON_CYAN, 14, center=True)

        clip_rect = pygame.Rect(shop_x, shop_y, shop_w, shop_h)
        prev_clip = surface.get_clip()
        surface.set_clip(clip_rect)

        self.tooltip_module = None
        for i, mid in enumerate(self.shop_items):
            defn = MODULE_DEFS[mid]
            item_y = shop_y + i * 36 - self.scroll_offset
            if item_y < shop_y - 36 or item_y > shop_y + shop_h:
                continue
            item_rect = pygame.Rect(shop_x, item_y, shop_w, 32)
            hover = item_rect.collidepoint(mx, my)
            selected = self.selected_module_id == mid
            stock = self._get_stock(mid)
            can_afford = ship.credits >= defn.cost and stock > 0

            if selected:
                bg_surf = pygame.Surface((shop_w, 32), pygame.SRCALPHA)
                bg_surf.fill((*NEON_CYAN[:3], 60))
                surface.blit(bg_surf, (shop_x, item_y))
                pygame.draw.rect(surface, NEON_CYAN, item_rect, 2)
                draw_text(surface, ">", shop_x - 12, item_y + 8, NEON_CYAN, 14)
            elif hover:
                bg_surf = pygame.Surface((shop_w, 32), pygame.SRCALPHA)
                bg_surf.fill((40, 50, 70, 60))
                surface.blit(bg_surf, (shop_x, item_y))
                self.tooltip_module = mid

            swatch_alpha = 1.0 if stock > 0 else 0.3
            sc = defn.color if stock > 0 else (40, 40, 40)
            pygame.draw.rect(surface, sc, (shop_x + 4, item_y + 4, 24, 24))
            pygame.draw.rect(surface, defn.glow_color if stock > 0 else (50, 50, 50),
                           (shop_x + 4, item_y + 4, 24, 24), 1)
            draw_text(surface, f"{defn.width}x{defn.height}", shop_x + 16, item_y + 16, WHITE, 8, center=True)
            name_color = WHITE if can_afford else (80, 80, 80)
            if stock <= 0:
                name_color = (50, 50, 50)
            draw_text(surface, defn.name, shop_x + 34, item_y + 4, name_color, 11)
            # Price + stock
            price_color = NEON_YELLOW if can_afford else NEON_RED
            if stock <= 0:
                price_color = (60, 30, 30)
            draw_text(surface, f"${defn.cost}", shop_x + 34, item_y + 18, price_color, 10)
            # Stock count
            stock_color = NEON_GREEN if stock >= 3 else (NEON_YELLOW if stock > 0 else NEON_RED)
            stock_text = f"x{stock}" if stock > 0 else "SOLD"
            draw_text(surface, stock_text, shop_x + shop_w - 30, item_y + 10, stock_color, 10)
            border = defn.glow_color if selected else (DIM_CYAN if hover else (30, 35, 50))
            pygame.draw.rect(surface, border, item_rect, 1)

        surface.set_clip(prev_clip)

        # Tooltip
        if self.tooltip_module:
            self._draw_tooltip(surface, mx, my, self.tooltip_module)

        # Ship stats
        stats_x = ox - 10
        stats_y = oy + ship.grid_h * cs + 50
        draw_text(surface, "SHIP STATS", stats_x, stats_y, NEON_CYAN, 13)
        stats_y += 18
        stats = [
            (f"Thrust: {ship.total_thrust:.0f}", NEON_ORANGE),
            (f"Fuel Cap: {ship.fuel_capacity:.0f}", FUEL_COLOR),
            (f"Ore Cap: {ship.ore_capacity:.0f}", ORE_COLOR),
            (f"Refinery: {ship.refinery_rate:.0f}/s", NEON_GREEN),
            (f"Shield: {ship.max_shield:.0f} (+{ship.shield_regen:.0f}/s)", NEON_BLUE),
            (f"Armor: {ship.total_armor:.0f}", (150, 150, 150)),
            (f"Hull Repair: {ship.total_hull_regen:.0f}/s", NEON_GREEN),
            (f"Probes: {ship.max_probes}", NEON_GREEN),
            (f"Weapons: {len(ship.weapon_modules)}", NEON_RED),
            (f"Grid: {ship.grid_w}x{ship.grid_h}", DIM_CYAN),
        ]
        for text, color in stats:
            draw_text(surface, text, stats_x, stats_y, color, 11)
            stats_y += 15

    def _draw_tooltip(self, surface, mx, my, mid):
        defn = MODULE_DEFS[mid]
        lines = [defn.name, f"Size: {defn.width}x{defn.height}  Cost: ${defn.cost}", defn.description]
        if defn.thrust > 0: lines.append(f"Thrust: +{defn.thrust:.0f}")
        if defn.fuel_capacity > 0: lines.append(f"Fuel Storage: +{defn.fuel_capacity:.0f}")
        if defn.ore_capacity > 0: lines.append(f"Ore Storage: +{defn.ore_capacity:.0f}")
        if defn.refinery_rate > 0: lines.append(f"Refining: {defn.refinery_rate:.0f} ore/sec -> fuel")
        if defn.damage > 0: lines.append(f"Damage: {defn.damage:.0f}  Rate: {defn.fire_rate:.1f}/s")
        if defn.shield_hp > 0: lines.append(f"Shield: +{defn.shield_hp:.0f} HP  Regen: {defn.shield_regen:.0f}/s")
        if defn.armor > 0: lines.append(f"Armor: +{defn.armor:.0f}")
        if defn.hull_regen > 0: lines.append(f"Hull Repair: +{defn.hull_regen:.0f} HP/sec")
        if defn.probe_count > 0: lines.append(f"Probes: +{defn.probe_count}")

        tw = 260
        th = 14 + len(lines) * 16
        tx = min(mx + 15, SCREEN_W - tw - 10)
        ty = min(my - 10, SCREEN_H - th - 10)

        tooltip_surf = pygame.Surface((tw, th), pygame.SRCALPHA)
        tooltip_surf.fill((10, 10, 25, 220))
        pygame.draw.rect(tooltip_surf, NEON_CYAN, (0, 0, tw, th), 1)
        surface.blit(tooltip_surf, (tx, ty))
        for i, line in enumerate(lines):
            color = NEON_CYAN if i == 0 else (NEON_YELLOW if i == 1 else WHITE)
            draw_text(surface, line, tx + 8, ty + 6 + i * 16, color, 10)


# ═════════════════════════════════════════════════════════════════════════════
#  PAUSE MENU
# ═════════════════════════════════════════════════════════════════════════════
class PauseMenu:
    def __init__(self):
        self.active = False
        self.selected = 0
        self.buttons = ['RESUME', 'SAVE', 'UPDATE', 'MENU', 'RESTART', 'QUIT']
        self.save_msg = ""
        self.save_msg_timer = 0.0
        self.updater = None
        self.update_info = None  # remote version info if available

    def toggle(self):
        self.active = not self.active
        self.selected = 0

    def update(self, dt):
        if self.save_msg_timer > 0:
            self.save_msg_timer -= dt

    def handle_event(self, event):
        """Returns None, 'resume', 'save', 'restart', or 'quit'."""
        if not self.active:
            return None

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.active = False
                return 'resume'
            if event.key in (pygame.K_w, pygame.K_UP):
                self.selected = (self.selected - 1) % len(self.buttons)
            if event.key in (pygame.K_s, pygame.K_DOWN):
                self.selected = (self.selected + 1) % len(self.buttons)
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                return self.buttons[self.selected].lower()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for i, label in enumerate(self.buttons):
                btn = pygame.Rect(SCREEN_W // 2 - 90, 260 + i * 55, 180, 42)
                if btn.collidepoint(mx, my):
                    return label.lower()

        if event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            for i, label in enumerate(self.buttons):
                btn = pygame.Rect(SCREEN_W // 2 - 90, 260 + i * 55, 180, 42)
                if btn.collidepoint(mx, my):
                    self.selected = i

        return None

    def show_save_result(self, success):
        self.save_msg = "Game saved!" if success else "Save failed!"
        self.save_msg_timer = 2.5

    def draw(self, surface, ship, world, time):
        if not self.active:
            return

        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        draw_text(surface, "PAUSED", SCREEN_W // 2, 190,
                 NEON_CYAN, 36, center=True, font_name="consolas")

        # Save message
        if self.save_msg_timer > 0:
            alpha = min(1.0, self.save_msg_timer)
            c = NEON_GREEN if "saved" in self.save_msg else NEON_RED
            draw_text(surface, self.save_msg, SCREEN_W // 2, 230,
                     safe_color(c[0] * alpha, c[1] * alpha, c[2] * alpha),
                     14, center=True)

        mx, my = pygame.mouse.get_pos()
        for i, label in enumerate(self.buttons):
            btn = pygame.Rect(SCREEN_W // 2 - 90, 260 + i * 55, 180, 42)
            hover = btn.collidepoint(mx, my)
            selected = i == self.selected

            if label == 'QUIT':
                base_color = NEON_RED
                dim_color = DIM_PINK
            elif label == 'RESTART':
                base_color = NEON_ORANGE
                dim_color = (80, 50, 0)
            elif label == 'MENU':
                base_color = NEON_PURPLE
                dim_color = (60, 30, 80)
            elif label == 'SAVE':
                base_color = NEON_GREEN
                dim_color = DIM_GREEN
            else:
                base_color = NEON_CYAN
                dim_color = DIM_CYAN

            if selected or hover:
                pulse = 0.7 + 0.3 * math.sin(time * 4)
                color = (int(base_color[0] * pulse), int(base_color[1] * pulse), int(base_color[2] * pulse))
                draw_neon_rect(surface, color, btn, 2, 50)
            else:
                draw_neon_rect(surface, dim_color, btn, 1)
                color = dim_color

            draw_text(surface, label, btn.centerx, btn.centery,
                     base_color if (selected or hover) else dim_color, 18, center=True)

        # Stats while paused
        sy = 500
        draw_text(surface, "SESSION STATS", SCREEN_W // 2, sy, DIM_CYAN, 13, center=True)
        sy += 24
        stats = [
            (f"Sectors Discovered: {len(world.sectors.discovered)}", NEON_CYAN),
            (f"Farthest: {world.sectors.farthest_distance} from home", NEON_PURPLE),
            (f"Credits: ${ship.credits}", NEON_YELLOW),
            (f"Hull: {int(ship.core_hp)}/{int(ship.core_max_hp)}", NEON_GREEN),
            (f"Fuel: {int(ship.fuel)}/{int(ship.fuel_capacity)}", NEON_ORANGE),
        ]
        for text, color in stats:
            draw_text(surface, text, SCREEN_W // 2, sy, color, 12, center=True)
            sy += 18

        # Controls reminder
        draw_text(surface, "ESC to resume", SCREEN_W // 2, SCREEN_H - 30,
                 (60, 70, 90), 11, center=True)


# ═════════════════════════════════════════════════════════════════════════════
#  MULTIPLAYER LOBBY UI
# ═════════════════════════════════════════════════════════════════════════════
class LobbyUI:
    def __init__(self):
        self.active = False
        self.mode = ''  # 'host' or 'join'
        self.ip_text = ''
        self.name_text = 'Player'
        self.editing_ip = True  # which field is focused
        self.friendly_fire = False
        self.auto_shoot = False
        self.status = ''
        self.status_color = DIM_CYAN
        self.host_ip = ''
        self.scanner = None
        self.selected_server = -1

    def open_host(self):
        self.active = True
        self.mode = 'host'
        self.status = ''
        from game.network import get_local_ip
        self.host_ip = get_local_ip()

    def open_join(self):
        self.active = True
        self.mode = 'join'
        self.ip_text = ''
        self.editing_ip = True
        self.status = ''
        self.selected_server = -1
        # Start scanning for LAN games
        from game.network import LANScanner
        self.scanner = LANScanner()
        self.scanner.start()

    def close(self):
        self.active = False
        if self.scanner:
            self.scanner.stop()
            self.scanner = None

    def handle_event(self, event):
        """Returns None, 'start_host', 'start_join', or 'back'."""
        if not self.active:
            return None

        mx, my = pygame.mouse.get_pos() if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION) else (0, 0)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return 'back'
            if event.key == pygame.K_RETURN:
                if self.mode == 'host':
                    return 'start_host'
                elif self.mode == 'join' and self.ip_text:
                    return 'start_join'

            # Text input for join IP
            if self.mode == 'join' and self.editing_ip:
                if event.key == pygame.K_BACKSPACE:
                    self.ip_text = self.ip_text[:-1]
                elif event.key == pygame.K_TAB:
                    self.editing_ip = False
                elif len(self.ip_text) < 21 and event.unicode.isprintable():
                    self.ip_text += event.unicode
            elif not self.editing_ip:
                if event.key == pygame.K_BACKSPACE:
                    self.name_text = self.name_text[:-1]
                elif event.key == pygame.K_TAB:
                    self.editing_ip = True
                elif len(self.name_text) < 15 and event.unicode.isprintable():
                    self.name_text += event.unicode

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.mode == 'host':
                # Friendly fire toggle
                ff_rect = pygame.Rect(SCREEN_W // 2 - 100, 300, 200, 30)
                if ff_rect.collidepoint(mx, my):
                    self.friendly_fire = not self.friendly_fire
                # Auto-shoot toggle
                as_rect = pygame.Rect(SCREEN_W // 2 - 100, 340, 200, 30)
                if as_rect.collidepoint(mx, my):
                    self.auto_shoot = not self.auto_shoot
                # Start button
                start_rect = pygame.Rect(SCREEN_W // 2 - 80, 400, 160, 40)
                if start_rect.collidepoint(mx, my):
                    return 'start_host'
            elif self.mode == 'join':
                # Click on discovered server
                if self.scanner:
                    servers = list(self.scanner.get_servers().items())
                    for i, (ip, info) in enumerate(servers):
                        srv_rect = pygame.Rect(SCREEN_W // 2 - 150, 200 + i * 45, 300, 40)
                        if srv_rect.collidepoint(mx, my):
                            self.ip_text = ip
                            self.selected_server = i
                            return 'start_join'
                # Name field
                name_rect = pygame.Rect(SCREEN_W // 2 - 100, SCREEN_H - 180, 200, 28)
                if name_rect.collidepoint(mx, my):
                    self.editing_ip = False
                # Manual IP field
                ip_rect = pygame.Rect(SCREEN_W // 2 - 100, SCREEN_H - 130, 200, 28)
                if ip_rect.collidepoint(mx, my):
                    self.editing_ip = True
                # Manual connect button
                connect_rect = pygame.Rect(SCREEN_W // 2 - 80, SCREEN_H - 90, 160, 35)
                if connect_rect.collidepoint(mx, my) and self.ip_text:
                    return 'start_join'

            # Back button
            back_rect = pygame.Rect(20, SCREEN_H - 50, 100, 35)
            if back_rect.collidepoint(mx, my):
                return 'back'

        return None

    def draw(self, surface, time):
        if not self.active:
            return

        surface.fill(BG_DARK)
        mx, my = pygame.mouse.get_pos()

        if self.mode == 'host':
            draw_text(surface, "HOST GAME", SCREEN_W // 2, 180, NEON_CYAN, 28, center=True)
            draw_text(surface, f"Your IP: {self.host_ip}", SCREEN_W // 2, 220, NEON_YELLOW, 16, center=True)
            draw_text(surface, f"Port: 7777", SCREEN_W // 2, 245, DIM_CYAN, 12, center=True)
            draw_text(surface, "Share your IP with friends to let them join",
                     SCREEN_W // 2, 270, (80, 90, 100), 11, center=True)

            # Friendly fire toggle
            ff_rect = pygame.Rect(SCREEN_W // 2 - 100, 300, 200, 30)
            ff_color = NEON_GREEN if self.friendly_fire else NEON_RED
            draw_neon_rect(surface, ff_color, ff_rect, 1)
            draw_text(surface, f"Friendly Fire: {'ON' if self.friendly_fire else 'OFF'}",
                     ff_rect.centerx, ff_rect.centery, ff_color, 13, center=True)

            # Auto-shoot toggle
            as_rect = pygame.Rect(SCREEN_W // 2 - 100, 340, 200, 30)
            as_color = NEON_ORANGE if self.auto_shoot else DIM_CYAN
            draw_neon_rect(surface, as_color, as_rect, 1)
            draw_text(surface, f"Auto-Shoot Players: {'ON' if self.auto_shoot else 'OFF'}",
                     as_rect.centerx, as_rect.centery, as_color, 13, center=True)

            # Start
            start_rect = pygame.Rect(SCREEN_W // 2 - 80, 400, 160, 40)
            hover = start_rect.collidepoint(mx, my)
            pulse = 0.7 + 0.3 * math.sin(time * 3)
            c = NEON_CYAN if hover else safe_color(NEON_CYAN[0] * pulse, NEON_CYAN[1] * pulse, NEON_CYAN[2] * pulse)
            draw_neon_rect(surface, c, start_rect, 2)
            draw_text(surface, "START HOST", start_rect.centerx, start_rect.centery, NEON_CYAN, 18, center=True)

        elif self.mode == 'join':
            draw_text(surface, "JOIN GAME", SCREEN_W // 2, 160, NEON_GREEN, 28, center=True)

            # ── LAN SERVER LIST ───────────────────────────────────
            draw_text(surface, "Games on your network:", SCREEN_W // 2, 190, DIM_CYAN, 12, center=True)

            servers = list(self.scanner.get_servers().items()) if self.scanner else []
            if servers:
                for i, (ip, info) in enumerate(servers):
                    srv_rect = pygame.Rect(SCREEN_W // 2 - 150, 210 + i * 45, 300, 40)
                    hover = srv_rect.collidepoint(mx, my)
                    border_c = NEON_GREEN if hover else DIM_GREEN
                    bg_surf = pygame.Surface((300, 40), pygame.SRCALPHA)
                    bg_surf.fill((20, 40, 20, 80) if hover else (10, 20, 10, 40))
                    surface.blit(bg_surf, srv_rect.topleft)
                    draw_neon_rect(surface, border_c, srv_rect, 2 if hover else 1)
                    # Server info
                    players = info.get('players', 0)
                    ff = "FF" if info.get('friendly_fire') else ""
                    draw_text(surface, f"{ip}:{info.get('port', 7777)}",
                             srv_rect.x + 10, srv_rect.y + 5, NEON_GREEN if hover else WHITE, 13)
                    draw_text(surface, f"{players} player(s) connected  {ff}",
                             srv_rect.x + 10, srv_rect.y + 22, DIM_CYAN, 10)
                    if hover:
                        draw_text(surface, "CLICK TO JOIN", srv_rect.right - 10, srv_rect.centery,
                                 NEON_GREEN, 11, center=True)
            else:
                # Scanning animation
                dots = "." * (int(time * 2) % 4)
                draw_text(surface, f"Scanning for games{dots}", SCREEN_W // 2, 230,
                         (80, 90, 100), 13, center=True)
                draw_text(surface, "Make sure the host has started their game",
                         SCREEN_W // 2, 250, (60, 70, 80), 10, center=True)

            # ── MANUAL CONNECT (fallback) ─────────────────────────
            manual_y = SCREEN_H - 195
            draw_text(surface, "- or connect manually -", SCREEN_W // 2, manual_y,
                     (50, 55, 65), 10, center=True)
            manual_y += 18

            # Name input
            draw_text(surface, "Name:", SCREEN_W // 2 - 100, manual_y, DIM_CYAN, 11)
            name_rect = pygame.Rect(SCREEN_W // 2 - 100, manual_y + 14, 200, 24)
            name_border = NEON_CYAN if not self.editing_ip else (40, 50, 60)
            pygame.draw.rect(surface, (15, 15, 30), name_rect)
            pygame.draw.rect(surface, name_border, name_rect, 1)
            name_display = self.name_text + ("|" if not self.editing_ip and int(time * 2) % 2 == 0 else "")
            draw_text(surface, name_display, name_rect.x + 6, name_rect.y + 4, WHITE, 12)
            manual_y += 44

            # IP input
            draw_text(surface, "Host IP:", SCREEN_W // 2 - 100, manual_y, DIM_CYAN, 11)
            ip_rect = pygame.Rect(SCREEN_W // 2 - 100, manual_y + 14, 200, 24)
            ip_border = NEON_CYAN if self.editing_ip else (40, 50, 60)
            pygame.draw.rect(surface, (15, 15, 30), ip_rect)
            pygame.draw.rect(surface, ip_border, ip_rect, 1)
            ip_display = self.ip_text + ("|" if self.editing_ip and int(time * 2) % 2 == 0 else "")
            draw_text(surface, ip_display, ip_rect.x + 6, ip_rect.y + 4, WHITE, 12)
            manual_y += 42

            # Manual connect button
            connect_rect = pygame.Rect(SCREEN_W // 2 - 80, manual_y, 160, 30)
            can_connect = len(self.ip_text) > 0
            hover = connect_rect.collidepoint(mx, my) and can_connect
            c = NEON_GREEN if hover else (DIM_GREEN if can_connect else (40, 40, 40))
            draw_neon_rect(surface, c, connect_rect, 2 if hover else 1)
            draw_text(surface, "CONNECT", connect_rect.centerx, connect_rect.centery, c, 13, center=True)

        # Status
        if self.status:
            draw_text(surface, self.status, SCREEN_W // 2, 460, self.status_color, 13, center=True)

        # Back button
        back_rect = pygame.Rect(20, SCREEN_H - 50, 100, 35)
        hover = back_rect.collidepoint(mx, my)
        draw_neon_rect(surface, NEON_RED if hover else DIM_PINK, back_rect, 1)
        draw_text(surface, "BACK", back_rect.centerx, back_rect.centery,
                 NEON_RED if hover else DIM_PINK, 14, center=True)


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ═════════════════════════════════════════════════════════════════════════════
class MainMenu:
    def __init__(self):
        self.active = True
        self.title_anim = 0.0
        self.stars_offset = 0.0
        self.has_save = False
        self.respawn_enabled = True
        self.strip_on_respawn = False
        self._check_save()

    def _check_save(self):
        from game.save import has_save
        self.has_save = has_save()

    def update(self, dt):
        self.title_anim += dt
        self.stars_offset += dt * 20

    def handle_event(self, event):
        """Returns None, 'new', or 'continue'."""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.active = False
                return 'new'
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            # New game button
            new_rect = pygame.Rect(SCREEN_W // 2 - 80, SCREEN_H // 2 + 30, 160, 40)
            if new_rect.collidepoint(mx, my):
                self.active = False
                return 'new'
            # Continue button
            if self.has_save:
                cont_rect = pygame.Rect(SCREEN_W // 2 - 80, SCREEN_H // 2 + 80, 160, 40)
                if cont_rect.collidepoint(mx, my):
                    self.active = False
                    return 'continue'
            # Multiplayer buttons
            mp_y = SCREEN_H // 2 + (130 if self.has_save else 85)
            host_rect = pygame.Rect(SCREEN_W // 2 - 80, mp_y, 75, 35)
            if host_rect.collidepoint(mx, my):
                return 'host'
            join_rect = pygame.Rect(SCREEN_W // 2 + 5, mp_y, 75, 35)
            if join_rect.collidepoint(mx, my):
                return 'join'
            # Respawn toggle
            resp_rect = pygame.Rect(SCREEN_W // 2 - 80, mp_y + 42, 160, 28)
            if resp_rect.collidepoint(mx, my):
                self.respawn_enabled = not self.respawn_enabled
            # Strip modules on respawn toggle
            if self.respawn_enabled:
                strip_rect = pygame.Rect(SCREEN_W // 2 - 80, mp_y + 74, 160, 28)
                if strip_rect.collidepoint(mx, my):
                    self.strip_on_respawn = not self.strip_on_respawn
        return None

    def draw(self, surface, time):
        surface.fill(BG_DARK)

        for i in range(30):
            y = (i * 30 + self.stars_offset) % SCREEN_H
            alpha = int(15 + 8 * math.sin(time + i))
            pygame.draw.line(surface, (alpha, alpha, alpha + 15), (0, int(y)), (SCREEN_W, int(y)))
        for i in range(40):
            x = (i * 35 + self.stars_offset * 0.5) % SCREEN_W
            alpha = int(10 + 6 * math.sin(time * 0.7 + i))
            pygame.draw.line(surface, (alpha, alpha, alpha + 10), (int(x), 0), (int(x), SCREEN_H))

        glow = pygame.Surface((600, 300), pygame.SRCALPHA)
        glow_alpha = int(18 + 8 * math.sin(time * 0.5))
        pygame.draw.ellipse(glow, (0, 60, 80, glow_alpha), (0, 0, 600, 300))
        surface.blit(glow, (SCREEN_W // 2 - 300, SCREEN_H // 3 - 100), special_flags=pygame.BLEND_ADD)

        title_y = SCREEN_H // 3 + math.sin(self.title_anim * 0.8) * 8
        draw_text(surface, "NEON VOID", SCREEN_W // 2, int(title_y),
                 NEON_CYAN, 52, center=True, font_name="consolas")
        draw_text(surface, "MINE . BUILD . EXPLORE", SCREEN_W // 2, int(title_y) + 40,
                 DIM_CYAN, 14, center=True)

        mx, my = pygame.mouse.get_pos()

        # New Game button
        new_rect = pygame.Rect(SCREEN_W // 2 - 80, SCREEN_H // 2 + 30, 160, 40)
        pulse = 0.7 + 0.3 * math.sin(time * 3)
        hover = new_rect.collidepoint(mx, my)
        btn_color = NEON_CYAN if hover else (int(NEON_CYAN[0] * pulse), int(NEON_CYAN[1] * pulse), int(NEON_CYAN[2] * pulse))
        draw_neon_rect(surface, btn_color, new_rect, 2)
        draw_text(surface, "NEW GAME", new_rect.centerx, new_rect.centery, NEON_CYAN, 18, center=True)

        # Continue button (if save exists)
        if self.has_save:
            cont_rect = pygame.Rect(SCREEN_W // 2 - 80, SCREEN_H // 2 + 80, 160, 40)
            hover2 = cont_rect.collidepoint(mx, my)
            cont_color = NEON_GREEN if hover2 else safe_color(NEON_GREEN[0] * pulse, NEON_GREEN[1] * pulse, NEON_GREEN[2] * pulse)
            draw_neon_rect(surface, cont_color, cont_rect, 2)
            draw_text(surface, "CONTINUE", cont_rect.centerx, cont_rect.centery, NEON_GREEN, 18, center=True)

        # Multiplayer buttons
        mp_y = SCREEN_H // 2 + (130 if self.has_save else 85)
        host_rect = pygame.Rect(SCREEN_W // 2 - 80, mp_y, 75, 35)
        h_hover = host_rect.collidepoint(mx, my)
        draw_neon_rect(surface, NEON_PURPLE if h_hover else (80, 40, 120), host_rect, 2 if h_hover else 1)
        draw_text(surface, "HOST", host_rect.centerx, host_rect.centery,
                 NEON_PURPLE if h_hover else (120, 60, 180), 14, center=True)

        join_rect = pygame.Rect(SCREEN_W // 2 + 5, mp_y, 75, 35)
        j_hover = join_rect.collidepoint(mx, my)
        draw_neon_rect(surface, NEON_PURPLE if j_hover else (80, 40, 120), join_rect, 2 if j_hover else 1)
        draw_text(surface, "JOIN", join_rect.centerx, join_rect.centery,
                 NEON_PURPLE if j_hover else (120, 60, 180), 14, center=True)

        # Respawn toggle
        resp_rect = pygame.Rect(SCREEN_W // 2 - 80, mp_y + 42, 160, 28)
        resp_c = NEON_GREEN if self.respawn_enabled else NEON_RED
        draw_neon_rect(surface, resp_c, resp_rect, 1)
        draw_text(surface, f"Respawn: {'ON' if self.respawn_enabled else 'OFF (permadeath)'}",
                 resp_rect.centerx, resp_rect.centery, resp_c, 11, center=True)

        # Strip modules on respawn toggle (only shown if respawn on)
        if self.respawn_enabled:
            strip_rect = pygame.Rect(SCREEN_W // 2 - 80, mp_y + 74, 160, 28)
            strip_c = NEON_ORANGE if self.strip_on_respawn else DIM_CYAN
            draw_neon_rect(surface, strip_c, strip_rect, 1)
            label = "Strip Modules: ON (hardcore)" if self.strip_on_respawn else "Strip Modules: OFF"
            draw_text(surface, label, strip_rect.centerx, strip_rect.centery, strip_c, 10, center=True)

        controls_y = SCREEN_H // 2 + (255 if self.has_save else 215)
        controls = [
            "WASD - Fly your ship        SHIFT - Boost",
            "RMB - Laser beam (pierces!)  MMB - Homing missiles",
            "E - Launch mining probe      F - Dock / Interact",
            "TAB / M - Sector map         ESC - Pause",
            "",
            "Explore sectors, mine asteroids, refine fuel,",
            "dock at stations to buy modules, expand your ship,",
            "and push deeper into hostile space.",
        ]
        for i, line in enumerate(controls):
            draw_text(surface, line, SCREEN_W // 2, controls_y + i * 18,
                     DIM_CYAN if line else (30, 30, 40), 12, center=True)


# ═════════════════════════════════════════════════════════════════════════════
#  GAME OVER SCREEN
# ═════════════════════════════════════════════════════════════════════════════
class GameOverScreen:
    def __init__(self):
        self.active = False
        self.fade = 0.0
        self.sectors_discovered = 0
        self.farthest = 0
        self.credits_earned = 0
        self.victory = False

    def activate(self, sectors_discovered, farthest, credits, victory=False):
        self.active = True
        self.fade = 0.0
        self.sectors_discovered = sectors_discovered
        self.farthest = farthest
        self.credits_earned = credits
        self.victory = victory

    def update(self, dt):
        if self.active:
            self.fade = min(1.0, self.fade + dt * 0.5)

    def handle_event(self, event):
        if not self.active or self.fade < 0.8:
            return False
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_r):
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            btn = pygame.Rect(SCREEN_W // 2 - 80, SCREEN_H // 2 + 80, 160, 45)
            if btn.collidepoint(event.pos):
                return True
        return False

    def draw(self, surface, time):
        if not self.active:
            return

        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(200 * self.fade)))
        surface.blit(overlay, (0, 0))

        if self.fade < 0.3:
            return

        alpha = min(1.0, (self.fade - 0.3) / 0.5)
        def c(color):
            return safe_color(color[0] * alpha, color[1] * alpha, color[2] * alpha)

        if self.victory:
            draw_text(surface, "VOID TITAN DESTROYED!", SCREEN_W // 2, SCREEN_H // 3 - 20,
                     c(NEON_GREEN), 36, center=True)
            draw_text(surface, "You conquered the void.", SCREEN_W // 2, SCREEN_H // 3 + 20,
                     c(NEON_CYAN), 16, center=True)
        else:
            draw_text(surface, "SHIP DESTROYED", SCREEN_W // 2, SCREEN_H // 3,
                     c(NEON_RED), 36, center=True)

        y = SCREEN_H // 2 - 20
        draw_text(surface, f"Sectors Discovered: {self.sectors_discovered}", SCREEN_W // 2, y,
                 c(NEON_CYAN), 18, center=True)
        y += 30
        draw_text(surface, f"Farthest from Home: {self.farthest} sectors", SCREEN_W // 2, y,
                 c(NEON_PURPLE), 16, center=True)
        y += 30
        draw_text(surface, f"Total Credits Earned: ${self.credits_earned}", SCREEN_W // 2, y,
                 c(NEON_YELLOW), 16, center=True)

        if self.fade >= 0.8:
            btn = pygame.Rect(SCREEN_W // 2 - 80, SCREEN_H // 2 + 80, 160, 45)
            pulse = 0.7 + 0.3 * math.sin(time * 3)
            btn_c = (int(NEON_CYAN[0] * pulse), int(NEON_CYAN[1] * pulse), int(NEON_CYAN[2] * pulse))
            draw_neon_rect(surface, btn_c, btn, 2)
            draw_text(surface, "RESTART", btn.centerx, btn.centery, c(NEON_CYAN), 18, center=True)
            draw_text(surface, "Press R or ENTER", SCREEN_W // 2, SCREEN_H // 2 + 140,
                     c(DIM_CYAN), 12, center=True)


# ═════════════════════════════════════════════════════════════════════════════
#  CHEST UI — deposit/withdraw specific amounts
# ═════════════════════════════════════════════════════════════════════════════
class ChestUI:
    def __init__(self):
        self.active = False
        self.chest = None
        self.mode = 'deposit'
        self.module_scroll = 0

    def open(self, chest):
        self.active = True
        self.chest = chest
        self.mode = 'deposit'
        self.module_scroll = 0

    def close(self):
        self.active = False
        self.chest = None

    def handle_event(self, event, ship, audio):
        """Returns 'close' or None."""
        if not self.active or not self.chest:
            return None

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_f):
                return 'close'

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            # Mode tabs
            dep_rect = pygame.Rect(SCREEN_W // 2 - 110, 140, 100, 35)
            wd_rect = pygame.Rect(SCREEN_W // 2 + 10, 140, 100, 35)
            if dep_rect.collidepoint(mx, my):
                self.mode = 'deposit'
                return None
            if wd_rect.collidepoint(mx, my):
                self.mode = 'withdraw'
                return None

            # Amount buttons for credits
            credits_y = 230
            for i, amt_label in enumerate([('10', 10), ('100', 100), ('1000', 1000), ('ALL', -1)]):
                label, amt = amt_label
                btn = pygame.Rect(SCREEN_W // 2 - 180 + i * 85, credits_y, 75, 30)
                if btn.collidepoint(mx, my):
                    self._transfer_credits(ship, amt)
                    audio.play('pickup', 0.3)
                    return None

            # Amount buttons for ore
            ore_y = 330
            for i, amt_label in enumerate([('5', 5), ('20', 20), ('100', 100), ('ALL', -1)]):
                label, amt = amt_label
                btn = pygame.Rect(SCREEN_W // 2 - 180 + i * 85, ore_y, 75, 30)
                if btn.collidepoint(mx, my):
                    self._transfer_ore(ship, amt)
                    audio.play('pickup', 0.3)
                    return None

            # Module list (deposit: from ship, withdraw: from chest)
            mod_y_start = 400
            if self.mode == 'deposit':
                # Ship's non-core modules that can be removed
                items = [m for m in ship.modules if m.defn.id != 'core']
                for i, m in enumerate(items[self.module_scroll:self.module_scroll + 5]):
                    btn = pygame.Rect(SCREEN_W // 2 - 220, mod_y_start + i * 30, 440, 26)
                    if btn.collidepoint(mx, my):
                        # Move module from ship to chest
                        self.chest.stored_modules.append([m.defn.id, m.level])
                        ship.remove_module(m)
                        audio.play('pickup', 0.3)
                        return None
            else:
                # Chest modules
                items = self.chest.stored_modules
                for i, (mid, level) in enumerate(items[self.module_scroll:self.module_scroll + 5]):
                    btn = pygame.Rect(SCREEN_W // 2 - 220, mod_y_start + i * 30, 440, 26)
                    if btn.collidepoint(mx, my):
                        # Place module on ship (needs empty spot)
                        from game.ship import MODULE_DEFS
                        defn = MODULE_DEFS.get(mid)
                        if defn:
                            placed = False
                            for gy2 in range(ship.grid_h):
                                for gx2 in range(ship.grid_w):
                                    if ship.can_place(mid, gx2, gy2):
                                        m = ship.place_module(mid, gx2, gy2)
                                        if m:
                                            m.level = level
                                            ship._recalc_stats()
                                        placed = True
                                        break
                                if placed:
                                    break
                            if placed:
                                self.chest.stored_modules.pop(self.module_scroll + i)
                                audio.play('buy', 0.4)
                        return None

            # Close button
            close_rect = pygame.Rect(SCREEN_W // 2 - 80, SCREEN_H - 60, 160, 40)
            if close_rect.collidepoint(mx, my):
                return 'close'

        if event.type == pygame.MOUSEWHEEL:
            self.module_scroll = max(0, self.module_scroll - event.y)

        return None

    def _transfer_credits(self, ship, amount):
        if amount == -1:
            amount = ship.credits if self.mode == 'deposit' else self.chest.stored_credits
        if self.mode == 'deposit':
            amount = min(amount, ship.credits)
            ship.credits -= amount
            self.chest.stored_credits += amount
        else:
            amount = min(amount, self.chest.stored_credits)
            self.chest.stored_credits -= amount
            ship.credits += amount

    def _transfer_ore(self, ship, amount):
        if amount == -1:
            amount = ship.ore if self.mode == 'deposit' else self.chest.stored_ore
        if self.mode == 'deposit':
            amount = min(amount, ship.ore)
            ship.ore -= amount
            self.chest.stored_ore += amount
        else:
            space = ship.ore_capacity - ship.ore
            amount = min(amount, self.chest.stored_ore, space)
            self.chest.stored_ore -= amount
            ship.ore += amount

    def draw(self, surface, ship, time):
        if not self.active or not self.chest:
            return

        # Overlay
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        surface.blit(overlay, (0, 0))

        mx, my = pygame.mouse.get_pos()

        # Title
        draw_text(surface, "STORAGE CHEST", SCREEN_W // 2, 60, NEON_YELLOW, 28, center=True)

        # Mode tabs
        dep_rect = pygame.Rect(SCREEN_W // 2 - 110, 140, 100, 35)
        wd_rect = pygame.Rect(SCREEN_W // 2 + 10, 140, 100, 35)
        dep_c = NEON_GREEN if self.mode == 'deposit' else DIM_GREEN
        wd_c = NEON_ORANGE if self.mode == 'withdraw' else (80, 50, 0)
        draw_neon_rect(surface, dep_c, dep_rect, 2 if self.mode == 'deposit' else 1)
        draw_neon_rect(surface, wd_c, wd_rect, 2 if self.mode == 'withdraw' else 1)
        draw_text(surface, "DEPOSIT", dep_rect.centerx, dep_rect.centery, dep_c, 13, center=True)
        draw_text(surface, "WITHDRAW", wd_rect.centerx, wd_rect.centery, wd_c, 13, center=True)

        # Status display
        status_y = 195
        draw_text(surface, f"Ship: ${ship.credits}  |  {int(ship.ore)} ore",
                 SCREEN_W // 4, status_y, NEON_CYAN, 13, center=True)
        draw_text(surface, f"Chest: ${self.chest.stored_credits}  |  {int(self.chest.stored_ore)} ore",
                 SCREEN_W * 3 // 4, status_y, NEON_YELLOW, 13, center=True)

        # Credits section
        draw_text(surface, "CREDITS", SCREEN_W // 2, 215, NEON_YELLOW, 14, center=True)
        for i, (label, amt) in enumerate([('10', 10), ('100', 100), ('1000', 1000), ('ALL', -1)]):
            btn = pygame.Rect(SCREEN_W // 2 - 180 + i * 85, 230, 75, 30)
            hover = btn.collidepoint(mx, my)
            c = NEON_YELLOW if hover else (100, 80, 30)
            draw_neon_rect(surface, c, btn, 2 if hover else 1)
            draw_text(surface, label, btn.centerx, btn.centery, c, 14, center=True)

        # Ore section
        draw_text(surface, "ORE", SCREEN_W // 2, 315, ORE_COLOR, 14, center=True)
        for i, (label, amt) in enumerate([('5', 5), ('20', 20), ('100', 100), ('ALL', -1)]):
            btn = pygame.Rect(SCREEN_W // 2 - 180 + i * 85, 330, 75, 30)
            hover = btn.collidepoint(mx, my)
            c = ORE_COLOR if hover else (80, 55, 30)
            draw_neon_rect(surface, c, btn, 2 if hover else 1)
            draw_text(surface, label, btn.centerx, btn.centery, c, 14, center=True)

        # Direction indicator
        arrow_y = 375
        if self.mode == 'deposit':
            draw_text(surface, "DEPOSIT: Ship -> Chest", SCREEN_W // 2, arrow_y, NEON_GREEN, 12, center=True)
        else:
            draw_text(surface, "WITHDRAW: Chest -> Ship", SCREEN_W // 2, arrow_y, NEON_ORANGE, 12, center=True)

        # Modules section
        draw_text(surface, "MODULES (click to transfer)", SCREEN_W // 2, 395, NEON_CYAN, 12, center=True)
        mod_y_start = 400
        if self.mode == 'deposit':
            from game.ship import MODULE_DEFS as _MD
            items = [(m.defn.id, m.level, m.defn.name) for m in ship.modules if m.defn.id != 'core']
            if not items:
                draw_text(surface, "(no removable modules on ship)", SCREEN_W // 2, mod_y_start + 20,
                         (80, 80, 100), 10, center=True)
        else:
            from game.ship import MODULE_DEFS as _MD
            items = [(mid, lvl, _MD[mid].name if mid in _MD else mid)
                    for mid, lvl in self.chest.stored_modules]
            if not items:
                draw_text(surface, "(chest has no modules)", SCREEN_W // 2, mod_y_start + 20,
                         (80, 80, 100), 10, center=True)

        for i, (mid, level, mname) in enumerate(items[self.module_scroll:self.module_scroll + 5]):
            btn = pygame.Rect(SCREEN_W // 2 - 220, mod_y_start + i * 30, 440, 26)
            hover = btn.collidepoint(mx, my)
            c = NEON_CYAN if hover else DIM_CYAN
            draw_neon_rect(surface, c, btn, 2 if hover else 1)
            stars = " " + "*" * (level - 1) if level > 1 else ""
            label = f"{mname} (Lv.{level}){stars}"
            draw_text(surface, label, btn.x + 10, btn.y + 6, c, 12)
            if hover:
                action = "-> Chest" if self.mode == 'deposit' else "-> Ship"
                draw_text(surface, action, btn.right - 70, btn.y + 6, NEON_YELLOW, 11)

        if len(items) > 5:
            draw_text(surface, f"({self.module_scroll + 1}-{min(self.module_scroll + 5, len(items))}/{len(items)}) scroll",
                     SCREEN_W // 2, mod_y_start + 155, (80, 80, 100), 10, center=True)

        # Close button
        close_rect = pygame.Rect(SCREEN_W // 2 - 80, SCREEN_H - 60, 160, 40)
        hover = close_rect.collidepoint(mx, my)
        pulse = 0.7 + 0.3 * math.sin(time * 3)
        c = NEON_CYAN if hover else safe_color(NEON_CYAN[0] * pulse, NEON_CYAN[1] * pulse, NEON_CYAN[2] * pulse)
        draw_neon_rect(surface, c, close_rect, 2)
        draw_text(surface, "CLOSE [F/ESC]", close_rect.centerx, close_rect.centery, c, 14, center=True)
