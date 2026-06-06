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
import math
import random
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

# ── Telemetry session (written to disk after every action) ────────────────────

_session: dict = {}   # mirrors the terminal telemetry JSON format exactly


# ── Environmental Sensor Simulator ─────────────────────────────────────────

class SensorSimulator:
    """
    Simulates environmental sensor readings for the rover's current position.
    Mirrors real Curiosity / Perseverance sensor systems (REMS).
    """

    # Surface temperature base values by terrain (°C)
    _TEMP_BASE = {"plain": -20, "sand": 15, "rock": -5, "ice": -80}

    # Slope base values by terrain (degrees)
    _SLOPE_BASE = {"plain": 2.0, "sand": 5.0, "rock": 18.0, "ice": 8.0}

    @classmethod
    def surface_temp(cls, terrain: str) -> float:
        """Terrain-dependent surface temperature with ±3 °C noise."""
        base = cls._TEMP_BASE.get(terrain, -20)
        return round(base + random.uniform(-3, 3), 1)

    @classmethod
    def dust_opacity(cls, x: int, y: int, grid_w: int, grid_h: int) -> float:
        """
        Atmospheric dust opacity (τ).  Higher toward grid edges
        — simulates dust storm zones away from the landing site.
        τ range: 0.1 (crystal clear) → 3.0 (full dust storm).
        """
        cx, cy   = grid_w / 2.0, grid_h / 2.0
        dx       = abs(x - cx) / max(cx, 1)
        dy       = abs(y - cy) / max(cy, 1)
        edge     = max(dx, dy)          # 0 at centre, 1 at corner
        tau      = 0.3 + edge * 1.8 + random.uniform(-0.1, 0.1)
        return round(max(0.1, min(tau, 3.0)), 2)

    @classmethod
    def uv_index(cls, y: int, grid_h: int) -> float:
        """
        UV radiation index.  Higher ground (larger Y) = thinner
        atmosphere = stronger UV.  Range: 0.5 – 5.0 UVI.
        """
        uv = 1.0 + (y / max(grid_h - 1, 1)) * 3.5 + random.uniform(-0.2, 0.2)
        return round(max(0.5, min(uv, 5.0)), 1)

    @classmethod
    def slope_deg(cls, terrain: str) -> float:
        """Estimated surface slope in degrees, ±1.5° noise."""
        base = cls._SLOPE_BASE.get(terrain, 2.0)
        return round(max(0.0, base + random.uniform(-1.5, 1.5)), 1)

    @classmethod
    def get_all(cls, x: int, y: int, terrain: str,
                grid_w: int, grid_h: int) -> dict:
        """Return a complete sensor snapshot for the current rover position."""
        tau = cls.dust_opacity(x, y, grid_w, grid_h)
        # Solar reduction: 0 % at τ ≤ 0.5, linear up to 50 % at τ = 2.5
        solar_reduction_pct = round(max(0.0, min(50.0, (tau - 0.5) * 25.0)), 1)
        return {
            "surface_temp":        cls.surface_temp(terrain),
            "dust_opacity":        tau,
            "uv_index":            cls.uv_index(y, grid_h),
            "slope_deg":           cls.slope_deg(terrain),
            "solar_reduction_pct": solar_reduction_pct,
            "terrain":             terrain,
        }


_current_sensors: dict = {}   # latest reading — updated after every action


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
    _init_session(mc["name"])
    _update_sensors()   # seed sensor readings for the start position


def _log(message: str) -> None:
    """Append a timestamped entry to the mission log (keep last 50)."""
    ts = datetime.now().strftime("%H:%M:%S")
    mission_log.append(f"[{ts}] {message}")
    if len(mission_log) > 50:
        mission_log.pop(0)


def _update_sensors() -> None:
    """Refresh _current_sensors based on the rover's current position."""
    global _current_sensors
    if not rover:
        return
    terrain_type = rover.terrain.get_terrain(rover.x, rover.y).value
    _current_sensors = SensorSimulator.get_all(
        rover.x, rover.y,
        terrain_type,
        rover.grid.width,
        rover.grid.height,
    )


# ── Telemetry helpers ─────────────────────────────────────────────────────────

def _init_session(mission_name: str) -> None:
    """Start a fresh in-memory telemetry session and assign a filename."""
    global _session
    ts   = datetime.now()
    fname = f"mission_{ts.strftime('%Y%m%d_%H%M%S')}.json"
    _session = {
        "mission_name": mission_name,
        "start_time":   ts.isoformat(),
        "end_time":     ts.isoformat(),
        "final_status": {},
        "path_history": [],
        "events":       [],
        "_filename":    fname,   # internal — stripped on write
    }
    # Log the mission_start event (matches terminal format exactly)
    _record_event("mission_start", {
        "position":         {"x": rover.x, "y": rover.y},
        "direction":        str(rover.direction),
        "commands_executed": 0,
        "cells_visited":    1,
        "battery":          rover.battery.get_status(),
    })


def _record_event(event_type: str, data: dict) -> None:
    """Append one event to the current session (same schema as terminal files)."""
    if not _session:
        return
    _session["events"].append({
        "timestamp": datetime.now().isoformat(),
        "type":      event_type,
        "data":      data,
    })


def _save_telemetry() -> None:
    """
    Snapshot the current session and write it to the telemetry folder.
    Called after every command/navigate/batch so the file is always current.
    """
    if not _session or not rover:
        return

    telemetry_dir = ROOT / config.get("mission", {}).get("telemetry_folder", "telemetry")
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    _session["end_time"]     = now
    _session["path_history"] = list(rover.path_history)
    _session["final_status"] = {
        "position":          {"x": rover.x, "y": rover.y},
        "direction":         str(rover.direction),
        "commands_executed": rover.command_count,
        "cells_visited":     len(set(map(tuple, rover.path_history))),
        "battery":           rover.battery.get_status(),
    }

    # Write without the internal _filename key
    payload = {k: v for k, v in _session.items() if not k.startswith("_")}
    filepath = telemetry_dir / _session["_filename"]
    try:
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as exc:
        logging.warning(f"Telemetry save failed: {exc}")


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
        "terrain":  terrain_cells,
        "sensors":  dict(_current_sensors),   # live environmental readings
        "mission":  mission.get_status(),
        "log":      list(reversed(mission_log)),
        "error":    None,
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
        # Dust-aware solar charge: high τ reduces yield
        _update_sensors()
        tau        = _current_sensors.get("dust_opacity", 0.3)
        reduction  = _current_sensors.get("solar_reduction_pct", 0.0) / 100.0
        base_rate  = rover.battery.solar_rate
        eff_rate   = max(1, round(base_rate * (1.0 - reduction)))
        # Apply effective charge directly (bypass solar_charge() to use eff_rate)
        shortfall  = rover.battery.max_charge - rover.battery.charge
        gained     = min(eff_rate, shortfall)
        if gained > 0:
            rover.battery.charge          += gained
            rover.battery.total_recharged += gained
        dust_note = f" (τ={tau}, -{_current_sensors.get('solar_reduction_pct',0):.0f}% dust)" \
                    if reduction > 0 else ""
        _log(f"Solar charge{dust_note} — +{gained} battery units "
             f"({rover.battery.charge}/{rover.battery.max_charge})")

    # Refresh sensor readings after any action that may change position
    _update_sensors()

    # Record event and persist to disk
    if cmd == "S":
        _record_event("solar_charge", {
            "gained":  gained if cmd == "S" else 0,
            "battery": rover.battery.get_status(),
            "sensors": dict(_current_sensors),
        })
    else:
        _record_event("command", {
            "command":        cmd,
            "rover_status":   rover.get_status(),
            "mission_status": mission.get_status(),
            "sensors":        dict(_current_sensors),
        })
    _save_telemetry()

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
        # Record each nav sub-step
        _record_event("command", {
            "command":        step,
            "rover_status":   rover.get_status(),
            "mission_status": mission.get_status(),
        })

    _log(f"Navigation complete. Final position: ({rover.x},{rover.y})")
    _save_telemetry()
    return jsonify(build_state_json())


@app.route("/api/reset", methods=["POST"])
def post_reset():
    """Reset the mission to its initial state (re-reads config)."""
    global config
    # Finalise and save the current session before resetting
    _save_telemetry()
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
        "terrain_cells": {
            f"{x},{y}": terrain_map.get_terrain(x, y).value
            for x in range(config["grid"]["width"])
            for y in range(config["grid"]["height"])
        },
        "obstacles": config["grid"].get("obstacles", []),
        "events":    events,     # full event list for frame-by-frame replay
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


# ── Mission Planner ───────────────────────────────────────────────────────────

@app.route("/api/plan", methods=["POST"])
def plan_mission():
    """
    Mission Feasibility Analysis — dry-run only, never mutates rover state.

    Accept:
      { "x": 5, "y": 7 }                         → A* navigate plan
      { "commands": ["M","M","R","G 5,7","S"] }   → batch plan

    Returns full analysis: path, energy, terrain, dust, risk, recommendation.
    """
    data = request.get_json(silent=True) or {}

    if "commands" in data:
        mode     = "batch"
        raw_cmds = data["commands"]
    elif "x" in data and "y" in data:
        mode = "navigate"
        try:
            gx, gy = int(data["x"]), int(data["y"])
        except (ValueError, TypeError):
            return jsonify({"error": "x and y must be integers"}), 400
    else:
        return jsonify({"error": "Provide {x,y} or {commands:[...]}"}), 400

    # ── helpers ──
    def _cost(x, y):
        return rover.terrain.get_battery_cost(x, y)

    def _ttype(x, y):
        return rover.terrain.get_terrain(x, y).value

    # ── waypoint lookup by position ──
    wp_map = {}
    for wp in mission.get_status().get("waypoints", []):
        wp_map[tuple(wp["position"])] = wp["name"]

    path            = []
    energy_cost     = 0
    solar_gain      = 0
    terrain_counts  = {"plain": 0, "sand": 0, "rock": 0, "ice": 0}
    wps_on_route    = []
    warnings        = []

    # ── build path ──
    if mode == "navigate":
        if not rover.grid.is_valid_position(gx, gy):
            return jsonify({"feasible": False, "risk_level": "HIGH",
                            "recommendation": "NOT_RECOMMENDED",
                            "warnings": [f"Target ({gx},{gy}) is outside the grid."]})
        if rover.grid.has_obstacle(gx, gy):
            return jsonify({"feasible": False, "risk_level": "HIGH",
                            "recommendation": "NOT_RECOMMENDED",
                            "warnings": [f"Target ({gx},{gy}) is an obstacle."]})
        raw_path = Pathfinder.find_path(rover.grid, (rover.x, rover.y), (gx, gy))
        if raw_path is None:
            return jsonify({"feasible": False, "risk_level": "HIGH",
                            "recommendation": "NOT_RECOMMENDED",
                            "warnings": ["No viable path — all routes blocked by obstacles."]})
        path = [list(p) for p in raw_path]
        for (x, y) in raw_path[1:]:
            energy_cost += _cost(x, y)
            t = _ttype(x, y)
            terrain_counts[t] = terrain_counts.get(t, 0) + 1
            if (x, y) in wp_map:
                wps_on_route.append({"name": wp_map[(x, y)], "position": [x, y]})
    else:
        CW      = ["North", "East", "South", "West"]
        DIR_VEC = {"North": (0,1), "East": (1,0), "South": (0,-1), "West": (-1,0)}
        sim_x, sim_y   = rover.x, rover.y
        sim_dir        = str(rover.direction)
        sim_charge     = rover.battery.charge
        path           = [[sim_x, sim_y]]

        for token in raw_cmds:
            t = str(token).upper().strip()
            if t == "M":
                dx, dy = DIR_VEC.get(sim_dir, (0, 1))
                nx, ny = sim_x + dx, sim_y + dy
                if rover.grid.is_valid_position(nx, ny) and not rover.grid.has_obstacle(nx, ny):
                    c = _cost(nx, ny)
                    energy_cost += c
                    sim_charge   = max(0, sim_charge - c)
                    tt = _ttype(nx, ny)
                    terrain_counts[tt] = terrain_counts.get(tt, 0) + 1
                    sim_x, sim_y = nx, ny
                    path.append([sim_x, sim_y])
                    if (sim_x, sim_y) in wp_map:
                        wps_on_route.append({"name": wp_map[(sim_x, sim_y)], "position": [sim_x, sim_y]})
            elif t == "L":
                sim_dir = CW[(CW.index(sim_dir) - 1) % 4]
            elif t == "R":
                sim_dir = CW[(CW.index(sim_dir) + 1) % 4]
            elif t == "S":
                tau       = SensorSimulator.dust_opacity(sim_x, sim_y, rover.grid.width, rover.grid.height)
                reduction = max(0.0, min(50.0, (tau - 0.5) * 25.0)) / 100.0
                eff_rate  = max(1, round(rover.battery.solar_rate * (1.0 - reduction)))
                gained    = min(eff_rate, rover.battery.max_charge - sim_charge)
                sim_charge = min(rover.battery.max_charge, sim_charge + gained)
                solar_gain += gained
            elif t.startswith("G"):
                try:
                    coords = t[1:].replace(",", " ").split()
                    gxb, gyb = int(coords[0]), int(coords[1])
                    sub = Pathfinder.find_path(rover.grid, (sim_x, sim_y), (gxb, gyb))
                    if sub:
                        for (px, py) in sub[1:]:
                            c = _cost(px, py)
                            energy_cost += c
                            sim_charge   = max(0, sim_charge - c)
                            tt = _ttype(px, py)
                            terrain_counts[tt] = terrain_counts.get(tt, 0) + 1
                            path.append([px, py])
                            if (px, py) in wp_map:
                                wps_on_route.append({"name": wp_map[(px, py)], "position": [px, py]})
                        sim_x, sim_y = gxb, gyb
                except Exception:
                    warnings.append(f"Could not plan sub-route for '{token}'.")

    # ── de-duplicate waypoints ──
    seen, unique_wps = set(), []
    for w in wps_on_route:
        k = tuple(w["position"])
        if k not in seen:
            seen.add(k); unique_wps.append(w)
    wps_on_route = unique_wps

    # ── atmospheric exposure ──
    if path:
        tau_vals = [SensorSimulator.dust_opacity(p[0], p[1], rover.grid.width, rover.grid.height) for p in path]
        avg_dust = round(sum(tau_vals) / len(tau_vals), 2)
        max_dust = round(max(tau_vals), 2)
    else:
        avg_dust = max_dust = 0.0

    # ── energy projection ──
    current_charge    = rover.battery.charge
    projected_battery = max(0, current_charge - energy_cost + solar_gain)
    projected_pct     = round((projected_battery / rover.battery.max_charge) * 100, 1)

    # ── risk scoring ──
    risk_score = 0

    if energy_cost > current_charge:
        risk_score += 40
        warnings.append(
            f"Insufficient battery — route costs {energy_cost} units "
            f"but only {current_charge} available. Rover may stall.")

    if projected_pct < 10:
        risk_score += 20
        warnings.append("Projected battery after route is critically low (≤ 10%). Charge first.")
    elif projected_pct < 25:
        risk_score += 10
        warnings.append("Projected battery will be below 25%. Proceed with caution.")

    if avg_dust >= 1.5:
        risk_score += 15
        warnings.append(f"High atmospheric dust on route (τ = {avg_dust}). Solar efficiency reduced.")
    elif avg_dust >= 0.8:
        risk_score += 5

    total_cells = sum(terrain_counts.values())
    rocky = terrain_counts.get("rock", 0)
    if total_cells > 0 and rocky / total_cells > 0.5:
        risk_score += 10
        warnings.append(f"Over 50% rock terrain ({rocky}/{total_cells} cells). High battery drain.")

    if total_cells > 20:
        risk_score += 5
        warnings.append(f"Long route ({total_cells} steps). Consider mid-route solar charging.")

    # ── risk tier ──
    if risk_score >= 40 or energy_cost > current_charge:
        risk_level, recommendation, feasible = "HIGH", "NOT_RECOMMENDED", False
    elif risk_score >= 15:
        risk_level, recommendation, feasible = "MEDIUM", "EXECUTE_WITH_CAUTION", True
    else:
        risk_level, recommendation, feasible = "LOW", "SAFE_TO_EXECUTE", True

    return jsonify({
        "mode":               mode,
        "feasible":           feasible,
        "path":               path,
        "steps":              max(0, len(path) - 1),
        "energy_cost":        energy_cost,
        "solar_gain":         solar_gain,
        "current_battery":    current_charge,
        "projected_battery":  projected_battery,
        "projected_pct":      projected_pct,
        "avg_dust":           avg_dust,
        "max_dust":           max_dust,
        "terrain_breakdown":  terrain_counts,
        "waypoints_on_route": wps_on_route,
        "risk_level":         risk_level,
        "recommendation":     recommendation,
        "warnings":           warnings,
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

            # Record event for every batch command
            if raw == "S":
                _record_event("solar_charge", {
                    "gained":  rover.battery.solar_rate,
                    "battery": rover.battery.get_status(),
                })
            else:
                _record_event("command", {
                    "command":        raw,
                    "rover_status":   rover.get_status(),
                    "mission_status": mission.get_status(),
                })
            steps.append({"command": raw, "state": build_state_json()})
        else:
            error_count += 1

    # Persist entire batch to disk in one write
    _save_telemetry()

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
