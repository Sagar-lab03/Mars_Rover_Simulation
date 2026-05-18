"""
main.py - Phase 2 Entry Point for Mars Rover Simulation

Builds on Phase 1 (rover.py) and adds:
  - Terrain system    (phase2/terrain.py)
  - Battery system    (phase2/battery.py)
  - Mission waypoints (phase2/mission.py)
  - A* auto-navigate  (phase2/pathfinder.py)

Run with:
    python phase2/main.py
"""

import sys
import logging
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Type

# --- Allow imports from project root ---
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

# Phase 1 core
from rover import (
    Grid, Rover, Direction,
    North, East, South, West,
    Command, MoveForward, TurnLeft, TurnRight,
    TelemetryLogger,
)

# Phase 2 modules
from phase2.terrain import TerrainMap, TerrainType, TERRAIN_DISPLAY, TERRAIN_COLOR
from phase2.battery import Battery
from phase2.mission import Mission, Waypoint
from phase2.pathfinder import Pathfinder

# -----------------------------------------------------------------
# Logging
# -----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

console = Console()

# Direction map (string -> class)
DIRECTION_MAP = {"N": North(), "E": East(), "S": South(), "W": West()}
DIR_SYMBOLS   = {"North": "^", "East": ">", "South": "v", "West": "<"}


# =================================================================
# Phase 2 Rover  (extends Phase 1 Rover with battery + terrain)
# =================================================================

class RoverV2(Rover):
    """
    Extended rover that understands battery drain and terrain costs.

    Inherits all Phase 1 behaviour and adds:
      - battery  : Battery instance tracking energy.
      - terrain  : TerrainMap for per-cell energy costs.
    """

    def __init__(
        self,
        x: int,
        y: int,
        direction: Direction,
        grid: Grid,
        battery: Battery,
        terrain: TerrainMap,
    ):
        super().__init__(x, y, direction, grid)
        self.battery = battery
        self.terrain = terrain

    def move_forward(self) -> bool:
        """
        Move forward if not blocked AND battery is sufficient.

        Returns:
            True on success, False if blocked or battery dead.
        """
        if self.battery.is_dead:
            console.print("[red]Battery dead — rover cannot move![/red]")
            return False

        new_x, new_y = self.direction.move_forward(self.x, self.y)

        if not self.grid.is_valid_position(new_x, new_y):
            console.print("[yellow]! Cannot move — grid boundary![/yellow]")
            return False

        if self.grid.has_obstacle(new_x, new_y):
            console.print("[yellow]! Cannot move — obstacle detected![/yellow]")
            return False

        # Consume battery based on destination terrain
        cost = self.terrain.get_battery_cost(new_x, new_y)
        self.battery.consume(cost)

        self.x, self.y = new_x, new_y
        self.path_history.append((self.x, self.y))
        self.command_count += 1
        return True

    def get_status(self) -> dict:
        """Return status dict including battery info."""
        base = super().get_status()
        base["battery"] = self.battery.get_status()
        return base


# =================================================================
# Phase 2 Grid Visualizer
# =================================================================

class GridVisualizerV2:
    """
    Terminal grid visualizer for Phase 2 (terrain + waypoints + battery bar).
    """

    @staticmethod
    def display(rover: RoverV2, mission: Mission) -> None:
        """
        Render the full grid with:
          - Terrain colouring
          - Rover position & direction
          - Obstacles  (X)
          - Path trail (visited cells)
          - Waypoints  (W = pending, * = reached)
          - Battery bar below the grid

        Args:
            rover:   The Phase-2 rover.
            mission: Current Mission object.
        """
        grid    = rover.grid
        terrain = rover.terrain

        console.print("\n[bold cyan]=== MARS SURFACE - PHASE 2 ===[/bold cyan]\n")

        waypoint_positions   = {wp.position: wp for wp in mission.waypoints}
        rover_symbol = DIR_SYMBOLS.get(str(rover.direction), "R")

        for y in range(grid.height - 1, -1, -1):
            row_parts: List[str] = []
            for x in range(grid.width):
                pos = (x, y)

                if pos == (rover.x, rover.y):
                    row_parts.append(f"[bold green]{rover_symbol}[/bold green]")

                elif pos in grid.obstacles:
                    row_parts.append("[red]X[/red]")

                elif pos in waypoint_positions:
                    wp = waypoint_positions[pos]
                    if wp.reached:
                        row_parts.append("[bold magenta]*[/bold magenta]")
                    else:
                        row_parts.append("[bold yellow]W[/bold yellow]")

                elif pos in rover.path_history:
                    t = terrain.get_terrain(x, y)
                    color = TERRAIN_COLOR[t]
                    char  = TERRAIN_DISPLAY[t]
                    row_parts.append(f"[{color}]{char}[/{color}]")

                else:
                    t = terrain.get_terrain(x, y)
                    color = TERRAIN_COLOR[t]
                    char  = TERRAIN_DISPLAY[t]
                    row_parts.append(f"[dim {color}]{char}[/dim {color}]")

            console.print(f"{y:2d} | " + " ".join(row_parts))

        # X-axis
        console.print("   +" + "-" * (grid.width * 2))
        console.print("     " + " ".join(str(x) for x in range(grid.width)))

        # Legend
        console.print(
            "\n[dim]Legend: "
            "[bold green]^>v<[/bold green] Rover  "
            "[red]X[/red] Obstacle  "
            "[yellow]W[/yellow] Waypoint  "
            "[magenta]*[/magenta] Reached  "
            "[yellow]~[/yellow] Sand  "
            "[bright_black]#[/bright_black] Rock  "
            "[cyan]*[/cyan] Ice  "
            "[dim]. Plain[/dim][/dim]\n"
        )

        # Battery bar
        GridVisualizerV2._render_battery(rover.battery)

        # Waypoint progress
        GridVisualizerV2._render_waypoints(mission)

    @staticmethod
    def _render_battery(battery: Battery) -> None:
        """Print a colour-coded battery bar."""
        pct      = battery.percentage
        filled   = int(pct / 5)       # 20-char bar
        empty    = 20 - filled
        bar_char = "#" * filled + "-" * empty

        if pct > 60:
            color = "green"
        elif pct > 30:
            color = "yellow"
        else:
            color = "red"

        console.print(
            f"[bold]Battery:[/bold] [{color}][{bar_char}][/{color}] "
            f"[{color}]{pct:.0f}%[/{color}] ({battery.charge}/{battery.max_charge}) "
            f"[dim]Status: {battery.status_label}[/dim]"
        )

    @staticmethod
    def _render_waypoints(mission: Mission) -> None:
        """Print a compact waypoint checklist."""
        console.print(
            f"\n[bold]Waypoints:[/bold] "
            f"[green]{mission.reached_count}[/green]"
            f"[dim]/{mission.total_count} reached[/dim]"
        )
        for wp in mission.waypoints:
            if wp.reached:
                console.print(f"  [green][DONE][/green] {wp.name} @ ({wp.x},{wp.y})")
            else:
                console.print(f"  [dim][TODO][/dim] {wp.name} @ ({wp.x},{wp.y})")
        console.print()


# =================================================================
# Configuration
# =================================================================

CONFIG_DEFAULTS = {
    "grid":    {"width": 10, "height": 10, "obstacles": []},
    "rover":   {"start_x": 0, "start_y": 0, "start_direction": "N"},
    "battery": {"max_charge": 100, "solar_rate": 5},
    "terrain": [],
    "mission": {
        "name": "Mars Exploration Phase 2",
        "enable_telemetry": True,
        "telemetry_folder": "telemetry",
        "waypoints": [],
    },
}


def load_config(path: str = "config.yaml") -> dict:
    """
    Load YAML config, falling back to defaults for missing keys.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Merged configuration dictionary.
    """
    try:
        with open(path, "r") as f:
            user_cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        console.print("[yellow]config.yaml not found — using defaults.[/yellow]")
        user_cfg = {}

    # Deep-merge: user values override defaults
    merged = {**CONFIG_DEFAULTS}
    for key, val in user_cfg.items():
        if isinstance(val, dict) and key in merged:
            merged[key] = {**merged[key], **val}
        else:
            merged[key] = val
    return merged


def build_rover(config: dict) -> RoverV2:
    """Construct a RoverV2 from the merged config."""
    gc = config["grid"]
    rc = config["rover"]
    bc = config["battery"]
    tc = config.get("terrain", [])

    obstacles = [tuple(o) for o in gc.get("obstacles", [])]
    grid      = Grid(gc["width"], gc["height"], obstacles)
    battery   = Battery(bc["max_charge"], bc["solar_rate"])
    terrain   = TerrainMap.from_config(gc["width"], gc["height"], tc)
    direction = {k: v for k, v in [
        ("N", North()), ("E", East()), ("S", South()), ("W", West())
    ]}[rc.get("start_direction", "N")]

    return RoverV2(rc["start_x"], rc["start_y"], direction, grid, battery, terrain)


def build_mission(config: dict) -> Mission:
    """Construct a Mission from the merged config."""
    mc = config["mission"]
    return Mission.from_config(mc["name"], mc.get("waypoints", []))


# =================================================================
# User Interface
# =================================================================

COMMAND_MAP: Dict[str, Type[Command]] = {
    "M": MoveForward,
    "L": TurnLeft,
    "R": TurnRight,
}


def show_menu() -> None:
    """Print the available command menu."""
    console.print("\n[bold]Commands:[/bold]")
    console.print("  [green]M[/green]        - Move Forward")
    console.print("  [yellow]L[/yellow]        - Turn Left")
    console.print("  [yellow]R[/yellow]        - Turn Right")
    console.print("  [cyan]G x,y[/cyan]    - Auto-navigate to (x,y) using A*")
    console.print("  [blue]S[/blue]        - Solar charge (rest 1 turn, +battery)")
    console.print("  [red]Q[/red]        - Quit mission")


def execute_command(
    cmd_str: str,
    rover: RoverV2,
    mission: Mission,
    telemetry: Optional[TelemetryLogger],
) -> bool:
    """
    Execute a single command string on the rover.

    Args:
        cmd_str:   The raw command (already upper-cased).
        rover:     The active rover.
        mission:   Current mission.
        telemetry: Optional telemetry logger.

    Returns:
        True to continue the loop, False to quit.
    """
    # --- Quit ---
    if cmd_str == "Q":
        return False

    # --- Solar charge ---
    if cmd_str == "S":
        gained = rover.battery.solar_charge()
        console.print(f"[cyan]Solar charge: +{gained} units[/cyan]")
        if telemetry:
            telemetry.log_event("solar_charge", {"gained": gained,
                                                  "battery": rover.battery.get_status()})
        return True

    # --- A* auto-navigate: G x,y ---
    if cmd_str.startswith("G"):
        _run_auto_navigate(cmd_str, rover, mission, telemetry)
        return True

    # --- Standard M / L / R ---
    if cmd_str in COMMAND_MAP:
        command = COMMAND_MAP[cmd_str]()
        command.execute(rover)

        # Check waypoints after every move
        reached = mission.check_position(rover.x, rover.y)
        if reached:
            console.print(
                f"[bold magenta]Waypoint reached: {reached.name}![/bold magenta]"
            )

        if telemetry:
            telemetry.log_event("command", {
                "command": cmd_str,
                "rover_status": rover.get_status(),
                "mission_status": mission.get_status(),
            })

        logging.info(f"Executed: {cmd_str}")
        return True

    console.print("[red]Unknown command. Try M, L, R, G x,y, S, or Q.[/red]")
    return True


def _run_auto_navigate(
    cmd_str: str,
    rover: RoverV2,
    mission: Mission,
    telemetry: Optional[TelemetryLogger],
) -> None:
    """
    Parse 'G x,y', find an A* path, execute each step.

    Args:
        cmd_str:   Full command string e.g. "G 5,7".
        rover:     The active rover.
        mission:   Current mission.
        telemetry: Optional telemetry logger.
    """
    try:
        parts = cmd_str.split()
        if len(parts) != 2:
            raise ValueError
        gx, gy = map(int, parts[1].split(","))
    except (ValueError, IndexError):
        console.print("[red]Usage: G x,y  e.g.  G 5,7[/red]")
        return

    console.print(f"\n[bold cyan]A* navigating to ({gx},{gy})...[/bold cyan]")

    path = Pathfinder.find_path(rover.grid, (rover.x, rover.y), (gx, gy))

    if path is None:
        console.print("[red]No path found — target may be blocked.[/red]")
        return

    if len(path) == 1:
        console.print("[yellow]Already at the target![/yellow]")
        return

    cmds = Pathfinder.path_to_commands(path, str(rover.direction))
    console.print(f"[dim]Path found: {len(path)-1} steps — commands: {' '.join(cmds)}[/dim]\n")

    for step_cmd in cmds:
        if rover.battery.is_dead:
            console.print("[red]Battery dead — auto-navigation aborted![/red]")
            break

        command = COMMAND_MAP[step_cmd]()
        command.execute(rover)

        reached = mission.check_position(rover.x, rover.y)
        if reached:
            console.print(
                f"[bold magenta]Waypoint reached: {reached.name}![/bold magenta]"
            )

        if telemetry:
            telemetry.log_event("auto_navigate_step", {
                "command": step_cmd,
                "rover_status": rover.get_status(),
            })

        GridVisualizerV2.display(rover, mission)

    console.print(f"[green]Navigation complete. Final position: ({rover.x},{rover.y})[/green]")

    if telemetry:
        telemetry.log_event("auto_navigate_complete", {
            "target": [gx, gy],
            "rover_status": rover.get_status(),
        })


def display_final_summary(rover: RoverV2, mission: Mission,
                           telemetry_path: Optional[str]) -> None:
    """Print the end-of-mission summary table."""
    status  = rover.get_status()
    battery = rover.battery.get_status()

    table = Table(title="Mission Summary - Phase 2",
                  show_header=True, header_style="bold magenta")
    table.add_column("Metric",  style="cyan")
    table.add_column("Value",   style="green")

    table.add_row("Final Position",
                  f"({status['position']['x']}, {status['position']['y']})")
    table.add_row("Final Direction",     status["direction"])
    table.add_row("Commands Executed",   str(status["commands_executed"]))
    table.add_row("Unique Cells Visited",str(status["cells_visited"]))
    table.add_row("Battery Remaining",
                  f"{battery['charge']}/{battery['max_charge']} ({battery['percentage']}%)")
    table.add_row("Energy Consumed",     str(battery["total_consumed"]))
    table.add_row("Energy Recharged",    str(battery["total_recharged"]))
    table.add_row("Waypoints Reached",
                  f"{mission.reached_count}/{mission.total_count}")
    table.add_row("Mission Complete",
                  "[green]YES[/green]" if mission.is_complete else "[red]NO[/red]")

    if telemetry_path:
        table.add_row("Telemetry Saved", telemetry_path)

    console.print("\n")
    console.print(table)
    console.print("\n")


# =================================================================
# Main
# =================================================================

def main() -> None:
    """Phase 2 entry point."""

    console.print(Panel.fit(
        "[bold cyan]MARS ROVER SIMULATION - Phase 2[/bold cyan]\n"
        "[dim]A* Navigation | Battery System | Terrain | Waypoints[/dim]",
        border_style="cyan",
    ))

    # Load config
    config = load_config()
    mc = config["mission"]

    console.print(f"\n[bold]Mission:[/bold] {mc['name']}\n")

    # Build objects
    rover   = build_rover(config)
    mission = build_mission(config)

    # Telemetry
    telemetry: Optional[TelemetryLogger] = None
    if mc.get("enable_telemetry", True):
        telemetry = TelemetryLogger(mc["name"],
                                    mc.get("telemetry_folder", "telemetry"))
        telemetry.log_event("mission_start", rover.get_status())

    # Initial display
    GridVisualizerV2.display(rover, mission)

    # ---- Main command loop ----
    running = True
    while running:
        show_menu()
        try:
            raw = console.input("\n[bold cyan]Command:[/bold cyan] ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            break

        running = execute_command(raw, rover, mission, telemetry)

        # Refresh grid after every action (except quit)
        if running:
            GridVisualizerV2.display(rover, mission)

        # Check mission completion
        if mission.is_complete:
            console.print(
                "[bold green]All waypoints reached — Mission Complete![/bold green]"
            )

    # ---- Wrap up ----
    telemetry_path: Optional[str] = None
    if telemetry:
        telemetry.log_event("mission_end", {
            "rover": rover.get_status(),
            "mission": mission.get_status(),
        })
        telemetry_path = telemetry.save(rover)
        console.print(f"[green]Telemetry saved: {telemetry_path}[/green]")

    display_final_summary(rover, mission, telemetry_path)
    console.print("[bold green]Mission signed off. Safe travels![/bold green]\n")


if __name__ == "__main__":
    main()
