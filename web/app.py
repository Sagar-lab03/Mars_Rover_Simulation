"""
web/app.py - Flask Web Server for Mars Rover Simulation (Phase 3)

Exposes a REST API that the browser uses to:
  - Read current rover state  (GET  /api/state)
  - Send a command            (POST /api/command)
  - Auto-navigate with A*     (POST /api/navigate)
  - Reset the mission         (POST /api/reset)

Run with:
    python web/app.py
Then open http://localhost:5000 in your browser.
"""

import sys
import json
import yaml
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# Allow imports from project root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, request, render_template, send_from_directory

from rover import Grid, North, East, South, West, TelemetryLogger
from phase2.battery    import Battery
from phase2.terrain    import TerrainMap, TerrainType
from phase2.mission    import Mission, Waypoint
from phase2.pathfinder import Pathfinder
from phase2.main       import RoverV2

# ── Flask app ────────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder="templates", static_folder="static")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# ── Global mission state (in-memory) ─────────────────────────────────────────

rover:   Optional[RoverV2] = None
mission: Optional[Mission] = None
mission_log: list          = []
config: dict               = {}


def load_config() -> dict:
    """Load config.yaml from project root, with sensible defaults."""
    defaults = {
        "grid":    {"width": 10, "height": 10, "obstacles": []},
        "rover":   {"start_x": 0, "start_y": 0, "start_direction": "N"},
        "battery": {"max_charge": 100, "solar_rate": 5},
        "terrain": [],
        "mission": {
            "name": "Mars Exploration Phase 3",
            "enable_telemetry": True,
            "telemetry_folder": "telemetry",
            "waypoints": [],
        },
    }
    try:
        with open(ROOT / "config.yaml", "r") as f:
            user = yaml.safe_load(f) or {}
        # shallow-merge each top-level section
        for k, v in user.items():
            if isinstance(v, dict) and k in defaults:
                defaults[k] = {**defaults[k], **v}
            else:
                defaults[k] = v
    except FileNotFoundError:
        pass
    return defaults


def build_mission_objects(cfg: dict):
    """Construct RoverV2 + Mission from a config dict."""
    global rover, mission, mission_log

    gc = cfg["grid"]
    rc = cfg["rover"]
    bc = cfg["battery"]
    tc = cfg.get("terrain", [])
    mc = cfg["mission"]

    obstacles = [tuple(o) for o in gc.get("obstacles", [])]
    grid      = Grid(gc["width"], gc["height"], obstacles)
    battery   = Battery(bc["max_charge"], bc["solar_rate"])
    terrain   = TerrainMap.from_config(gc["width"], gc["height"], tc)

    dir_map = {"N": North(), "E": East(), "S": South(), "W": West()}
    direction = dir_map.get(rc.get("start_direction", "N"), North())

    rover   = RoverV2(rc["start_x"], rc["start_y"], direction, grid, battery, terrain)
    mission = Mission.from_config(mc["name"], mc.get("waypoints", []))

    mission_log.clear()
    _log(f"Mission started — Rover at ({rover.x},{rover.y}) facing {rover.direction}")


def _log(message: str) -> None:
    """Append a timestamped entry to the mission log (keep last 50)."""
    ts = datetime.now().strftime("%H:%M:%S")
    mission_log.append(f"[{ts}] {message}")
    if len(mission_log) > 50:
        mission_log.pop(0)


def build_state_json() -> dict:
    """
    Serialize the complete current state to a plain dict (JSON-safe).
    This is the single data contract between server and browser.
    """
    # Terrain map: key = "x,y", value = terrain type string
    terrain_cells = {}
    for (x, y), t in rover.terrain._map.items():
        terrain_cells[f"{x},{y}"] = t.value

    return {
        "rover": {
            "x": rover.x,
            "y": rover.y,
            "direction": str(rover.direction),
            "path_history": list(rover.path_history),
            "commands_executed": rover.command_count,
        },
        "battery": rover.battery.get_status(),
        "grid": {
            "width":     rover.grid.width,
            "height":    rover.grid.height,
            "obstacles": list(rover.grid.obstacles),
        },
        "terrain": terrain_cells,
        "mission": mission.get_status(),
        "log":     list(reversed(mission_log)),   # newest first
        "error":   None,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the single-page application."""
    return render_template("index.html")


@app.route("/api/state", methods=["GET"])
def get_state():
    """Return the current full rover state as JSON."""
    return jsonify(build_state_json())


@app.route("/api/command", methods=["POST"])
def post_command():
    """
    Execute a single rover command.

    Body: { "command": "M" | "L" | "R" | "S" }
    Returns: full state JSON
    """
    data = request.get_json(silent=True) or {}
    cmd  = str(data.get("command", "")).upper().strip()

    if cmd not in ("M", "L", "R", "S"):
        return jsonify({"error": f"Unknown command '{cmd}'. Use M, L, R or S."}), 400

    # Execute
    if cmd == "M":
        success = rover.move_forward()
        if success:
            reached = mission.check_position(rover.x, rover.y)
            terrain_here = rover.terrain.get_terrain(rover.x, rover.y).value
            cost = rover.terrain.get_battery_cost(rover.x, rover.y)
            _log(f"Moved to ({rover.x},{rover.y}) — {terrain_here} terrain (-{cost} battery)")
            if reached:
                _log(f"Waypoint reached: {reached.name}!")
            if mission.is_complete:
                _log("All waypoints reached — Mission Complete!")
        else:
            _log("Move blocked (obstacle or boundary)")

    elif cmd == "L":
        rover.turn_left()
        _log(f"Turned left — now facing {rover.direction}")

    elif cmd == "R":
        rover.turn_right()
        _log(f"Turned right — now facing {rover.direction}")

    elif cmd == "S":
        gained = rover.battery.solar_charge()
        _log(f"Solar charge — +{gained} battery units ({rover.battery.charge}/{rover.battery.max_charge})")

    state = build_state_json()
    return jsonify(state)


@app.route("/api/navigate", methods=["POST"])
def post_navigate():
    """
    A* auto-navigate to a target cell.

    Body: { "x": 5, "y": 7 }
    Returns: full state JSON after all steps are executed
    """
    data = request.get_json(silent=True) or {}
    try:
        gx = int(data["x"])
        gy = int(data["y"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Body must contain integer fields 'x' and 'y'."}), 400

    _log(f"A* navigation requested to ({gx},{gy})")

    # Validate target
    if not rover.grid.is_valid_position(gx, gy):
        msg = f"Target ({gx},{gy}) is outside the grid."
        _log(msg)
        state = build_state_json()
        state["error"] = msg
        return jsonify(state), 400

    if rover.grid.has_obstacle(gx, gy):
        msg = f"Target ({gx},{gy}) is an obstacle — cannot navigate there."
        _log(msg)
        state = build_state_json()
        state["error"] = msg
        return jsonify(state), 400

    path = Pathfinder.find_path(rover.grid, (rover.x, rover.y), (gx, gy))

    if path is None:
        msg = f"No path found to ({gx},{gy}) — target may be unreachable."
        _log(msg)
        state = build_state_json()
        state["error"] = msg
        return jsonify(state), 400

    if len(path) == 1:
        _log(f"Already at ({gx},{gy})!")
        return jsonify(build_state_json())

    cmds = Pathfinder.path_to_commands(path, str(rover.direction))
    _log(f"Path found — {len(path)-1} steps: {' '.join(cmds)}")

    for step in cmds:
        if rover.battery.is_dead:
            _log("Battery dead — navigation aborted.")
            break

        if step == "M":
            success = rover.move_forward()
            if success:
                reached = mission.check_position(rover.x, rover.y)
                terrain_here = rover.terrain.get_terrain(rover.x, rover.y).value
                cost = rover.terrain.get_battery_cost(rover.x, rover.y)
                _log(f"  -> ({rover.x},{rover.y}) [{terrain_here}, -{cost}]")
                if reached:
                    _log(f"Waypoint reached: {reached.name}!")
                if mission.is_complete:
                    _log("All waypoints reached — Mission Complete!")
        elif step == "L":
            rover.turn_left()
        elif step == "R":
            rover.turn_right()

    _log(f"Navigation complete. Final position: ({rover.x},{rover.y})")
    return jsonify(build_state_json())


@app.route("/api/reset", methods=["POST"])
def post_reset():
    """Reset the mission to its initial state (re-reads config)."""
    global config
    config = load_config()
    build_mission_objects(config)
    _log("Mission reset.")
    return jsonify(build_state_json())


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config = load_config()
    build_mission_objects(config)
    print("\n  Mars Rover Mission Control")
    print("  Open http://localhost:5000 in your browser\n")
    app.run(debug=True, port=5000)
