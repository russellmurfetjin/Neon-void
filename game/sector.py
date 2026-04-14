"""Sector-based world generation: sectors, stations, POIs, patrol groups."""
import math
import random
import hashlib
import pygame
from typing import Dict, List, Optional, Tuple
from game.core import *


# ═════════════════════════════════════════════════════════════════════════════
#  STATION NAMES
# ═════════════════════════════════════════════════════════════════════════════
_PREFIXES = ["Nova", "Void", "Neon", "Iron", "Cryo", "Sol", "Astra", "Pulse",
             "Drift", "Edge", "Deep", "Flux", "Apex", "Zero", "Omega", "Vex"]
_SUFFIXES = ["Gate", "Hub", "Port", "Dock", "Core", "Base", "Post", "Keep",
             "Reach", "Hold", "Point", "Yard", "Forge", "Bay", "Spire", "Arc"]


def _sector_seed(coord: Tuple[int, int]) -> int:
    h = hashlib.md5(f"{coord[0]},{coord[1]}".encode()).hexdigest()
    return int(h[:8], 16)


def _sector_rng(coord: Tuple[int, int]) -> random.Random:
    return random.Random(_sector_seed(coord))


# ═════════════════════════════════════════════════════════════════════════════
#  STATION
# ═════════════════════════════════════════════════════════════════════════════
class Station:
    def __init__(self, x: float, y: float, name: str, station_type: str, rng: random.Random):
        self.x = x
        self.y = y
        self.name = name
        self.station_type = station_type
        self.dock_range = DOCK_RANGE

        # Pricing varies by type
        if station_type == 'fuel_depot':
            self.fuel_price = max(1, STATION_FUEL_PRICE - 1)
            self.repair_price = STATION_REPAIR_PRICE + 1
        elif station_type == 'trade_hub':
            self.fuel_price = STATION_FUEL_PRICE + 1
            self.repair_price = STATION_REPAIR_PRICE
        elif station_type == 'military':
            self.fuel_price = STATION_FUEL_PRICE
            self.repair_price = max(1, STATION_REPAIR_PRICE - 1)
        else:  # outpost
            self.fuel_price = STATION_FUEL_PRICE
            self.repair_price = STATION_REPAIR_PRICE

        # Module inventory with stock per item (exclude reward-only modules)
        from game.ship import MODULE_DEFS, REWARD_MODULES
        all_mods = [mid for mid in MODULE_DEFS if mid != 'core' and mid not in REWARD_MODULES]
        self.shop_inventory = sorted(all_mods)
        # Stock: how many of each module this station has
        self.stock: dict = {}
        for mid in all_mods:
            if station_type == 'trade_hub':
                self.stock[mid] = rng.randint(3, 6)
            elif station_type == 'military':
                # Military has more weapons
                if any(w in mid for w in ('laser', 'missile', 'gatling', 'twin', 'turret', 'autolaser')):
                    self.stock[mid] = rng.randint(3, 5)
                else:
                    self.stock[mid] = rng.randint(1, 3)
            elif station_type == 'fuel_depot':
                if 'fuel' in mid or 'engine' in mid:
                    self.stock[mid] = rng.randint(3, 5)
                else:
                    self.stock[mid] = rng.randint(1, 2)
            else:  # outpost
                self.stock[mid] = rng.randint(1, 3)
        # Research Center always in stock at every station
        if 'research' in self.stock:
            self.stock['research'] = max(self.stock['research'], 1)

        # Visual
        self.rotation = 0.0
        self.ring_anim = 0.0

    def update(self, dt):
        self.rotation += dt * 0.2
        self.ring_anim += dt

    def draw(self, surface, camera, time):
        sx, sy = camera.world_to_screen(self.x, self.y)
        z = camera.zoom

        # Outer ring
        ring_r = (50 + math.sin(self.ring_anim * 0.5) * 3) * z
        ring_alpha = int(40 + 20 * math.sin(time * 2))
        ring_surf = pygame.Surface((int(ring_r * 2 + 4), int(ring_r * 2 + 4)), pygame.SRCALPHA)
        pygame.draw.circle(ring_surf, (*NEON_CYAN[:3], ring_alpha),
                         (int(ring_r + 2), int(ring_r + 2)), int(ring_r), 2)
        surface.blit(ring_surf, (int(sx - ring_r - 2), int(sy - ring_r - 2)),
                    special_flags=pygame.BLEND_ADD)

        # Station body (hexagonal)
        r = 28 * z
        pts = []
        for i in range(6):
            angle = self.rotation + i * math.pi / 3
            pts.append((sx + math.cos(angle) * r, sy + math.sin(angle) * r))
        pygame.draw.polygon(surface, (30, 40, 60), pts)
        pygame.draw.polygon(surface, NEON_CYAN, pts, 2)

        # Inner structure
        r2 = 14 * z
        pts2 = []
        for i in range(6):
            angle = -self.rotation * 1.5 + i * math.pi / 3
            pts2.append((sx + math.cos(angle) * r2, sy + math.sin(angle) * r2))
        pygame.draw.polygon(surface, (40, 55, 80), pts2)
        pygame.draw.polygon(surface, NEON_BLUE, pts2, 1)

        # Center glow
        draw_glow_circle(surface, NEON_CYAN, (sx, sy), 5, 18, 50)

        # Label
        draw_text(surface, self.name, int(sx), int(sy - ring_r - 14),
                 NEON_CYAN, 11, center=True)

        # Dock range indicator
        dock_surf = pygame.Surface((int(self.dock_range * 2 + 4), int(self.dock_range * 2 + 4)), pygame.SRCALPHA)
        pygame.draw.circle(dock_surf, (0, 255, 255, 12),
                         (int(self.dock_range + 2), int(self.dock_range + 2)), int(self.dock_range), 1)
        surface.blit(dock_surf, (int(sx - self.dock_range - 2), int(sy - self.dock_range - 2)),
                    special_flags=pygame.BLEND_ADD)

    def can_dock(self, ship_x, ship_y):
        return dist(self.x, self.y, ship_x, ship_y) < self.dock_range


# ═════════════════════════════════════════════════════════════════════════════
#  POINT OF INTEREST
# ═════════════════════════════════════════════════════════════════════════════
class POI:
    def __init__(self, x: float, y: float, poi_type: str, rng: random.Random):
        self.x = x
        self.y = y
        self.poi_type = poi_type
        self.discovered = False
        self.looted = False
        self.researched = False
        self.research_progress = 0.0
        self.reward_module = None
        self.interaction_range = 60.0

        # Type-specific data
        if poi_type == 'derelict':
            self.loot_credits = rng.randint(80, 250)
            self.loot_fuel = rng.randint(10, 40)
            self.has_ambush = rng.random() < 0.35
            self.color = (120, 100, 60)
            self.label = "Derelict Ship"
        elif poi_type == 'cache':
            self.loot_credits = rng.randint(30, 120)
            self.loot_fuel = rng.randint(5, 25)
            self.has_ambush = False
            self.color = NEON_YELLOW
            self.label = "Supply Cache"
        elif poi_type == 'anomaly':
            self.loot_credits = 0
            self.loot_fuel = 0
            self.has_ambush = False
            self.color = NEON_PURPLE
            self.label = "Anomaly"
            self.effect_radius = 200
            self.effect = rng.choice(['refinery_boost', 'ore_boost', 'fuel_drain'])
            from game.ship import REWARD_MODULES
            self.reward_module = rng.choice(REWARD_MODULES)
            self.researched = False
            self.research_progress = 0.0
        elif poi_type == 'signal':
            self.loot_credits = rng.randint(50, 200)
            self.loot_fuel = rng.randint(0, 20)
            self.has_ambush = rng.random() < 0.5
            self.color = NEON_GREEN
            self.label = "Signal Source"
        else:
            self.color = DIM_CYAN
            self.label = "Unknown"
            self.loot_credits = 0
            self.loot_fuel = 0
            self.has_ambush = False

    def draw(self, surface, camera, time):
        if self.looted and self.poi_type != 'anomaly':
            return
        sx, sy = camera.world_to_screen(self.x, self.y)

        if not self.discovered:
            # Unknown blip
            pulse = 0.3 + 0.3 * math.sin(time * 2)
            draw_glow_circle(surface, (60, 60, 80), (sx, sy), 3, 10, int(30 * pulse))
            return

        pulse = 0.5 + 0.5 * math.sin(time * 3)

        if self.poi_type == 'derelict':
            # Broken ship outline
            r = 12
            pts = [
                (sx + r, sy), (sx + r * 0.3, sy - r * 0.6),
                (sx - r * 0.8, sy - r * 0.3), (sx - r * 0.5, sy + r * 0.4),
                (sx + r * 0.2, sy + r * 0.5),
            ]
            pygame.draw.polygon(surface, (50, 40, 25), pts)
            pygame.draw.polygon(surface, self.color, pts, 1)
        elif self.poi_type == 'cache':
            # Crate
            pygame.draw.rect(surface, (60, 55, 20), (int(sx - 8), int(sy - 8), 16, 16))
            pygame.draw.rect(surface, self.color, (int(sx - 8), int(sy - 8), 16, 16), 1)
        elif self.poi_type == 'anomaly':
            # Swirling energy
            r = 20 + math.sin(time * 2) * 5
            glow_surf = pygame.Surface((int(r * 4), int(r * 4)), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*self.color[:3], int(25 * pulse)),
                             (int(r * 2), int(r * 2)), int(r))
            surface.blit(glow_surf, (int(sx - r * 2), int(sy - r * 2)),
                        special_flags=pygame.BLEND_ADD)
            pygame.draw.circle(surface, self.color, (int(sx), int(sy)), int(r * 0.4), 2)
        elif self.poi_type == 'signal':
            # Radio waves
            for i in range(3):
                wave_r = 8 + i * 8 + math.sin(time * 3 + i) * 3
                alpha = int(60 * pulse / (i + 1))
                wave_surf = pygame.Surface((int(wave_r * 2 + 4), int(wave_r * 2 + 4)), pygame.SRCALPHA)
                pygame.draw.circle(wave_surf, (*self.color[:3], alpha),
                                 (int(wave_r + 2), int(wave_r + 2)), int(wave_r), 1)
                surface.blit(wave_surf, (int(sx - wave_r - 2), int(sy - wave_r - 2)),
                            special_flags=pygame.BLEND_ADD)
            draw_glow_circle(surface, self.color, (sx, sy), 3, 8, 50)

        # Label
        if not self.looted:
            draw_text(surface, self.label, int(sx), int(sy - 20),
                     self.color, 9, center=True)


# ═════════════════════════════════════════════════════════════════════════════
#  PATROL GROUP (enemy spawn definition within a sector)
# ═════════════════════════════════════════════════════════════════════════════
class PatrolGroup:
    def __init__(self, cx: float, cy: float, count: int, tier: int, is_boss: bool = False):
        self.cx = cx      # patrol center (world coords)
        self.cy = cy
        self.count = count
        self.tier = tier
        self.is_boss = is_boss
        self.spawned = False
        self.cleared = False
        self.clear_time = 0.0  # game time when cleared

    @property
    def patrol_radius(self):
        return 200


# ═════════════════════════════════════════════════════════════════════════════
#  SECTOR
# ═════════════════════════════════════════════════════════════════════════════
SECTOR_TYPES = ['empty', 'asteroid_field', 'nebula', 'pirate_territory', 'station', 'derelict_field']

class Sector:
    def __init__(self, coord: Tuple[int, int]):
        self.coord = coord
        self.seed = _sector_seed(coord)
        self.rng = _sector_rng(coord)

        self.threat_level = min(5, (abs(coord[0]) + abs(coord[1])) // 2)
        self.discovered = False
        self.generated = False

        # Content (populated by generate())
        self.sector_type = 'empty'
        self.station: Optional[Station] = None
        self.pois: List[POI] = []
        self.patrol_groups: List[PatrolGroup] = []
        self.asteroid_data: List[dict] = []  # serialized asteroid info for regeneration

        # Determine sector type
        self._determine_type()

    def _determine_type(self):
        rng = self.rng
        cx, cy = self.coord

        # Origin is always a station
        if cx == 0 and cy == 0:
            self.sector_type = 'station'
            return

        # Void Titan lair — fixed location, the goal of the game
        if cx == 6 and cy == -4:
            self.sector_type = 'pirate_territory'
            self.threat_level = 5
            return

        # Stations appear in a pattern: roughly every 4-5 sectors, guaranteed reachable
        station_hash = (abs(cx) + abs(cy) * 7 + self.seed) % 13
        if station_hash < 3:
            self.sector_type = 'station'
            return

        # Other types based on seed
        roll = rng.random()
        if roll < 0.25:
            self.sector_type = 'asteroid_field'
        elif roll < 0.40:
            self.sector_type = 'pirate_territory'
        elif roll < 0.55:
            self.sector_type = 'nebula'
        elif roll < 0.65:
            self.sector_type = 'derelict_field'
        else:
            self.sector_type = 'empty'

    @property
    def world_origin(self) -> Tuple[float, float]:
        """Top-left corner of this sector in world coordinates."""
        return self.coord[0] * SECTOR_SIZE, self.coord[1] * SECTOR_SIZE

    @property
    def world_center(self) -> Tuple[float, float]:
        ox, oy = self.world_origin
        return ox + SECTOR_SIZE / 2, oy + SECTOR_SIZE / 2

    def generate(self):
        """Generate all content for this sector."""
        if self.generated:
            return
        self.generated = True
        rng = _sector_rng(self.coord)  # fresh rng for deterministic regeneration
        ox, oy = self.world_origin

        # Station
        if self.sector_type == 'station':
            name_prefix = rng.choice(_PREFIXES)
            name_suffix = rng.choice(_SUFFIXES)
            name = f"{name_prefix} {name_suffix}"
            stype = rng.choice(['trade_hub', 'outpost', 'fuel_depot', 'military'])
            if self.coord == (0, 0):
                stype = 'trade_hub'
                name = "Home Station"
            sx = ox + SECTOR_SIZE / 2 + rng.uniform(-200, 200)
            sy = oy + SECTOR_SIZE / 2 + rng.uniform(-200, 200)
            self.station = Station(sx, sy, name, stype, rng)

        # Asteroids
        if self.sector_type == 'asteroid_field':
            count = rng.randint(25, 45)
        elif self.sector_type == 'nebula':
            count = rng.randint(3, 8)
        elif self.sector_type == 'derelict_field':
            count = rng.randint(8, 15)
        elif self.sector_type == 'station':
            count = rng.randint(3, 8)
        elif self.sector_type == 'pirate_territory':
            count = rng.randint(5, 12)
        else:
            count = rng.randint(5, 15)

        self.asteroid_data = []
        for _ in range(count):
            ax = ox + rng.uniform(100, SECTOR_SIZE - 100)
            ay = oy + rng.uniform(100, SECTOR_SIZE - 100)
            self.asteroid_data.append({'x': ax, 'y': ay})

        # Patrol groups
        if self.sector_type == 'pirate_territory':
            n_patrols = rng.randint(4, 7 + self.threat_level)
        elif self.sector_type in ('empty', 'asteroid_field', 'nebula'):
            n_patrols = rng.randint(1, 3 + self.threat_level)
        elif self.sector_type == 'derelict_field':
            n_patrols = rng.randint(2, 4 + self.threat_level)
        elif self.sector_type == 'station':
            n_patrols = 0  # stations are safe
        else:
            n_patrols = rng.randint(0, 2)

        tier = max(1, self.threat_level)
        for _ in range(n_patrols):
            px = ox + rng.uniform(200, SECTOR_SIZE - 200)
            py = oy + rng.uniform(200, SECTOR_SIZE - 200)
            count = rng.randint(2, 3 + self.threat_level)
            self.patrol_groups.append(PatrolGroup(px, py, count, tier))

        # Boss patrol in high-threat non-station sectors
        if self.threat_level >= 3 and self.sector_type != 'station' and rng.random() < 0.3:
            px = ox + rng.uniform(300, SECTOR_SIZE - 300)
            py = oy + rng.uniform(300, SECTOR_SIZE - 300)
            self.patrol_groups.append(PatrolGroup(px, py, 2 + self.threat_level, tier, is_boss=True))

        # Void Titan — the final boss, the goal of the game
        if self.coord == (6, -4):
            cx_w = ox + SECTOR_SIZE / 2
            cy_w = oy + SECTOR_SIZE / 2
            self.patrol_groups.append(PatrolGroup(cx_w, cy_w, 8, 6, is_boss=True))
            self.pois.append(POI(cx_w, cy_w - 200, 'signal', rng))

        # POIs
        if self.sector_type == 'derelict_field':
            for _ in range(rng.randint(2, 4)):
                px = ox + rng.uniform(200, SECTOR_SIZE - 200)
                py = oy + rng.uniform(200, SECTOR_SIZE - 200)
                self.pois.append(POI(px, py, 'derelict', rng))
        elif self.sector_type == 'nebula':
            px = ox + rng.uniform(300, SECTOR_SIZE - 300)
            py = oy + rng.uniform(300, SECTOR_SIZE - 300)
            self.pois.append(POI(px, py, 'anomaly', rng))

        # Random POIs in any sector
        if rng.random() < 0.4:
            px = ox + rng.uniform(200, SECTOR_SIZE - 200)
            py = oy + rng.uniform(200, SECTOR_SIZE - 200)
            poi_type = rng.choice(['cache', 'signal', 'derelict'])
            self.pois.append(POI(px, py, poi_type, rng))


# ═════════════════════════════════════════════════════════════════════════════
#  SECTOR MANAGER
# ═════════════════════════════════════════════════════════════════════════════
class SectorManager:
    def __init__(self):
        self.loaded: Dict[Tuple[int, int], Sector] = {}
        self.discovered: set = set()  # persistent across loads
        self.current_coord = (0, 0)
        self.farthest_distance = 0

    def get_sector_coord(self, world_x: float, world_y: float) -> Tuple[int, int]:
        return (int(math.floor(world_x / SECTOR_SIZE)),
                int(math.floor(world_y / SECTOR_SIZE)))

    def get_sector(self, coord: Tuple[int, int]) -> Sector:
        if coord not in self.loaded:
            s = Sector(coord)
            s.generate()
            if coord in self.discovered:
                s.discovered = True
            self.loaded[coord] = s
        return self.loaded[coord]

    def update_streaming(self, ship_x: float, ship_y: float, game_time: float):
        """Load sectors around the player, unload distant ones."""
        new_coord = self.get_sector_coord(ship_x, ship_y)
        self.current_coord = new_coord

        # Track discovery
        d = abs(new_coord[0]) + abs(new_coord[1])
        self.farthest_distance = max(self.farthest_distance, d)

        # Discover current sector
        if new_coord not in self.discovered:
            self.discovered.add(new_coord)
            if new_coord in self.loaded:
                self.loaded[new_coord].discovered = True

        # Load 3x3 around player
        needed = set()
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                c = (new_coord[0] + dx, new_coord[1] + dy)
                needed.add(c)
                self.get_sector(c)  # ensure loaded

        # Unload sectors outside 5x5
        to_unload = []
        for coord in self.loaded:
            if (abs(coord[0] - new_coord[0]) > 2 or
                abs(coord[1] - new_coord[1]) > 2):
                to_unload.append(coord)
        for coord in to_unload:
            # Mark patrol clear times before unloading
            sector = self.loaded[coord]
            for pg in sector.patrol_groups:
                if pg.cleared:
                    pg.clear_time = game_time
            del self.loaded[coord]

        return needed

    def get_loaded_sectors(self) -> List[Sector]:
        return list(self.loaded.values())

    def get_current_sector(self) -> Sector:
        return self.get_sector(self.current_coord)

    def find_nearest_station(self, world_x: float, world_y: float) -> Optional[Station]:
        """Find nearest station across loaded sectors."""
        best = None
        best_d = float('inf')
        for sector in self.loaded.values():
            if sector.station:
                d = dist(world_x, world_y, sector.station.x, sector.station.y)
                if d < best_d:
                    best_d = d
                    best = sector.station
        return best

    def find_nearest_station_direction(self, world_x: float, world_y: float) -> Optional[Tuple[float, float, float]]:
        """Returns (angle, distance, name) to nearest known station."""
        best = None
        best_d = float('inf')
        # Check discovered sectors for stations
        for coord in self.discovered:
            sector = self.loaded.get(coord)
            if sector and sector.station:
                d = dist(world_x, world_y, sector.station.x, sector.station.y)
                if d < best_d:
                    best_d = d
                    best = sector.station
        # Also check all loaded
        for sector in self.loaded.values():
            if sector.station:
                d = dist(world_x, world_y, sector.station.x, sector.station.y)
                if d < best_d:
                    best_d = d
                    best = sector.station
        if best:
            angle = angle_to(world_x, world_y, best.x, best.y)
            return angle, best_d, best.name
        return None
