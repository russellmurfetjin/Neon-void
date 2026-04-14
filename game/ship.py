"""Ship grid system, module definitions, and resource management."""
import pygame
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from game.core import *


# ═════════════════════════════════════════════════════════════════════════════
#  MODULE DEFINITIONS
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class ModuleDef:
    name: str
    id: str
    width: int          # grid cells
    height: int
    color: Tuple[int, int, int]
    glow_color: Tuple[int, int, int]
    cost: int
    description: str
    hp: int = 20
    # gameplay stats (module-specific)
    thrust: float = 0.0
    fuel_capacity: float = 0.0
    ore_capacity: float = 0.0
    refinery_rate: float = 0.0
    damage: float = 0.0
    fire_rate: float = 0.0
    shield_hp: float = 0.0
    shield_regen: float = 0.0
    armor: float = 0.0
    hull_regen: float = 0.0
    probe_count: int = 0


MODULE_DEFS: Dict[str, ModuleDef] = {}

def _reg(m: ModuleDef):
    MODULE_DEFS[m.id] = m

# Core (cannot remove)
_reg(ModuleDef("Ship Core", "core", 2, 2, (60, 80, 120), NEON_CYAN, 0,
               "The heart of your ship. Provides basic systems.", hp=100))

# Engines
_reg(ModuleDef("Ion Engine", "engine_1", 1, 1, (80, 60, 30), NEON_ORANGE, 50,
               "Basic thruster. +100 thrust.", thrust=100.0))
_reg(ModuleDef("Plasma Drive", "engine_2", 1, 2, (120, 80, 20), NEON_YELLOW, 200,
               "Advanced engine. +250 thrust.", thrust=250.0))

# Fuel
_reg(ModuleDef("Fuel Tank", "fuel_tank", 1, 1, (60, 50, 20), NEON_ORANGE, 40,
               "Stores 50 fuel.", fuel_capacity=50.0))
_reg(ModuleDef("Large Fuel Tank", "fuel_tank_lg", 2, 1, (80, 60, 20), NEON_ORANGE, 120,
               "Stores 150 fuel.", fuel_capacity=150.0))

# Ore Storage
_reg(ModuleDef("Ore Hold", "ore_hold", 1, 1, (70, 50, 30), ORE_COLOR, 35,
               "Stores 40 raw ore.", ore_capacity=40.0))
_reg(ModuleDef("Large Ore Hold", "ore_hold_lg", 2, 1, (90, 65, 35), ORE_COLOR, 100,
               "Stores 120 raw ore.", ore_capacity=120.0))

# Refinery
_reg(ModuleDef("Basic Refinery", "refinery_1", 1, 2, (50, 70, 60), NEON_GREEN, 150,
               "Converts raw ore to fuel. 5/sec.", refinery_rate=5.0))
_reg(ModuleDef("Advanced Refinery", "refinery_2", 2, 2, (60, 90, 70), NEON_GREEN, 400,
               "Fast ore-to-fuel conversion. 15/sec.", refinery_rate=15.0))

# Weapons — Guns (LMB, fire projectiles at mouse)
_reg(ModuleDef("Gatling Gun", "gatling_1", 1, 1, (70, 70, 30), NEON_YELLOW, 45,
               "Rapid-fire bullets. 5 dmg, very fast.", damage=5, fire_rate=8.0))
_reg(ModuleDef("Twin Guns", "twin_gun", 1, 1, (90, 80, 30), NEON_ORANGE, 120,
               "Dual cannons. 9 dmg each, fast.", damage=9, fire_rate=5.0))

# Weapons — Lasers (RMB, piercing beam)
_reg(ModuleDef("Laser Turret", "laser_1", 1, 1, (80, 30, 30), NEON_RED, 80,
               "Piercing beam. 8 dmg. RMB to fire.", damage=LASER_DAMAGE, fire_rate=1 / LASER_COOLDOWN))
_reg(ModuleDef("Twin Laser", "laser_2", 1, 1, (100, 40, 40), NEON_PINK, 200,
               "Heavy beam. 14 dmg. RMB to fire.", damage=14, fire_rate=1 / 0.25))

# Weapons — Missiles (MMB, homing projectiles)
_reg(ModuleDef("Missile Pod", "missile_1", 1, 2, (60, 60, 80), NEON_PURPLE, 250,
               "Homing missiles. 35 dmg. MMB to fire.", damage=MISSILE_DAMAGE, fire_rate=1 / MISSILE_COOLDOWN))

# Weapons — Auto-turrets (automatic, targets nearest enemy)
_reg(ModuleDef("Auto-Turret", "turret_1", 1, 1, (50, 80, 50), NEON_GREEN, 100,
               "Auto-fires at nearest enemy. Stackable!", damage=6, fire_rate=3.0))
_reg(ModuleDef("Heavy Turret", "turret_2", 1, 1, (60, 100, 60), (100, 255, 100), 280,
               "Strong auto-turret. 12 dmg. Stackable!", damage=12, fire_rate=2.0))

# Weapons — Auto-laser (automatic beam, weaker than manual laser)
_reg(ModuleDef("Mini Laser", "autolaser_1", 1, 1, (70, 25, 25), (255, 80, 80), 130,
               "Auto-fires a small beam at nearest enemy. Stackable!", damage=4, fire_rate=1.5))

# Defense
_reg(ModuleDef("Shield Generator", "shield_1", 1, 1, (30, 50, 80), NEON_BLUE, 120,
               "Energy shield. +40 HP, regens.", shield_hp=40.0, shield_regen=3.0))
_reg(ModuleDef("Heavy Shield", "shield_2", 2, 1, (40, 60, 100), NEON_CYAN, 350,
               "Powerful shield. +100 HP, fast regen.", shield_hp=100.0, shield_regen=8.0))
_reg(ModuleDef("Armor Plate", "armor_1", 1, 1, (70, 70, 70), (150, 150, 150), 45,
               "Reinforced hull. +15 armor.", armor=15.0, hp=40))

# Repair / Healing
_reg(ModuleDef("Repair Drone", "repair_1", 1, 1, (40, 80, 40), NEON_GREEN, 150,
               "Slowly repairs hull. +2 HP/sec. Stackable!", hull_regen=2.0))
_reg(ModuleDef("Nano Repair Bay", "repair_2", 1, 2, (50, 100, 50), (100, 255, 100), 400,
               "Advanced repair system. +6 HP/sec.", hull_regen=6.0))
_reg(ModuleDef("Emergency Kit", "repair_3", 1, 1, (80, 60, 30), NEON_ORANGE, 90,
               "Boosts max hull by 30 and repairs 1 HP/sec.", hp=30, hull_regen=1.0))

# Probe
_reg(ModuleDef("Probe Bay", "probe_bay", 1, 1, (50, 60, 50), NEON_GREEN, 80,
               "Launches mining probes. 2 probes.", probe_count=2))
_reg(ModuleDef("Adv. Probe Bay", "probe_bay_2", 2, 1, (60, 80, 60), NEON_GREEN, 220,
               "Advanced probe bay. 5 probes.", probe_count=5))

# Research
_reg(ModuleDef("Research Center", "research", 2, 2, (80, 50, 100), NEON_PURPLE, 500,
               "Research anomalies for unique modules. Fly near one and press F.", hp=30))

# ── ANOMALY REWARD MODULES (not sold in shops, only from research) ───────
_reg(ModuleDef("Void Engine", "reward_engine", 1, 1, (100, 50, 150), (200, 100, 255), 0,
               "Anomaly tech. +200 thrust in a tiny 1x1!", thrust=200.0))
_reg(ModuleDef("Plasma Lance", "reward_autolaser", 1, 1, (150, 50, 50), (255, 100, 100), 0,
               "Anomaly tech. Piercing auto-beam. 18 dmg, fast.", damage=18, fire_rate=2.5))
_reg(ModuleDef("Phase Shield", "reward_shield", 1, 1, (50, 50, 150), (100, 100, 255), 0,
               "Anomaly tech. +80 shield, 6/s regen in 1x1!", shield_hp=80.0, shield_regen=6.0))
_reg(ModuleDef("Nano Swarm", "reward_repair", 1, 1, (50, 150, 50), (100, 255, 100), 0,
               "Anomaly tech. Repairs 8 HP/sec in 1x1!", hull_regen=8.0))
_reg(ModuleDef("Singularity Core", "reward_all", 2, 2, (150, 100, 200), (220, 160, 255), 0,
               "Anomaly tech. +150 thrust, +50 shield, 3 HP/s, 15 armor.",
               thrust=150.0, shield_hp=50.0, shield_regen=3.0, hull_regen=3.0, armor=15.0, hp=50))

REWARD_MODULES = ['reward_engine', 'reward_autolaser', 'reward_shield', 'reward_repair', 'reward_all']


# ═════════════════════════════════════════════════════════════════════════════
#  PLACED MODULE (instance on grid)
# ═════════════════════════════════════════════════════════════════════════════
class PlacedModule:
    def __init__(self, defn: ModuleDef, gx: int, gy: int):
        self.defn = defn
        self.gx = gx
        self.gy = gy
        self.level = 1  # 1-5, upgraded at stations
        self.hp = defn.hp
        self.max_hp = defn.hp
        self.cooldown = 0.0
        self.active = True
        self.anim_time = 0.0

    @property
    def id(self):
        return self.defn.id

    @property
    def mult(self):
        """Stat multiplier based on level. Lvl1=1.0, Lvl2=1.3, Lvl5=2.2"""
        return 1.0 + 0.3 * (self.level - 1)

    @property
    def thrust(self): return self.defn.thrust * self.mult
    @property
    def fuel_capacity(self): return self.defn.fuel_capacity * self.mult
    @property
    def ore_capacity(self): return self.defn.ore_capacity * self.mult
    @property
    def refinery_rate(self): return self.defn.refinery_rate * self.mult
    @property
    def damage(self): return self.defn.damage * self.mult
    @property
    def fire_rate(self): return self.defn.fire_rate * (1.0 + 0.15 * (self.level - 1))
    @property
    def shield_hp(self): return self.defn.shield_hp * self.mult
    @property
    def shield_regen(self): return self.defn.shield_regen * self.mult
    @property
    def armor(self): return self.defn.armor * self.mult
    @property
    def hull_regen(self): return self.defn.hull_regen * self.mult
    @property
    def probe_count(self): return self.defn.probe_count + (self.level - 1)  # +1 probe per level

    def upgrade_cost(self):
        if self.level >= 5:
            return 0
        return int(self.defn.cost * (0.7 + 0.3 * self.level))

    def cells(self):
        for dx in range(self.defn.width):
            for dy in range(self.defn.height):
                yield self.gx + dx, self.gy + dy


# ═════════════════════════════════════════════════════════════════════════════
#  SHIP (player ship with grid)
# ═════════════════════════════════════════════════════════════════════════════
INITIAL_GRID_W = 5
INITIAL_GRID_H = 5
EXPAND_COST = 200

class Ship:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 0.0  # visual angle (faces mouse)

        # Grid
        self.grid_w = INITIAL_GRID_W
        self.grid_h = INITIAL_GRID_H
        self.modules: List[PlacedModule] = []

        # Resources
        self.fuel = STARTING_FUEL
        self.ore = 0.0
        self.credits = STARTING_CREDITS

        # Combat
        self.shield = 0.0
        self.max_shield = 0.0
        self.shield_regen = 0.0

        # Probes
        self.max_probes = 0
        self.active_probes = 0
        self.refinery_enabled = True

        # State
        self.alive = True
        self.docked = False
        self.invuln_timer = 2.0  # brief invulnerability at start
        self.boost = False
        self.engine_anim = 0.0
        self.sectors_discovered = 0
        self.farthest_sector = 0
        self.distress_charging = False
        self.distress_timer = 0.0
        self.distress_cooldown = 0.0
        self.skin = 'default'  # 'default', 'arrowhead', 'battleship', 'stealth', 'raptor'

        # Place default modules
        self._place_defaults()

    def _place_defaults(self):
        self.place_module("core", 1, 1)
        self.place_module("engine_1", 2, 3)
        self.place_module("gatling_1", 0, 1)
        self.place_module("fuel_tank", 4, 1)
        self.place_module("ore_hold", 4, 2)
        self.place_module("probe_bay", 0, 2)

    def cell_occupied(self, gx, gy, exclude=None):
        for m in self.modules:
            if m is exclude:
                continue
            for cx, cy in m.cells():
                if cx == gx and cy == gy:
                    return m
        return None

    def can_place(self, mod_id, gx, gy, exclude=None):
        defn = MODULE_DEFS[mod_id]
        for dx in range(defn.width):
            for dy in range(defn.height):
                cx, cy = gx + dx, gy + dy
                if cx < 0 or cx >= self.grid_w or cy < 0 or cy >= self.grid_h:
                    return False
                if self.cell_occupied(cx, cy, exclude):
                    return False
        return True

    def place_module(self, mod_id, gx, gy) -> Optional[PlacedModule]:
        if not self.can_place(mod_id, gx, gy):
            return None
        m = PlacedModule(MODULE_DEFS[mod_id], gx, gy)
        self.modules.append(m)
        self._recalc_stats()
        return m

    def remove_module(self, module: PlacedModule):
        if module.defn.id == "core":
            return False
        self.modules.remove(module)
        self._recalc_stats()
        return True

    def expand_grid(self, direction: str) -> bool:
        """Expand grid by 1 row/column. direction: 'up','down','left','right'"""
        if self.credits < EXPAND_COST:
            return False
        self.credits -= EXPAND_COST
        if direction == 'right':
            self.grid_w += 1
        elif direction == 'left':
            self.grid_w += 1
            for m in self.modules:
                m.gx += 1
        elif direction == 'down':
            self.grid_h += 1
        elif direction == 'up':
            self.grid_h += 1
            for m in self.modules:
                m.gy += 1
        self._recalc_stats()
        return True

    def can_shrink(self, direction: str) -> bool:
        """Check if a row/column can be removed (no modules in it, grid > 3x3)."""
        if self.grid_w <= 3 or self.grid_h <= 3:
            if direction in ('left', 'right') and self.grid_w <= 3:
                return False
            if direction in ('up', 'down') and self.grid_h <= 3:
                return False
        for m in self.modules:
            for cx, cy in m.cells():
                if direction == 'right' and cx == self.grid_w - 1:
                    return False
                if direction == 'left' and cx == 0:
                    return False
                if direction == 'down' and cy == self.grid_h - 1:
                    return False
                if direction == 'up' and cy == 0:
                    return False
        return True

    def shrink_grid(self, direction: str) -> bool:
        """Remove a row/column. Returns True if successful."""
        if not self.can_shrink(direction):
            return False
        # Refund half the expand cost
        self.credits += EXPAND_COST // 2
        if direction == 'right':
            self.grid_w -= 1
        elif direction == 'left':
            self.grid_w -= 1
            for m in self.modules:
                m.gx -= 1
        elif direction == 'down':
            self.grid_h -= 1
        elif direction == 'up':
            self.grid_h -= 1
            for m in self.modules:
                m.gy -= 1
        self._recalc_stats()
        return True

    def _recalc_stats(self):
        self.max_shield = 0
        self.shield_regen = 0
        self.max_probes = 0
        for m in self.modules:
            if not m.active:
                continue
            self.max_shield += m.shield_hp
            self.shield_regen += m.shield_regen
            self.max_probes += m.probe_count
        self.shield = min(self.shield, self.max_shield)

    @property
    def total_thrust(self):
        return PLAYER_THRUST + sum(m.thrust for m in self.modules if m.active)

    @property
    def fuel_capacity(self):
        return sum(m.fuel_capacity for m in self.modules if m.active)

    @property
    def ore_capacity(self):
        return sum(m.ore_capacity for m in self.modules if m.active)

    @property
    def refinery_rate(self):
        return sum(m.refinery_rate for m in self.modules if m.active)

    @property
    def total_armor(self):
        return sum(m.armor for m in self.modules if m.active)

    @property
    def total_hull_regen(self):
        return sum(m.hull_regen for m in self.modules if m.active)

    @property
    def core_hp(self):
        for m in self.modules:
            if m.defn.id == "core":
                return m.hp
        return 0

    @property
    def core_max_hp(self):
        for m in self.modules:
            if m.defn.id == "core":
                return m.max_hp
        return 0

    @property
    def weapon_modules(self):
        return [m for m in self.modules if m.active and m.defn.damage > 0]

    @property
    def gun_modules(self):
        """Gatling/Twin guns — LMB projectile weapons."""
        return [m for m in self.modules if m.active and m.defn.damage > 0
                and ('gatling' in m.defn.id or 'twin_gun' in m.defn.id)]

    @property
    def laser_modules(self):
        """Laser turrets — RMB beam weapons (not auto-lasers)."""
        return [m for m in self.modules if m.active and m.defn.damage > 0
                and m.defn.id.startswith('laser')]

    @property
    def missile_modules(self):
        """Missile pods — MMB homing weapons."""
        return [m for m in self.modules if m.active and m.defn.damage > 0
                and 'missile' in m.defn.id]

    @property
    def turret_modules(self):
        """Auto-turrets — fire automatically at nearest enemy."""
        return [m for m in self.modules if m.active and m.defn.damage > 0
                and 'turret' in m.defn.id]

    @property
    def autolaser_modules(self):
        """Mini auto-lasers — fire short beams at nearest enemy."""
        return [m for m in self.modules if m.active and m.defn.damage > 0
                and 'autolaser' in m.defn.id]

    def take_damage(self, amount):
        amount -= self.total_armor * 0.3
        amount = max(1, amount)
        if self.shield > 0:
            absorbed = min(self.shield, amount)
            self.shield -= absorbed
            amount -= absorbed
        if amount > 0:
            core = next((m for m in self.modules if m.defn.id == "core"), None)
            if core:
                core.hp -= amount
                if core.hp <= 0:
                    self.alive = False

    @property
    def fuel_range(self):
        """Estimate how far (in world units) the ship can travel on current fuel."""
        if FUEL_DRAIN_RATE <= 0:
            return float('inf')
        travel_time = self.fuel / FUEL_DRAIN_RATE
        avg_speed = min(self.total_thrust * 0.5, PLAYER_MAX_SPEED * 0.6)
        return travel_time * avg_speed

    @property
    def fuel_range_sectors(self):
        return self.fuel_range / SECTOR_SIZE

    def update(self, dt, keys, mouse_world_x, mouse_world_y):
        if not self.alive or self.docked:
            return

        self.invuln_timer = max(0, self.invuln_timer - dt)
        self.engine_anim += dt

        # Facing
        self.angle = angle_to(self.x, self.y, mouse_world_x, mouse_world_y)

        # Input
        thrust_x, thrust_y = 0, 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            thrust_y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            thrust_y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            thrust_x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            thrust_x += 1

        self.boost = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]

        # Apply thrust
        mag = math.sqrt(thrust_x ** 2 + thrust_y ** 2)
        if mag > 0:
            thrust_x /= mag
            thrust_y /= mag
            if self.fuel > 0:
                thrust = self.total_thrust
                if self.boost:
                    thrust *= PLAYER_BOOST_MULT
            else:
                # Emergency thrusters — slow but never locked out
                thrust = PLAYER_THRUST * 0.15
                self.boost = False
            self.vx += thrust_x * thrust * dt
            self.vy += thrust_y * thrust * dt

            drain = FUEL_BOOST_DRAIN if self.boost else FUEL_DRAIN_RATE
            self.fuel = max(0, self.fuel - drain * dt)

        # Drag
        self.vx *= PLAYER_DRAG
        self.vy *= PLAYER_DRAG

        # Speed cap
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        max_spd = PLAYER_MAX_SPEED * (PLAYER_BOOST_MULT if self.boost else 1.0)
        if speed > max_spd:
            self.vx = self.vx / speed * max_spd
            self.vy = self.vy / speed * max_spd

        # Position (no world bounds - infinite exploration)
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Shield regen
        if self.shield < self.max_shield:
            self.shield = min(self.max_shield, self.shield + self.shield_regen * dt)

        # Hull regen (from repair modules)
        if self.total_hull_regen > 0:
            core = next((m for m in self.modules if m.defn.id == "core"), None)
            if core and core.hp < core.max_hp:
                core.hp = min(core.max_hp, core.hp + self.total_hull_regen * dt)

        # Refinery: convert ore -> fuel (toggleable with R)
        if self.refinery_enabled and self.ore > 0 and self.fuel < self.fuel_capacity:
            convert = min(self.refinery_rate * dt, self.ore, self.fuel_capacity - self.fuel)
            self.ore -= convert
            self.fuel += convert

        # Weapon cooldowns
        for m in self.modules:
            if m.defn.damage > 0:
                m.cooldown = max(0, m.cooldown - dt)
                m.anim_time += dt

    def draw(self, surface, camera, time):
        sx, sy = camera.world_to_screen(self.x, self.y)
        ship_size = max(self.grid_w, self.grid_h) * 2.5 * camera.zoom
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        outline = NEON_CYAN if self.invuln_timer > 0 else DIM_CYAN

        # Helper to rotate/offset a point
        def pt(fx, fy):
            return (sx + cos_a * fx - sin_a * fy,
                    sy + sin_a * fx + cos_a * fy)

        s = ship_size
        skin = getattr(self, 'skin', 'default')

        if skin == 'battleship':
            # Big rectangular hull with protruding gun turrets
            hull = [pt(s * 2.2, s * 0.5), pt(s * 2.2, -s * 0.5),
                    pt(-s * 1.5, -s * 1.1), pt(-s * 1.8, 0), pt(-s * 1.5, s * 1.1)]
            pygame.draw.polygon(surface, (40, 50, 60), hull)
            pygame.draw.polygon(surface, outline, hull, 2)
            # Turret bumps
            for tx, ty in [(s * 0.8, -s * 0.5), (s * 0.8, s * 0.5), (-s * 0.3, 0)]:
                tp = pt(tx, ty)
                pygame.draw.circle(surface, (60, 70, 80), (int(tp[0]), int(tp[1])), 4)
                pygame.draw.circle(surface, outline, (int(tp[0]), int(tp[1])), 4, 1)
            # Bridge
            bridge = [pt(s * 0.3, s * 0.3), pt(-s * 0.5, s * 0.3),
                     pt(-s * 0.5, -s * 0.3), pt(s * 0.3, -s * 0.3)]
            pygame.draw.polygon(surface, (80, 100, 120), bridge)

        elif skin == 'arrowhead':
            # Sharp arrow/dart
            hull = [pt(s * 2.5, 0), pt(-s * 1.2, -s * 1.3),
                    pt(-s * 0.8, 0), pt(-s * 1.2, s * 1.3)]
            pygame.draw.polygon(surface, (30, 30, 50), hull)
            pygame.draw.polygon(surface, outline, hull, 2)
            # Center stripe
            stripe = [pt(s * 2.3, 0), pt(-s * 0.8, 0)]
            pygame.draw.line(surface, NEON_CYAN, stripe[0], stripe[1], 2)

        elif skin == 'stealth':
            # Angular black stealth fighter
            hull = [pt(s * 2.0, 0), pt(s * 0.8, -s * 0.4),
                   pt(-s * 0.5, -s * 1.5), pt(-s * 1.2, -s * 1.0),
                   pt(-s * 1.2, s * 1.0), pt(-s * 0.5, s * 1.5),
                   pt(s * 0.8, s * 0.4)]
            pygame.draw.polygon(surface, (15, 15, 25), hull)
            pygame.draw.polygon(surface, NEON_PURPLE, hull, 2)

        elif skin == 'raptor':
            # Bird-like fighter with swept wings
            hull = [pt(s * 2.3, 0), pt(s * 0.8, -s * 0.3),
                   pt(s * 0.2, -s * 1.5), pt(-s * 0.8, -s * 1.2),
                   pt(-s * 1.3, -s * 0.3), pt(-s * 1.0, 0),
                   pt(-s * 1.3, s * 0.3), pt(-s * 0.8, s * 1.2),
                   pt(s * 0.2, s * 1.5), pt(s * 0.8, s * 0.3)]
            pygame.draw.polygon(surface, (50, 30, 30), hull)
            pygame.draw.polygon(surface, NEON_RED, hull, 2)
            # Cockpit
            cp = pt(s * 1.2, 0)
            pygame.draw.circle(surface, NEON_YELLOW, (int(cp[0]), int(cp[1])), 3)

        else:  # 'default' asteroid-like
            hull_points = [
                pt(s * 2, 0),
                pt(-s, -s * 1.2),
                pt(-s * 0.5, 0),
                pt(-s, s * 1.2),
            ]
            pygame.draw.polygon(surface, HULL_COLOR, hull_points)
            pygame.draw.polygon(surface, outline, hull_points, 2)

        # Engine glow
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        if speed > 10 or self.fuel > 0:
            glow_intensity = min(1.0, speed / 200)
            engine_x = sx - cos_a * ship_size * 0.8
            engine_y = sy - sin_a * ship_size * 0.8
            glow_r = 6 + glow_intensity * 8 + math.sin(time * 15) * 2
            color = NEON_ORANGE if not self.boost else NEON_YELLOW
            draw_glow_circle(surface, color, (engine_x, engine_y), glow_r, glow_r * 3, 50)

        # Shield bubble
        if self.shield > 0:
            shield_ratio = self.shield / max(1, self.max_shield)
            shield_r = ship_size * 2.5
            shield_surf = pygame.Surface((int(shield_r * 2 + 4), int(shield_r * 2 + 4)), pygame.SRCALPHA)
            alpha = int(30 + 40 * shield_ratio + math.sin(time * 3) * 10)
            pygame.draw.circle(shield_surf, (*NEON_BLUE, alpha),
                             (int(shield_r + 2), int(shield_r + 2)), int(shield_r), 2)
            surface.blit(shield_surf, (int(sx - shield_r - 2), int(sy - shield_r - 2)),
                        special_flags=pygame.BLEND_ADD)

        # Module indicators (small dots showing weapon positions)
        for m in self.modules:
            if m.defn.damage > 0:
                offset_x = (m.gx - self.grid_w / 2 + m.defn.width / 2) * 5
                offset_y = (m.gy - self.grid_h / 2 + m.defn.height / 2) * 5
                wx = sx + cos_a * offset_x - sin_a * offset_y
                wy = sy + sin_a * offset_x + cos_a * offset_y
                flash = 1.0 if m.cooldown > 0 else 0.5 + 0.5 * math.sin(m.anim_time * 5)
                r = 2 + flash
                pygame.draw.circle(surface, m.defn.glow_color, (int(wx), int(wy)), int(r))
