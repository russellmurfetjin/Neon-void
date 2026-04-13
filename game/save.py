"""Save/load system using JSON."""
import json
import os
from typing import Optional

SAVE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "savegame.json")


def save_game(game) -> bool:
    """Serialize game state to JSON file. Returns True on success."""
    try:
        ship = game.ship
        world = game.world
        sectors = world.sectors

        data = {
            "version": 2,
            # Ship
            "ship": {
                "x": ship.x,
                "y": ship.y,
                "vx": ship.vx,
                "vy": ship.vy,
                "angle": ship.angle,
                "grid_w": ship.grid_w,
                "grid_h": ship.grid_h,
                "fuel": ship.fuel,
                "ore": ship.ore,
                "credits": ship.credits,
                "shield": ship.shield,
                "alive": ship.alive,
                "docked": ship.docked,
                "refinery_enabled": ship.refinery_enabled,
                "sectors_discovered": ship.sectors_discovered,
                "farthest_sector": ship.farthest_sector,
                "modules": [
                    {
                        "id": m.defn.id,
                        "gx": m.gx,
                        "gy": m.gy,
                        "hp": m.hp,
                    }
                    for m in ship.modules
                ],
            },
            # World
            "game_time": world.game_time,
            "total_credits_earned": game.total_credits_earned,
            "void_titan_killed": world.void_titan_killed,
            "titan_victory_shown": world.titan_victory_shown,
            "missions_completed": world.missions_completed,
            # Sectors - only save persistent state (discovery, POI loot, patrol clears)
            "sectors": {
                "discovered": [list(c) for c in sectors.discovered],
                "farthest_distance": sectors.farthest_distance,
                "sector_state": {},
            },
        }

        # Save per-sector persistent state (POI/patrol status)
        for coord, sector in sectors.loaded.items():
            key = f"{coord[0]},{coord[1]}"
            sec_data = {
                "pois": [
                    {"discovered": p.discovered, "looted": p.looted,
                     "researched": getattr(p, 'researched', False),
                     "research_progress": getattr(p, 'research_progress', 0)}
                    for p in sector.pois
                ],
                "patrols": [
                    {"spawned": pg.spawned, "cleared": pg.cleared, "clear_time": pg.clear_time}
                    for pg in sector.patrol_groups
                ],
            }
            if sector.station and hasattr(sector.station, 'stock'):
                sec_data["station_stock"] = sector.station.stock
            data["sectors"]["sector_state"][key] = sec_data

        # Also save asteroid depletion for loaded sectors
        asteroid_states = []
        for a in world.asteroids:
            if a.depleted or a.ore < a.max_ore:
                asteroid_states.append({
                    "x": round(a.x, 1),
                    "y": round(a.y, 1),
                    "ore": a.ore,
                    "depleted": a.depleted,
                })
        data["asteroid_states"] = asteroid_states

        with open(SAVE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Save failed: {e}")
        return False


def load_game(game) -> bool:
    """Restore game state from JSON file. Returns True on success."""
    try:
        if not os.path.exists(SAVE_FILE):
            return False

        with open(SAVE_FILE, 'r') as f:
            data = json.load(f)

        if data.get("version", 0) < 2:
            return False

        from game.ship import Ship, MODULE_DEFS
        from game.world import World
        from game.core import Camera, ParticleSystem

        # Create fresh game objects
        game.ship = Ship()
        game.world = World()
        game.particles = ParticleSystem()
        game.camera = Camera()

        ship = game.ship
        world = game.world
        sectors = world.sectors
        sd = data["ship"]

        # Restore ship
        ship.x = sd["x"]
        ship.y = sd["y"]
        ship.vx = sd["vx"]
        ship.vy = sd["vy"]
        ship.angle = sd["angle"]
        ship.grid_w = sd["grid_w"]
        ship.grid_h = sd["grid_h"]
        ship.fuel = sd["fuel"]
        ship.ore = sd["ore"]
        ship.credits = sd["credits"]
        ship.shield = sd["shield"]
        ship.alive = sd["alive"]
        ship.docked = sd["docked"]
        ship.refinery_enabled = sd.get("refinery_enabled", True)
        ship.sectors_discovered = sd.get("sectors_discovered", 0)
        ship.farthest_sector = sd.get("farthest_sector", 0)
        ship.invuln_timer = 0

        # Restore modules
        ship.modules.clear()
        for md in sd["modules"]:
            if md["id"] in MODULE_DEFS:
                placed = ship.place_module(md["id"], md["gx"], md["gy"])
                if placed:
                    placed.hp = md["hp"]
        ship._recalc_stats()

        # Restore world
        world.game_time = data["game_time"]
        game.total_credits_earned = data["total_credits_earned"]
        game.time = data["game_time"]
        world.void_titan_killed = data.get("void_titan_killed", False)
        world.titan_victory_shown = data.get("titan_victory_shown", False)
        world.missions_completed = data.get("missions_completed", 0)
        world._generate_missions()

        # Restore sector discovery
        sectors.discovered = {tuple(c) for c in data["sectors"]["discovered"]}
        sectors.farthest_distance = data["sectors"].get("farthest_distance", 0)

        # Stream sectors around player
        sectors.update_streaming(ship.x, ship.y, world.game_time)

        # Restore per-sector state
        for key, sec_data in data["sectors"].get("sector_state", {}).items():
            parts = key.split(",")
            coord = (int(parts[0]), int(parts[1]))
            sector = sectors.loaded.get(coord)
            if not sector:
                sector = sectors.get_sector(coord)

            # Restore POI state
            for i, poi_data in enumerate(sec_data.get("pois", [])):
                if i < len(sector.pois):
                    sector.pois[i].discovered = poi_data["discovered"]
                    sector.pois[i].looted = poi_data["looted"]
                    if hasattr(sector.pois[i], 'researched'):
                        sector.pois[i].researched = poi_data.get("researched", False)
                        sector.pois[i].research_progress = poi_data.get("research_progress", 0)

            # Restore patrol state
            for i, pat_data in enumerate(sec_data.get("patrols", [])):
                if i < len(sector.patrol_groups):
                    sector.patrol_groups[i].spawned = pat_data["spawned"]
                    sector.patrol_groups[i].cleared = pat_data["cleared"]
                    sector.patrol_groups[i].clear_time = pat_data["clear_time"]

            # Restore station stock
            if sector.station and "station_stock" in sec_data:
                sector.station.stock = sec_data["station_stock"]

            # Mark discovered
            if coord in sectors.discovered:
                sector.discovered = True

        # Regenerate asteroids for loaded sectors
        world.asteroids.clear()
        world._loaded_asteroid_sectors.clear()
        world._sync_entities()

        # Restore asteroid depletion
        for astate in data.get("asteroid_states", []):
            for a in world.asteroids:
                if abs(a.x - astate["x"]) < 2 and abs(a.y - astate["y"]) < 2:
                    a.ore = astate["ore"]
                    a.depleted = astate["depleted"]
                    break

        # Camera to player
        game.camera.x = ship.x
        game.camera.y = ship.y
        game.camera.target_x = ship.x
        game.camera.target_y = ship.y

        # If docked, open station UI
        if ship.docked:
            for sector in sectors.get_loaded_sectors():
                if sector.station and sector.station.can_dock(ship.x, ship.y):
                    game.station_ui.open(sector.station, world)
                    break

        return True
    except Exception as e:
        print(f"Load failed: {e}")
        return False


def has_save() -> bool:
    return os.path.exists(SAVE_FILE)


def delete_save():
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
