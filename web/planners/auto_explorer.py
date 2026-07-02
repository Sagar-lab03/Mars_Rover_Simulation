"""
web/planners/auto_explorer.py
──────────────────────────────
Autonomous Exploration Agent — single-step decision engine.

Public API
──────────
  run_step(rover, mission, log_fn, record_fn, profile_name) -> dict

      Executes one autonomous exploration step:
        1. Battery safety gate
        2. Scan & score all unvisited cells (via science_engine)
        3. Compute A* travel cost for the top candidate pool
        4. Lightweight feasibility check (battery projection + dust)
        5. Execute navigation if a route is approved
        6. Return structured result for the Flask route to serialise

      log_fn    — callable(str) passed in from app.py (_log)
      record_fn — callable(str, dict) passed in from app.py (_record_event)

      The function never touches Flask globals directly, keeping it
      fully testable outside a request context.

Stop conditions (returned as should_continue=False):
  - Battery below BATTERY_SAFETY_THRESHOLD
  - No scoreable unvisited candidates found
  - No candidates reachable via A*
  - All shortlisted candidates classified NOT_RECOMMENDED
"""

from __future__ import annotations

import sys
import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_WEB  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _p in (_ROOT, _WEB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from phase2.pathfinder import Pathfinder            # type: ignore
from sensor_simulator import SensorSimulator        # type: ignore
from planners.science_engine import score_cell, compute_mission_score

# ── Constants ─────────────────────────────────────────────────────────────────

BATTERY_SAFETY_THRESHOLD = 20   # minimum charge; stop exploring below this
MAX_CANDIDATES_TO_TRY    = 3    # max shortlisted candidates to evaluate
TOP_POOL_FACTOR          = 4    # top_pool size = MAX_CANDIDATES × this factor


# ── Main Step Function ────────────────────────────────────────────────────────

def run_step(
    rover,
    mission,
    log_fn,
    record_fn,
    profile_name: str = "balanced",
) -> dict:
    """
    Execute one autonomous exploration step and return a result dict.

    The dict always contains:
      should_continue  bool
      stop_reason      str | None
      reasoning        list[str]
      target           dict | None   (position, science_value, risk)
      mission_score    int
    It does NOT contain 'state' — the Flask route adds that.
    """
    reasoning: list[str] = []

    # ── 1. Battery safety gate ────────────────────────────────────────────────
    charge = rover.battery.charge
    if charge < BATTERY_SAFETY_THRESHOLD:
        return _stop(
            reasoning=[
                f"⚠ Battery at {charge}u — below safety threshold ({BATTERY_SAFETY_THRESHOLD}u).",
                "Autonomous exploration halted. Use Solar Charge (S) to recharge.",
            ],
            stop_reason=f"Battery critical ({charge}u). Solar charge recommended before resuming.",
            mission_score=compute_mission_score(rover, mission, profile_name),
        )

    reasoning.append(f"🔋 Battery: {charge}u — sufficient for exploration.")

    # ── 2. Scan: score all unvisited cells ────────────────────────────────────
    visited   = set(map(tuple, rover.path_history))
    rover_pos = (rover.x, rover.y)

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
            if sv > 0:
                candidates.append({
                    "position":      [x, y],
                    "science_value": sv,
                    "reasons":       reasons,
                })

    if not candidates:
        return _stop(
            reasoning=reasoning + [
                "✓ Scan complete — all high-value cells have been explored.",
                "Autonomous mission finished.",
            ],
            stop_reason="No unvisited science targets remain. Exploration complete.",
            mission_score=compute_mission_score(rover, mission, profile_name),
        )

    reasoning.append(f"🔍 Scanned {len(candidates)} unvisited candidate cells.")

    # ── 3. Rank; compute A* cost for top pool ─────────────────────────────────
    candidates.sort(key=lambda c: c["science_value"], reverse=True)
    top_pool = candidates[: MAX_CANDIDATES_TO_TRY * TOP_POOL_FACTOR]

    reachable = []
    for c in top_pool:
        x, y = c["position"]
        path = Pathfinder.find_path(rover.grid, rover_pos, (x, y))
        if path is None:
            continue
        travel_cost = max(1, sum(
            rover.terrain.get_battery_cost(px, py) for px, py in path[1:]
        ))
        efficiency  = round(c["science_value"] / travel_cost, 3)
        final_score = round(c["science_value"] * 0.6 + efficiency * 10 * 0.4, 1)
        reachable.append({
            **c,
            "travel_cost": travel_cost,
            "efficiency":  efficiency,
            "score":       final_score,
            "path":        path,
        })

    if not reachable:
        return _stop(
            reasoning=reasoning + [
                "⚠ A* found no routes to any candidate cell.",
                "Autonomous exploration halted.",
            ],
            stop_reason="No reachable science targets — rover may be surrounded by obstacles.",
            mission_score=compute_mission_score(rover, mission, profile_name),
        )

    reachable.sort(key=lambda c: c["score"], reverse=True)

    # ── 4. Feasibility check ──────────────────────────────────────────────────
    selected = None
    for candidate in reachable[: MAX_CANDIDATES_TO_TRY]:
        x, y        = candidate["position"]
        travel_cost = candidate["travel_cost"]
        projected   = charge - travel_cost
        proj_pct    = round((projected / rover.battery.max_charge) * 100, 1)

        dust_vals = [
            SensorSimulator.dust_opacity(px, py, rover.grid.width, rover.grid.height)
            for px, py in candidate["path"][1:]
        ]
        avg_dust = round(sum(dust_vals) / len(dust_vals), 2) if dust_vals else 0.0

        if projected < BATTERY_SAFETY_THRESHOLD:
            risk = "NOT_RECOMMENDED"
        elif proj_pct < 20 and avg_dust > 1.5:
            risk = "NOT_RECOMMENDED"
        elif proj_pct < 25 or avg_dust > 1.5:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        if risk == "NOT_RECOMMENDED":
            reasoning.append(
                f"✗ Target ({x},{y}) skipped — projected battery {projected}u ({proj_pct}%) too low."
            )
            continue

        selected = {
            **candidate,
            "risk":      risk,
            "projected": projected,
            "proj_pct":  proj_pct,
            "avg_dust":  avg_dust,
        }
        break

    if selected is None:
        return _stop(
            reasoning=reasoning + [
                "⛔ No approvable routes found.",
                "Recommend solar charging (S) before resuming auto-exploration.",
            ],
            stop_reason="All candidate routes are NOT_RECOMMENDED — insufficient battery for safe travel.",
            mission_score=compute_mission_score(rover, mission, profile_name),
        )

    # ── 5. Execute navigation ─────────────────────────────────────────────────
    x, y       = selected["position"]
    top_reason = selected["reasons"][0] if selected["reasons"] else "High science value"
    risk_icon  = "✓" if selected["risk"] == "LOW" else "⚠"

    reasoning.append(
        f"🎯 Target ({x},{y}) selected — {top_reason} "
        f"(science: {selected['science_value']}, efficiency: {selected['efficiency']})."
    )
    reasoning.append(
        f"{risk_icon} Route: {len(selected['path'])-1} steps, cost {selected['travel_cost']}u, "
        f"projected battery {selected['proj_pct']}% — risk {selected['risk']}."
    )

    cmds = Pathfinder.path_to_commands(selected["path"], str(rover.direction))
    for step in cmds:
        if rover.battery.is_dead:
            break
        if step == "M":
            success = rover.move_forward()
            if success:
                reached = mission.check_position(rover.x, rover.y)
                terrain_here = rover.terrain.get_terrain(rover.x, rover.y).value
                cost = rover.terrain.get_battery_cost(rover.x, rover.y)
                log_fn(f"AUTO [{rover.x},{rover.y}] [{terrain_here}, -{cost}]")
                if reached:
                    log_fn(f"Waypoint reached: {reached.name}!")
        elif step == "L":
            rover.turn_left()
        elif step == "R":
            rover.turn_right()
        record_fn("command", {
            "command":        step,
            "rover_status":   rover.get_status(),
            "mission_status": mission.get_status(),
        })

    reasoning.append(
        f"✓ Navigation complete — rover now at ({rover.x},{rover.y}), battery {rover.battery.charge}u."
    )

    # ── 6. Continuation check ─────────────────────────────────────────────────
    new_visited   = set(map(tuple, rover.path_history))
    mission_score = compute_mission_score(rover, mission, profile_name)
    low_battery   = rover.battery.charge < BATTERY_SAFETY_THRESHOLD
    has_more      = any(
        not rover.grid.has_obstacle(cx, cy)
        and (cx, cy) != (rover.x, rover.y)
        and (cx, cy) not in new_visited
        for cx in range(rover.grid.width)
        for cy in range(rover.grid.height)
    )
    should_continue = has_more and not low_battery

    stop_reason = None
    if low_battery:
        stop_reason = f"Battery at {rover.battery.charge}u — below safety threshold."
    elif not has_more:
        stop_reason = "All accessible science targets explored. Mission survey complete."

    return {
        "should_continue": should_continue,
        "stop_reason":     stop_reason,
        "reasoning":       reasoning,
        "target":          {
            "position":      [x, y],
            "science_value": selected["science_value"],
            "risk":          selected["risk"],
        },
        "mission_score":   mission_score,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _stop(reasoning: list[str], stop_reason: str, mission_score: int) -> dict:
    """Return a stopped-step result with no target."""
    return {
        "should_continue": False,
        "stop_reason":     stop_reason,
        "reasoning":       reasoning,
        "target":          None,
        "mission_score":   mission_score,
    }
