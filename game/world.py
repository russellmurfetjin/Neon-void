"""World entities and sector-based exploration manager."""
import pygame
import math
import random
from typing import List, Optional, Tuple
from game.core import *
from game.ship import Ship
from game.sector import SectorManager, Sector, Station, POI, PatrolGroup
from game.building import Building, BUILDING_DEFS


# ═════════════════════════════════════════════════════════════════════════════
#  ASTEROID
# ═════════════════════════════════════════════════════════════════════════════
class Asteroid:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        # Seed from position so all clients generate identical asteroids
        rng = random.Random(hash((round(x, 1), round(y, 1))))
        self.radius = rng.uniform(25, 60)
        self.ore = self.radius * rng.uniform(2.0, 4.0)
        self.max_ore = self.ore
        self.rotation = rng.uniform(0, math.pi * 2)
        self.rot_speed = rng.uniform(-0.3, 0.3)
        self.depleted = False
        self.being_mined = False
        self.points = []
        n_points = rng.randint(7, 12)
        for i in range(n_points):
            angle = (i / n_points) * math.pi * 2
            r = self.radius * rng.uniform(0.7, 1.3)
            self.points.append((angle, r))
        self.color = (
            rng.randint(80, 120),
            rng.randint(60, 90),
            rng.randint(40, 60),
        )
        self.highlight = (
            min(255, self.color[0] + 40),
            min(255, self.color[1] + 30),
            min(255, self.color[2] + 20),
        )

    def update(self, dt):
        self.rotation += self.rot_speed * dt
        if self.ore <= 0:
            self.depleted = True
            self.being_mined = False

    def draw(self, surface, camera, time):
        if self.depleted:
            return  # don't draw destroyed asteroids
        sx, sy = camera.world_to_screen(self.x, self.y)
        z = camera.zoom
        pts = []
        for angle, r in self.points:
            a = angle + self.rotation
            px = sx + math.cos(a) * r * z
            py = sy + math.sin(a) * r * z
            pts.append((px, py))
        if len(pts) >= 3:
            pygame.draw.polygon(surface, self.color, pts)
            pygame.draw.polygon(surface, self.highlight, pts, 2)

        if not self.depleted and self.max_ore > 0:
            fuel_ratio = max(0, min(1, self.ore / self.max_ore))
            indicator_color = (
                int(lerp(80, 255, fuel_ratio)),
                int(lerp(40, 160, fuel_ratio)),
                int(lerp(10, 0, fuel_ratio)),
            )
            draw_bar(surface, int(sx - 15), int(sy - self.radius - 12),
                    30, 4, fuel_ratio, indicator_color, (20, 15, 10), (60, 50, 30))

        if self.being_mined:
            glow_alpha = int(30 + 20 * math.sin(time * 6))
            glow_r = self.radius * 1.5
            glow_surf = pygame.Surface((int(glow_r * 2), int(glow_r * 2)), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*NEON_GREEN[:3], glow_alpha),
                             (int(glow_r), int(glow_r)), int(glow_r))
            surface.blit(glow_surf, (int(sx - glow_r), int(sy - glow_r)),
                        special_flags=pygame.BLEND_ADD)


# ═════════════════════════════════════════════════════════════════════════════
#  MINING PROBE
# ═════════════════════════════════════════════════════════════════════════════
class MiningProbe:
    def __init__(self, x, y, target_asteroid: Asteroid):
        self.x = x
        self.y = y
        self.target = target_asteroid
        self.state = 'traveling'
        self.mine_timer = 0.0
        self.cargo = 0.0
        self.max_cargo = PROBE_CARRY
        self.alive = True
        self.trail_timer = 0.0

    def update(self, dt, ship: Ship, particles: ParticleSystem):
        self.trail_timer += dt

        if self.state == 'traveling':
            dx = self.target.x - self.x
            dy = self.target.y - self.y
            d = math.sqrt(dx * dx + dy * dy)
            if d < self.target.radius:
                self.state = 'mining'
                self.target.being_mined = True
            else:
                self.x += (dx / d) * PROBE_SPEED * dt
                self.y += (dy / d) * PROBE_SPEED * dt

        elif self.state == 'mining':
            self.mine_timer += dt
            rate = self.max_cargo / PROBE_MINE_TIME
            mined = min(rate * dt, self.target.ore, self.max_cargo - self.cargo)
            self.cargo += mined
            self.target.ore -= mined
            if self.cargo >= self.max_cargo or self.target.ore <= 0:
                self.state = 'returning'
                self.target.being_mined = False
                particles.burst(self.x, self.y, 15, 60, 0.5, NEON_ORANGE, 2)

        elif self.state == 'returning':
            dx = ship.x - self.x
            dy = ship.y - self.y
            d = math.sqrt(dx * dx + dy * dy)
            if d < 30:
                # Deliver ore to ship's ore hold
                space = ship.ore_capacity - ship.ore
                delivered = min(self.cargo, space)
                ship.ore += delivered
                # Overflow goes to fuel directly
                overflow = self.cargo - delivered
                if overflow > 0:
                    fuel_space = ship.fuel_capacity - ship.fuel
                    ship.fuel += min(overflow * 0.5, fuel_space)
                self.alive = False
                ship.active_probes -= 1
                particles.burst(ship.x, ship.y, 10, 40, 0.3, ORE_COLOR, 2)
                if delivered > 0:
                    particles.burst(ship.x, ship.y, 6, 30, 0.3, NEON_GREEN, 1.5)
            else:
                self.x += (dx / d) * PROBE_SPEED * 1.3 * dt
                self.y += (dy / d) * PROBE_SPEED * 1.3 * dt

        if self.trail_timer > 0.05:
            self.trail_timer = 0.0
            color = NEON_GREEN if self.state != 'mining' else ORE_COLOR
            particles.emit(
                self.x + random.uniform(-3, 3),
                self.y + random.uniform(-3, 3),
                random.uniform(-20, 20), random.uniform(-20, 20),
                0.3, color, 1.5
            )

    def draw(self, surface, camera, time):
        sx, sy = camera.world_to_screen(self.x, self.y)
        z = camera.zoom
        glow = 0.5 + 0.5 * math.sin(time * 8)
        color = NEON_GREEN if self.state != 'mining' else NEON_ORANGE
        draw_glow_circle(surface, color, (sx, sy), max(2, int(4 * z)), max(4, int(12 * z)), int(40 + 30 * glow))

        if self.cargo > 0:
            ratio = self.cargo / self.max_cargo
            w = max(8, int(16 * z))
            draw_bar(surface, int(sx - w // 2), int(sy - 10 * z), w, max(2, int(3 * z)), ratio, ORE_COLOR, (20, 15, 10))

        if self.state == 'mining':
            tsx, tsy = camera.world_to_screen(self.target.x, self.target.y)
            pulse = 0.5 + 0.5 * math.sin(time * 10)
            beam_c = safe_color(NEON_GREEN[0] * pulse, NEON_GREEN[1] * pulse, NEON_GREEN[2] * pulse)
            pygame.draw.line(surface, beam_c, (int(sx), int(sy)), (int(tsx), int(tsy)), 2)


# ═════════════════════════════════════════════════════════════════════════════
#  PROJECTILE
# ═════════════════════════════════════════════════════════════════════════════
class Projectile:
    def __init__(self, x, y, vx, vy, damage, owner='player', proj_type='laser',
                 target=None, color=NEON_RED):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.owner = owner
        self.proj_type = proj_type
        self.target = target
        self.color = color
        self.alive = True
        self.life = 4.0
        self.trail_timer = 0.0

    def update(self, dt, particles):
        self.life -= dt
        if self.life <= 0:
            self.alive = False
            return

        if self.proj_type == 'missile' and self.target and hasattr(self.target, 'alive') and self.target.alive:
            dx = self.target.x - self.x
            dy = self.target.y - self.y
            desired = math.atan2(dy, dx)
            current = math.atan2(self.vy, self.vx)
            diff = desired - current
            while diff > math.pi: diff -= math.pi * 2
            while diff < -math.pi: diff += math.pi * 2
            turn = clamp(diff, -MISSILE_TURN_RATE * dt, MISSILE_TURN_RATE * dt)
            new_angle = current + turn
            speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
            self.vx = math.cos(new_angle) * speed
            self.vy = math.sin(new_angle) * speed

        self.x += self.vx * dt
        self.y += self.vy * dt

        self.trail_timer += dt
        if self.trail_timer > 0.02:
            self.trail_timer = 0.0
            particles.emit(
                self.x + random.uniform(-2, 2),
                self.y + random.uniform(-2, 2),
                -self.vx * 0.1 + random.uniform(-10, 10),
                -self.vy * 0.1 + random.uniform(-10, 10),
                0.2, self.color, 1.5 if self.proj_type == 'laser' else 2.5
            )

    def draw(self, surface, camera):
        sx, sy = camera.world_to_screen(self.x, self.y)
        z = camera.zoom
        if self.proj_type == 'bullet':
            speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
            if speed > 0:
                nx, ny = self.vx / speed * 5 * z, self.vy / speed * 5 * z
                pygame.draw.line(surface, self.color,
                               (int(sx - nx), int(sy - ny)),
                               (int(sx + nx), int(sy + ny)), max(1, int(2 * z)))
            pygame.draw.circle(surface, self.color, (int(sx), int(sy)), max(1, int(2 * z)))
        elif self.proj_type == 'laser':
            speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
            if speed > 0:
                nx, ny = self.vx / speed * 8 * z, self.vy / speed * 8 * z
                pygame.draw.line(surface, self.color,
                               (int(sx - nx), int(sy - ny)),
                               (int(sx + nx), int(sy + ny)), max(1, int(2 * z)))
            draw_glow_circle(surface, self.color, (sx, sy), max(1, int(2 * z)), max(3, int(8 * z)), 50)
        elif self.proj_type == 'missile':
            draw_glow_circle(surface, self.color, (sx, sy), max(2, int(3 * z)), max(4, int(12 * z)), 60)


# ═════════════════════════════════════════════════════════════════════════════
#  ENEMY
# ═════════════════════════════════════════════════════════════════════════════
class Enemy:
    # enemy_type: 'normal', 'elite', 'miniboss', 'boss'
    def __init__(self, x, y, tier=1, is_boss=False, enemy_type='normal'):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.tier = tier
        self.is_boss = is_boss or enemy_type == 'boss'
        self.enemy_type = enemy_type if not is_boss else 'boss'

        # Scale stats by type
        if self.enemy_type == 'elite':
            scale = tier * 2
            self.radius = 18 + tier * 3
        elif self.enemy_type == 'miniboss':
            scale = tier * 3
            self.radius = 22 + tier * 4
        elif self.enemy_type == 'boss':
            scale = tier + 4
            self.radius = 15 + tier * 3 + 20
        else:
            scale = tier
            self.radius = 15 + tier * 3

        self.hp = ENEMY_BASE_HP * scale
        self.max_hp = self.hp
        self.speed = ENEMY_BASE_SPEED * (1 + tier * 0.15)
        self.damage = ENEMY_BASE_DAMAGE * (1 + tier * 0.3)
        self.fire_cooldown = 0.0
        self.fire_rate = 1.5 / (1 + tier * 0.2)
        self.credit_value = ENEMY_CREDIT_DROP * scale
        self.alive = True
        self.hit_flash = 0.0
        self.angle = random.uniform(0, math.pi * 2)

        if self.enemy_type == 'boss':
            self.speed *= 0.6
            self.fire_rate *= 0.5
        elif self.enemy_type == 'miniboss':
            self.speed *= 0.8
            self.fire_rate *= 0.6
            self.damage *= 1.5
        elif self.enemy_type == 'elite':
            self.speed *= 1.2
            self.fire_rate *= 0.7

        # AI
        self.aggro = False
        self.ai_state = 'patrol'
        self.patrol_cx = x
        self.patrol_cy = y
        self.patrol_angle = random.uniform(0, math.pi * 2)
        self.preferred_range = random.uniform(150, 300)
        self.strafe_angle = random.choice([-1, 1])
        self.strafe_timer = 0.0

        # Visual by type
        if self.enemy_type == 'boss':
            self.color = NEON_PINK
            self.body_color = (80, 20, 40)
        elif self.enemy_type == 'miniboss':
            self.color = NEON_CYAN
            self.body_color = (20, 60, 70)
        elif self.enemy_type == 'elite':
            self.color = NEON_YELLOW
            self.body_color = (70, 60, 20)
        elif tier >= 3:
            self.color = NEON_PURPLE
            self.body_color = (50, 20, 70)
        elif tier >= 2:
            self.color = NEON_RED
            self.body_color = (70, 20, 20)
        else:
            self.color = NEON_ORANGE
            self.body_color = (70, 50, 20)

    def update(self, dt, ship: Ship, projectiles: List, particles: ParticleSystem):
        if not self.alive:
            return

        self.hit_flash = max(0, self.hit_flash - dt * 5)
        self.fire_cooldown = max(0, self.fire_cooldown - dt)
        self.strafe_timer += dt

        dx = ship.x - self.x
        dy = ship.y - self.y
        d = math.sqrt(dx * dx + dy * dy)
        if d < 1:
            d = 1

        # Aggro/disengage detection
        if self.aggro and d > PATROL_DETECT_RANGE * 2.5:
            # Player got too far away — return to patrol
            self.aggro = False
        if not self.aggro:
            if d < PATROL_DETECT_RANGE:
                self.aggro = True
            else:
                # Patrol behavior: orbit around patrol center
                self.patrol_angle += dt * 0.3
                target_x = self.patrol_cx + math.cos(self.patrol_angle) * 150
                target_y = self.patrol_cy + math.sin(self.patrol_angle) * 150
                tdx = target_x - self.x
                tdy = target_y - self.y
                td = max(1, math.sqrt(tdx ** 2 + tdy ** 2))
                self.vx += (tdx / td) * self.speed * 0.5 * dt
                self.vy += (tdy / td) * self.speed * 0.5 * dt
                self.vx *= 0.97
                self.vy *= 0.97
                self.angle = math.atan2(self.vy, self.vx)
                self.x += self.vx * dt
                self.y += self.vy * dt
                return

        self.angle = math.atan2(dy, dx)

        # Combat AI
        if d > self.preferred_range * 1.5:
            self.ai_state = 'approach'
        elif d < self.preferred_range * 0.7:
            self.ai_state = 'retreat'
        else:
            self.ai_state = 'strafe'

        if self.ai_state == 'approach':
            self.vx += (dx / d) * self.speed * dt * 2
            self.vy += (dy / d) * self.speed * dt * 2
        elif self.ai_state == 'retreat':
            self.vx -= (dx / d) * self.speed * dt * 1.5
            self.vy -= (dy / d) * self.speed * dt * 1.5
        elif self.ai_state == 'strafe':
            if self.strafe_timer > 2.0:
                self.strafe_timer = 0
                self.strafe_angle *= -1
            perp_x = -dy / d * self.strafe_angle
            perp_y = dx / d * self.strafe_angle
            self.vx += perp_x * self.speed * dt * 2
            self.vy += perp_y * self.speed * dt * 2

        self.vx *= 0.96
        self.vy *= 0.96

        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        if speed > self.speed:
            self.vx = self.vx / speed * self.speed
            self.vy = self.vy / speed * self.speed

        self.x += self.vx * dt
        self.y += self.vy * dt

        # Fire at player
        if d < 500 and self.fire_cooldown <= 0 and ship.alive:
            self.fire_cooldown = self.fire_rate
            fire_angle = math.atan2(dy, dx)
            if speed > 0:
                lead = d / LASER_SPEED * 0.5
                fire_angle = math.atan2(
                    dy + (ship.vy - self.vy) * lead,
                    dx + (ship.vx - self.vx) * lead
                )
            proj_speed = LASER_SPEED * 0.7
            pvx = math.cos(fire_angle) * proj_speed
            pvy = math.sin(fire_angle) * proj_speed
            proj = Projectile(
                self.x + math.cos(fire_angle) * self.radius,
                self.y + math.sin(fire_angle) * self.radius,
                pvx, pvy, self.damage, 'enemy', 'laser', color=self.color
            )
            projectiles.append(proj)
            fx = self.x + math.cos(fire_angle) * self.radius
            fy = self.y + math.sin(fire_angle) * self.radius
            particles.burst(fx, fy, 7, 90, 0.2, self.color, 2)
            particles.emit(fx, fy,
                          math.cos(fire_angle) * 120, math.sin(fire_angle) * 120,
                          0.08, WHITE, 1.5)

            if self.is_boss or self.enemy_type == 'miniboss':
                for offset in [-0.3, 0.3]:
                    a2 = fire_angle + offset
                    proj2 = Projectile(
                        self.x + math.cos(a2) * self.radius,
                        self.y + math.sin(a2) * self.radius,
                        math.cos(a2) * proj_speed,
                        math.sin(a2) * proj_speed,
                        self.damage * 0.6, 'enemy', 'laser', color=self.color
                    )
                    projectiles.append(proj2)

    def take_hit(self, damage, particles):
        self.hp -= damage
        self.hit_flash = 1.0
        self.aggro = True
        # Impact sparks — directional burst
        particles.burst(self.x, self.y, 12, 120, 0.25, self.color, 2)
        particles.burst(self.x, self.y, 4, 60, 0.15, WHITE, 1.5)  # white spark core
        if self.hp <= 0:
            self.alive = False
            # Big multi-layered explosion
            if self.is_boss or self.enemy_type == 'miniboss':
                # Massive explosion for bosses
                particles.burst(self.x, self.y, 100, 300, 1.2, self.color, 4)
                particles.burst(self.x, self.y, 60, 200, 0.9, NEON_YELLOW, 3)
                particles.burst(self.x, self.y, 40, 250, 0.7, WHITE, 2)
                particles.burst(self.x, self.y, 30, 150, 1.5, NEON_ORANGE, 5, glow=True)
                # Debris ring
                for _ in range(20):
                    angle = random.uniform(0, math.pi * 2)
                    spd = random.uniform(80, 200)
                    particles.emit(
                        self.x, self.y,
                        math.cos(angle) * spd, math.sin(angle) * spd,
                        random.uniform(0.5, 1.5),
                        random.choice([self.color, self.body_color, NEON_YELLOW]),
                        random.uniform(2, 5)
                    )
            elif self.enemy_type == 'elite':
                particles.burst(self.x, self.y, 50, 220, 0.9, self.color, 3)
                particles.burst(self.x, self.y, 30, 180, 0.6, NEON_YELLOW, 2.5)
                particles.burst(self.x, self.y, 15, 140, 0.8, WHITE, 2)
            else:
                # Normal enemy explosion
                particles.burst(self.x, self.y, 35, 180, 0.7, self.color, 3)
                particles.burst(self.x, self.y, 20, 130, 0.5, NEON_YELLOW, 2)
                particles.burst(self.x, self.y, 8, 100, 0.4, WHITE, 1.5)

    def draw(self, surface, camera, time):
        sx, sy = camera.world_to_screen(self.x, self.y)

        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        r = self.radius * camera.zoom

        if self.is_boss or self.enemy_type == 'miniboss':
            pts = [
                (sx + cos_a * r * 1.5, sy + sin_a * r * 1.5),
                (sx + cos_a * (-r * 0.3) - sin_a * (-r * 1.2),
                 sy + sin_a * (-r * 0.3) + cos_a * (-r * 1.2)),
                (sx + cos_a * (-r * 0.8) - sin_a * (-r * 0.5),
                 sy + sin_a * (-r * 0.8) + cos_a * (-r * 0.5)),
                (sx + cos_a * (-r * 1.2), sy + sin_a * (-r * 1.2)),
                (sx + cos_a * (-r * 0.8) - sin_a * (r * 0.5),
                 sy + sin_a * (-r * 0.8) + cos_a * (r * 0.5)),
                (sx + cos_a * (-r * 0.3) - sin_a * (r * 1.2),
                 sy + sin_a * (-r * 0.3) + cos_a * (r * 1.2)),
            ]
        else:
            pts = [
                (sx + cos_a * r * 1.3, sy + sin_a * r * 1.3),
                (sx - sin_a * r * 0.8, sy + cos_a * r * 0.8),
                (sx - cos_a * r * 0.8, sy - sin_a * r * 0.8),
                (sx + sin_a * r * 0.8, sy - cos_a * r * 0.8),
            ]

        body_c = self.body_color
        if self.hit_flash > 0:
            f = self.hit_flash
            body_c = (
                int(lerp(body_c[0], 255, f)),
                int(lerp(body_c[1], 255, f)),
                int(lerp(body_c[2], 255, f)),
            )

        pygame.draw.polygon(surface, body_c, pts)
        pygame.draw.polygon(surface, self.color, pts, 2)

        # Engine glow on back of enemy
        engine_x = sx - cos_a * r * 0.7
        engine_y = sy - sin_a * r * 0.7
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        engine_r = 3 + min(4, speed / 50) + math.sin(time * 12) * 1.5
        engine_c = safe_color(self.color[0] * 0.6, self.color[1] * 0.4, self.color[2] * 0.2)
        pygame.draw.circle(surface, engine_c, (int(engine_x), int(engine_y)), max(1, int(engine_r)))

        # Eye glow
        eye_x = sx + cos_a * r * 0.4
        eye_y = sy + sin_a * r * 0.4
        glow = 0.5 + 0.5 * math.sin(time * 5)
        draw_glow_circle(surface, self.color, (eye_x, eye_y),
                        3 + (2 if self.is_boss else 0), 10, int(40 + 30 * glow))

        # Damage smoke when low HP
        hp_ratio = self.hp / max(1, self.max_hp)
        if hp_ratio < 0.5:
            smoke_intensity = 1.0 - hp_ratio * 2  # 0 at 50%, 1 at 0%
            if random.random() < smoke_intensity * 0.4:
                smoke_c = safe_color(80 + random.randint(0, 40), 40 + random.randint(0, 20), 10)
                pygame.draw.circle(surface, smoke_c,
                                 (int(sx + random.uniform(-r * 0.5, r * 0.5)),
                                  int(sy + random.uniform(-r * 0.5, r * 0.5))),
                                 random.randint(1, 3))
            # Sparking when critical
            if hp_ratio < 0.25 and random.random() < 0.15:
                spark_x = sx + random.uniform(-r, r)
                spark_y = sy + random.uniform(-r, r)
                pygame.draw.circle(surface, NEON_YELLOW, (int(spark_x), int(spark_y)), 1)

        if self.hp < self.max_hp:
            bar_w = r * 2
            draw_bar(surface, int(sx - bar_w / 2), int(sy - r - 10),
                    int(bar_w), 4, self.hp / self.max_hp,
                    self.color, (20, 20, 30), (60, 60, 80))

        if self.enemy_type == 'boss':
            draw_text(surface, "BOSS", int(sx), int(sy - r - 20),
                     NEON_PINK, 12, center=True, font_name="consolas")
        elif self.enemy_type == 'miniboss':
            draw_text(surface, "MINIBOSS", int(sx), int(sy - r - 20),
                     NEON_CYAN, 10, center=True, font_name="consolas")
        elif self.enemy_type == 'elite':
            draw_text(surface, "ELITE", int(sx), int(sy - r - 20),
                     NEON_YELLOW, 10, center=True, font_name="consolas")


# ═════════════════════════════════════════════════════════════════════════════
#  DRONE — friendly AI drones spawned by drone bay modules
# ═════════════════════════════════════════════════════════════════════════════
class Drone:
    def __init__(self, x, y, drone_type, owner_module):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.drone_type = drone_type  # 'gun', 'kamikaze', 'laser'
        self.owner_module = owner_module  # to track respawns
        self.hp = 20 if drone_type == 'kamikaze' else 35
        self.max_hp = self.hp
        self.radius = 6
        self.alive = True
        self.angle = 0.0
        self.fire_cooldown = 0.0
        self.orbit_angle = random.uniform(0, math.pi * 2)
        self.exploded = False
        # Miner-specific state
        self.mine_target = None
        self.mine_state = 'idle'  # 'idle', 'going', 'mining', 'returning'
        self.cargo = 0.0
        self.mine_timer = 0.0

    def update(self, dt, ship, enemies, projectiles, particles, active_beams, asteroids=None):
        if not self.alive:
            return

        # Mining drones have their own logic
        if self.drone_type == 'miner':
            self._mine_update(dt, ship, asteroids or [], particles)
            return

        # Prefer designated target if set + alive + in range + can take damage
        target = getattr(ship, 'drone_target', None)
        best_enemy = None
        if (target is not None and getattr(target, 'alive', False)
                and hasattr(target, 'take_hit')
                and dist(self.x, self.y, target.x, target.y) < 800):
            best_enemy = target
        else:
            # Auto-target nearest
            best_d = 350
            for e in enemies:
                if not e.alive:
                    continue
                d = dist(self.x, self.y, e.x, e.y)
                if d < best_d:
                    best_d = d
                    best_enemy = e

        self.fire_cooldown = max(0, self.fire_cooldown - dt)

        if best_enemy:
            # Engage enemy based on type
            dx = best_enemy.x - self.x
            dy = best_enemy.y - self.y
            d = max(1, math.sqrt(dx * dx + dy * dy))
            self.angle = math.atan2(dy, dx)

            if self.drone_type == 'kamikaze':
                # Ram the enemy
                self.vx += (dx / d) * 600 * dt
                self.vy += (dy / d) * 600 * dt
                if d < best_enemy.radius + 10:
                    # Explode!
                    best_enemy.take_hit(40, particles)
                    self.alive = False
                    self.exploded = True
                    particles.burst(self.x, self.y, 30, 200, 0.6, NEON_RED, 3)
                    particles.burst(self.x, self.y, 15, 150, 0.4, NEON_YELLOW, 2)
                    return
            elif self.drone_type == 'gun':
                # Orbit and shoot
                ideal_d = 180
                if d > ideal_d + 30:
                    self.vx += (dx / d) * 300 * dt
                    self.vy += (dy / d) * 300 * dt
                elif d < ideal_d - 30:
                    self.vx -= (dx / d) * 200 * dt
                    self.vy -= (dy / d) * 200 * dt
                else:
                    # Strafe
                    self.vx += (-dy / d) * 150 * dt
                    self.vy += (dx / d) * 150 * dt
                if self.fire_cooldown <= 0:
                    self.fire_cooldown = 0.4
                    proj = Projectile(
                        self.x, self.y,
                        math.cos(self.angle) * LASER_SPEED * 0.7,
                        math.sin(self.angle) * LASER_SPEED * 0.7,
                        6, 'player', 'bullet', color=NEON_YELLOW
                    )
                    projectiles.append(proj)
            elif self.drone_type == 'laser':
                # Stay at medium range and fire beams
                ideal_d = 220
                if d > ideal_d + 30:
                    self.vx += (dx / d) * 250 * dt
                    self.vy += (dy / d) * 250 * dt
                elif d < ideal_d - 30:
                    self.vx -= (dx / d) * 200 * dt
                    self.vy -= (dy / d) * 200 * dt
                if self.fire_cooldown <= 0:
                    self.fire_cooldown = 0.8
                    beam_range = 350
                    bx = math.cos(self.angle)
                    by = math.sin(self.angle)
                    active_beams.append({
                        'sx': self.x + bx * 8, 'sy': self.y + by * 8,
                        'ex': self.x + bx * beam_range, 'ey': self.y + by * beam_range,
                        'color': NEON_PINK, 'life': 0.15, 'width': 1,
                    })
                    best_enemy.take_hit(12, particles)
        else:
            # Orbit the player (or sprint to catch up if far)
            self.orbit_angle += dt * 1.5
            orbit_r = 60
            target_x = ship.x + math.cos(self.orbit_angle) * orbit_r
            target_y = ship.y + math.sin(self.orbit_angle) * orbit_r
            dx = target_x - self.x
            dy = target_y - self.y
            d = max(1, math.sqrt(dx * dx + dy * dy))
            # If far from player, fly directly + match player velocity to catch up
            if d > 200:
                dx = ship.x - self.x
                dy = ship.y - self.y
                d = max(1, math.sqrt(dx * dx + dy * dy))
                self.vx = (dx / d) * 800 + ship.vx
                self.vy = (dy / d) * 800 + ship.vy
            else:
                self.vx += (dx / d) * 400 * dt
                self.vy += (dy / d) * 400 * dt
            self.angle = math.atan2(self.vy, self.vx) if d > 5 else self.angle

        # Drag and speed cap (boost cap when catching up to player)
        ship_d = dist(self.x, self.y, ship.x, ship.y)
        catch_up = ship_d > 200
        self.vx *= 0.93 if not catch_up else 1.0
        self.vy *= 0.93 if not catch_up else 1.0
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        base_max = 400 if self.drone_type == 'kamikaze' else 280
        ship_speed = math.sqrt(ship.vx ** 2 + ship.vy ** 2)
        max_spd = max(base_max, ship_speed + 200)  # always faster than the player
        if speed > max_spd:
            self.vx = self.vx / speed * max_spd
            self.vy = self.vy / speed * max_spd

        self.x += self.vx * dt
        self.y += self.vy * dt

    def _mine_update(self, dt, ship, asteroids, particles):
        max_cargo = 20.0
        # Pick target if needed
        if self.mine_state == 'idle' or (self.mine_target and self.mine_target.depleted):
            self.mine_target = None
            best_d = 600
            for a in asteroids:
                if a.depleted:
                    continue
                d = dist(self.x, self.y, a.x, a.y)
                if d < best_d:
                    best_d = d
                    self.mine_target = a
            if self.mine_target:
                self.mine_state = 'going'
            else:
                # Orbit ship if no asteroids
                self.orbit_angle += dt * 1.5
                tx = ship.x + math.cos(self.orbit_angle) * 60
                ty = ship.y + math.sin(self.orbit_angle) * 60
                self._fly_to(tx, ty, dt, 350, ship)
                return

        if self.mine_state == 'going' and self.mine_target:
            d = dist(self.x, self.y, self.mine_target.x, self.mine_target.y)
            if d < self.mine_target.radius + 5:
                self.mine_state = 'mining'
                self.mine_timer = 0
            else:
                self._fly_to(self.mine_target.x, self.mine_target.y, dt, 280, ship)

        elif self.mine_state == 'mining' and self.mine_target:
            self.mine_timer += dt
            rate = max_cargo / 2.5  # mine 20 ore in 2.5 seconds
            mined = min(rate * dt, self.mine_target.ore, max_cargo - self.cargo)
            self.cargo += mined
            self.mine_target.ore -= mined
            if random.random() < 0.4:
                particles.emit(self.mine_target.x + random.uniform(-10, 10),
                              self.mine_target.y + random.uniform(-10, 10),
                              random.uniform(-30, 30), random.uniform(-30, 30),
                              0.3, ORE_COLOR, 1.5)
            if self.cargo >= max_cargo or self.mine_target.ore <= 0:
                self.mine_state = 'returning'
                if self.mine_target.ore <= 0:
                    self.mine_target.depleted = True

        elif self.mine_state == 'returning':
            d = dist(self.x, self.y, ship.x, ship.y)
            if d < 25:
                space = ship.ore_capacity - ship.ore
                ship.ore += min(self.cargo, space)
                self.cargo = 0
                self.mine_state = 'idle'
            else:
                self._fly_to(ship.x, ship.y, dt, 350, ship)

    def _fly_to(self, tx, ty, dt, max_spd, ship=None):
        dx, dy = tx - self.x, ty - self.y
        d = max(1, math.sqrt(dx * dx + dy * dy))
        # Sprint when far away
        if d > 200:
            self.vx = (dx / d) * max(800, max_spd * 2)
            self.vy = (dy / d) * max(800, max_spd * 2)
            if ship:
                self.vx += ship.vx
                self.vy += ship.vy
        else:
            self.vx += (dx / d) * 350 * dt
            self.vy += (dy / d) * 350 * dt
            self.vx *= 0.93
            self.vy *= 0.93
        sp = math.sqrt(self.vx ** 2 + self.vy ** 2)
        ship_spd = math.sqrt(ship.vx ** 2 + ship.vy ** 2) if ship else 0
        cap = max(max_spd, ship_spd + 200)
        if sp > cap:
            self.vx = self.vx / sp * cap
            self.vy = self.vy / sp * cap
        self.angle = math.atan2(self.vy, self.vx)
        self.x += self.vx * dt
        self.y += self.vy * dt

    def take_hit(self, damage, particles):
        self.hp -= damage
        particles.burst(self.x, self.y, 4, 60, 0.2, self.color(), 1.5)
        if self.hp <= 0:
            self.alive = False
            particles.burst(self.x, self.y, 15, 100, 0.3, self.color(), 2)

    def color(self):
        if self.drone_type == 'kamikaze':
            return NEON_RED
        if self.drone_type == 'laser':
            return NEON_PINK
        if self.drone_type == 'miner':
            return ORE_COLOR
        return NEON_YELLOW

    def draw(self, surface, camera, time):
        if not self.alive:
            return
        sx, sy = camera.world_to_screen(self.x, self.y)
        z = camera.zoom
        r = self.radius * z
        c = self.color()
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        # Small triangle
        pts = [
            (sx + cos_a * r * 1.5, sy + sin_a * r * 1.5),
            (sx - cos_a * r - sin_a * r * 0.8, sy - sin_a * r + cos_a * r * 0.8),
            (sx - cos_a * r + sin_a * r * 0.8, sy - sin_a * r - cos_a * r * 0.8),
        ]
        pygame.draw.polygon(surface, (30, 30, 30), pts)
        pygame.draw.polygon(surface, c, pts, 1)
        draw_glow_circle(surface, c, (sx, sy), max(1, int(2 * z)), max(3, int(6 * z)), 40)


# ═════════════════════════════════════════════════════════════════════════════
#  ESCORT NPC — friendly ship you protect during escort missions
# ═════════════════════════════════════════════════════════════════════════════
class EscortNPC:
    def __init__(self, x, y, dest_x, dest_y):
        self.x = x
        self.y = y
        self.dest_x = dest_x
        self.dest_y = dest_y
        self.vx = 0.0
        self.vy = 0.0
        self.hp = 150
        self.max_hp = 150
        self.radius = 18
        self.alive = True
        self.angle = 0.0
        self.hit_flash = 0.0
        self.reached_dest = False

    def update(self, dt, particles):
        if not self.alive:
            return
        self.hit_flash = max(0, self.hit_flash - dt * 5)
        dx = self.dest_x - self.x
        dy = self.dest_y - self.y
        d = math.sqrt(dx * dx + dy * dy)
        if d < 150:
            self.reached_dest = True
            self.vx *= 0.95
            self.vy *= 0.95
        else:
            speed = 90.0
            self.vx += (dx / d) * speed * dt * 2
            self.vy += (dy / d) * speed * dt * 2
            self.vx *= 0.97
            self.vy *= 0.97
            sp = math.sqrt(self.vx ** 2 + self.vy ** 2)
            if sp > speed:
                self.vx = self.vx / sp * speed
                self.vy = self.vy / sp * speed
            self.angle = math.atan2(self.vy, self.vx)
        self.x += self.vx * dt
        self.y += self.vy * dt

    def take_hit(self, damage, particles):
        self.hp -= damage
        self.hit_flash = 1.0
        particles.burst(self.x, self.y, 6, 80, 0.2, NEON_CYAN, 2)
        if self.hp <= 0:
            self.alive = False
            particles.burst(self.x, self.y, 50, 200, 0.8, NEON_CYAN, 4)

    def draw(self, surface, camera, time):
        if not self.alive:
            return
        sx, sy = camera.world_to_screen(self.x, self.y)
        z = camera.zoom
        r = self.radius * z
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        # Rounded cargo ship shape
        pts = [
            (sx + cos_a * r * 1.3, sy + sin_a * r * 1.3),
            (sx + cos_a * r * 0.5 - sin_a * r * 0.8, sy + sin_a * r * 0.5 + cos_a * r * 0.8),
            (sx - cos_a * r * 0.9 - sin_a * r * 0.9, sy - sin_a * r * 0.9 + cos_a * r * 0.9),
            (sx - cos_a * r * 0.9 + sin_a * r * 0.9, sy - sin_a * r * 0.9 - cos_a * r * 0.9),
            (sx + cos_a * r * 0.5 + sin_a * r * 0.8, sy + sin_a * r * 0.5 - cos_a * r * 0.8),
        ]
        body_c = (40, 60, 90)
        if self.hit_flash > 0:
            body_c = safe_color(lerp(body_c[0], 255, self.hit_flash),
                               lerp(body_c[1], 255, self.hit_flash),
                               lerp(body_c[2], 255, self.hit_flash))
        pygame.draw.polygon(surface, body_c, pts)
        pygame.draw.polygon(surface, NEON_CYAN, pts, 2)
        # "ESCORT" label
        draw_text(surface, "ALLY", int(sx), int(sy - r - 14), NEON_CYAN, 10, center=True)
        # HP bar
        if self.hp < self.max_hp:
            draw_bar(surface, int(sx - r), int(sy - r - 5), int(r * 2), 4,
                    self.hp / self.max_hp, NEON_CYAN, (20, 20, 30))


# ═════════════════════════════════════════════════════════════════════════════
#  PICKUP
# ═════════════════════════════════════════════════════════════════════════════
class Pickup:
    def __init__(self, x, y, pickup_type='credits', value=25):
        self.x = x
        self.y = y
        self.pickup_type = pickup_type
        self.value = value
        self.alive = True
        self.life = 20.0
        self.bob_offset = random.uniform(0, math.pi * 2)

    def update(self, dt, ship: Ship, particles: ParticleSystem, audio):
        self.life -= dt
        if self.life <= 0:
            self.alive = False
            return

        dx = ship.x - self.x
        dy = ship.y - self.y
        d = math.sqrt(dx * dx + dy * dy)

        if d < 100:
            pull = (100 - d) / 100 * 300
            self.x += (dx / max(1, d)) * pull * dt
            self.y += (dy / max(1, d)) * pull * dt

        if d < 25:
            self.alive = False
            if self.pickup_type == 'credits':
                ship.credits += self.value
                particles.burst(self.x, self.y, 8, 60, 0.3, NEON_YELLOW, 2)
            elif self.pickup_type == 'fuel':
                ship.fuel = min(ship.fuel_capacity, ship.fuel + self.value)
                particles.burst(self.x, self.y, 8, 60, 0.3, NEON_ORANGE, 2)
            elif self.pickup_type == 'repair':
                for m in ship.modules:
                    if m.defn.id == "core":
                        m.hp = min(m.max_hp, m.hp + self.value)
                particles.burst(self.x, self.y, 8, 60, 0.3, NEON_GREEN, 2)
            audio.play('pickup', 0.4)

    def draw(self, surface, camera, time):
        sx, sy = camera.world_to_screen(self.x, self.y)
        bob = math.sin(time * 3 + self.bob_offset) * 4

        if self.pickup_type == 'credits':
            color = NEON_YELLOW
            symbol = "$"
        elif self.pickup_type == 'fuel':
            color = NEON_ORANGE
            symbol = "F"
        else:
            color = NEON_GREEN
            symbol = "+"

        alpha = min(1.0, self.life / 3.0)
        z = camera.zoom
        draw_glow_circle(surface, color, (sx, sy + bob), max(3, int(6 * z)), max(8, int(16 * z)), int(50 * alpha))
        draw_text(surface, symbol, int(sx), int(sy + bob), color, max(8, int(10 * z)), center=True)


# ═════════════════════════════════════════════════════════════════════════════
#  MISSIONS
# ═════════════════════════════════════════════════════════════════════════════
MISSION_TYPES = [
    # (name_template, type, base_reward, description_template)
    ("Pirate Hunt", "kill", 150, "Destroy {count} enemies in sector [{sx},{sy}]."),
    ("Sector Sweep", "kill", 250, "Clear all patrols in sector [{sx},{sy}]."),
    ("Mining Run", "mine", 120, "Mine {count} fuel from asteroids."),
    ("Deep Recon", "explore", 200, "Discover {count} new sectors."),
    ("Bounty Hunt", "boss", 500, "Destroy the elite in sector [{sx},{sy}]."),
]

class Mission:
    def __init__(self, difficulty, rng_seed):
        rng = random.Random(rng_seed)
        self.difficulty = difficulty
        self.reward = 0
        self.description = ""
        self.name = ""
        self.active = False
        self.completed = False
        self.failed = False

        # Pick mission type scaled by difficulty
        if difficulty >= 5 and rng.random() < 0.3:
            mtype = 'boss'
        elif difficulty >= 3 and rng.random() < 0.25:
            mtype = 'kill_many'
        elif difficulty >= 2 and rng.random() < 0.35:
            mtype = rng.choice(['delivery', 'escort'])
        else:
            mtype = rng.choice(['kill', 'mine', 'explore', 'delivery'])

        scale = 1.0 + difficulty * 0.4
        # Target sector: further away for harder missions
        dist_range = 2 + difficulty
        self.target_sx = rng.randint(-dist_range, dist_range)
        self.target_sy = rng.randint(-dist_range, dist_range)

        if mtype == 'kill':
            self.type = 'kill'
            self.target_count = 3 + difficulty * 2
            self.current_count = 0
            self.reward = int(100 * scale + self.target_count * 15)
            self.name = f"Pirate Hunt Lv.{difficulty}"
            self.description = f"Destroy {self.target_count} enemies near sector [{self.target_sx},{self.target_sy}]."
        elif mtype == 'kill_many':
            self.type = 'kill'
            self.target_count = 8 + difficulty * 3
            self.current_count = 0
            self.reward = int(200 * scale + self.target_count * 12)
            self.name = f"Sector Sweep Lv.{difficulty}"
            self.description = f"Destroy {self.target_count} enemies anywhere."
            self.target_sx = 0
            self.target_sy = 0
        elif mtype == 'mine':
            self.type = 'mine'
            self.target_count = int(30 + difficulty * 20)
            self.current_count = 0
            self.reward = int(80 * scale + self.target_count * 2)
            self.name = f"Mining Contract Lv.{difficulty}"
            self.description = f"Collect {self.target_count} fuel from asteroids."
        elif mtype == 'explore':
            self.type = 'explore'
            self.target_count = 3 + difficulty
            self.current_count = 0
            self.reward = int(150 * scale + self.target_count * 30)
            self.name = f"Deep Recon Lv.{difficulty}"
            self.description = f"Discover {self.target_count} new sectors."
        elif mtype == 'boss':
            self.type = 'boss'
            self.target_count = 1
            self.current_count = 0
            self.reward = int(400 * scale)
            self.name = f"Bounty Hunt Lv.{difficulty}"
            self.description = f"Kill a boss-class enemy near sector [{self.target_sx},{self.target_sy}]."
        elif mtype == 'delivery':
            self.type = 'delivery'
            self.target_count = 1
            self.current_count = 0
            self.reward = int(180 * scale + 30 * difficulty)
            self.has_package = False
            self.target_station_name = None  # set when accepted
            self.name = f"Delivery Contract Lv.{difficulty}"
            self.description = f"Deliver package — destination station to be assigned."
        elif mtype == 'escort':
            self.type = 'escort'
            self.target_count = 1
            self.current_count = 0
            self.reward = int(350 * scale + 50 * difficulty)
            self.escort_spawned = False
            self.escort_alive = False
            self.name = f"Escort Mission Lv.{difficulty}"
            self.description = f"Protect an NPC ship to sector [{self.target_sx},{self.target_sy}]."

    @property
    def progress_text(self):
        return f"{self.current_count}/{self.target_count}"

    @property
    def is_done(self):
        return self.current_count >= self.target_count


# ═════════════════════════════════════════════════════════════════════════════
#  WORLD (exploration-based)
# ═════════════════════════════════════════════════════════════════════════════
class World:
    def __init__(self):
        self.sectors = SectorManager()
        self.asteroids: List[Asteroid] = []
        self.enemies: List[Enemy] = []
        self.projectiles: List[Projectile] = []
        self.probes: List[MiningProbe] = []
        self.pickups: List[Pickup] = []
        self.buildings: List[Building] = []
        self.drones: List[Drone] = []
        self.escort_npc: Optional[EscortNPC] = None
        self._active_beams: List[dict] = []
        # Per-remote-player mining loot {pid: [credits, ore]}
        self.player_loot = {}
        self.game_time = 0.0
        self.void_titan_killed = False
        self.titan_victory_shown = False
        self.on_kill_callback = None  # set by main.py for multiplayer scoring

        # Missions
        self.active_mission: Optional[Mission] = None
        self.missions_completed = 0
        self.available_missions: List[Mission] = []
        self._generate_missions()

        # Sector transition tracking
        self._last_sector_coord = (0, 0)
        self._loaded_asteroid_sectors: set = set()

        # Initialize starting area
        self.sectors.update_streaming(0, 0, 0)
        self._sync_entities()

    def _generate_missions(self):
        """Generate 3 available missions at current difficulty."""
        self.available_missions.clear()
        difficulty = self.missions_completed + 1
        for i in range(3):
            seed = hash((self.missions_completed, i, self.game_time))
            m = Mission(difficulty, seed)
            self.available_missions.append(m)

    def accept_mission(self, index) -> Optional[str]:
        """Accept a mission from the available list. Returns message."""
        if self.active_mission and not self.active_mission.completed:
            return "Already on a mission! Complete or abandon it first."
        if index < 0 or index >= len(self.available_missions):
            return None
        m = self.available_missions[index]
        self.active_mission = m
        m.active = True
        m.current_count = 0
        # For delivery, pick a real named station near the target sector
        if m.type == 'delivery':
            best_station = None
            best_d = float('inf')
            target_x = m.target_sx * SECTOR_SIZE + SECTOR_SIZE / 2
            target_y = m.target_sy * SECTOR_SIZE + SECTOR_SIZE / 2
            # Search wider radius — load sectors around the target
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    sec = self.sectors.get_sector((m.target_sx + dx, m.target_sy + dy))
                    if sec.station:
                        d = dist(target_x, target_y, sec.station.x, sec.station.y)
                        if d < best_d:
                            best_d = d
                            best_station = sec.station
                            sec_coord = (m.target_sx + dx, m.target_sy + dy)
            if best_station:
                m.target_station_name = best_station.name
                m.target_station_x = best_station.x
                m.target_station_y = best_station.y
                # Update target sector to the station's actual sector
                m.target_sx = int(math.floor(best_station.x / SECTOR_SIZE))
                m.target_sy = int(math.floor(best_station.y / SECTOR_SIZE))
                m.description = f"Deliver to {best_station.name} [{m.target_sx},{m.target_sy}]"
        return f"Mission accepted: {m.name}"

    def abandon_mission(self) -> Optional[str]:
        if not self.active_mission or self.active_mission.completed:
            return "No active mission."
        self.active_mission.failed = True
        self.active_mission = None
        return "Mission abandoned."

    def complete_mission(self, ship) -> Optional[str]:
        """Turn in a completed mission for reward."""
        if not self.active_mission or not self.active_mission.is_done:
            return None
        reward = self.active_mission.reward
        name = self.active_mission.name
        ship.credits += reward
        self.active_mission.completed = True
        self.missions_completed += 1
        self.active_mission = None
        self._generate_missions()  # refresh available missions
        return f"{name} COMPLETE! +${reward}"

    def _update_escort_mission(self, dt, ship, particles):
        """Stub - escort missions not active in this version."""
        pass

    def track_delivery(self, ship):
        """Stub - delivery missions not active in this version."""
        pass

    def _update_drones(self, dt, ship, particles):
        """Spawn and update AI drones from drone bay modules."""
        # Count alive drones per owner module
        counts = {}
        for d in self.drones:
            if d.alive:
                counts[id(d.owner_module)] = counts.get(id(d.owner_module), 0) + 1

        # Spawn missing drones for each drone bay module
        for m in ship.drone_modules:
            key = id(m)
            target = m.defn.drone_count + (m.level - 1)  # +1 per upgrade level
            current = counts.get(key, 0)
            if current < target:
                # Spawn one drone per frame until full
                angle = random.uniform(0, math.pi * 2)
                d = Drone(ship.x + math.cos(angle) * 30, ship.y + math.sin(angle) * 30,
                         m.defn.drone_type, m)
                self.drones.append(d)

        # Update all drones
        for d in self.drones:
            d.update(dt, ship, self.enemies, self.projectiles, particles, self._active_beams, self.asteroids)

        # Remove dead drones
        self.drones = [d for d in self.drones if d.alive]
        """Spawn/update escort NPC for escort missions."""
        m = self.active_mission
        if not m or m.completed or m.type != 'escort':
            # Clean up escort if no longer needed
            if self.escort_npc:
                self.escort_npc = None
            return
        # Spawn the NPC near the player once
        if not m.escort_spawned:
            dest_x = m.target_sx * SECTOR_SIZE + SECTOR_SIZE / 2
            dest_y = m.target_sy * SECTOR_SIZE + SECTOR_SIZE / 2
            # Spawn near player
            self.escort_npc = EscortNPC(
                ship.x + 100, ship.y, dest_x, dest_y
            )
            m.escort_spawned = True
            m.escort_alive = True
        # Update the NPC
        if self.escort_npc:
            self.escort_npc.update(dt, particles)
            # Check if enemies are hitting the escort
            for p in self.projectiles:
                if p.owner == 'enemy' and p.alive and self.escort_npc.alive:
                    if dist(p.x, p.y, self.escort_npc.x, self.escort_npc.y) < self.escort_npc.radius:
                        self.escort_npc.take_hit(p.damage, particles)
                        p.alive = False
            # Fail mission if escort dies
            if not self.escort_npc.alive:
                m.failed = True
                m.current_count = -1  # signal failed state
            # Complete mission if escort reaches destination
            elif self.escort_npc.reached_dest:
                m.current_count = m.target_count

    def track_delivery(self, ship):
        """Check if player is delivering a package at a station."""
        m = self.active_mission
        if not m or m.completed or m.type != 'delivery':
            return
        # Player is docking at target sector
        cur_coord = self.sectors.get_sector_coord(ship.x, ship.y)
        if cur_coord == (m.target_sx, m.target_sy):
            m.current_count = m.target_count

    def track_kill(self, enemy):
        """Call when an enemy is killed to update mission + multiplayer scoring."""
        # Mission tracking
        if self.active_mission and not self.active_mission.completed:
            m = self.active_mission
            if m.type == 'kill':
                m.current_count += 1
            elif m.type == 'boss' and (enemy.is_boss or enemy.enemy_type in ('boss', 'miniboss')):
                m.current_count += 1
        # Multiplayer kill callback (host scores)
        if self.on_kill_callback:
            self.on_kill_callback(enemy, 0)  # 0 = host pid

    def track_mine(self, amount):
        """Call when fuel is mined to update mission progress."""
        if not self.active_mission or self.active_mission.completed:
            return
        if self.active_mission.type == 'mine':
            self.active_mission.current_count += int(amount)

    def track_explore(self, new_count):
        """Call with total discovered sectors to update mission progress."""
        if not self.active_mission or self.active_mission.completed:
            return
        if self.active_mission.type == 'explore':
            self.active_mission.current_count = new_count

    def _sync_entities(self):
        """Sync asteroids from loaded sectors. Enemies spawn on patrol detection."""
        for sector in self.sectors.get_loaded_sectors():
            coord = sector.coord
            if coord not in self._loaded_asteroid_sectors:
                self._loaded_asteroid_sectors.add(coord)
                rng = random.Random(sector.seed + 999)
                for ad in sector.asteroid_data:
                    self.asteroids.append(Asteroid(ad['x'], ad['y']))

    def _cleanup_distant_entities(self, ship_x, ship_y):
        """Remove entities far from the player (from unloaded sectors)."""
        max_dist = SECTOR_SIZE * 3
        self.asteroids = [a for a in self.asteroids
                         if dist(a.x, a.y, ship_x, ship_y) < max_dist]
        self.enemies = [e for e in self.enemies if e.alive and
                       dist(e.x, e.y, ship_x, ship_y) < max_dist]
        self.pickups = [p for p in self.pickups if p.alive and
                       dist(p.x, p.y, ship_x, ship_y) < max_dist]

        # Clean up asteroid sector tracking
        loaded_coords = {s.coord for s in self.sectors.get_loaded_sectors()}
        self._loaded_asteroid_sectors &= loaded_coords

    def _check_patrol_spawns(self, ship: Ship, particles: ParticleSystem):
        """Check if player is near any patrol groups and spawn enemies."""
        for sector in self.sectors.get_loaded_sectors():
            for pg in sector.patrol_groups:
                if pg.spawned or pg.cleared:
                    # Check if cleared patrol should respawn
                    if pg.cleared and (self.game_time - pg.clear_time) > PATROL_RESPAWN_TIME:
                        pg.cleared = False
                        pg.spawned = False
                    else:
                        continue

                d = dist(ship.x, ship.y, pg.cx, pg.cy)
                if d < PATROL_DETECT_RANGE + pg.patrol_radius:
                    pg.spawned = True
                    rng = random.Random(sector.seed + hash((pg.cx, pg.cy)))
                    for i in range(pg.count):
                        angle = rng.uniform(0, math.pi * 2)
                        r = rng.uniform(30, pg.patrol_radius)
                        ex = pg.cx + math.cos(angle) * r
                        ey = pg.cy + math.sin(angle) * r
                        # Determine enemy type
                        if pg.is_boss and i == 0:
                            etype = 'boss'
                        elif pg.tier >= 3 and i == 1 and pg.count >= 4:
                            etype = 'miniboss'
                        elif pg.tier >= 2 and rng.random() < 0.25:
                            etype = 'elite'
                        else:
                            etype = 'normal'
                        enemy = Enemy(ex, ey, tier=pg.tier, enemy_type=etype)
                        enemy.patrol_cx = pg.cx
                        enemy.patrol_cy = pg.cy
                        self.enemies.append(enemy)

    def _check_patrol_cleared(self):
        """Check if all enemies from a patrol are dead, mark it cleared."""
        for sector in self.sectors.get_loaded_sectors():
            for pg in sector.patrol_groups:
                if not pg.spawned or pg.cleared:
                    continue
                # Check if any enemies near this patrol are still alive
                alive_nearby = any(
                    e.alive and dist(e.patrol_cx, e.patrol_cy, pg.cx, pg.cy) < 50
                    for e in self.enemies
                    if hasattr(e, 'patrol_cx')
                )
                if not alive_nearby:
                    pg.cleared = True
                    pg.clear_time = self.game_time

    def _check_poi_discovery(self, ship: Ship, particles: ParticleSystem, audio):
        """Discover nearby POIs."""
        for sector in self.sectors.get_loaded_sectors():
            for poi in sector.pois:
                if poi.discovered:
                    continue
                d = dist(ship.x, ship.y, poi.x, poi.y)
                if d < POI_DETECT_RANGE:
                    poi.discovered = True
                    audio.play('discover', 0.5)

    def interact_poi(self, ship: Ship, particles: ParticleSystem, audio) -> Optional[str]:
        """Try to interact with nearest POI. Returns message or None."""
        # Check anomaly research first
        has_research = any(m.defn.id == 'research' for m in ship.modules if m.active)
        for sector in self.sectors.get_loaded_sectors():
            for poi in sector.pois:
                if poi.poi_type == 'anomaly' and poi.discovered and not poi.researched:
                    d = dist(ship.x, ship.y, poi.x, poi.y)
                    if d < poi.effect_radius:
                        if not has_research:
                            return "Need a Research Center module to study anomalies!"
                        # Start/continue research
                        return self._research_anomaly(poi, ship, particles, audio)

        for sector in self.sectors.get_loaded_sectors():
            for poi in sector.pois:
                if not poi.discovered or poi.looted:
                    continue
                if poi.poi_type == 'anomaly':
                    continue
                d = dist(ship.x, ship.y, poi.x, poi.y)
                if d < poi.interaction_range:
                    poi.looted = True
                    ship.credits += poi.loot_credits
                    if poi.loot_fuel > 0:
                        ship.fuel = min(ship.fuel_capacity, ship.fuel + poi.loot_fuel)
                    particles.burst(poi.x, poi.y, 20, 100, 0.5, poi.color, 3)
                    audio.play('pickup', 0.5)

                    msg = f"Found: +${poi.loot_credits}"
                    if poi.loot_fuel > 0:
                        msg += f", +{poi.loot_fuel} fuel"

                    # Ambush!
                    if poi.has_ambush:
                        for _ in range(random.randint(3, 5)):
                            angle = random.uniform(0, math.pi * 2)
                            r = random.uniform(200, 350)
                            enemy = Enemy(
                                poi.x + math.cos(angle) * r,
                                poi.y + math.sin(angle) * r,
                                tier=max(1, sector.threat_level),
                            )
                            enemy.aggro = True
                            enemy.patrol_cx = poi.x
                            enemy.patrol_cy = poi.y
                            self.enemies.append(enemy)
                        msg += " - AMBUSH!"
                        audio.play('warning', 0.6)

                    return msg
        return None

    def _research_anomaly(self, poi, ship, particles, audio):
        """Progress anomaly research. Returns status message."""
        from game.ship import MODULE_DEFS
        RESEARCH_STEPS = 5

        poi.research_progress += 1
        particles.burst(poi.x, poi.y, 15, 80, 0.4, NEON_PURPLE, 2)
        audio.play('discover', 0.4)

        if poi.research_progress >= RESEARCH_STEPS:
            # Research complete — grant the reward module
            poi.researched = True
            reward_id = poi.reward_module
            reward_def = MODULE_DEFS.get(reward_id)
            if reward_def:
                # Find empty spot on the ship grid
                placed = False
                for gy in range(ship.grid_h):
                    for gx in range(ship.grid_w):
                        if ship.can_place(reward_id, gx, gy):
                            ship.place_module(reward_id, gx, gy)
                            placed = True
                            break
                    if placed:
                        break

                particles.burst(poi.x, poi.y, 50, 150, 0.8, NEON_PURPLE, 4)
                particles.burst(ship.x, ship.y, 30, 100, 0.5, (200, 100, 255), 3)
                audio.play('buy', 0.7)

                if placed:
                    return f"RESEARCH COMPLETE! Got: {reward_def.name} (auto-placed on ship)"
                else:
                    return f"RESEARCH COMPLETE! Got: {reward_def.name} — No space! Expand grid and dock to place it."
            return "Research complete but reward not found."
        else:
            remaining = RESEARCH_STEPS - int(poi.research_progress)
            return f"Researching anomaly... {int(poi.research_progress)}/{RESEARCH_STEPS} (press F {remaining} more times)"

    def get_nearby_poi(self, ship_x, ship_y) -> Optional[POI]:
        """Get nearest interactable POI."""
        for sector in self.sectors.get_loaded_sectors():
            for poi in sector.pois:
                if not poi.discovered or poi.looted:
                    continue
                if poi.poi_type == 'anomaly':
                    continue
                d = dist(ship_x, ship_y, poi.x, poi.y)
                if d < poi.interaction_range * 2:
                    return poi
        return None

    def launch_probe(self, ship: Ship, target: Asteroid, audio):
        if ship.active_probes >= ship.max_probes:
            return False
        if target.depleted:
            return False
        probe = MiningProbe(ship.x, ship.y, target)
        self.probes.append(probe)
        ship.active_probes += 1
        audio.play('probe_launch', 0.5)
        return True

    def get_nearest_asteroid(self, x, y, max_range=500):
        best = None
        best_d = max_range
        for a in self.asteroids:
            if a.depleted:
                continue
            d = dist(x, y, a.x, a.y)
            if d < best_d:
                best_d = d
                best = a
        return best

    def fire_guns(self, ship: Ship, target_wx: float, target_wy: float,
                  particles: ParticleSystem, audio):
        """LMB — Fire gatling/twin gun projectiles toward mouse."""
        aim_angle = angle_to(ship.x, ship.y, target_wx, target_wy)
        fired = False

        for m in ship.gun_modules:
            if m.cooldown > 0:
                continue
            m.cooldown = 1.0 / m.fire_rate

            # Twin guns fire two bullets with slight spread
            shots = 2 if 'twin' in m.defn.id else 1
            spread = 0.08 if shots > 1 else 0.03

            for i in range(shots):
                offset = (i - (shots - 1) / 2) * spread * 2
                a = aim_angle + offset + random.uniform(-spread, spread)
                proj = Projectile(
                    ship.x + math.cos(a) * 20,
                    ship.y + math.sin(a) * 20,
                    math.cos(a) * LASER_SPEED * 0.9,
                    math.sin(a) * LASER_SPEED * 0.9,
                    m.damage, 'player', 'bullet',
                    color=NEON_YELLOW
                )
                self.projectiles.append(proj)

            # Muzzle flash
            mx = ship.x + math.cos(aim_angle) * 20
            my = ship.y + math.sin(aim_angle) * 20
            particles.burst(mx, my, 5, 80, 0.12, NEON_YELLOW, 2)
            particles.emit(mx, my,
                          math.cos(aim_angle) * 150, math.sin(aim_angle) * 150,
                          0.08, WHITE, 1.5)
            audio.play('laser', 0.1)
            fired = True
        return fired

    def fire_lasers(self, ship: Ship, target_wx: float, target_wy: float,
                    particles: ParticleSystem, audio, camera):
        """RMB — Piercing laser beam that hits everything in its path."""
        aim_angle = angle_to(ship.x, ship.y, target_wx, target_wy)
        fired = False

        for m in ship.laser_modules:
            if m.cooldown > 0:
                continue
            m.cooldown = 1.0 / m.fire_rate
            fired = True

        if not fired:
            return False

        total_damage = sum(m.damage for m in ship.laser_modules if m.cooldown > 0.001)
        if total_damage <= 0:
            return False

        beam_range = 900.0
        bx = math.cos(aim_angle)
        by = math.sin(aim_angle)
        start_x = ship.x + bx * 25
        start_y = ship.y + by * 25
        end_x = start_x + bx * beam_range
        end_y = start_y + by * beam_range

        self._active_beams.append({
            'sx': start_x, 'sy': start_y,
            'ex': end_x, 'ey': end_y,
            'color': NEON_RED, 'life': 0.12,
            'width': min(4, 1 + len(ship.laser_modules)),
        })

        def point_to_line_dist(px, py):
            ax, ay = start_x, start_y
            abx2, aby2 = end_x - ax, end_y - ay
            apx, apy = px - ax, py - ay
            ab_sq = abx2 * abx2 + aby2 * aby2
            if ab_sq == 0:
                return dist(px, py, ax, ay)
            t = max(0, min(1, (apx * abx2 + apy * aby2) / ab_sq))
            return dist(px, py, ax + t * abx2, ay + t * aby2)

        for e in self.enemies:
            if not e.alive:
                continue
            d = point_to_line_dist(e.x, e.y)
            if d < e.radius + 8:
                e.take_hit(total_damage, particles)
                audio.play('hit', 0.3)
                camera.shake(3)
                if not e.alive:
                    self.pickups.append(Pickup(e.x, e.y, 'credits', e.credit_value))
                    if random.random() < 0.3:
                        self.pickups.append(Pickup(e.x + random.uniform(-20, 20),
                                                   e.y + random.uniform(-20, 20), 'fuel', 15))
                    audio.play('explosion' if not e.is_boss else 'explosion_big', 0.5)
                    camera.shake(8 if not e.is_boss else 20)
                    self.track_kill(e)
                    if e.is_boss and self._is_void_titan(e):
                        self.void_titan_killed = True

        for a in self.asteroids:
            if a.depleted:
                continue
            d = point_to_line_dist(a.x, a.y)
            if d < a.radius:
                chip = min(a.ore, total_damage * 0.4)
                a.ore -= chip
                # Shooting gives mostly ore, a little fuel
                ore_space = ship.ore_capacity - ship.ore
                ship.ore += min(chip * 0.7, ore_space)
                ship.fuel += min(chip * 0.2, ship.fuel_capacity - ship.fuel)
                ship.credits += int(chip)
                particles.burst(a.x, a.y, 8, 70, 0.2, NEON_ORANGE, 2)
                particles.burst(a.x, a.y, 3, 40, 0.15, WHITE, 1)
                if a.ore <= 0:
                    a.depleted = True
                    # Rock shatter effect
                    particles.burst(a.x, a.y, 40, 150, 0.8, ORE_COLOR, 4)
                    particles.burst(a.x, a.y, 20, 100, 0.5, NEON_ORANGE, 2)
                    particles.burst(a.x, a.y, 10, 80, 0.4, WHITE, 1.5)
                    # Chunk debris
                    for _ in range(8):
                        angle = random.uniform(0, math.pi * 2)
                        spd = random.uniform(60, 140)
                        particles.emit(a.x, a.y,
                                      math.cos(angle) * spd, math.sin(angle) * spd,
                                      random.uniform(0.5, 1.2), ORE_COLOR, random.uniform(3, 6), glow=False)
                    audio.play('explosion', 0.4)
                    camera.shake(6)

        # Muzzle flash
        particles.burst(start_x, start_y, 10, 100, 0.15, NEON_RED, 2.5)
        particles.burst(start_x, start_y, 4, 50, 0.1, WHITE, 1.5)
        # Sparks along beam path
        for i in range(8):
            t = random.uniform(0.05, 0.95)
            px = start_x + (end_x - start_x) * t
            py = start_y + (end_y - start_y) * t
            particles.emit(px + random.uniform(-8, 8), py + random.uniform(-8, 8),
                          random.uniform(-40, 40), random.uniform(-40, 40),
                          random.uniform(0.1, 0.25), NEON_RED, random.uniform(1, 2.5))

        audio.play('laser', 0.2)
        camera.shake(2)
        return True

    def fire_missiles(self, ship: Ship, target_wx: float, target_wy: float,
                      particles: ParticleSystem, audio):
        """MMB — Homing missiles toward nearest enemy."""
        aim_angle = angle_to(ship.x, ship.y, target_wx, target_wy)

        best_enemy = None
        best_dist = 800
        for e in self.enemies:
            if not e.alive:
                continue
            d = dist(ship.x, ship.y, e.x, e.y)
            if d < best_dist:
                best_dist = d
                best_enemy = e

        fired = False
        for m in ship.missile_modules:
            if m.cooldown > 0:
                continue
            m.cooldown = 1.0 / m.fire_rate

            proj = Projectile(
                ship.x + math.cos(aim_angle) * 20,
                ship.y + math.sin(aim_angle) * 20,
                math.cos(aim_angle) * MISSILE_SPEED,
                math.sin(aim_angle) * MISSILE_SPEED,
                m.damage, 'player', 'missile',
                target=best_enemy, color=NEON_PURPLE
            )
            self.projectiles.append(proj)
            # Missile launch smoke + flash
            mx = ship.x + math.cos(aim_angle) * 20
            my = ship.y + math.sin(aim_angle) * 20
            particles.burst(mx, my, 8, 100, 0.2, NEON_PURPLE, 2.5)
            particles.burst(mx, my, 12, 60, 0.4, (80, 60, 100), 3, glow=False)  # exhaust smoke
            particles.emit(mx, my,
                          -math.cos(aim_angle) * 80, -math.sin(aim_angle) * 80,
                          0.3, WHITE, 2)
            audio.play('missile', 0.3)
            fired = True
        return fired

    def fire_turrets(self, ship: Ship, particles: ParticleSystem, audio):
        """Auto-turrets — fire automatically at nearest enemy. Called every frame."""
        for m in ship.turret_modules:
            if m.cooldown > 0:
                continue

            # Find nearest enemy
            best_enemy = None
            best_dist = 500
            for e in self.enemies:
                if not e.alive:
                    continue
                d = dist(ship.x, ship.y, e.x, e.y)
                if d < best_dist:
                    best_dist = d
                    best_enemy = e

            if not best_enemy:
                continue

            m.cooldown = 1.0 / m.fire_rate
            aim = angle_to(ship.x, ship.y, best_enemy.x, best_enemy.y)
            spread = random.uniform(-0.05, 0.05)

            proj = Projectile(
                ship.x + math.cos(aim) * 15,
                ship.y + math.sin(aim) * 15,
                math.cos(aim + spread) * LASER_SPEED * 0.8,
                math.sin(aim + spread) * LASER_SPEED * 0.8,
                m.damage, 'player', 'bullet',
                color=NEON_GREEN
            )
            self.projectiles.append(proj)
            particles.emit(
                ship.x + math.cos(aim) * 15,
                ship.y + math.sin(aim) * 15,
                random.uniform(-20, 20), random.uniform(-20, 20),
                0.1, NEON_GREEN, 1.5
            )
            audio.play('laser', 0.06)

    def fire_autolasers(self, ship: Ship, particles: ParticleSystem, audio, camera):
        """Auto mini-lasers — fire short beams at nearest enemy automatically."""
        for m in ship.autolaser_modules:
            if m.cooldown > 0:
                continue

            best_enemy = None
            best_dist = 400
            for e in self.enemies:
                if not e.alive:
                    continue
                d = dist(ship.x, ship.y, e.x, e.y)
                if d < best_dist:
                    best_dist = d
                    best_enemy = e

            if not best_enemy:
                continue

            m.cooldown = 1.0 / m.fire_rate
            aim = angle_to(ship.x, ship.y, best_enemy.x, best_enemy.y)

            # Short beam (half the range of manual laser)
            beam_range = 450.0
            bx = math.cos(aim)
            by = math.sin(aim)
            sx = ship.x + bx * 20
            sy = ship.y + by * 20
            ex = sx + bx * beam_range
            ey = sy + by * beam_range

            self._active_beams.append({
                'sx': sx, 'sy': sy, 'ex': ex, 'ey': ey,
                'color': (255, 80, 80), 'life': 0.08,
                'width': 1,
            })

            # Damage the targeted enemy directly
            best_enemy.take_hit(m.damage, particles)
            audio.play('hit', 0.1)
            if not best_enemy.alive:
                self.pickups.append(Pickup(best_enemy.x, best_enemy.y, 'credits', best_enemy.credit_value))
                if random.random() < 0.3:
                    self.pickups.append(Pickup(best_enemy.x + random.uniform(-20, 20),
                                               best_enemy.y + random.uniform(-20, 20), 'fuel', 15))
                audio.play('explosion' if not best_enemy.is_boss else 'explosion_big', 0.4)
                camera.shake(5)
                self.track_kill(best_enemy)
                if best_enemy.is_boss and self._is_void_titan(best_enemy):
                    self.void_titan_killed = True

    def update(self, dt, ship: Ship, particles: ParticleSystem, audio, camera):
        self.game_time += dt

        # Update beam lifetimes
        for beam in self._active_beams:
            beam['life'] -= dt
        self._active_beams = [b for b in self._active_beams if b['life'] > 0]

        # Sector streaming
        new_coord = self.sectors.get_sector_coord(ship.x, ship.y)
        self.sectors.update_streaming(ship.x, ship.y, self.game_time)

        if new_coord != self._last_sector_coord:
            self._last_sector_coord = new_coord
            self._sync_entities()
            self._cleanup_distant_entities(ship.x, ship.y)
            ship.sectors_discovered = len(self.sectors.discovered)
            ship.farthest_sector = self.sectors.farthest_distance
            self.track_explore(ship.sectors_discovered)

        # Update stations
        for sector in self.sectors.get_loaded_sectors():
            if sector.station:
                sector.station.update(dt)

        # POI discovery
        self._check_poi_discovery(ship, particles, audio)

        # Patrol spawning
        self._check_patrol_spawns(ship, particles)
        self._check_patrol_cleared()

        # Asteroids
        for a in self.asteroids:
            a.update(dt)

        # Probes (track fuel delivered for missions)
        prev_fuel = ship.fuel
        for p in self.probes:
            p.update(dt, ship, particles)
        fuel_mined = ship.fuel - prev_fuel
        if fuel_mined > 0:
            self.track_mine(fuel_mined)
        self.probes = [p for p in self.probes if p.alive]

        # Projectiles
        for p in self.projectiles:
            p.update(dt, particles)
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Enemies
        for e in self.enemies:
            e.update(dt, ship, self.projectiles, particles)

        # Pickups
        for p in self.pickups:
            p.update(dt, ship, particles, audio)
        self.pickups = [p for p in self.pickups if p.alive]

        # Collision: player projectiles vs enemies
        for p in self.projectiles:
            if p.owner != 'player' or not p.alive:
                continue
            for e in self.enemies:
                if not e.alive:
                    continue
                if dist(p.x, p.y, e.x, e.y) < e.radius + 5:
                    e.take_hit(p.damage, particles)
                    p.alive = False
                    audio.play('hit', 0.3)
                    camera.shake(3)
                    if not e.alive:
                        self.pickups.append(Pickup(e.x, e.y, 'credits', e.credit_value))
                        if random.random() < 0.3:
                            self.pickups.append(Pickup(
                                e.x + random.uniform(-20, 20),
                                e.y + random.uniform(-20, 20),
                                'fuel', 15
                            ))
                        if random.random() < 0.25:
                            self.pickups.append(Pickup(
                                e.x + random.uniform(-20, 20),
                                e.y + random.uniform(-20, 20),
                                'repair', 20
                            ))
                        audio.play('explosion' if not e.is_boss else 'explosion_big', 0.5)
                        camera.shake(8 if not e.is_boss else 20)
                        self.track_kill(e)
                        if e.is_boss and self._is_void_titan(e):
                            self.void_titan_killed = True
                    break

        # Collision: enemy projectiles vs player
        if ship.alive and ship.invuln_timer <= 0:
            ship_r = max(ship.grid_w, ship.grid_h) * 8
            for p in self.projectiles:
                if p.owner != 'enemy' or not p.alive:
                    continue
                if dist(p.x, p.y, ship.x, ship.y) < ship_r:
                    ship.take_damage(p.damage)
                    p.alive = False
                    particles.burst(ship.x, ship.y, 10, 80, 0.3, NEON_RED, 2)
                    audio.play('hit', 0.4)
                    camera.shake(5)

        # Collision: enemy projectiles vs drones
        for p in self.projectiles:
            if p.owner != 'enemy' or not p.alive:
                continue
            for d in self.drones:
                if not d.alive:
                    continue
                if dist(p.x, p.y, d.x, d.y) < d.radius + 3:
                    d.take_hit(p.damage, particles)
                    p.alive = False
                    break

        # Collision: ALL projectiles vs asteroids (asteroids block everything)
        for p in self.projectiles:
            if not p.alive:
                continue
            for a in self.asteroids:
                if a.depleted:
                    continue
                if dist(p.x, p.y, a.x, a.y) < a.radius:
                    p.alive = False
                    chip = min(a.ore, p.damage * 0.5)
                    a.ore -= chip
                    if p.owner == 'player':
                        # Host gets loot
                        ore_space = ship.ore_capacity - ship.ore
                        ship.ore += min(chip * 0.7, ore_space)
                        ship.fuel += min(chip * 0.2, ship.fuel_capacity - ship.fuel)
                        ship.credits += int(chip)
                    elif p.owner == 'remote_player':
                        # Send loot to that specific remote player
                        pid = getattr(p, '_remote_pid', -1)
                        if pid > 0:
                            self.player_loot[pid] = self.player_loot.get(pid, [0, 0.0])
                            self.player_loot[pid][0] += int(chip)
                            self.player_loot[pid][1] += chip * 0.7
                    # All projectiles spark on impact
                    particles.burst(p.x, p.y, 10, 90, 0.25, NEON_ORANGE, 2)
                    particles.burst(p.x, p.y, 3, 40, 0.15, WHITE, 1)
                    if a.ore <= 0:
                        a.depleted = True
                        particles.burst(a.x, a.y, 40, 150, 0.8, ORE_COLOR, 4)
                        particles.burst(a.x, a.y, 20, 100, 0.5, NEON_ORANGE, 2)
                        for _ in range(8):
                            ang = random.uniform(0, math.pi * 2)
                            spd = random.uniform(60, 140)
                            particles.emit(a.x, a.y,
                                          math.cos(ang) * spd, math.sin(ang) * spd,
                                          random.uniform(0.5, 1.2), ORE_COLOR, random.uniform(3, 6), glow=False)
                        audio.play('explosion', 0.4)
                        camera.shake(6)
                    else:
                        audio.play('hit', 0.2)
                    break

        # Clean up dead enemies
        self.enemies = [e for e in self.enemies if e.alive]

        # Auto-weapons fire automatically
        if ship.alive and not ship.docked:
            self.fire_turrets(ship, particles, audio)
            self.fire_autolasers(ship, particles, audio, camera)

        # Update escort NPC (for escort missions)
        self._update_escort_mission(dt, ship, particles)

        # Maintain drones — spawn if below count, update existing
        self._update_drones(dt, ship, particles)

        # Update buildings
        for b in self.buildings:
            b.update(dt)
            if not b.alive:
                continue
            # Base turret — auto-fire at enemies
            if b.defn.id == 'base_turret' and b.fire_cooldown <= 0:
                best_e = None
                best_d = 400
                for e in self.enemies:
                    if not e.alive:
                        continue
                    d = dist(b.x, b.y, e.x, e.y)
                    if d < best_d:
                        best_d = d
                        best_e = e
                if best_e:
                    b.fire_cooldown = 0.4
                    aim = angle_to(b.x, b.y, best_e.x, best_e.y)
                    b.rotation = aim
                    proj = Projectile(
                        b.x + math.cos(aim) * b.defn.radius,
                        b.y + math.sin(aim) * b.defn.radius,
                        math.cos(aim) * LASER_SPEED * 0.7,
                        math.sin(aim) * LASER_SPEED * 0.7,
                        8, 'player', 'bullet', color=NEON_GREEN
                    )
                    self.projectiles.append(proj)
                    particles.emit(
                        b.x + math.cos(aim) * b.defn.radius,
                        b.y + math.sin(aim) * b.defn.radius,
                        random.uniform(-15, 15), random.uniform(-15, 15),
                        0.1, NEON_GREEN, 1.5)

            # Repair pad — heal nearby ship
            if b.defn.id == 'repair_pad' and ship.alive:
                d = dist(b.x, b.y, ship.x, ship.y)
                if d < 120:
                    core = next((m for m in ship.modules if m.defn.id == "core"), None)
                    if core and core.hp < core.max_hp:
                        core.hp = min(core.max_hp, core.hp + 3.0 * dt)

        # Barricade blocking enemy projectiles
        for p in self.projectiles:
            if p.owner == 'enemy' and p.alive:
                for b in self.buildings:
                    if not b.alive or b.defn.id == 'beacon':
                        continue
                    if dist(p.x, p.y, b.x, b.y) < b.defn.radius:
                        p.alive = False
                        b.hp -= p.damage
                        particles.burst(p.x, p.y, 5, 60, 0.15, b.defn.glow, 1.5)
                        if b.hp <= 0:
                            b.alive = False
                            particles.burst(b.x, b.y, 30, 120, 0.6, b.defn.glow, 3)
                        break

        # Remove dead buildings
        self.buildings = [b for b in self.buildings if b.alive]

    def draw(self, surface, camera, time):
        vis = camera.visible_rect()

        # Sector boundaries (subtle grid)
        self._draw_sector_grid(surface, camera)

        # Stations
        for sector in self.sectors.get_loaded_sectors():
            if sector.station:
                sx, sy = camera.world_to_screen(sector.station.x, sector.station.y)
                if -100 < sx < SCREEN_W + 100 and -100 < sy < SCREEN_H + 100:
                    sector.station.draw(surface, camera, time)

        # POIs
        for sector in self.sectors.get_loaded_sectors():
            for poi in sector.pois:
                px, py = camera.world_to_screen(poi.x, poi.y)
                if -50 < px < SCREEN_W + 50 and -50 < py < SCREEN_H + 50:
                    poi.draw(surface, camera, time)

        # Platforms first (so other buildings draw on top)
        for b in self.buildings:
            if b.defn.id == 'platform':
                b.draw(surface, camera, time)
        # Other buildings on top of platforms
        for b in self.buildings:
            if b.defn.id != 'platform':
                b.draw(surface, camera, time)

        # Asteroids
        for a in self.asteroids:
            if vis.collidepoint(a.x, a.y) or dist(a.x, a.y, vis.centerx, vis.centery) < a.radius + 400:
                a.draw(surface, camera, time)

        # Pickups
        for p in self.pickups:
            if vis.collidepoint(p.x, p.y):
                p.draw(surface, camera, time)

        # Probes
        for p in self.probes:
            if vis.collidepoint(p.x, p.y):
                p.draw(surface, camera, time)

        # Projectiles
        for p in self.projectiles:
            if vis.collidepoint(p.x, p.y):
                p.draw(surface, camera)

        # Enemies
        for e in self.enemies:
            if vis.collidepoint(e.x, e.y) or dist(e.x, e.y, vis.centerx, vis.centery) < e.radius + 200:
                e.draw(surface, camera, time)

        # Escort NPC
        if self.escort_npc and self.escort_npc.alive:
            self.escort_npc.draw(surface, camera, time)

        # Drones
        for d in self.drones:
            d.draw(surface, camera, time)

        # Laser beams (optimized — no per-beam full-screen surfaces)
        for beam in self._active_beams:
            alpha = clamp(beam['life'] / 0.12, 0, 1)
            sx1, sy1 = camera.world_to_screen(beam['sx'], beam['sy'])
            sx2, sy2 = camera.world_to_screen(beam['ex'], beam['ey'])
            w = beam['width']
            c = beam['color']

            # Outer glow — draw wide dim line directly
            glow_c = safe_color(c[0] * 0.3 * alpha, c[1] * 0.3 * alpha, c[2] * 0.3 * alpha)
            pygame.draw.line(surface, glow_c,
                           (int(sx1), int(sy1)), (int(sx2), int(sy2)), w * 5)

            # Mid beam
            mid_c = safe_color(c[0] * 0.7 * alpha, c[1] * 0.7 * alpha, c[2] * 0.7 * alpha)
            pygame.draw.line(surface, mid_c,
                           (int(sx1), int(sy1)), (int(sx2), int(sy2)), w * 2)

            # Core beam (bright center)
            core_c = safe_color((c[0] * 0.5 + 128) * alpha, (c[1] * 0.5 + 128) * alpha, (c[2] * 0.5 + 128) * alpha)
            pygame.draw.line(surface, core_c,
                           (int(sx1), int(sy1)), (int(sx2), int(sy2)), max(1, w))

    def _is_void_titan(self, enemy):
        """Check if this boss is the Void Titan (in sector 6,-4)."""
        titan_sector = (6, -4)
        sx = titan_sector[0] * SECTOR_SIZE
        sy = titan_sector[1] * SECTOR_SIZE
        pcx = getattr(enemy, 'patrol_cx', 0)
        pcy = getattr(enemy, 'patrol_cy', 0)
        return (sx < pcx < sx + SECTOR_SIZE and
                sy < pcy < sy + SECTOR_SIZE)

    def _draw_sector_grid(self, surface, camera):
        """Draw subtle sector boundary lines."""
        vis = camera.visible_rect()
        start_sx = int(vis.x // SECTOR_SIZE) * SECTOR_SIZE
        start_sy = int(vis.y // SECTOR_SIZE) * SECTOR_SIZE

        for wx in range(start_sx, int(vis.right) + SECTOR_SIZE, SECTOR_SIZE):
            sx, _ = camera.world_to_screen(wx, 0)
            if 0 <= sx <= SCREEN_W:
                pygame.draw.line(surface, (15, 18, 30), (int(sx), 0), (int(sx), SCREEN_H))

        for wy in range(start_sy, int(vis.bottom) + SECTOR_SIZE, SECTOR_SIZE):
            _, sy = camera.world_to_screen(0, wy)
            if 0 <= sy <= SCREEN_H:
                pygame.draw.line(surface, (15, 18, 30), (0, int(sy)), (SCREEN_W, int(sy)))
