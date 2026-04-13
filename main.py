"""
NEON VOID — A space mining, building, and exploration game.

Explore an infinite procedurally-generated galaxy of sectors.
Mine asteroids with probes, refine ore into fuel onboard,
dock at space stations to buy modules and expand your ship,
and push deeper into increasingly hostile space.

Controls:
    WASD        - Fly
    SHIFT       - Boost (extra fuel cost)
    E           - Launch mining probe at nearest asteroid
    F           - Dock at station / Interact with POI
    TAB / M     - Open sector map
    Mouse       - Aim weapons (auto-fire at enemies)
    ESC         - Quit / Close menu
"""
import pygame
import sys
import os
import math
import random
import logging
from typing import Optional
from game.core import *

# Set up logging to file + console
_game_dir = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(_game_dir, 'neonvoid.log'), mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("neonvoid")
from game.ship import Ship
from game.world import World
from game.ui import HUD, StationUI, SectorMap, PauseMenu, MainMenu, GameOverScreen, LobbyUI
from game.save import save_game, load_game, has_save
from game.network import GameServer, GameClient, get_local_ip
from game.updater import AsyncUpdater, get_local_version, get_update_url


class Game:
    def __init__(self):
        pygame.init()
        self.fullscreen = False
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("NEON VOID")
        self.clock = pygame.time.Clock()

        self.camera = Camera()
        self.particles = ParticleSystem()
        self.stars = StarField()
        self.audio = AudioManager()

        self.menu = MainMenu()
        self.game_over = GameOverScreen()
        self.hud = HUD()
        self.station_ui = StationUI()
        self.sector_map = SectorMap()
        self.pause_menu = PauseMenu()
        self.lobby = LobbyUI()

        # Multiplayer
        self.server: Optional[GameServer] = None
        self.client: Optional[GameClient] = None
        self.is_host = False
        self.is_client = False

        self.time = 0.0
        self.total_credits_earned = 0

        self._new_game()

    def _new_game(self):
        # Clean up multiplayer if active
        self._stop_multiplayer()
        self.ship = Ship()
        self.world = World()
        self.particles = ParticleSystem()
        self.game_over.active = False
        self.station_ui.close()
        self.sector_map.active = False
        self.pause_menu.active = False
        self.lobby.close()
        self.hud = HUD()
        self.time = 0.0
        self.total_credits_earned = 0
        self.camera = Camera()

        # Start docked at home station
        home = self.world.sectors.get_sector((0, 0))
        if home.station:
            self.ship.x = home.station.x
            self.ship.y = home.station.y
            self.ship.docked = True
            self.station_ui.open(home.station, self.world)

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)
            self.time += dt

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue

                # F11 fullscreen toggle (works in any state)
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    self.fullscreen = not self.fullscreen
                    if self.fullscreen:
                        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
                    else:
                        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
                    continue

                # Lobby
                if self.lobby.active:
                    result = self.lobby.handle_event(event)
                    if result == 'back':
                        self.lobby.close()
                        self.menu.active = True
                    elif result == 'start_host':
                        self._start_host()
                    elif result == 'start_join':
                        self._start_join()
                    continue

                # Menu
                if self.menu.active:
                    result = self.menu.handle_event(event)
                    if result == 'new':
                        pass  # _new_game already called in __init__
                    elif result == 'continue':
                        if load_game(self):
                            self.hud.notify("Save loaded!", NEON_GREEN, 2.0)
                        else:
                            self.hud.notify("Failed to load save", NEON_RED, 2.0)
                    elif result == 'host':
                        self.menu.active = False
                        self.lobby.open_host()
                    elif result == 'join':
                        self.menu.active = False
                        self.lobby.open_join()
                    continue

                # Game over
                if self.game_over.active:
                    if self.game_over.handle_event(event):
                        self._new_game()
                    continue

                # Pause menu
                if self.pause_menu.active:
                    result = self.pause_menu.handle_event(event)
                    if result == 'resume':
                        self.pause_menu.active = False
                    elif result == 'save':
                        success = save_game(self)
                        self.pause_menu.show_save_result(success)
                    elif result == 'update':
                        self._check_for_update()
                    elif result == 'restart':
                        self._new_game()
                    elif result == 'quit':
                        save_game(self)  # auto-save on quit
                        running = False
                    continue

                # ESC handling — open pause menu
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self.station_ui.active:
                        self._undock()
                    elif self.sector_map.active:
                        self.sector_map.active = False
                    else:
                        self.pause_menu.toggle()
                    continue

                # Sector map
                if self.sector_map.active:
                    self.sector_map.handle_event(event, self.world.sectors)
                    continue

                # Station UI
                if self.station_ui.active:
                    result = self.station_ui.handle_event(event, self.ship, self.audio)
                    if result == 'undock':
                        self._undock()
                    continue

                # Gameplay events
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_TAB, pygame.K_m):
                        self.sector_map.toggle()
                    elif event.key == pygame.K_e:
                        self._try_launch_probe()
                    elif event.key == pygame.K_f:
                        self._try_dock_or_interact()
                    elif event.key == pygame.K_r:
                        self.ship.refinery_enabled = not self.ship.refinery_enabled
                        state = "ON" if self.ship.refinery_enabled else "OFF (ore preserved for selling)"
                        self.hud.notify(f"Refinery: {state}", NEON_GREEN if self.ship.refinery_enabled else NEON_ORANGE, 2.0)

            # ── UPDATE ────────────────────────────────────────────
            if self.lobby.active:
                self.lobby.draw(self.screen, self.time)
                pygame.display.flip()
                continue

            if self.menu.active:
                self.menu.update(dt)
                self.menu.draw(self.screen, self.time)
                pygame.display.flip()
                continue

            if self.game_over.active:
                self.game_over.update(dt)
                self._draw_gameplay(dt)
                self.game_over.draw(self.screen, self.time)
                pygame.display.flip()
                continue

            # Pause — draw frozen frame + pause overlay
            if self.pause_menu.active:
                self.pause_menu.update(dt)
                self._draw_gameplay(0)
                self.pause_menu.draw(self.screen, self.ship, self.world, self.time)
                pygame.display.flip()
                self.time += dt  # keep time ticking for animations
                continue

            if not self.station_ui.active and not self.sector_map.active:
                # Get mouse in world coords
                mx, my = pygame.mouse.get_pos()
                wmx, wmy = self.camera.screen_to_world(mx, my)

                # Update ship
                keys = pygame.key.get_pressed()
                prev_credits = self.ship.credits
                self.ship.update(dt, keys, wmx, wmy)
                credit_gain = self.ship.credits - prev_credits
                if credit_gain > 0:
                    self.total_credits_earned += credit_gain

                # Distress beacon — hold H to charge, warps to nearest station
                self.ship.distress_cooldown = max(0, self.ship.distress_cooldown - dt)
                if keys[pygame.K_h] and self.ship.alive and not self.ship.docked and self.ship.distress_cooldown <= 0:
                    if not self.ship.distress_charging:
                        self.ship.distress_charging = True
                        self.ship.distress_timer = 0.0
                        self.hud.notify("CHARGING DISTRESS BEACON... hold H", NEON_YELLOW, 4.0)
                    self.ship.distress_timer += dt
                    if self.ship.distress_timer >= 3.0:
                        self._distress_warp()
                else:
                    if self.ship.distress_charging:
                        self.ship.distress_charging = False
                        self.ship.distress_timer = 0.0

                # Fire weapons — LMB: guns, RMB: laser beam, MMB: missiles
                mouse_buttons = pygame.mouse.get_pressed()
                if self.ship.alive and not self.ship.docked:
                    if mouse_buttons[0]:  # LMB - gatling/twin guns
                        self.world.fire_guns(self.ship, wmx, wmy,
                                            self.particles, self.audio)
                    if mouse_buttons[2]:  # RMB - laser beam
                        self.world.fire_lasers(self.ship, wmx, wmy,
                                              self.particles, self.audio, self.camera)
                    if mouse_buttons[1]:  # MMB - missiles
                        self.world.fire_missiles(self.ship, wmx, wmy,
                                                self.particles, self.audio)

                # Send input to host if we're a client
                if self.is_client and self.client and self.client.connected:
                    self.client.send_input(
                        {'w': keys[pygame.K_w], 's': keys[pygame.K_s],
                         'a': keys[pygame.K_a], 'd': keys[pygame.K_d],
                         'shift': keys[pygame.K_LSHIFT]},
                        wmx, wmy,
                        mouse_buttons[0], mouse_buttons[2], mouse_buttons[1]
                    )

                # Engine particles
                speed = math.sqrt(self.ship.vx ** 2 + self.ship.vy ** 2)
                if speed > 20:
                    cos_a = math.cos(self.ship.angle)
                    sin_a = math.sin(self.ship.angle)
                    ship_size = max(self.ship.grid_w, self.ship.grid_h) * 4
                    ex = self.ship.x - cos_a * ship_size * 0.8
                    ey = self.ship.y - sin_a * ship_size * 0.8
                    trail_color = NEON_YELLOW if self.ship.boost else NEON_ORANGE
                    self.particles.trail(ex, ey, -self.ship.vx * 0.3, -self.ship.vy * 0.3,
                                        trail_color, 2, 2 if self.ship.boost else 1)

                # Update world
                self.world.update(dt, self.ship, self.particles, self.audio, self.camera)

                # Multiplayer: update remote players and sync state
                if self.is_host and self.server:
                    self.server.update_players(dt, self.ship)
                    self._process_remote_combat()
                    self._process_pvp(dt)
                    self.server.beams_snapshot = [
                        {'sx': b['sx'], 'sy': b['sy'], 'ex': b['ex'], 'ey': b['ey'],
                         'color': list(b['color']), 'life': b['life']}
                        for b in self.world._active_beams
                    ]
                    # Sync projectiles so clients can see bullets
                    self.server.projectiles_snapshot = [
                        {'x': round(p.x, 1), 'y': round(p.y, 1),
                         'vx': round(p.vx, 1), 'vy': round(p.vy, 1),
                         'type': p.proj_type, 'color': list(p.color)}
                        for p in self.world.projectiles if p.alive and p.owner in ('player', 'remote_player')
                    ][:30]
                    # Sync probes
                    self.server.probes_snapshot = [
                        {'x': round(p.x, 1), 'y': round(p.y, 1),
                         'state': p.state, 'cargo': round(p.cargo, 1)}
                        for p in self.world.probes if p.alive
                    ]
                    # Sync depleted asteroids
                    self.server.depleted_asteroids = [
                        (round(a.x, 1), round(a.y, 1))
                        for a in self.world.asteroids if a.depleted
                    ]
                # Client: sync depleted asteroids from host
                if self.is_client and self.client and self.client.connected:
                    with self.client.lock:
                        depleted = list(self.client.depleted_asteroids)
                    if depleted:
                        depleted_set = set((round(d[0], 1), round(d[1], 1)) for d in depleted)
                        for a in self.world.asteroids:
                            key = (round(a.x, 1), round(a.y, 1))
                            if key in depleted_set:
                                a.depleted = True
                if self.is_client and self.client and not self.client.connected:
                    self.hud.notify("Disconnected from host!", NEON_RED, 3.0)
                    self.is_client = False
                    self.client = None

                # Check win — Void Titan killed (continue playing after)
                if self.world.void_titan_killed and not self.world.titan_victory_shown:
                    self.world.titan_victory_shown = True
                    self.hud.notify("VOID TITAN DESTROYED! You conquered the void. Game continues...", NEON_GREEN, 6.0)
                    self.camera.shake(30)
                    self.particles.burst(self.ship.x, self.ship.y, 80, 250, 1.0, NEON_GREEN, 4)
                    self.particles.burst(self.ship.x, self.ship.y, 60, 200, 0.8, NEON_CYAN, 3)
                    self.ship.credits += 1000  # titan bounty

                # Check death
                if not self.ship.alive:
                    self.game_over.activate(
                        len(self.world.sectors.discovered),
                        self.world.sectors.farthest_distance,
                        self.total_credits_earned
                    )
                    self.audio.play('explosion_big', 0.7)
                    self.camera.shake(25)
                    self.particles.burst(self.ship.x, self.ship.y, 100, 300, 1.0, NEON_CYAN, 3)
                    self.particles.burst(self.ship.x, self.ship.y, 60, 200, 0.8, NEON_ORANGE, 4)

            # Camera
            self.camera.follow(self.ship.x, self.ship.y)
            self.camera.update(dt)

            # Particles
            self.particles.update(dt)

            # HUD
            self.hud.update(dt)

            # ── DRAW ─────────────────────────────────────────────
            self._draw_gameplay(dt)

            # Overlays
            if self.station_ui.active:
                self.station_ui.draw(self.screen, self.ship, self.time)
            elif self.sector_map.active:
                self.sector_map.draw(self.screen, self.world.sectors, self.ship, self.time)

            # Multiplayer info overlay
            if self.is_host and self.server:
                count = self.server.get_player_count()
                draw_text(self.screen, f"HOSTING ({count} connected)", 15, SCREEN_H - 70,
                         NEON_PURPLE, 11)
                self._draw_mp_hud(self.server.scores, self.server.kill_feed, True)
            elif self.is_client and self.client and self.client.connected:
                draw_text(self.screen, f"CONNECTED as {self.client.my_name}", 15, SCREEN_H - 70,
                         NEON_GREEN, 11)
                # Copy data to avoid holding lock during draw
                try:
                    with self.client.lock:
                        scores = dict(self.client.scores)
                        feed = list(self.client.kill_feed)
                    self._draw_mp_hud(scores, feed, False)
                except Exception:
                    pass

            pygame.display.flip()

        self._stop_multiplayer()
        pygame.quit()
        sys.exit()

    def _try_dock_or_interact(self):
        # Try docking first
        for sector in self.world.sectors.get_loaded_sectors():
            if sector.station and sector.station.can_dock(self.ship.x, self.ship.y):
                self.ship.docked = True
                self.ship.vx = 0
                self.ship.vy = 0
                self.station_ui.open(sector.station, self.world)
                self.audio.play('dock', 0.5)
                self.hud.notify(f"Docked at {sector.station.name} (auto-saved)", NEON_CYAN, 2.0)
                save_game(self)  # auto-save on dock
                return

        # Try POI interaction
        msg = self.world.interact_poi(self.ship, self.particles, self.audio)
        if msg:
            color = NEON_RED if "AMBUSH" in msg else NEON_GREEN
            self.hud.notify(msg, color, 3.0)
            return

        # Nothing to interact with
        station_info = self.world.sectors.find_nearest_station_direction(self.ship.x, self.ship.y)
        if station_info:
            _, d, name = station_info
            if d < 500:
                self.hud.notify(f"Move closer to {name} to dock", DIM_CYAN, 1.5)
            else:
                self.hud.notify(f"Nearest station: {name} ({int(d)}m away)", DIM_CYAN, 1.5)
        else:
            self.hud.notify("Nothing to interact with", DIM_CYAN, 1.5)

    def _start_host(self):
        """Start hosting a multiplayer game."""
        self.server = GameServer(
            friendly_fire=self.lobby.friendly_fire,
            auto_shoot_players=self.lobby.auto_shoot,
        )
        try:
            self.server.start()
            self.is_host = True
            self.lobby.close()
            self.hud.notify(f"Hosting on {get_local_ip()}:7777 — waiting for players...", NEON_PURPLE, 5.0)
            # Set up kill callback for scoreboard
            def on_kill(enemy, pid):
                label = "BOSS" if enemy.is_boss else ("ELITE" if enemy.enemy_type == 'elite' else "enemy")
                name = self.server.get_player_name(pid)
                self.server.add_kill(name, label, [0, 255, 255])
                self.server.add_score(pid)
            self.world.on_kill_callback = on_kill
        except Exception as e:
            self.lobby.status = f"Failed to start server: {e}"
            self.lobby.status_color = NEON_RED
            self.server = None

    def _start_join(self):
        """Join a hosted game."""
        ip = self.lobby.ip_text.strip()
        name = self.lobby.name_text.strip() or "Player"
        self.lobby.status = f"Connecting to {ip}..."
        self.lobby.status_color = NEON_YELLOW

        self.client = GameClient()
        if self.client.connect(ip, name=name):
            self.is_client = True
            self.lobby.close()
            self.hud.notify(f"Connected! You are {self.client.my_name}", NEON_GREEN, 3.0)
        else:
            self.lobby.status = f"Failed: {self.client.error}"
            self.lobby.status_color = NEON_RED
            self.client = None

    def _stop_multiplayer(self):
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
            self.server = None
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.client = None
        self.is_host = False
        self.is_client = False
        if hasattr(self, 'world') and self.world:
            self.world.on_kill_callback = None

    def _check_for_update(self):
        """Check for game updates."""
        url = get_update_url()
        if not url:
            ver, build = get_local_version()
            self.pause_menu.show_save_result(False)
            self.pause_menu.save_msg = f"v{ver} (build {build}) — No update URL configured"
            self.pause_menu.save_msg_timer = 4.0
            return

        if not self.pause_menu.updater:
            self.pause_menu.updater = AsyncUpdater()

        if self.pause_menu.updater.checking:
            return  # already checking

        if self.pause_menu.updater.result is not None:
            # We have a result from a previous check
            result = self.pause_menu.updater.result
            if result is None:
                self.pause_menu.save_msg = "You're up to date!"
                self.pause_menu.save_msg_timer = 3.0
            elif "error" in result:
                self.pause_menu.save_msg = f"Update check failed: {result['error'][:50]}"
                self.pause_menu.save_msg_timer = 4.0
            else:
                # Update available — download it
                self.pause_menu.save_msg = f"Downloading v{result.get('version', '?')}..."
                self.pause_menu.save_msg_timer = 10.0
                self.pause_menu.updater.download(result)
            self.pause_menu.updater.result = None  # consume
            return

        if self.pause_menu.updater.downloading:
            if self.pause_menu.updater.download_result:
                success, msg = self.pause_menu.updater.download_result
                self.pause_menu.save_msg = msg
                self.pause_menu.save_msg_timer = 6.0
                self.pause_menu.updater.download_result = None
            return

        # Start checking
        ver, build = get_local_version()
        self.pause_menu.save_msg = f"Checking for updates... (current: v{ver})"
        self.pause_menu.save_msg_timer = 5.0
        self.pause_menu.updater.check()

    def _process_pvp(self, dt):
        """Host: handle player-vs-player interactions (friendly fire, collisions)."""
        if not self.server:
            return

        with self.server.lock:
            remote_players = list(self.server.remote_players.values())

        if not remote_players:
            return

        # Friendly fire: host's projectiles hit remote players
        if self.server.friendly_fire:
            for p in self.world.projectiles:
                if p.owner != 'player' or not p.alive:
                    continue
                for rp in remote_players:
                    if not rp.alive:
                        continue
                    if dist(p.x, p.y, rp.x, rp.y) < 20:
                        rp.hp -= p.damage
                        p.alive = False
                        self.particles.burst(rp.x, rp.y, 10, 80, 0.3, tuple(rp.color), 2)
                        self.audio.play('hit', 0.3)
                        if rp.hp <= 0:
                            rp.alive = False
                            rp.hp = 0
                            rp.respawn_timer = 3.0  # respawn in 3 seconds
                            self.particles.burst(rp.x, rp.y, 50, 200, 0.8, tuple(rp.color), 4)
                            self.server.add_kill("Host", rp.name, [0, 255, 255])
                            self.server.add_score(0)
                            self.audio.play('explosion_big', 0.5)
                            self.camera.shake(10)
                        break

            # Check beams vs remote players
            for beam in self.world._active_beams:
                for rp in remote_players:
                    if not rp.alive:
                        continue
                    # Point-to-line distance
                    sx, sy = beam['sx'], beam['sy']
                    ex, ey = beam['ex'], beam['ey']
                    abx, aby = ex - sx, ey - sy
                    apx, apy = rp.x - sx, rp.y - sy
                    ab_sq = abx * abx + aby * aby
                    if ab_sq > 0:
                        t = max(0, min(1, (apx * abx + apy * aby) / ab_sq))
                        d = dist(rp.x, rp.y, sx + t * abx, sy + t * aby)
                        if d < 25:
                            rp.hp -= 8
                            self.particles.burst(rp.x, rp.y, 8, 60, 0.2, tuple(rp.color), 2)
                            if rp.hp <= 0:
                                rp.alive = False
                                rp.respawn_timer = 3.0
                                self.particles.burst(rp.x, rp.y, 50, 200, 0.8, tuple(rp.color), 4)
                                self.server.add_kill("Host", rp.name, [0, 255, 255])
                                self.server.add_score(0)

        # Remote player projectiles hit the host
        if self.server.friendly_fire and self.ship.alive and self.ship.invuln_timer <= 0:
            ship_r = max(self.ship.grid_w, self.ship.grid_h) * 5
            for p in self.world.projectiles:
                if p.owner != 'remote_player' or not p.alive:
                    continue
                if dist(p.x, p.y, self.ship.x, self.ship.y) < ship_r:
                    self.ship.take_damage(p.damage)
                    p.alive = False
                    self.particles.burst(self.ship.x, self.ship.y, 10, 80, 0.3, NEON_RED, 2)
                    self.audio.play('hit', 0.4)
                    self.camera.shake(5)
                    if not self.ship.alive:
                        pid = getattr(p, '_remote_pid', -1)
                        name = self.server.get_player_name(pid)
                        self.server.add_kill(name, "Host", [255, 100, 100])
                        self.server.add_score(pid)

        # Remote projectiles also damage enemies (co-op)
        for p in self.world.projectiles:
            if p.owner != 'remote_player' or not p.alive:
                continue
            for e in self.world.enemies:
                if not e.alive:
                    continue
                if dist(p.x, p.y, e.x, e.y) < e.radius + 5:
                    e.take_hit(p.damage, self.particles)
                    p.alive = False
                    self.audio.play('hit', 0.3)
                    if not e.alive:
                        pid = getattr(p, '_remote_pid', -1)
                        name = self.server.get_player_name(pid)
                        label = "BOSS" if e.is_boss else "enemy"
                        self.server.add_kill(name, label, [100, 255, 100])
                        self.server.add_score(pid)
                        from game.world import Pickup
                        self.world.pickups.append(Pickup(e.x, e.y, 'credits', e.credit_value))
                        self.audio.play('explosion', 0.5)
                    break

        # Auto-shoot players (turrets target other players)
        if self.server.auto_shoot_players:
            for rp in remote_players:
                if not rp.alive:
                    continue
                d = dist(self.ship.x, self.ship.y, rp.x, rp.y)
                if d < 500:
                    for m in self.ship.turret_modules:
                        if m.cooldown > 0:
                            continue
                        # Check if there's a closer enemy first
                        closer_enemy = False
                        for e in self.world.enemies:
                            if e.alive and dist(self.ship.x, self.ship.y, e.x, e.y) < d:
                                closer_enemy = True
                                break
                        if closer_enemy:
                            continue
                        m.cooldown = 1.0 / m.defn.fire_rate
                        from game.world import Projectile
                        aim = angle_to(self.ship.x, self.ship.y, rp.x, rp.y)
                        proj = Projectile(
                            self.ship.x + math.cos(aim) * 15,
                            self.ship.y + math.sin(aim) * 15,
                            math.cos(aim) * LASER_SPEED * 0.8,
                            math.sin(aim) * LASER_SPEED * 0.8,
                            m.defn.damage, 'player', 'bullet', color=NEON_RED
                        )
                        self.world.projectiles.append(proj)
                        self.audio.play('laser', 0.06)

    def _process_remote_combat(self):
        """Host: process combat actions from remote players."""
        if not self.server:
            return
        from game.world import Projectile
        actions = self.server.get_pending_actions()
        for action in actions:
            px, py = action['x'], action['y']
            angle = action['angle']
            color = tuple(action.get('color', [100, 255, 100]))

            if action['type'] == 'gun':
                spread = random.uniform(-0.05, 0.05)
                a = angle + spread
                proj = Projectile(
                    px + math.cos(a) * 20, py + math.sin(a) * 20,
                    math.cos(a) * LASER_SPEED * 0.9, math.sin(a) * LASER_SPEED * 0.9,
                    5, 'remote_player', 'bullet', color=color
                )
                proj._remote_pid = action['pid']
                self.world.projectiles.append(proj)
                self.particles.burst(px + math.cos(a) * 20, py + math.sin(a) * 20,
                                    3, 60, 0.1, color, 1.5)

            elif action['type'] == 'laser':
                beam_range = 900
                bx, by = math.cos(angle), math.sin(angle)
                sx, sy = px + bx * 25, py + by * 25
                ex, ey = sx + bx * beam_range, sy + by * beam_range
                self.world._active_beams.append({
                    'sx': sx, 'sy': sy, 'ex': ex, 'ey': ey,
                    'color': color, 'life': 0.12, 'width': 2,
                })
                # Beam damage to enemies
                for e in self.world.enemies:
                    if not e.alive:
                        continue
                    # Quick line-point distance
                    abx, aby = ex - sx, ey - sy
                    apx, apy = e.x - sx, e.y - sy
                    ab_sq = abx * abx + aby * aby
                    if ab_sq > 0:
                        t = max(0, min(1, (apx * abx + apy * aby) / ab_sq))
                        d = dist(e.x, e.y, sx + t * abx, sy + t * aby)
                        if d < e.radius + 8:
                            e.take_hit(8, self.particles)
                            if not e.alive:
                                pid = action['pid']
                                name = self.server.get_player_name(pid)
                                label = "BOSS" if e.is_boss else ("ELITE" if e.enemy_type == 'elite' else "enemy")
                                self.server.add_kill(name, label, color)
                                self.server.add_score(pid)
                                self.world.pickups.append(
                                    __import__('game.world', fromlist=['Pickup']).Pickup(
                                        e.x, e.y, 'credits', e.credit_value))
                # Friendly fire: beam hits host ship
                if self.server.friendly_fire and self.ship.alive and self.ship.invuln_timer <= 0:
                    abx2, aby2 = ex - sx, ey - sy
                    apx2, apy2 = self.ship.x - sx, self.ship.y - sy
                    ab_sq2 = abx2 * abx2 + aby2 * aby2
                    if ab_sq2 > 0:
                        t2 = max(0, min(1, (apx2 * abx2 + apy2 * aby2) / ab_sq2))
                        d2 = dist(self.ship.x, self.ship.y, sx + t2 * abx2, sy + t2 * aby2)
                        ship_r = max(self.ship.grid_w, self.ship.grid_h) * 5
                        if d2 < ship_r:
                            self.ship.take_damage(8)
                            self.particles.burst(self.ship.x, self.ship.y, 10, 80, 0.3, NEON_RED, 2)
                            self.audio.play('hit', 0.4)
                            self.camera.shake(5)
                            pid = action['pid']
                            if not self.ship.alive:
                                name = self.server.get_player_name(pid)
                                self.server.add_kill(name, "Host", color)
                                self.server.add_score(pid)

                self.particles.burst(sx, sy, 6, 80, 0.12, color, 2)

            elif action['type'] == 'missile':
                best_enemy = None
                best_d = 800
                for e in self.world.enemies:
                    if not e.alive:
                        continue
                    d = dist(px, py, e.x, e.y)
                    if d < best_d:
                        best_d = d
                        best_enemy = e
                proj = Projectile(
                    px + math.cos(angle) * 20, py + math.sin(angle) * 20,
                    math.cos(angle) * MISSILE_SPEED, math.sin(angle) * MISSILE_SPEED,
                    35, 'remote_player', 'missile', target=best_enemy, color=NEON_PURPLE
                )
                proj._remote_pid = action['pid']
                self.world.projectiles.append(proj)
                self.particles.burst(px + math.cos(angle) * 20, py + math.sin(angle) * 20,
                                    8, 80, 0.2, NEON_PURPLE, 2)

    def _distress_warp(self):
        """Emergency warp to nearest known station. Costs half your credits."""
        self.ship.distress_charging = False
        self.ship.distress_timer = 0.0
        self.ship.distress_cooldown = 30.0  # can't spam it

        # Find nearest station (check all discovered sectors)
        best_station = None
        best_d = float('inf')
        for coord in self.world.sectors.discovered:
            sector = self.world.sectors.loaded.get(coord)
            if not sector:
                sector = self.world.sectors.get_sector(coord)
            if sector and sector.station:
                d = dist(self.ship.x, self.ship.y, sector.station.x, sector.station.y)
                if d < best_d:
                    best_d = d
                    best_station = sector.station

        if not best_station:
            # Fallback: warp to origin
            self.ship.x = 0
            self.ship.y = 0
        else:
            self.ship.x = best_station.x + 120
            self.ship.y = best_station.y

        self.ship.vx = 0
        self.ship.vy = 0
        self.ship.invuln_timer = 3.0

        # Costs half your credits (rescue ain't free)
        penalty = self.ship.credits // 2
        self.ship.credits -= penalty

        self.particles.burst(self.ship.x, self.ship.y, 40, 200, 0.6, NEON_CYAN, 3)
        self.audio.play('dock', 0.6)
        self.camera.shake(10)
        self.hud.notify(f"EMERGENCY WARP! -{penalty} credits", NEON_YELLOW, 3.0)

        # Re-stream sectors around new position
        self.world.sectors.update_streaming(self.ship.x, self.ship.y, self.world.game_time)
        self.world._loaded_asteroid_sectors.clear()
        self.world.asteroids.clear()
        self.world._sync_entities()

    def _undock(self):
        self.ship.docked = False
        self.station_ui.close()
        self.ship.invuln_timer = 1.5
        self.audio.play('undock', 0.5)
        self.hud.notify("Undocked. Fly safe.", NEON_CYAN, 2.0)

    def _try_launch_probe(self):
        target = self.world.get_nearest_asteroid(self.ship.x, self.ship.y, 500)
        if target:
            if self.world.launch_probe(self.ship, target, self.audio):
                self.hud.notify("Probe launched!", NEON_GREEN, 1.5)
            else:
                if self.ship.active_probes >= self.ship.max_probes:
                    self.hud.notify("All probes deployed!", NEON_ORANGE, 1.5)
                elif target.depleted:
                    self.hud.notify("Asteroid depleted!", NEON_RED, 1.5)
        else:
            self.hud.notify("No asteroid in range", DIM_CYAN, 1.5)

    def _draw_mp_hud(self, scores, kill_feed, is_host):
        """Draw multiplayer scoreboard and kill feed."""
        # Kill feed (top-center)
        fy = 80
        if kill_feed:
            entries = kill_feed[-5:] if is_host else kill_feed[-5:]
            for entry in entries:
                if is_host:
                    text, color, ts = entry
                else:
                    text, color = entry
                draw_text(self.screen, text, SCREEN_W // 2, fy,
                         safe_color(color[0], color[1], color[2]) if isinstance(color, (list, tuple)) else DIM_CYAN,
                         10, center=True)
                fy += 14

        # Scoreboard (top-left area, below resources)
        if scores:
            sy = 180
            draw_text(self.screen, "SCOREBOARD", 15, sy, NEON_PURPLE, 11)
            sy += 16
            # Get player names
            sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
            for pid_str, kills in sorted_scores[:6]:
                pid = int(pid_str)
                if is_host and self.server:
                    name = self.server.get_player_name(pid)
                else:
                    # Client: look up name from remote_players
                    players = self.client.get_players() if self.client else {}
                    pdata = players.get(pid_str, {})
                    name = pdata.get('name', 'Host' if pid == 0 else f'P{pid}')
                color = NEON_CYAN if pid == 0 else NEON_GREEN
                draw_text(self.screen, f"  {name}: {kills}", 15, sy, color, 10)
                sy += 14

    def _draw_remote_players(self):
        """Draw other players from multiplayer."""
        players = {}
        if self.is_host and self.server:
            with self.server.lock:
                players = {str(pid): p.to_dict() for pid, p in self.server.remote_players.items()}
        elif self.is_client and self.client:
            players = self.client.get_players()

        for pid, pdata in players.items():
            if self.is_client and int(pid) == self.client.my_id:
                continue  # don't draw ourselves
            if not pdata.get('alive', True):
                continue
            px, py = pdata.get('x', 0), pdata.get('y', 0)
            sx, sy = self.camera.world_to_screen(px, py)
            if sx < -100 or sx > SCREEN_W + 100 or sy < -100 or sy > SCREEN_H + 100:
                continue

            angle = pdata.get('angle', 0)
            color = tuple(pdata.get('color', [0, 255, 255]))
            name = pdata.get('name', '?')

            # Ship shape
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            r = 16
            pts = [
                (sx + cos_a * r * 2, sy + sin_a * r * 2),
                (sx + cos_a * (-r) - sin_a * (-r * 1.2),
                 sy + sin_a * (-r) + cos_a * (-r * 1.2)),
                (sx + cos_a * (-r * 0.5), sy + sin_a * (-r * 0.5)),
                (sx + cos_a * (-r) - sin_a * (r * 1.2),
                 sy + sin_a * (-r) + cos_a * (r * 1.2)),
            ]
            pygame.draw.polygon(self.screen, (color[0] // 3, color[1] // 3, color[2] // 3), pts)
            pygame.draw.polygon(self.screen, color, pts, 2)

            # Engine glow
            vx = pdata.get('vx', 0)
            vy = pdata.get('vy', 0)
            speed = math.sqrt(vx * vx + vy * vy)
            if speed > 10:
                eng_x = sx - cos_a * r * 0.8
                eng_y = sy - sin_a * r * 0.8
                eng_r = 3 + min(5, speed / 80)
                eng_c = safe_color(color[0] * 0.8, color[1] * 0.5, color[2] * 0.2)
                pygame.draw.circle(self.screen, eng_c, (int(eng_x), int(eng_y)), max(1, int(eng_r)))

            # Name tag
            draw_text(self.screen, name, int(sx), int(sy - 28), color, 11, center=True)

            # HP bar
            hp = pdata.get('hp', 100)
            max_hp = pdata.get('max_hp', 100)
            if max_hp > 0:
                draw_bar(self.screen, int(sx - 18), int(sy - 20), 36, 5,
                        hp / max_hp, color, (20, 20, 30), safe_color(color[0] * 0.5, color[1] * 0.5, color[2] * 0.5))

            # Respawn indicator
            respawn = pdata.get('respawn', 0)
            if not pdata.get('alive', True) and respawn > 0:
                draw_text(self.screen, f"RESPAWN: {respawn:.0f}s", int(sx), int(sy), NEON_RED, 12, center=True)

        # Draw synced entities from server (client-side rendering)
        if self.is_client and self.client:
            with self.client.lock:
                remote_projs = list(self.client.remote_projectiles)
                remote_beams = list(self.client.remote_beams)
                remote_probes = list(self.client.remote_probes)

            # Probes
            for p in remote_probes:
                px, py = p.get('x', 0), p.get('y', 0)
                sx, sy = self.camera.world_to_screen(px, py)
                if sx < -50 or sx > SCREEN_W + 50 or sy < -50 or sy > SCREEN_H + 50:
                    continue
                state = p.get('state', 'traveling')
                color = NEON_GREEN if state != 'mining' else ORE_COLOR
                glow = 0.5 + 0.5 * math.sin(self.time * 8)
                draw_glow_circle(self.screen, color, (sx, sy), 4, 12, int(40 + 30 * glow))
                cargo = p.get('cargo', 0)
                if cargo > 0:
                    draw_bar(self.screen, int(sx - 8), int(sy - 10), 16, 3,
                            cargo / PROBE_CARRY, ORE_COLOR, (20, 15, 10))

            for p in remote_projs:
                px, py = p.get('x', 0), p.get('y', 0)
                sx, sy = self.camera.world_to_screen(px, py)
                if sx < -50 or sx > SCREEN_W + 50 or sy < -50 or sy > SCREEN_H + 50:
                    continue
                c = tuple(p.get('color', [255, 255, 0]))
                ptype = p.get('type', 'bullet')
                if ptype == 'bullet':
                    vx, vy = p.get('vx', 0), p.get('vy', 0)
                    spd = max(1, math.sqrt(vx * vx + vy * vy))
                    nx, ny = vx / spd * 5, vy / spd * 5
                    pygame.draw.line(self.screen, c, (int(sx - nx), int(sy - ny)), (int(sx + nx), int(sy + ny)), 2)
                elif ptype == 'missile':
                    draw_glow_circle(self.screen, c, (sx, sy), 3, 10, 50)

            for b in remote_beams:
                sx1, sy1 = self.camera.world_to_screen(b.get('sx', 0), b.get('sy', 0))
                sx2, sy2 = self.camera.world_to_screen(b.get('ex', 0), b.get('ey', 0))
                c = tuple(b.get('color', [255, 80, 80]))
                alpha = max(0, min(1, b.get('life', 0.1) / 0.12))
                beam_c = safe_color(c[0] * 0.7 * alpha, c[1] * 0.7 * alpha, c[2] * 0.7 * alpha)
                pygame.draw.line(self.screen, beam_c, (int(sx1), int(sy1)), (int(sx2), int(sy2)), 3)
                core_c = safe_color((c[0] * 0.5 + 128) * alpha, (c[1] * 0.5 + 128) * alpha, (c[2] * 0.5 + 128) * alpha)
                pygame.draw.line(self.screen, core_c, (int(sx1), int(sy1)), (int(sx2), int(sy2)), 1)

    def _draw_gameplay(self, dt):
        self.screen.fill(BG_DARK)

        # Stars
        self.stars.draw(self.screen, self.camera, self.time)

        # World entities
        self.world.draw(self.screen, self.camera, self.time)

        # Player ship
        if self.ship.alive and not self.ship.docked:
            self.ship.draw(self.screen, self.camera, self.time)

        # Remote players (multiplayer)
        self._draw_remote_players()

        # Particles
        self.particles.draw(self.screen, self.camera)

        # Crosshair
        if self.ship.alive and not self.ship.docked:
            mx, my = pygame.mouse.get_pos()
            size = 8
            btns = pygame.mouse.get_pressed()
            if btns[0]:  # LMB - guns
                color = NEON_YELLOW
            elif btns[2]:  # RMB - laser
                color = NEON_RED
            elif btns[1]:  # MMB - missile
                color = NEON_PURPLE
            else:
                color = (80, 100, 120)
            pygame.draw.line(self.screen, color, (mx - size, my), (mx + size, my), 1)
            pygame.draw.line(self.screen, color, (mx, my - size), (mx, my + size), 1)
            pygame.draw.circle(self.screen, color, (mx, my), size, 1)

        # Nearby indicators
        self._draw_indicators()

        # HUD (only when not in station/map)
        if not self.station_ui.active and not self.sector_map.active:
            self.hud.draw(self.screen, self.ship, self.world, self.time, self.camera)

    def _draw_indicators(self):
        if self.ship.docked:
            return

        # Dock indicator near stations
        for sector in self.world.sectors.get_loaded_sectors():
            if sector.station:
                d = dist(self.ship.x, self.ship.y, sector.station.x, sector.station.y)
                if d < sector.station.dock_range * 2:
                    sx, sy = self.camera.world_to_screen(sector.station.x, sector.station.y)
                    if d < sector.station.dock_range:
                        draw_text(self.screen, "[F] DOCK", int(sx), int(sy + 65),
                                 NEON_CYAN, 13, center=True)
                    else:
                        draw_text(self.screen, "Move closer to dock", int(sx), int(sy + 65),
                                 DIM_CYAN, 10, center=True)

        # Asteroid mining indicator
        nearest = self.world.get_nearest_asteroid(self.ship.x, self.ship.y, 600)
        if nearest:
            d = dist(self.ship.x, self.ship.y, nearest.x, nearest.y)
            if d > 50 and d < 500:
                angle = angle_to(self.ship.x, self.ship.y, nearest.x, nearest.y)
                indicator_dist = min(80, d * 0.3)
                sx, sy = self.camera.world_to_screen(self.ship.x, self.ship.y)
                ix = sx + math.cos(angle) * indicator_dist
                iy = sy + math.sin(angle) * indicator_dist
                alpha = max(0.3, 1.0 - d / 600)
                color = (int(ORE_COLOR[0] * alpha), int(ORE_COLOR[1] * alpha), int(ORE_COLOR[2] * alpha))
                arrow_pts = [
                    (ix + math.cos(angle) * 8, iy + math.sin(angle) * 8),
                    (ix + math.cos(angle + 2.5) * 5, iy + math.sin(angle + 2.5) * 5),
                    (ix + math.cos(angle - 2.5) * 5, iy + math.sin(angle - 2.5) * 5),
                ]
                pygame.draw.polygon(self.screen, color, arrow_pts)
                if d < 500:
                    draw_text(self.screen, f"[E] Mine ore ({int(nearest.ore)})",
                             int(ix + 15), int(iy - 8), color, 10)

        # Anomaly research indicator
        for sector in self.world.sectors.get_loaded_sectors():
            for poi in sector.pois:
                if poi.poi_type == 'anomaly' and poi.discovered and not poi.researched:
                    d = dist(self.ship.x, self.ship.y, poi.x, poi.y)
                    if d < poi.effect_radius:
                        sx, sy = self.camera.world_to_screen(poi.x, poi.y)
                        has_research = any(m.defn.id == 'research' for m in self.ship.modules if m.active)
                        if has_research:
                            progress = int(getattr(poi, 'research_progress', 0))
                            draw_text(self.screen, f"[F] Research Anomaly ({progress}/5)",
                                     int(sx), int(sy + 30), NEON_PURPLE, 13, center=True)
                            from game.ship import MODULE_DEFS
                            reward_def = MODULE_DEFS.get(poi.reward_module, None)
                            if reward_def:
                                draw_text(self.screen, f"Reward: {reward_def.name}",
                                         int(sx), int(sy + 46), (160, 100, 255), 10, center=True)
                        else:
                            draw_text(self.screen, "Need Research Center module!",
                                     int(sx), int(sy + 30), (120, 60, 160), 11, center=True)

        # POI interaction indicator
        poi = self.world.get_nearby_poi(self.ship.x, self.ship.y)
        if poi:
            d = dist(self.ship.x, self.ship.y, poi.x, poi.y)
            sx, sy = self.camera.world_to_screen(poi.x, poi.y)
            if d < poi.interaction_range:
                draw_text(self.screen, f"[F] {poi.label}", int(sx), int(sy + 25),
                         poi.color, 12, center=True)


if __name__ == "__main__":
    try:
        game = Game()
        game.run()
    except (KeyboardInterrupt, SystemExit):
        pygame.quit()
        sys.exit(0)
    except Exception as e:
        import traceback
        error_text = traceback.format_exc()

        # Write crash to file FIRST — this always works
        crash_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
        with open(crash_path, "w") as f:
            f.write(error_text)

        # Print to terminal
        print(error_text)
        print(f"\nCrash saved to: {crash_path}")
        print("Paste the contents of crash.log to get help.")

        # Try to keep terminal open
        try:
            input("Press ENTER to close...")
        except Exception:
            pass

        sys.exit(1)
