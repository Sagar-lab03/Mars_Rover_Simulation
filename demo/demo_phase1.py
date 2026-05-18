"""
demo/demo_phase1.py - Automated Phase 1 Demo (moved from root)

Runs a scripted rover mission without user input to showcase Phase 1.

Run with:
    python demo/demo_phase1.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rover import Grid, Rover, North, MoveForward, TurnRight, TurnLeft, GridVisualizer
from rich.console import Console

console = Console()


def demo():
    """Run a simple automated demo."""
    console.print("\n[bold cyan]=== MARS ROVER PHASE 1 - AUTOMATED DEMO ===[/bold cyan]\n")

    grid  = Grid(10, 10, obstacles=[(2, 2), (3, 5), (7, 8)])
    rover = Rover(0, 0, North(), grid)

    console.print("[yellow]Initial State:[/yellow]")
    GridVisualizer.display_grid(rover)

    commands = [
        ("Move Forward",  MoveForward()),
        ("Move Forward",  MoveForward()),
        ("Turn Right",    TurnRight()),
        ("Move Forward",  MoveForward()),
        ("Move Forward",  MoveForward()),
        ("Turn Left",     TurnLeft()),
        ("Move Forward",  MoveForward()),
    ]

    for desc, cmd in commands:
        console.print(f"\n[cyan]Executing: {desc}[/cyan]")
        cmd.execute(rover)
        GridVisualizer.display_grid(rover)

    status = rover.get_status()
    console.print(f"\n[bold green]Demo Complete![/bold green]")
    console.print(f"Final Position  : ({status['position']['x']}, {status['position']['y']})")
    console.print(f"Final Direction : {status['direction']}")
    console.print(f"Commands Run    : {status['commands_executed']}")
    console.print(f"Cells Visited   : {status['cells_visited']}\n")


if __name__ == "__main__":
    demo()
