"""
demo/demo_phase2.py - Automated Phase 2 Demo

Showcases all Phase 2 features without user input:
  1. Terrain-aware movement (battery drain varies by surface)
  2. Battery system with solar recharging
  3. Mission waypoints (marking as reached)
  4. A* auto-navigation to a waypoint

Run with:
    python demo/demo_phase2.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.rule import Rule

from rover import Grid, North
from phase2.battery   import Battery
from phase2.terrain   import TerrainMap, TerrainType
from phase2.mission   import Mission, Waypoint
from phase2.pathfinder import Pathfinder
from phase2.main      import (
    RoverV2, GridVisualizerV2, COMMAND_MAP
)

console = Console()


def section(title: str) -> None:
    console.print()
    console.print(Rule(f"[bold cyan]{title}[/bold cyan]", style="cyan"))
    console.print()


def pause() -> None:
    """Small visual pause so output is readable."""
    import time
    time.sleep(0.4)


def main() -> None:
    console.print()
    console.print("[bold cyan]=== MARS ROVER PHASE 2 - AUTOMATED DEMO ===[/bold cyan]")
    console.print("[dim]Watch how terrain, battery, waypoints, and A* work together![/dim]\n")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    grid = Grid(10, 10, obstacles=[(2, 2), (3, 5), (7, 8), (5, 3)])

    terrain = TerrainMap(10, 10)
    terrain.set_terrain(1, 1, TerrainType.SAND)
    terrain.set_terrain(2, 1, TerrainType.SAND)
    terrain.set_terrain(3, 1, TerrainType.SAND)
    terrain.set_terrain(6, 4, TerrainType.ROCK)
    terrain.set_terrain(6, 5, TerrainType.ROCK)
    terrain.set_terrain(0, 5, TerrainType.ICE)
    terrain.set_terrain(0, 6, TerrainType.ICE)

    battery = Battery(max_charge=100, solar_rate=5)

    mission = Mission("Demo Mission")
    mission.add_waypoint(Waypoint("Sample Site Alpha", 4, 4))
    mission.add_waypoint(Waypoint("High Ground Sigma", 8, 8))

    rover = RoverV2(0, 0, North(), grid, battery, terrain)

    # ------------------------------------------------------------------
    # 1) Initial state
    # ------------------------------------------------------------------
    section("1. Initial State")
    console.print("[dim]Rover starts at (0,0) facing North. Battery: 100%[/dim]")
    GridVisualizerV2.display(rover, mission)
    pause()

    # ------------------------------------------------------------------
    # 2) Manual movement — show terrain battery drain
    # ------------------------------------------------------------------
    section("2. Manual Movement — Terrain Battery Drain")

    moves = [
        ("M", "Move forward onto PLAIN  (costs  5 units)"),
        ("M", "Move forward onto PLAIN  (costs  5 units)"),
        ("R", "Turn right — now facing East"),
        ("M", "Move forward onto SAND   (costs 10 units)"),
        ("M", "Move forward onto SAND   (costs 10 units)"),
        ("L", "Turn left  — now facing North"),
    ]

    for cmd_str, description in moves:
        console.print(f"[yellow]>> {cmd_str}[/yellow]  [dim]{description}[/dim]")
        before = rover.battery.charge
        COMMAND_MAP[cmd_str]().execute(rover)
        after  = rover.battery.charge
        if cmd_str == "M":
            console.print(
                f"   Battery: {before} -> [cyan]{after}[/cyan]"
                f"  (drained [red]{before - after}[/red] units)"
            )
        mission.check_position(rover.x, rover.y)
        pause()

    GridVisualizerV2.display(rover, mission)

    # ------------------------------------------------------------------
    # 3) Solar recharge
    # ------------------------------------------------------------------
    section("3. Solar Recharge")
    before = rover.battery.charge
    gained = rover.battery.solar_charge()
    console.print(
        f"[cyan]Rover rests and solar panels recharge.[/cyan]\n"
        f"Battery: {before} -> [green]{rover.battery.charge}[/green]  (+{gained} units)"
    )
    pause()

    # ------------------------------------------------------------------
    # 4) A* auto-navigate to first waypoint
    # ------------------------------------------------------------------
    section("4. A* Auto-Navigation to 'Sample Site Alpha' (4,4)")
    start  = (rover.x, rover.y)
    goal   = (4, 4)
    path   = Pathfinder.find_path(rover.grid, start, goal)

    if path:
        cmds = Pathfinder.path_to_commands(path, str(rover.direction))
        console.print(f"[dim]Path found: {len(path)-1} steps[/dim]")
        console.print(f"[dim]Commands  : {' '.join(cmds)}[/dim]\n")

        for step_cmd in cmds:
            if rover.battery.is_dead:
                console.print("[red]Battery dead — stopping![/red]")
                break
            COMMAND_MAP[step_cmd]().execute(rover)
            reached = mission.check_position(rover.x, rover.y)
            if reached:
                console.print(
                    f"[bold magenta]Waypoint reached: {reached.name}![/bold magenta]"
                )
            pause()

        GridVisualizerV2.display(rover, mission)
    else:
        console.print("[red]No path found.[/red]")

    # ------------------------------------------------------------------
    # 5) A* auto-navigate to second waypoint
    # ------------------------------------------------------------------
    section("5. A* Auto-Navigation to 'High Ground Sigma' (8,8)")
    path2 = Pathfinder.find_path(rover.grid, (rover.x, rover.y), (8, 8))

    if path2:
        cmds2 = Pathfinder.path_to_commands(path2, str(rover.direction))
        console.print(f"[dim]Path found: {len(path2)-1} steps[/dim]")
        console.print(f"[dim]Commands  : {' '.join(cmds2)}[/dim]\n")

        for step_cmd in cmds2:
            if rover.battery.is_dead:
                console.print("[red]Battery dead — topping up with solar...[/red]")
                while rover.battery.charge < 20:
                    rover.battery.solar_charge()
            COMMAND_MAP[step_cmd]().execute(rover)
            reached = mission.check_position(rover.x, rover.y)
            if reached:
                console.print(
                    f"[bold magenta]Waypoint reached: {reached.name}![/bold magenta]"
                )
            pause()

        GridVisualizerV2.display(rover, mission)
    else:
        console.print("[red]No path found.[/red]")

    # ------------------------------------------------------------------
    # 6) Final summary
    # ------------------------------------------------------------------
    section("6. Mission Summary")
    status  = rover.get_status()
    battery = rover.battery.get_status()

    console.print(f"  Final Position  : ({status['position']['x']}, {status['position']['y']})")
    console.print(f"  Final Direction : {status['direction']}")
    console.print(f"  Commands Run    : {status['commands_executed']}")
    console.print(f"  Cells Visited   : {status['cells_visited']}")
    console.print(f"  Battery Left    : {battery['charge']}/{battery['max_charge']} ({battery['percentage']}%)")
    console.print(f"  Energy Consumed : {battery['total_consumed']} units")
    console.print(f"  Waypoints       : {mission.reached_count}/{mission.total_count}")
    console.print(
        f"\n  [bold]Mission Complete:[/bold] "
        + ("[bold green]YES[/bold green]" if mission.is_complete else "[bold red]NO[/bold red]")
    )
    console.print()


if __name__ == "__main__":
    main()
