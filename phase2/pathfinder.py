"""
pathfinder.py - A* Pathfinding for Mars Rover Simulation (Phase 2)

Implements the A* search algorithm to find the shortest obstacle-free
path between two cells on the rover's grid.

Why A*?
-------
A* is the industry-standard informed search algorithm. It combines
Dijkstra's guaranteed shortest-path with a heuristic that guides the
search toward the goal — making it much faster on larger grids.

Heuristic used: Manhattan distance (grid movement, no diagonals).

Usage
-----
    from phase2.pathfinder import Pathfinder

    path = Pathfinder.find_path(grid, start=(0,0), goal=(5,7))
    if path:
        for step in path:
            print(step)   # (x, y) tuples from start to goal
"""

import heapq
from typing import List, Optional, Tuple, Dict

# Type aliases
Position = Tuple[int, int]


class Pathfinder:
    """
    Provides A* pathfinding on a Grid (Phase 1).

    All methods are static — no instance needed.
    """

    @staticmethod
    def heuristic(a: Position, b: Position) -> int:
        """
        Manhattan distance between two grid cells.

        This is admissible (never over-estimates) for 4-directional grids.

        Args:
            a: First cell (x, y).
            b: Second cell (x, y).

        Returns:
            Manhattan distance as an integer.
        """
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def find_path(grid, start: Position, goal: Position) -> Optional[List[Position]]:
        """
        Find the shortest obstacle-free path from start to goal using A*.

        Args:
            grid:  A Phase-1 Grid object (must have .width, .height,
                   .has_obstacle(), .is_valid_position()).
            start: Starting cell (x, y).
            goal:  Target cell (x, y).

        Returns:
            An ordered list of (x, y) positions from start to goal
            (inclusive of both endpoints), or None if no path exists.
        """
        # Guard: trivial case
        if start == goal:
            return [start]

        # Guard: goal is blocked
        if grid.has_obstacle(goal[0], goal[1]):
            return None

        # Priority queue entries: (f_score, position)
        open_heap: List[Tuple[int, Position]] = []
        heapq.heappush(open_heap, (0, start))

        # Maps each position to its cheapest known predecessor
        came_from: Dict[Position, Optional[Position]] = {start: None}

        # g_score[pos] = cheapest known cost from start to pos
        g_score: Dict[Position, int] = {start: 0}

        # 4-directional neighbours: N, E, S, W
        neighbours = [(0, 1), (1, 0), (0, -1), (-1, 0)]

        while open_heap:
            _, current = heapq.heappop(open_heap)

            # Goal reached — reconstruct and return path
            if current == goal:
                return Pathfinder._reconstruct(came_from, goal)

            cx, cy = current
            for dx, dy in neighbours:
                nx, ny = cx + dx, cy + dy
                neighbour: Position = (nx, ny)

                # Skip out-of-bounds or obstacle cells
                if not grid.is_valid_position(nx, ny):
                    continue
                if grid.has_obstacle(nx, ny):
                    continue

                tentative_g = g_score[current] + 1  # uniform step cost

                if tentative_g < g_score.get(neighbour, float("inf")):
                    came_from[neighbour] = current
                    g_score[neighbour] = tentative_g
                    f_score = tentative_g + Pathfinder.heuristic(neighbour, goal)
                    heapq.heappush(open_heap, (f_score, neighbour))

        # Exhausted all reachable cells — no path found
        return None

    @staticmethod
    def _reconstruct(came_from: Dict[Position, Optional[Position]],
                     goal: Position) -> List[Position]:
        """
        Walk the came_from map backwards to build the full path.

        Args:
            came_from: Predecessor map produced by A*.
            goal:      The destination cell.

        Returns:
            Ordered list of positions from start to goal.
        """
        path: List[Position] = []
        current: Optional[Position] = goal
        while current is not None:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path

    @staticmethod
    def path_to_commands(path: List[Position],
                         start_direction: str) -> List[str]:
        """
        Convert an A* path (list of positions) into rover commands (M/L/R).

        Args:
            path:            Ordered list of (x, y) positions.
            start_direction: Starting direction string: "North","East",
                             "South", or "West".

        Returns:
            List of command strings ('M', 'L', 'R').
        """
        if len(path) < 2:
            return []

        # Direction vectors and turn logic
        DIR_VECTOR = {
            "North": (0,  1),
            "East":  (1,  0),
            "South": (0, -1),
            "West":  (-1, 0),
        }
        # Clockwise order for turns
        CW = ["North", "East", "South", "West"]

        commands: List[str] = []
        current_dir = start_direction

        for i in range(len(path) - 1):
            cx, cy = path[i]
            nx, ny = path[i + 1]
            dx, dy = nx - cx, ny - cy

            # Find which direction matches this step
            target_dir = next(
                d for d, v in DIR_VECTOR.items() if v == (dx, dy)
            )

            # Turn until facing the right way
            while current_dir != target_dir:
                cur_idx = CW.index(current_dir)
                tgt_idx = CW.index(target_dir)
                # Choose shortest turn (left or right)
                if (tgt_idx - cur_idx) % 4 == 1:
                    commands.append("R")
                    current_dir = CW[(cur_idx + 1) % 4]
                else:
                    commands.append("L")
                    current_dir = CW[(cur_idx - 1) % 4]

            commands.append("M")  # Move forward one step

        return commands
