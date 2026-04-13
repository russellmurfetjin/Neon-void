"""Networking layer for multiplayer. Host runs simulation, clients send inputs."""
import socket
import threading
import json
import time
import math
import random
from typing import Dict, List, Optional, Tuple

DEFAULT_PORT = 7777
BEACON_PORT = 7778
TICK_RATE = 20  # state updates per second
BUFFER_SIZE = 65536


def get_local_ip():
    """Get this machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ═════════════════════════════════════════════════════════════════════════════
#  SHARED PROTOCOL
# ═════════════════════════════════════════════════════════════════════════════
def send_msg(sock, data: dict):
    """Send a JSON message with length prefix."""
    try:
        raw = json.dumps(data, separators=(',', ':')).encode('utf-8')
        header = len(raw).to_bytes(4, 'big')
        sock.sendall(header + raw)
        return True
    except Exception:
        return False


def recv_msg(sock) -> Optional[dict]:
    """Receive a length-prefixed JSON message. Returns None on error."""
    try:
        header = b''
        while len(header) < 4:
            chunk = sock.recv(4 - len(header))
            if not chunk:
                return None
            header += chunk
        length = int.from_bytes(header, 'big')
        if length > BUFFER_SIZE:
            return None
        data = b''
        while len(data) < length:
            chunk = sock.recv(min(length - len(data), 8192))
            if not chunk:
                return None
            data += chunk
        return json.loads(data.decode('utf-8'))
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  REMOTE PLAYER STATE (what the host tracks per connected client)
# ═════════════════════════════════════════════════════════════════════════════
class RemotePlayer:
    def __init__(self, player_id: int, name: str):
        self.id = player_id
        self.name = name
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 0.0
        self.hp = 100.0
        self.max_hp = 100.0
        self.shield = 0.0
        self.max_shield = 0.0
        self.alive = True
        self.color = (0, 255, 255)
        # Input state from client
        self.input_keys = {'w': False, 's': False, 'a': False, 'd': False, 'shift': False}
        self.input_mouse_wx = 0.0
        self.input_mouse_wy = 0.0
        self.input_fire_gun = False
        self.input_fire_laser = False
        self.input_fire_missile = False
        # Firing cooldown
        self.gun_cooldown = 0.0
        self.laser_cooldown = 0.0
        self.missile_cooldown = 0.0

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name,
            'x': round(self.x, 1), 'y': round(self.y, 1),
            'vx': round(self.vx, 1), 'vy': round(self.vy, 1),
            'angle': round(self.angle, 2),
            'hp': round(self.hp, 1), 'max_hp': round(self.max_hp, 1),
            'shield': round(self.shield, 1), 'max_shield': round(self.max_shield, 1),
            'alive': self.alive,
            'color': self.color,
        }


# ═════════════════════════════════════════════════════════════════════════════
#  SERVER (runs on host)
# ═════════════════════════════════════════════════════════════════════════════
class GameServer:
    def __init__(self, port=DEFAULT_PORT, friendly_fire=False, auto_shoot_players=False):
        self.port = port
        self.friendly_fire = friendly_fire
        self.auto_shoot_players = auto_shoot_players
        self.running = False
        self.clients: Dict[int, dict] = {}  # id -> {socket, thread, player}
        self.next_id = 1
        self.lock = threading.Lock()
        self.server_socket = None
        self.accept_thread = None
        # Remote player data
        self.remote_players: Dict[int, RemotePlayer] = {}
        # Outgoing state snapshot
        self.state_snapshot = {}
        self.beams_snapshot = []
        self.projectiles_snapshot = []
        self.host_ship_data = {}  # host's ship state for clients to see
        self.pending_actions = []  # combat actions from remote players
        self.kill_feed = []  # recent kill messages [(text, color, time)]
        self.scores: Dict[int, int] = {0: 0}  # pid -> kill count (0 = host)

    def start(self):
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1.0)
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(4)
        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()
        # Start LAN broadcast beacon
        self.beacon_thread = threading.Thread(target=self._beacon_loop, daemon=True)
        self.beacon_thread.start()

    def stop(self):
        self.running = False
        with self.lock:
            for cid, client in list(self.clients.items()):
                try:
                    client['socket'].close()
                except Exception:
                    pass
            self.clients.clear()
            self.remote_players.clear()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def _beacon_loop(self):
        """Broadcast UDP beacon so LAN clients can discover this server."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            local_ip = get_local_ip()
            while self.running:
                beacon = json.dumps({
                    'game': 'NEON_VOID',
                    'ip': local_ip,
                    'port': self.port,
                    'players': self.get_player_count(),
                    'friendly_fire': self.friendly_fire,
                    'auto_shoot': self.auto_shoot_players,
                }).encode('utf-8')
                try:
                    sock.sendto(beacon, ('<broadcast>', BEACON_PORT))
                except Exception:
                    pass
                time.sleep(1.0)
            sock.close()
        except Exception:
            pass

    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                conn.settimeout(5.0)
                # Receive join message
                msg = recv_msg(conn)
                if not msg or msg.get('type') != 'join':
                    conn.close()
                    continue

                with self.lock:
                    pid = self.next_id
                    self.next_id += 1
                    name = msg.get('name', f'Player {pid}')
                    player = RemotePlayer(pid, name)
                    colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 255, 100)]
                    player.color = colors[pid % len(colors)]
                    self.remote_players[pid] = player

                # Send welcome BEFORE starting client thread
                send_msg(conn, {
                    'type': 'welcome',
                    'id': pid,
                    'name': name,
                    'color': player.color,
                    'settings': {
                        'friendly_fire': self.friendly_fire,
                        'auto_shoot_players': self.auto_shoot_players,
                    }
                })

                with self.lock:
                    thread = threading.Thread(target=self._client_loop, args=(pid, conn), daemon=True)
                    self.clients[pid] = {'socket': conn, 'thread': thread, 'player': player}
                    thread.start()
            except socket.timeout:
                continue
            except Exception:
                if not self.running:
                    break

    def _client_loop(self, pid, conn):
        """Receive inputs from a client, send state updates."""
        conn.settimeout(2.0)
        last_send = 0
        while self.running:
            # Receive input
            try:
                msg = recv_msg(conn)
                if msg is None:
                    break
                if msg.get('type') == 'input':
                    with self.lock:
                        if pid in self.remote_players:
                            p = self.remote_players[pid]
                            p.input_keys = msg.get('keys', p.input_keys)
                            p.input_mouse_wx = msg.get('mwx', 0)
                            p.input_mouse_wy = msg.get('mwy', 0)
                            p.input_fire_gun = msg.get('gun', False)
                            p.input_fire_laser = msg.get('laser', False)
                            p.input_fire_missile = msg.get('missile', False)
                elif msg.get('type') == 'disconnect':
                    break
            except socket.timeout:
                pass
            except Exception:
                break

            # Send state at tick rate
            now = time.time()
            if now - last_send > 1.0 / TICK_RATE:
                last_send = now
                with self.lock:
                    snapshot = self._build_snapshot()
                if not send_msg(conn, snapshot):
                    break

        # Clean up
        with self.lock:
            self.clients.pop(pid, None)
            self.remote_players.pop(pid, None)
        try:
            conn.close()
        except Exception:
            pass

    def _build_snapshot(self):
        players = {str(pid): p.to_dict() for pid, p in self.remote_players.items()}
        if self.host_ship_data:
            players['0'] = self.host_ship_data
        # Recent kill feed (last 5)
        feed = [(text, color) for text, color, t in self.kill_feed[-5:]]
        return {
            'type': 'state',
            'players': players,
            'beams': self.beams_snapshot,
            'projectiles': self.projectiles_snapshot,
            'scores': {str(k): v for k, v in self.scores.items()},
            'kill_feed': feed,
            'settings': {
                'friendly_fire': self.friendly_fire,
                'auto_shoot_players': self.auto_shoot_players,
            },
        }

    def update_players(self, dt, host_ship):
        """Update remote player physics on the host. Called from game loop."""
        # Capture host ship state for clients
        self.host_ship_data = {
            'id': 0, 'name': 'Host',
            'x': round(host_ship.x, 1), 'y': round(host_ship.y, 1),
            'vx': round(host_ship.vx, 1), 'vy': round(host_ship.vy, 1),
            'angle': round(host_ship.angle, 2),
            'hp': round(host_ship.core_hp, 1), 'max_hp': round(host_ship.core_max_hp, 1),
            'shield': round(host_ship.shield, 1), 'max_shield': round(host_ship.max_shield, 1),
            'alive': host_ship.alive,
            'color': [0, 255, 255],
        }

        with self.lock:
            for pid, p in self.remote_players.items():
                if not p.alive:
                    continue

                # Spawn new players near host if still at origin
                if p.x == 0 and p.y == 0 and (host_ship.x != 0 or host_ship.y != 0):
                    p.x = host_ship.x + random.uniform(-100, 100)
                    p.y = host_ship.y + random.uniform(-100, 100)
                    p.hp = host_ship.core_max_hp
                    p.max_hp = host_ship.core_max_hp

                thrust = host_ship.total_thrust
                drag = 0.98
                max_speed = 500.0

                # Apply input
                tx, ty = 0, 0
                if p.input_keys.get('w'): ty -= 1
                if p.input_keys.get('s'): ty += 1
                if p.input_keys.get('a'): tx -= 1
                if p.input_keys.get('d'): tx += 1

                boosting = p.input_keys.get('shift', False)

                mag = math.sqrt(tx * tx + ty * ty)
                if mag > 0:
                    tx /= mag
                    ty /= mag
                    t = thrust * (2.5 if boosting else 1.0)
                    p.vx += tx * t * dt
                    p.vy += ty * t * dt

                p.vx *= drag
                p.vy *= drag
                speed = math.sqrt(p.vx ** 2 + p.vy ** 2)
                if speed > max_speed:
                    p.vx = p.vx / speed * max_speed
                    p.vy = p.vy / speed * max_speed

                p.x += p.vx * dt
                p.y += p.vy * dt
                p.angle = math.atan2(p.input_mouse_wy - p.y, p.input_mouse_wx - p.x)

                # Cooldowns
                p.gun_cooldown = max(0, p.gun_cooldown - dt)
                p.laser_cooldown = max(0, p.laser_cooldown - dt)
                p.missile_cooldown = max(0, p.missile_cooldown - dt)

                # Combat — queue actions for the host world to process
                if p.input_fire_gun and p.gun_cooldown <= 0:
                    p.gun_cooldown = 0.125  # 8 shots/sec
                    self.pending_actions.append({
                        'type': 'gun', 'pid': pid,
                        'x': p.x, 'y': p.y, 'angle': p.angle,
                        'color': p.color,
                    })
                if p.input_fire_laser and p.laser_cooldown <= 0:
                    p.laser_cooldown = 0.3
                    self.pending_actions.append({
                        'type': 'laser', 'pid': pid,
                        'x': p.x, 'y': p.y, 'angle': p.angle,
                        'color': p.color,
                    })
                if p.input_fire_missile and p.missile_cooldown <= 0:
                    p.missile_cooldown = 1.5
                    self.pending_actions.append({
                        'type': 'missile', 'pid': pid,
                        'x': p.x, 'y': p.y, 'angle': p.angle,
                        'color': p.color,
                    })

                # HP/shield from host ship (simplified)
                p.max_hp = host_ship.core_max_hp
                p.max_shield = host_ship.max_shield

    def get_player_count(self):
        with self.lock:
            return len(self.remote_players)

    def add_kill(self, killer_name, victim_name, color=(255, 255, 255)):
        self.kill_feed.append((f"{killer_name} destroyed {victim_name}", color, time.time()))
        # Prune old entries
        now = time.time()
        self.kill_feed = [(t, c, ts) for t, c, ts in self.kill_feed if now - ts < 10]

    def add_score(self, pid, amount=1):
        if pid not in self.scores:
            self.scores[pid] = 0
        self.scores[pid] += amount

    def get_pending_actions(self):
        actions = self.pending_actions
        self.pending_actions = []
        return actions

    def get_player_name(self, pid):
        if pid == 0:
            return "Host"
        with self.lock:
            p = self.remote_players.get(pid)
            return p.name if p else f"Player {pid}"


# ═════════════════════════════════════════════════════════════════════════════
#  LAN SCANNER (discovers servers on local network)
# ═════════════════════════════════════════════════════════════════════════════
class LANScanner:
    def __init__(self):
        self.running = False
        self.lock = threading.Lock()
        self.found_servers: Dict[str, dict] = {}  # ip -> server info
        self.thread = None

    def start(self):
        self.running = True
        self.found_servers.clear()
        self.thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _scan_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1.0)
            sock.bind(('', BEACON_PORT))
            while self.running:
                try:
                    data, addr = sock.recvfrom(4096)
                    info = json.loads(data.decode('utf-8'))
                    if info.get('game') == 'NEON_VOID':
                        ip = info.get('ip', addr[0])
                        info['last_seen'] = time.time()
                        with self.lock:
                            self.found_servers[ip] = info
                except socket.timeout:
                    pass
                except Exception:
                    pass
                # Prune stale servers (not seen in 5 seconds)
                now = time.time()
                with self.lock:
                    stale = [ip for ip, s in self.found_servers.items()
                            if now - s.get('last_seen', 0) > 5]
                    for ip in stale:
                        del self.found_servers[ip]
            sock.close()
        except Exception:
            pass

    def get_servers(self) -> Dict[str, dict]:
        with self.lock:
            return dict(self.found_servers)


# ═════════════════════════════════════════════════════════════════════════════
#  CLIENT (runs on joining player)
# ═════════════════════════════════════════════════════════════════════════════
class GameClient:
    def __init__(self):
        self.connected = False
        self.socket = None
        self.thread = None
        self.my_id = 0
        self.my_name = ""
        self.my_color = (0, 255, 255)
        self.settings = {}
        self.lock = threading.Lock()
        # Latest state from server
        self.remote_players: Dict[str, dict] = {}
        self.remote_beams: List[dict] = []
        self.remote_projectiles: List[dict] = []
        self.scores: Dict[str, int] = {}
        self.kill_feed: List[tuple] = []
        self.error = ""

    def connect(self, host_ip: str, port: int = DEFAULT_PORT, name: str = "Player"):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((host_ip, port))

            # Send join
            send_msg(self.socket, {'type': 'join', 'name': name})

            # Receive welcome
            msg = recv_msg(self.socket)
            if not msg or msg.get('type') != 'welcome':
                self.error = "Server rejected connection"
                self.socket.close()
                return False

            self.my_id = msg['id']
            self.my_name = msg['name']
            self.my_color = tuple(msg.get('color', [0, 255, 255]))
            self.settings = msg.get('settings', {})
            self.connected = True

            # Start receive thread
            self.socket.settimeout(2.0)
            self.thread = threading.Thread(target=self._recv_loop, daemon=True)
            self.thread.start()
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def disconnect(self):
        self.connected = False
        if self.socket:
            try:
                send_msg(self.socket, {'type': 'disconnect'})
                self.socket.close()
            except Exception:
                pass

    def send_input(self, keys, mouse_wx, mouse_wy, fire_gun, fire_laser, fire_missile):
        if not self.connected:
            return
        try:
            send_msg(self.socket, {
                'type': 'input',
                'keys': keys,
                'mwx': round(mouse_wx, 1),
                'mwy': round(mouse_wy, 1),
                'gun': fire_gun,
                'laser': fire_laser,
                'missile': fire_missile,
            })
        except Exception:
            self.connected = False

    def _recv_loop(self):
        while self.connected:
            try:
                msg = recv_msg(self.socket)
                if msg is None:
                    self.connected = False
                    self.error = "Disconnected from host"
                    break
                if msg.get('type') == 'state':
                    with self.lock:
                        self.remote_players = msg.get('players', {})
                        self.remote_beams = msg.get('beams', [])
                        self.remote_projectiles = msg.get('projectiles', [])
                        self.scores = msg.get('scores', {})
                        self.kill_feed = msg.get('kill_feed', [])
                        self.settings = msg.get('settings', self.settings)
            except socket.timeout:
                continue
            except Exception:
                self.connected = False
                self.error = "Connection lost"
                break

    def get_players(self) -> Dict[str, dict]:
        with self.lock:
            return dict(self.remote_players)

    def get_beams(self) -> List[dict]:
        with self.lock:
            return list(self.remote_beams)
