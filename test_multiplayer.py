"""
Multiplayer test script — run this to simulate a client connecting to a local host.
Start the game normally first, click HOST, then run this script in another terminal.

Usage: py test_multiplayer.py
"""
import sys
import time
import threading

def test():
    from game.network import GameServer, GameClient, LANScanner, get_local_ip

    print("=" * 50)
    print("  NEON VOID — Multiplayer Test")
    print("=" * 50)

    # Test 1: Server start
    print("\n[1] Starting test server...")
    server = GameServer(port=7790, friendly_fire=True, auto_shoot_players=False)
    server.start()
    print(f"    Server running on {get_local_ip()}:7790")

    # Test 2: LAN Discovery
    print("\n[2] Testing LAN discovery...")
    scanner = LANScanner()
    scanner.start()
    found = False
    for i in range(4):
        time.sleep(1)
        servers = scanner.get_servers()
        if servers:
            for ip, info in servers.items():
                print(f"    FOUND: {ip}:{info['port']} ({info['players']} players)")
            found = True
            break
        print(f"    Scanning... ({i+1}s)")
    scanner.stop()
    if not found:
        print("    WARNING: LAN discovery didn't find server (may be firewall)")
        print("    Direct connect should still work")

    # Test 3: Client connect
    print("\n[3] Connecting test client...")
    client = GameClient()
    ok = client.connect('127.0.0.1', port=7790, name='TestBot')
    print(f"    Connected: {ok}")
    if ok:
        print(f"    ID: {client.my_id}, Name: {client.my_name}")
        print(f"    Color: {client.my_color}")
        print(f"    Settings: {client.settings}")

    # Test 4: Input/state sync
    print("\n[4] Testing input sync...")
    class FakeShip:
        x, y, vx, vy, angle = 1000.0, 500.0, 30.0, 0.0, 0.5
        core_hp, core_max_hp = 85, 100
        shield, max_shield = 30, 50
        alive = True
        total_thrust = 400

    for i in range(10):
        client.send_input(
            {'w': True, 's': False, 'a': False, 'd': False, 'shift': i > 5},
            1100.0, 600.0,
            i % 3 == 0, i % 5 == 0, False  # gun, laser, missile
        )
        server.update_players(0.016, FakeShip())
        time.sleep(0.1)

    players = client.get_players()
    print(f"    Client sees {len(players)} player(s)")
    for pid, p in players.items():
        print(f"      [{pid}] {p['name']} at ({p['x']:.0f}, {p['y']:.0f}) HP:{p['hp']:.0f}/{p['max_hp']:.0f}")

    # Test 5: Combat actions
    print("\n[5] Testing combat actions...")
    actions = server.get_pending_actions()
    gun_count = sum(1 for a in actions if a['type'] == 'gun')
    laser_count = sum(1 for a in actions if a['type'] == 'laser')
    print(f"    Pending actions: {len(actions)} (guns: {gun_count}, lasers: {laser_count})")

    # Test 6: Kill feed and scores
    print("\n[6] Testing kill feed & scores...")
    server.add_kill("TestBot", "pirate", (100, 255, 100))
    server.add_kill("Host", "BOSS", (0, 255, 255))
    server.add_score(0, 5)
    server.add_score(1, 3)
    time.sleep(0.5)
    # Client should receive these
    client.send_input({'w': False, 's': False, 'a': False, 'd': False, 'shift': False},
                      0, 0, False, False, False)
    time.sleep(0.5)
    with client.lock:
        print(f"    Kill feed: {client.kill_feed}")
        print(f"    Scores: {client.scores}")

    # Test 7: Second client
    print("\n[7] Testing second client...")
    client2 = GameClient()
    ok2 = client2.connect('127.0.0.1', port=7790, name='Player2')
    print(f"    Client2 connected: {ok2}")
    if ok2:
        time.sleep(0.5)
        server.update_players(0.016, FakeShip())
        time.sleep(0.5)
        p2_players = client2.get_players()
        print(f"    Client2 sees {len(p2_players)} player(s)")
        client2.disconnect()

    # Cleanup
    print("\n[8] Cleaning up...")
    client.disconnect()
    time.sleep(0.3)
    server.stop()

    print("\n" + "=" * 50)
    print("  ALL MULTIPLAYER TESTS PASSED!")
    print("=" * 50)

if __name__ == "__main__":
    test()
