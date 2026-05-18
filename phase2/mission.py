"""
mission.py - Mission Objectives System for Mars Rover Simulation (Phase 2)

Defines waypoints the rover must visit to complete its mission.
Each waypoint is a named (x, y) target. The mission tracks which
waypoints have been reached and reports overall completion status.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class Waypoint:
    """
    A single mission target the rover must reach.

    Attributes:
        name   : Human-readable label (e.g. "Sample Site Alpha").
        x      : Target column on the grid.
        y      : Target row on the grid.
        reached: True once the rover visits this cell.
    """
    name: str
    x: int
    y: int
    reached: bool = field(default=False, init=False)

    @property
    def position(self) -> Tuple[int, int]:
        """Return the (x, y) tuple for this waypoint."""
        return (self.x, self.y)

    def __str__(self) -> str:
        status = "DONE" if self.reached else "TODO"
        return f"[{status}] {self.name} @ ({self.x}, {self.y})"


class Mission:
    """
    Tracks overall mission objectives (waypoints).

    Usage
    -----
    Create a Mission, add Waypoints, then call `check_position` after
    each rover move.  Use `is_complete` to know when all targets are hit.
    """

    def __init__(self, name: str, waypoints: Optional[List[Waypoint]] = None):
        """
        Initialise the mission.

        Args:
            name:      Mission title shown in the UI.
            waypoints: Initial list of Waypoint objects (optional).
        """
        self.name: str = name
        self.waypoints: List[Waypoint] = waypoints or []

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_waypoint(self, waypoint: Waypoint) -> None:
        """Append a waypoint to the mission."""
        self.waypoints.append(waypoint)

    def check_position(self, x: int, y: int) -> Optional[Waypoint]:
        """
        Check if (x, y) coincides with any unreached waypoint and mark it.

        Args:
            x: Current rover column.
            y: Current rover row.

        Returns:
            The Waypoint that was just reached, or None.
        """
        for wp in self.waypoints:
            if not wp.reached and wp.x == x and wp.y == y:
                wp.reached = True
                return wp
        return None

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @property
    def is_complete(self) -> bool:
        """Return True when every waypoint has been reached."""
        return all(wp.reached for wp in self.waypoints)

    @property
    def reached_count(self) -> int:
        """Number of waypoints reached so far."""
        return sum(1 for wp in self.waypoints if wp.reached)

    @property
    def total_count(self) -> int:
        """Total number of waypoints in this mission."""
        return len(self.waypoints)

    def get_status(self) -> dict:
        """
        Return a serialisable snapshot of mission progress.

        Returns:
            Dictionary suitable for telemetry / display.
        """
        return {
            "name": self.name,
            "total_waypoints": self.total_count,
            "reached_waypoints": self.reached_count,
            "complete": self.is_complete,
            "waypoints": [
                {
                    "name": wp.name,
                    "position": list(wp.position),
                    "reached": wp.reached,
                }
                for wp in self.waypoints
            ],
        }

    @classmethod
    def from_config(cls, mission_name: str,
                    waypoints_config: List[dict]) -> "Mission":
        """
        Build a Mission from a YAML/dict config list.

        Expected format per entry:
            { name: "Sample Site Alpha", x: 3, y: 7 }

        Args:
            mission_name:      Mission title.
            waypoints_config:  List of waypoint dicts from config.yaml.

        Returns:
            A populated Mission instance.
        """
        waypoints = [
            Waypoint(
                name=wp.get("name", f"WP-{i}"),
                x=wp["x"],
                y=wp["y"],
            )
            for i, wp in enumerate(waypoints_config)
        ]
        return cls(name=mission_name, waypoints=waypoints)
