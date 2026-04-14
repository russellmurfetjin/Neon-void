"""Base building system — placeable world structures."""
import pygame
import math
import random
from typing import Dict, List, Optional
from game.core import *


# ═════════════════════════════════════════════════════════════════════════════
#  BUILDING DEFINITIONS
# ═════════════════════════════════════════════════════════════════════════════
BUILDING_DEFS = {}

class BuildingDef:
    def __init__(self, name, bid, cost, hp, radius, color, glow, description):
        self.name = name
        self.id = bid
        self.cost = cost
        self.hp = hp
        self.radius = radius
        self.color = color
        self.glow = glow
        self.description = description

def _breg(b):
    BUILDING_DEFS[b.id] = b

_breg(BuildingDef("Barricade", "barricade", 80, 200, 30,
                   (80, 80, 90), (150, 150, 170),
                   "Blocks projectiles. Tough wall."))
_breg(BuildingDef("Storage Chest", "chest", 120, 80, 20,
                   (70, 55, 30), NEON_YELLOW,
                   "Stores credits and ore. Interact with F."))
_breg(BuildingDef("Auto Turret", "base_turret", 250, 100, 22,
                   (50, 70, 50), NEON_GREEN,
                   "Stationary turret. Auto-fires at enemies."))
_breg(BuildingDef("Beacon", "beacon", 60, 50, 15,
                   (30, 50, 80), NEON_CYAN,
                   "Shows on map. Marks a location."))
_breg(BuildingDef("Platform", "platform", 40, 150, 40,
                   (40, 45, 55), DIM_CYAN,
                   "Large floor platform. Base foundation."))
_breg(BuildingDef("Repair Station", "repair_pad", 300, 120, 25,
                   (40, 80, 40), NEON_GREEN,
                   "Heals nearby ships. +3 HP/sec in range."))


# ═════════════════════════════════════════════════════════════════════════════
#  PLACED BUILDING (world instance)
# ═════════════════════════════════════════════════════════════════════════════
class Building:
    def __init__(self, x, y, bid):
        self.x = x
        self.y = y
        self.defn = BUILDING_DEFS[bid]
        self.hp = self.defn.hp
        self.max_hp = self.defn.hp
        self.alive = True
        self.rotation = random.uniform(0, math.pi * 2)
        # Chest storage
        self.stored_credits = 0
        self.stored_ore = 0.0
        self.stored_modules = []  # list of (module_id, level)
        # Turret state
        self.fire_cooldown = 0.0
        # Beacon label
        self.label = ""

    def update(self, dt):
        if not self.alive:
            return
        self.fire_cooldown = max(0, self.fire_cooldown - dt)
        self.rotation += dt * 0.1

    def draw(self, surface, camera, time):
        if not self.alive:
            return
        sx, sy = camera.world_to_screen(self.x, self.y)
        if sx < -100 or sx > SCREEN_W + 100 or sy < -100 or sy > SCREEN_H + 100:
            return

        r = self.defn.radius * camera.zoom
        bid = self.defn.id

        if bid == 'barricade':
            # Thick wall shape
            cos_a = math.cos(self.rotation)
            sin_a = math.sin(self.rotation)
            pts = [
                (sx + cos_a * r - sin_a * 8, sy + sin_a * r + cos_a * 8),
                (sx + cos_a * r + sin_a * 8, sy + sin_a * r - cos_a * 8),
                (sx - cos_a * r + sin_a * 8, sy - sin_a * r - cos_a * 8),
                (sx - cos_a * r - sin_a * 8, sy - sin_a * r + cos_a * 8),
            ]
            pygame.draw.polygon(surface, self.defn.color, pts)
            pygame.draw.polygon(surface, self.defn.glow, pts, 2)

        elif bid == 'chest':
            # Crate shape
            pygame.draw.rect(surface, self.defn.color,
                           (int(sx - r), int(sy - r * 0.7), int(r * 2), int(r * 1.4)))
            pygame.draw.rect(surface, self.defn.glow,
                           (int(sx - r), int(sy - r * 0.7), int(r * 2), int(r * 1.4)), 2)
            # Lock/latch
            pygame.draw.rect(surface, NEON_YELLOW,
                           (int(sx - 4), int(sy - 3), 8, 6))
            # Contents indicator
            if self.stored_credits > 0 or self.stored_ore > 0:
                draw_text(surface, f"${self.stored_credits} | {int(self.stored_ore)}ore",
                         int(sx), int(sy - r - 10), NEON_YELLOW, 9, center=True)

        elif bid == 'base_turret':
            # Turret base
            pygame.draw.circle(surface, self.defn.color, (int(sx), int(sy)), int(r))
            pygame.draw.circle(surface, self.defn.glow, (int(sx), int(sy)), int(r), 2)
            # Gun barrel
            cos_a = math.cos(self.rotation)
            sin_a = math.sin(self.rotation)
            pygame.draw.line(surface, NEON_GREEN,
                           (int(sx), int(sy)),
                           (int(sx + cos_a * r * 1.5), int(sy + sin_a * r * 1.5)), 3)
            glow = 0.5 + 0.5 * math.sin(time * 5)
            draw_glow_circle(surface, NEON_GREEN,
                           (sx + cos_a * r * 0.3, sy + sin_a * r * 0.3), 3, 8, int(30 + 20 * glow))

        elif bid == 'beacon':
            # Pulsing beacon
            pulse = 0.5 + 0.5 * math.sin(time * 3)
            beacon_r = r + pulse * 5
            pygame.draw.circle(surface, self.defn.color, (int(sx), int(sy)), int(r * 0.6))
            pygame.draw.circle(surface, self.defn.glow, (int(sx), int(sy)), int(beacon_r), 2)
            # Outer pulse ring
            ring_r = r * 2 + pulse * 15
            ring_c = safe_color(self.defn.glow[0] * 0.3, self.defn.glow[1] * 0.3, self.defn.glow[2] * 0.3)
            pygame.draw.circle(surface, ring_c, (int(sx), int(sy)), int(ring_r), 1)
            if self.label:
                draw_text(surface, self.label, int(sx), int(sy - r - 12),
                         NEON_CYAN, 10, center=True)

        elif bid == 'platform':
            # Large hex platform
            pts = []
            for i in range(6):
                angle = i * math.pi / 3
                pts.append((sx + math.cos(angle) * r, sy + math.sin(angle) * r))
            pygame.draw.polygon(surface, self.defn.color, pts)
            pygame.draw.polygon(surface, self.defn.glow, pts, 1)
            # Attachment point markers (small dim dots)
            for i in range(6):
                angle = i * math.pi / 3
                ax = sx + math.cos(angle) * r * 0.7
                ay = sy + math.sin(angle) * r * 0.7
                pygame.draw.circle(surface, (50, 80, 100), (int(ax), int(ay)), 2)
            pygame.draw.circle(surface, (50, 80, 100), (int(sx), int(sy)), 2)

        elif bid == 'repair_pad':
            # Green cross
            pygame.draw.circle(surface, self.defn.color, (int(sx), int(sy)), int(r))
            pygame.draw.circle(surface, self.defn.glow, (int(sx), int(sy)), int(r), 2)
            # Cross symbol
            pygame.draw.rect(surface, NEON_GREEN, (int(sx - 3), int(sy - 10), 6, 20))
            pygame.draw.rect(surface, NEON_GREEN, (int(sx - 10), int(sy - 3), 20, 6))
            # Heal range indicator
            heal_r = 120
            heal_c = safe_color(0, 80 * pulse if 'pulse' in dir() else 40, 0)
            pygame.draw.circle(surface, (0, 30, 0), (int(sx), int(sy)), heal_r, 1)

        # HP bar (if damaged)
        if self.hp < self.max_hp:
            draw_bar(surface, int(sx - 15), int(sy + r + 4), 30, 4,
                    self.hp / self.max_hp, NEON_GREEN, (20, 20, 30))

    def to_dict(self):
        return {
            'x': round(self.x, 1), 'y': round(self.y, 1),
            'bid': self.defn.id, 'hp': self.hp,
            'credits': self.stored_credits, 'ore': round(self.stored_ore, 1),
            'modules': self.stored_modules,
            'label': self.label,
        }

    @staticmethod
    def from_dict(d):
        b = Building(d['x'], d['y'], d['bid'])
        b.hp = d.get('hp', b.max_hp)
        b.stored_credits = d.get('credits', 0)
        b.stored_ore = d.get('ore', 0)
        b.stored_modules = d.get('modules', [])
        b.label = d.get('label', '')
        return b
