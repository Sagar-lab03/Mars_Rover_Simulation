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

from flask import Flask, jsonify, request, render_template, send_from_directory, Response

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


# ── Analytics Routes ─────────────────────────────────────────────────────────

@app.route("/analytics")
def analytics_page():
    """Serve the analytics dashboard."""
    return render_template("analytics.html")


@app.route("/api/analytics/missions", methods=["GET"])
def get_missions():
    """List all telemetry files with summary metadata."""
    telemetry_dir = ROOT / config.get("mission", {}).get("telemetry_folder", "telemetry")
    missions = []
    if telemetry_dir.exists():
        for f in sorted(telemetry_dir.glob("mission_*.json"), reverse=True):
            try:
                with open(f) as fp:
                    d = json.load(fp)
                fs = d.get("final_status", {})
                bat = fs.get("battery", {})
                # Duration
                duration = 0
                try:
                    from datetime import datetime as dt
                    t0 = dt.fromisoformat(d.get("start_time", ""))
                    t1 = dt.fromisoformat(d.get("end_time", ""))
                    duration = round((t1 - t0).total_seconds(), 1)
                except Exception:
                    pass
                missions.append({
                    "filename":          f.name,
                    "mission_name":      d.get("mission_name", "Unknown"),
                    "start_time":        d.get("start_time", ""),
                    "duration_seconds":  duration,
                    "commands_executed": fs.get("commands_executed", 0),
                    "cells_visited":     fs.get("cells_visited", 0),
                    "energy_consumed":   bat.get("total_consumed", 0),
                    "final_battery_pct": bat.get("percentage", 0),
                })
            except Exception:
                pass
    return jsonify({"missions": missions})


@app.route("/api/analytics/mission/<filename>", methods=["GET"])
def get_mission_detail(filename):
    """Return full analytics for one telemetry file."""
    telemetry_dir = ROOT / config.get("mission", {}).get("telemetry_folder", "telemetry")
    filepath = telemetry_dir / filename
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404

    with open(filepath) as f:
        data = json.load(f)

    events       = data.get("events", [])
    path_history = data.get("path_history", [])
    final_status = data.get("final_status", {})

    # Battery timeline & command counts
    battery_timeline = [{"step": 0, "pct": 100.0, "charge": 100, "command": "START", "event": "start"}]
    command_counts   = {"M": 0, "L": 0, "R": 0, "S": 0}
    step = 0

    for ev in events:
        ev_type = ev.get("type", "")
        ev_data = ev.get("data", {})

        if ev_type == "command":
            step += 1
            cmd    = ev_data.get("command", "?")
            status = ev_data.get("rover_status") or ev_data.get("status") or {}
            bat    = status.get("battery", {})
            pct    = bat.get("percentage",   battery_timeline[-1]["pct"])
            charge = bat.get("charge",       battery_timeline[-1]["charge"])
            evt    = "solar" if cmd == "S" else ("move" if cmd == "M" else "turn")
            battery_timeline.append({"step": step, "pct": pct, "charge": charge,
                                     "command": cmd, "event": evt})
            if cmd in command_counts:
                command_counts[cmd] += 1

        elif ev_type == "solar_charge":
            step += 1
            bat    = ev_data.get("battery", {})
            pct    = bat.get("percentage",   battery_timeline[-1]["pct"])
            charge = bat.get("charge",       battery_timeline[-1]["charge"])
            battery_timeline.append({"step": step, "pct": pct, "charge": charge,
                                     "command": "S", "event": "solar"})
            command_counts["S"] = command_counts.get("S", 0) + 1

    # Terrain breakdown of visited cells
    terrain_cfg = config.get("terrain", [])
    terrain_map  = TerrainMap.from_config(
        config["grid"]["width"], config["grid"]["height"], terrain_cfg)
    terrain_visited = {"plain": 0, "sand": 0, "rock": 0, "ice": 0}
    for (x, y) in path_history:
        t = terrain_map.get_terrain(x, y).value
        terrain_visited[t] = terrain_visited.get(t, 0) + 1

    # Visit heatmap: "x,y" -> count
    heatmap = {}
    for (x, y) in path_history:
        key = f"{x},{y}"
        heatmap[key] = heatmap.get(key, 0) + 1

    # Duration
    duration = 0
    try:
        from datetime import datetime as dt
        t0 = dt.fromisoformat(data.get("start_time", ""))
        t1 = dt.fromisoformat(data.get("end_time", ""))
        duration = round((t1 - t0).total_seconds(), 1)
    except Exception:
        pass

    bat_final = final_status.get("battery", {})
    return jsonify({
        "filename":        filename,
        "mission_name":    data.get("mission_name", "Unknown"),
        "start_time":      data.get("start_time", ""),
        "end_time":        data.get("end_time", ""),
        "duration_seconds": duration,
        "battery_timeline": battery_timeline,
        "command_counts":   command_counts,
        "terrain_visited":  terrain_visited,
        "heatmap":          heatmap,
        "path_history":     path_history,
        "grid":             {"width": config["grid"]["width"],
                             "height": config["grid"]["height"]},
        "mission_stats": {
            "total_commands":    final_status.get("commands_executed", 0),
            "cells_visited":     final_status.get("cells_visited", 0),
            "energy_consumed":   bat_final.get("total_consumed", 0),
            "energy_recharged":  bat_final.get("total_recharged", 0),
            "final_battery_pct": bat_final.get("percentage", 0),
            "final_position":    final_status.get("position", {}),
            "final_direction":   final_status.get("direction", ""),
        },
    })


# ── Batch Routes ──────────────────────────────────────────────────────────────

@app.route("/api/batch/execute", methods=["POST"])
def batch_execute():
    """
    Execute a batch of commands and return all intermediate states.

    Body: { "commands": ["M","M","R","G 5,7","S"] }
    Returns: { "steps": [...], "final_state": {...}, "summary": {...} }
    """
    data     = request.get_json(silent=True) or {}
    raw_cmds = data.get("commands", [])

    steps       = []
    error_count = 0

    for raw in raw_cmds:
        raw = str(raw).upper().strip()
        if not raw:
            continue

        # ── G x,y ──
        if raw.startswith("G"):
            try:
                # Accept "G5,7", "G 5,7", "G 5 7"
                coords = raw[1:].replace(",", " ").split()
                gx, gy = int(coords[0]), int(coords[1])
            except Exception:
                error_count += 1
                continue

            path = Pathfinder.find_path(rover.grid, (rover.x, rover.y), (gx, gy))
            if path is None:
                _log(f"[Batch] No path to ({gx},{gy})")
                error_count += 1
                continue

            nav_cmds = Pathfinder.path_to_commands(path, str(rover.direction))
            for nc in nav_cmds:
                if rover.battery.is_dead:
                    _log("[Batch] Battery dead — navigation aborted")
                    break
                if nc == "M":
                    rover.move_forward()
                    reached = mission.check_position(rover.x, rover.y)
                    if reached:
                        _log(f"[Batch] Waypoint: {reached.name}!")
                elif nc == "L":
                    rover.turn_left()
                elif nc == "R":
                    rover.turn_right()
                steps.append({"command": f"G→{nc}", "state": build_state_json()})
            _log(f"[Batch] Navigated to ({rover.x},{rover.y})")

        # ── M / L / R / S ──
        elif raw in ("M", "L", "R", "S"):
            if raw == "M":
                success = rover.move_forward()
                if success:
                    reached = mission.check_position(rover.x, rover.y)
                    if reached:
                        _log(f"[Batch] Waypoint: {reached.name}!")
                else:
                    _log("[Batch] Move blocked")
            elif raw == "L":
                rover.turn_left()
                _log(f"[Batch] Turned left → {rover.direction}")
            elif raw == "R":
                rover.turn_right()
                _log(f"[Batch] Turned right → {rover.direction}")
            elif raw == "S":
                gained = rover.battery.solar_charge()
                _log(f"[Batch] Solar +{gained}")
            steps.append({"command": raw, "state": build_state_json()})
        else:
            error_count += 1

    summary = {
        "total_steps":  len(steps),
        "error_count":  error_count,
        "final_pos":    f"({rover.x},{rover.y})",
        "battery_pct":  rover.battery.percentage,
    }
    return jsonify({"steps": steps, "final_state": build_state_json(),
                    "summary": summary})


@app.route("/api/batch/template", methods=["GET"])
def batch_template():
    """Return a sample batch command file for download."""
    template = (
        "# Mars Rover Batch Command File\n"
        "# ================================\n"
        "# Commands:\n"
        "#   M        - Move Forward (drains battery based on terrain)\n"
        "#   L        - Turn Left 90 degrees\n"
        "#   R        - Turn Right 90 degrees\n"
        "#   S        - Solar Charge (restore battery)\n"
        "#   G x,y    - A* Auto-navigate to coordinates  e.g. G 5,7\n"
        "#\n"
        "# Rules:\n"
        "#   - Commands can be space-separated on one line or one per line\n"
        "#   - Lines starting with # are comments and are ignored\n"
        "#   - Blank lines are ignored\n"
        "#\n"
        "# ─────────────────────────────────\n"
        "# Sample Mission Sequence\n"
        "# ─────────────────────────────────\n"
        "\n"
        "# Phase 1: Move north along the edge\n"
        "M M M\n"
        "\n"
        "# Phase 2: Turn east and explore\n"
        "R M M M L\n"
        "\n"
        "# Phase 3: A* auto-navigate to Sample Site Alpha\n"
        "G 5,7\n"
        "\n"
        "# Phase 4: Recharge solar panels\n"
        "S\n"
        "\n"
        "# Phase 5: Head to High Ground\n"
        "G 9,9\n"
    )
    return Response(
        template,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=mission_commands.txt"},
    )


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config = load_config()
    build_mission_objects(config)
    print("\n  Mars Rover Mission Control")
    print("  Open http://localhost:5000 in your browser\n")
    app.run(debug=True, port=5000)
