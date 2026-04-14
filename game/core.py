"""Core engine systems: constants, camera, particles, audio, and utilities."""
import pygame
import math
import random
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# ── DISPLAY ──────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
TILE = 32

# ── COLORS (neon cyberpunk palette) ──────────────────────────────────────────
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BG_DARK = (4, 4, 12)

NEON_CYAN = (0, 255, 255)
NEON_PINK = (255, 0, 128)
NEON_BLUE = (0, 128, 255)
NEON_GREEN = (0, 255, 128)
NEON_ORANGE = (255, 160, 0)
NEON_YELLOW = (255, 255, 0)
NEON_RED = (255, 40, 40)
NEON_PURPLE = (180, 60, 255)

DIM_CYAN = (0, 80, 80)
DIM_PINK = (80, 0, 40)
DIM_BLUE = (0, 40, 80)
DIM_GREEN = (0, 80, 40)

HULL_COLOR = (30, 35, 50)
GRID_COLOR = (20, 25, 40)
GRID_LINE = (40, 50, 70)
GRID_HIGHLIGHT = (60, 80, 120)

# ── RESOURCE COLORS ──────────────────────────────────────────────────────────
ORE_COLOR = (180, 120, 60)
OIL_COLOR = (40, 40, 40)
FUEL_COLOR = NEON_ORANGE
ICE_COLOR = (150, 200, 255)
COOLANT_COLOR = (100, 180, 255)

# ── GAME BALANCE ─────────────────────────────────────────────────────────────
PLAYER_THRUST = 300.0
PLAYER_BOOST_MULT = 2.5
PLAYER_DRAG = 0.98
PLAYER_MAX_SPEED = 500.0
FUEL_DRAIN_RATE = 2.0
FUEL_BOOST_DRAIN = 6.0
STARTING_FUEL = 50.0
STARTING_CREDITS = 100

PROBE_SPEED = 200.0
PROBE_MINE_TIME = 3.0
PROBE_CARRY = 15.0
REFINERY_RATE = 5.0

ENEMY_BASE_HP = 30
ENEMY_BASE_SPEED = 120.0
ENEMY_BASE_DAMAGE = 10
ENEMY_CREDIT_DROP = 35

LASER_DAMAGE = 8
LASER_SPEED = 800.0
LASER_COOLDOWN = 0.3
MISSILE_DAMAGE = 35
MISSILE_SPEED = 400.0
MISSILE_COOLDOWN = 1.5
MISSILE_TURN_RATE = 4.0

# ── WORLD / SECTORS ─────────────────────────────────────────────────────────
SECTOR_SIZE = 4000
PATROL_DETECT_RANGE = 1000
PATROL_RESPAWN_TIME = 120.0
POI_DETECT_RANGE = 350
DOCK_RANGE = 100
STATION_FUEL_PRICE = 2
STATION_REPAIR_PRICE = 3
ORE_SELL_PRICE = 4  # good money — risk: no fuel if you sell all ore

STAR_LAYERS = 3
STARS_PER_LAYER = 150


# ═════════════════════════════════════════════════════════════════════════════
#  CAMERA
# ═════════════════════════════════════════════════════════════════════════════
class Camera:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.shake_x = 0.0
        self.shake_y = 0.0
        self.shake_intensity = 0.0
        self.shake_decay = 5.0
        self.smooth = 5.0
        self.zoom = 1.0  # 1.0 = normal, 0.5 = zoomed out 2x
        self.target_zoom = 1.0

    def follow(self, x: float, y: float):
        self.target_x = x
        self.target_y = y

    def shake(self, intensity: float):
        self.shake_intensity = max(self.shake_intensity, intensity)

    def update(self, dt: float):
        self.x += (self.target_x - self.x) * self.smooth * dt
        self.y += (self.target_y - self.y) * self.smooth * dt
        self.zoom += (self.target_zoom - self.zoom) * 8 * dt
        if self.shake_intensity > 0.1:
            self.shake_x = random.uniform(-1, 1) * self.shake_intensity
            self.shake_y = random.uniform(-1, 1) * self.shake_intensity
            self.shake_intensity *= max(0, 1 - self.shake_decay * dt)
        else:
            self.shake_x = 0
            self.shake_y = 0
            self.shake_intensity = 0

    def world_to_screen(self, wx: float, wy: float) -> Tuple[float, float]:
        sx = (wx - self.x) * self.zoom + SCREEN_W / 2 + self.shake_x
        sy = (wy - self.y) * self.zoom + SCREEN_H / 2 + self.shake_y
        return sx, sy

    def screen_to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        wx = (sx - SCREEN_W / 2 - self.shake_x) / self.zoom + self.x
        wy = (sy - SCREEN_H / 2 - self.shake_y) / self.zoom + self.y
        return wx, wy

    def visible_rect(self) -> pygame.Rect:
        margin = 100
        w = SCREEN_W / self.zoom
        h = SCREEN_H / self.zoom
        return pygame.Rect(
            self.x - w / 2 - margin,
            self.y - h / 2 - margin,
            w + margin * 2,
            h + margin * 2,
        )


# ═════════════════════════════════════════════════════════════════════════════
#  PARTICLES
# ═════════════════════════════════════════════════════════════════════════════
class Particle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'life', 'max_life', 'color', 'size', 'glow')

    def __init__(self, x, y, vx, vy, life, color, size=2.0, glow=True):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.color = color
        self.size = size
        self.glow = glow


class ParticleSystem:
    def __init__(self, max_particles=3000):
        self.particles: List[Particle] = []
        self.max_particles = max_particles

    def emit(self, x, y, vx, vy, life, color, size=2.0, glow=True):
        if len(self.particles) < self.max_particles:
            self.particles.append(Particle(x, y, vx, vy, life, color, size, glow))

    def burst(self, x, y, count, speed, life, color, size=2.0, glow=True, spread=math.pi * 2):
        for _ in range(min(count, self.max_particles - len(self.particles))):
            angle = random.uniform(0, spread)
            spd = random.uniform(speed * 0.3, speed)
            vx = math.cos(angle) * spd
            vy = math.sin(angle) * spd
            l = life * random.uniform(0.5, 1.0)
            s = size * random.uniform(0.5, 1.5)
            self.particles.append(Particle(x, y, vx, vy, l, color, s, glow))

    def trail(self, x, y, vx, vy, color, size=2.0, count=1):
        for _ in range(count):
            pvx = vx + random.uniform(-30, 30)
            pvy = vy + random.uniform(-30, 30)
            self.emit(
                x + random.uniform(-3, 3),
                y + random.uniform(-3, 3),
                pvx, pvy,
                random.uniform(0.2, 0.5),
                color, size
            )

    def update(self, dt):
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life > 0:
                p.x += p.vx * dt
                p.y += p.vy * dt
                p.vx *= 0.97
                p.vy *= 0.97
                alive.append(p)
        self.particles = alive

    def draw(self, surface, camera):
        vis = camera.visible_rect()
        glow_count = 0
        for p in self.particles:
            if not vis.collidepoint(p.x, p.y):
                continue
            sx, sy = camera.world_to_screen(p.x, p.y)
            alpha = max(0, min(1, p.life / p.max_life))
            r = max(0, min(255, int(p.color[0] * alpha)))
            g = max(0, min(255, int(p.color[1] * alpha)))
            b = max(0, min(255, int(p.color[2] * alpha)))
            size = max(1, int(p.size * alpha))
            if p.glow and size >= 3 and glow_count < 80:
                glow_count += 1
                glow_size = size * 3
                glow_surf = pygame.Surface((glow_size * 2, glow_size * 2), pygame.SRCALPHA)
                glow_alpha = max(0, min(255, int(40 * alpha)))
                pygame.draw.circle(glow_surf, (r, g, b, glow_alpha), (glow_size, glow_size), glow_size)
                surface.blit(glow_surf, (int(sx - glow_size), int(sy - glow_size)), special_flags=pygame.BLEND_ADD)
            pygame.draw.circle(surface, (r, g, b), (int(sx), int(sy)), size)


# ═════════════════════════════════════════════════════════════════════════════
#  STARFIELD (parallax background)
# ═════════════════════════════════════════════════════════════════════════════
class StarField:
    def __init__(self):
        self.layers = []
        for layer in range(STAR_LAYERS):
            stars = []
            parallax = 0.05 + layer * 0.1
            brightness = 60 + layer * 60
            for _ in range(STARS_PER_LAYER):
                x = random.uniform(-SCREEN_W * 3, SCREEN_W * 3)
                y = random.uniform(-SCREEN_H * 3, SCREEN_H * 3)
                size = random.randint(1, 2 + layer)
                twinkle_speed = random.uniform(1.0, 4.0)
                twinkle_offset = random.uniform(0, math.pi * 2)
                color_shift = random.choice([
                    (brightness, brightness, brightness),
                    (brightness, brightness, int(brightness * 0.7)),
                    (int(brightness * 0.7), brightness, brightness),
                    (int(brightness * 0.8), int(brightness * 0.8), brightness),
                ])
                stars.append((x, y, size, color_shift, twinkle_speed, twinkle_offset))
            self.layers.append((parallax, stars))

    def draw(self, surface, camera, time):
        for parallax, stars in self.layers:
            for x, y, size, color, twinkle_spd, twinkle_off in stars:
                sx = x - camera.x * parallax + SCREEN_W / 2
                sy = y - camera.y * parallax + SCREEN_H / 2
                sx = sx % (SCREEN_W + 200) - 100
                sy = sy % (SCREEN_H + 200) - 100
                twinkle = 0.6 + 0.4 * math.sin(time * twinkle_spd + twinkle_off)
                c = (int(color[0] * twinkle), int(color[1] * twinkle), int(color[2] * twinkle))
                if size <= 1:
                    surface.set_at((int(sx), int(sy)), c)
                else:
                    pygame.draw.circle(surface, c, (int(sx), int(sy)), size)


# ═════════════════════════════════════════════════════════════════════════════
#  PROCEDURAL AUDIO
# ═════════════════════════════════════════════════════════════════════════════
class AudioManager:
    def __init__(self):
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self.enabled = True
        except Exception:
            self.enabled = False
            return
        self.sounds = {}
        try:
            self._generate_sounds()
        except Exception:
            # numpy might not be installed — audio still works, just no sounds
            self.enabled = False
            return
        self.music_playing = False

    def _generate_sounds(self):
        if not self.enabled:
            return
        self.sounds['laser'] = self._make_laser()
        self.sounds['missile'] = self._make_missile()
        self.sounds['explosion'] = self._make_explosion()
        self.sounds['explosion_big'] = self._make_explosion(big=True)
        self.sounds['hit'] = self._make_hit()
        self.sounds['pickup'] = self._make_pickup()
        self.sounds['probe_launch'] = self._make_probe()
        self.sounds['buy'] = self._make_buy()
        self.sounds['warning'] = self._make_warning()
        self.sounds['boost'] = self._make_boost()
        self.sounds['dock'] = self._make_dock()
        self.sounds['undock'] = self._make_undock()
        self.sounds['discover'] = self._make_discover()

    def _synth(self, duration, freq_func, amp_func=None, sample_rate=44100):
        n_samples = int(duration * sample_rate)
        t = np.linspace(0, duration, n_samples, dtype=np.float32)
        wave = np.zeros(n_samples, dtype=np.float32)
        freqs = freq_func(t)
        phase = np.cumsum(freqs / sample_rate) * 2 * np.pi
        wave = np.sin(phase)
        if amp_func:
            wave *= amp_func(t, duration)
        else:
            envelope = np.exp(-t / duration * 3)
            wave *= envelope
        wave = np.clip(wave * 0.3, -1, 1)
        stereo = np.column_stack((wave, wave))
        samples = (stereo * 32767).astype(np.int16)
        return pygame.sndarray.make_sound(samples)

    def _make_laser(self):
        return self._synth(0.15, lambda t: 880 - t * 3000,
                          lambda t, d: np.exp(-t / d * 5))

    def _make_missile(self):
        return self._synth(0.3, lambda t: 200 + np.sin(t * 50) * 100,
                          lambda t, d: np.exp(-t / d * 2))

    def _make_explosion(self, big=False):
        dur = 0.5 if not big else 0.8
        n = int(dur * 44100)
        noise = np.random.uniform(-1, 1, n).astype(np.float32)
        envelope = np.exp(-np.linspace(0, 1, n) * (3 if not big else 2))
        wave = noise * envelope * 0.4
        stereo = np.column_stack((wave, wave))
        samples = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
        return pygame.sndarray.make_sound(samples)

    def _make_hit(self):
        return self._synth(0.1, lambda t: 300 - t * 2000,
                          lambda t, d: np.exp(-t / d * 8))

    def _make_pickup(self):
        return self._synth(0.2, lambda t: 440 + t * 2000,
                          lambda t, d: np.exp(-t / d * 4))

    def _make_probe(self):
        return self._synth(0.3, lambda t: 200 + t * 400,
                          lambda t, d: np.sin(t / d * np.pi))

    def _make_buy(self):
        return self._synth(0.25, lambda t: 523 + t * 800,
                          lambda t, d: np.sin(t / d * np.pi))

    def _make_warning(self):
        return self._synth(0.4, lambda t: 440 * (1 + 0.5 * np.sin(t * 20)),
                          lambda t, d: np.sin(t / d * np.pi))

    def _make_boost(self):
        n = int(0.3 * 44100)
        noise = np.random.uniform(-1, 1, n).astype(np.float32)
        t = np.linspace(0, 0.3, n)
        filtered = noise * np.exp(-t * 5) * 0.3
        wave = np.sin(np.cumsum(150 / 44100 * np.ones(n)) * 2 * np.pi) * 0.2 * np.exp(-t * 3)
        combined = filtered + wave
        stereo = np.column_stack((combined, combined))
        samples = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
        return pygame.sndarray.make_sound(samples)

    def _make_dock(self):
        return self._synth(0.4, lambda t: 300 + t * 600,
                          lambda t, d: np.sin(t / d * np.pi) * 0.8)

    def _make_undock(self):
        return self._synth(0.3, lambda t: 600 - t * 400,
                          lambda t, d: np.sin(t / d * np.pi) * 0.8)

    def _make_discover(self):
        return self._synth(0.5, lambda t: 523 + t * 400 + np.sin(t * 30) * 50,
                          lambda t, d: np.sin(t / d * np.pi))

    def play(self, name, volume=0.5):
        if not self.enabled or name not in self.sounds:
            return
        s = self.sounds[name]
        s.set_volume(volume)
        s.play()

    def start_ambient(self):
        if not self.enabled or self.music_playing:
            return
        self.music_playing = True


def safe_color(r, g, b):
    """Clamp RGB values to valid 0-255 range."""
    return (max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))))


# ═════════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════
def dist(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def angle_to(x1, y1, x2, y2):
    return math.atan2(y2 - y1, x2 - x1)


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


_FONT_CACHE = {}

def get_font(size, font_name=None):
    key = (font_name or "consolas", size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = pygame.font.SysFont(key[0], key[1])
    return _FONT_CACHE[key]


def draw_text(surface, text, x, y, color=WHITE, size=16, center=False, font_name=None):
    font = get_font(size, font_name)
    rendered = font.render(str(text), True, color)
    if center:
        rect = rendered.get_rect(center=(x, y))
    else:
        rect = rendered.get_rect(topleft=(x, y))
    surface.blit(rendered, rect)
    return rect


def draw_glow_circle(surface, color, center, radius, glow_radius=None, alpha=60):
    if glow_radius is None:
        glow_radius = radius * 2.5
    glow_size = int(glow_radius * 2)
    if glow_size < 4:
        return
    glow_surf = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
    pygame.draw.circle(glow_surf, (*color[:3], alpha), (glow_size // 2, glow_size // 2), int(glow_radius))
    surface.blit(glow_surf, (int(center[0] - glow_radius), int(center[1] - glow_radius)), special_flags=pygame.BLEND_ADD)
    pygame.draw.circle(surface, color, (int(center[0]), int(center[1])), int(radius))


def draw_bar(surface, x, y, w, h, ratio, color, bg_color=(20, 20, 30), border_color=None):
    # Guard against NaN, inf, or bad values
    try:
        ratio = max(0.0, min(1.0, float(ratio)))
    except (ValueError, TypeError):
        ratio = 0.0
    if w <= 0 or h <= 0:
        return
    pygame.draw.rect(surface, bg_color, (x, y, w, h))
    fill_w = max(0, int(w * ratio))
    if fill_w > 0:
        pygame.draw.rect(surface, color, (x, y, fill_w, h))
    if border_color:
        pygame.draw.rect(surface, border_color, (x, y, w, h), 1)


def draw_neon_rect(surface, color, rect, width=1, glow_alpha=40):
    pygame.draw.rect(surface, color, rect, width)
    glow_rect = pygame.Rect(rect.x - 2, rect.y - 2, rect.w + 4, rect.h + 4)
    glow_surf = pygame.Surface((glow_rect.w, glow_rect.h), pygame.SRCALPHA)
    pygame.draw.rect(glow_surf, (*color[:3], glow_alpha), (0, 0, glow_rect.w, glow_rect.h), width + 2)
    surface.blit(glow_surf, glow_rect.topleft, special_flags=pygame.BLEND_ADD)
