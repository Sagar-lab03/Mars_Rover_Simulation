"""
web/planners/science_engine.py
──────────────────────────────
Science Prioritization Engine — deterministic, rule-based cell scoring.

Public API
──────────
  score_cell(x, y, rover, mission, profile_name) -> (int, list[str])
      Score one candidate cell.  Returns (science_value, reasons[]).

  get_recommendations(rover, mission, n, profile_name) -> dict
      Return the top-n recommendations as a JSON-serialisable dict.

  compute_mission_score(rover, mission) -> int
      Sum science values for every cell the rover has visited.

All functions are pure with respect to rover/mission state — they never
mutate either object.  The Flask route passes the module-level globals
in; the planner only reads them.
"""

from __future__ import annotations

import sys
import os

# Allow importing phase2 modules when this package is used from web/app.py
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_WEB  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _p in (_ROOT, _WEB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from phase2.pathfinder import Pathfinder            # type: ignore
from sensor_simulator import SensorSimulator        # type: ignore
from planners.mission_profiles import get_profile


# ── Cell Scorer ───────────────────────────────────────────────────────────────

def score_cell(
    x: int,
    y: int,
    rover,
    mission,
    profile_name: str = "balanced",
) -> tuple[int, list[str]]:
    """
    Compute the science yield score (0–100) for a candidate cell.
    Returns (science_value, reasons[]).

    Scoring factors (deterministic, rule-based):
      1. Terrain base value       — geological interest weighted by profile
      2. Terrain boundary bonus   — adjacency to multiple biome types
      3. UV anomaly bonus         — high UV = thinner atmosphere overhead
      4. Extreme temperature      — cold signatures → cryogenic interest
      5. Mission waypoint bonus   — designated science targets score higher
      6. Dust storm penalty       — heavy dust degrades instrument performance

    Each factor is scaled by the active mission profile's weight multipliers.
    """
    w = get_profile(profile_name)
    reasons: list[str] = []
    score = 0

    ttype = rover.terrain.get_terrain(x, y).value

    # 1. Terrain base ─────────────────────────────────────────────────────────
    terrain_base = {"rock": 40, "ice": 35, "sand": 20, "plain": 10}
    base_raw = terrain_base.get(ttype, 10)
    profile_mult = w.get(ttype, 1.0)
    base = round(base_raw * profile_mult)
    score += base

    if ttype == "rock":
        reasons.append("Rock terrain — high geological interest")
    elif ttype == "ice":
        reasons.append("Ice terrain — potential subsurface water")
    elif ttype == "sand":
        reasons.append("Sand terrain — aeolian deposit analysis")

    # 2. Terrain boundary bonus ───────────────────────────────────────────────
    neighbour_types: set[str] = set()
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if rover.grid.is_valid_position(nx, ny) and not rover.grid.has_obstacle(nx, ny):
                neighbour_types.add(rover.terrain.get_terrain(nx, ny).value)

    foreign = neighbour_types - {ttype}
    if len(foreign) >= 2:
        bonus = round(30 * w.get("boundary", 1.0))
        score += bonus
        reasons.append("Multi-terrain boundary zone — 3+ biomes converge")
    elif len(foreign) == 1:
        bonus = round(20 * w.get("boundary", 1.0))
        score += bonus
        reasons.append("Terrain boundary zone — biome transition region")

    # 3. UV anomaly ───────────────────────────────────────────────────────────
    uv = SensorSimulator.uv_index(y, rover.grid.height)
    uv_mult = w.get("uv", 1.0)
    if uv >= 3.5:
        score += round(15 * uv_mult)
        reasons.append(f"High UV anomaly (UVI {uv:.1f}) — atmospheric thinning")
    elif uv >= 2.5:
        score += round(8 * uv_mult)
        reasons.append(f"Elevated UV index (UVI {uv:.1f})")

    # 4. Extreme temperature signature ────────────────────────────────────────
    temp = SensorSimulator.surface_temp(ttype)
    if temp < -65:
        score += round(10 * w.get("temperature", 1.0))
        reasons.append(f"Extreme cold signature ({temp}°C) — cryogenic interest")

    # 5. Mission waypoint bonus ───────────────────────────────────────────────
    wp_positions = {tuple(wp["position"]) for wp in mission.get_status().get("waypoints", [])}
    if (x, y) in wp_positions:
        score += round(20 * w.get("waypoint", 1.0))
        reasons.append("Designated mission science target")

    # 6. Dust storm penalty ───────────────────────────────────────────────────
    dust = SensorSimulator.dust_opacity(x, y, rover.grid.width, rover.grid.height)
    if dust > 1.5:
        score -= round(5 * w.get("dust_penalty", 1.0))

    return max(0, min(100, score)), reasons


# ── Recommendation Engine ─────────────────────────────────────────────────────

def get_recommendations(rover, mission, n: int = 3, profile_name: str = "balanced") -> dict:
    """
    Return the top-n science recommendations as a JSON-serialisable dict.

    Filters out visited cells, computes A* travel cost for the top pool,
    and ranks by final_score = 60% science_value + 40% efficiency×10.

    Keys returned:
      recommendations   list of target dicts
      total_candidates  total unvisited scoreable cells
      mission_score     cumulative science value of all visited cells
    """
    visited   = set(map(tuple, rover.path_history))
    rover_pos = (rover.x, rover.y)

    # Score all candidate cells
    candidates = []
    for x in range(rover.grid.width):
        for y in range(rover.grid.height):
            if rover.grid.has_obstacle(x, y):
                continue
            if (x, y) == rover_pos:
                continue
            if (x, y) in visited:
                continue
            sv, reasons = score_cell(x, y, rover, mission, profile_name)
            candidates.append({
                "position":      [x, y],
                "terrain":       rover.terrain.get_terrain(x, y).value,
                "science_value": sv,
                "reasons":       reasons,
            })

    # Pre-filter by science_value before running A* (expensive)
    candidates.sort(key=lambda c: c["science_value"], reverse=True)
    top_pool = candidates[: min(len(candidates), n * 6)]

    # A* travel cost for each shortlisted candidate
    reachable = []
    eff_weight = get_profile(profile_name).get("cost_weight", 0.4)
    sci_weight = 1.0 - eff_weight

    for c in top_pool:
        x, y = c["position"]
        path = Pathfinder.find_path(rover.grid, rover_pos, (x, y))
        if path is None:
            continue
        travel_cost = max(1, sum(
            rover.terrain.get_battery_cost(px, py) for px, py in path[1:]
        ))
        efficiency  = round(c["science_value"] / travel_cost, 3)
        final_score = round(c["science_value"] * sci_weight + efficiency * 10 * eff_weight, 1)
        reachable.append({
            **c,
            "travel_cost": travel_cost,
            "efficiency":  efficiency,
            "score":       final_score,
        })

    reachable.sort(key=lambda c: c["score"], reverse=True)

    return {
        "recommendations":  reachable[:n],
        "total_candidates": len(candidates),
        "mission_score":    compute_mission_score(rover, mission),
    }


# ── Mission Score ─────────────────────────────────────────────────────────────

def compute_mission_score(rover, mission, profile_name: str = "balanced") -> int:
    """Sum science values for all cells the rover has visited."""
    visited = set(map(tuple, rover.path_history))
    return sum(
        score_cell(vx, vy, rover, mission, profile_name)[0]
        for vx, vy in visited
        if rover.grid.is_valid_position(vx, vy) and not rover.grid.has_obstacle(vx, vy)
    )
