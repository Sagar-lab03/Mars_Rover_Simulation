"""
terrain.py - Terrain Types for Mars Rover Simulation (Phase 2)

Defines different terrain types that the rover can encounter on Mars.
Each terrain affects battery consumption differently when moving through it.

Terrain Types:
    - Plain:   Standard flat ground. Normal battery usage.
    - Sand:    Loose sand. Higher battery consumption (slows the rover).
    - Rock:    Rocky patches. Highest battery consumption.
    - Ice:     Icy surface. Lower battery consumption but slippery concept.
"""

from enum import Enum
from typing import Dict, Tuple, List


class TerrainType(Enum):
    """Enum representing terrain types on the Martian surface."""
    PLAIN = "plain"
    SAND  = "sand"
    ROCK  = "rock"
    ICE   = "ice"


# Battery cost per move on each terrain type
TERRAIN_BATTERY_COST: Dict[TerrainType, int] = {
    TerrainType.PLAIN: 5,
    TerrainType.SAND:  10,
    TerrainType.ROCK:  15,
    TerrainType.ICE:   3,
}

# Display characters for each terrain in the terminal grid
TERRAIN_DISPLAY: Dict[TerrainType, str] = {
    TerrainType.PLAIN: ".",
    TerrainType.SAND:  "~",
    TerrainType.ROCK:  "#",
    TerrainType.ICE:   "*",
}

# Rich color tags for each terrain
TERRAIN_COLOR: Dict[TerrainType, str] = {
    TerrainType.PLAIN: "dim",
    TerrainType.SAND:  "yellow",
    TerrainType.ROCK:  "bright_black",
    TerrainType.ICE:   "cyan",
}


class TerrainMap:
    """
    Manages terrain across the grid.

    Stores a terrain type for each (x, y) cell. Cells not explicitly
    set default to TerrainType.PLAIN.
    """

    def __init__(self, width: int, height: int):
        """
        Initialise the terrain map.

        Args:
            width:  Number of columns in the grid.
            height: Number of rows in the grid.
        """
        self.width = width
        self.height = height
        # Default everything to PLAIN
        self._map: Dict[Tuple[int, int], TerrainType] = {}

    def set_terrain(self, x: int, y: int, terrain: TerrainType) -> None:
        """
        Assign a terrain type to a specific cell.

        Args:
            x:       Column index.
            y:       Row index.
            terrain: The TerrainType to assign.
        """
        self._map[(x, y)] = terrain

    def get_terrain(self, x: int, y: int) -> TerrainType:
        """
        Return the terrain type at (x, y), defaulting to PLAIN.

        Args:
            x: Column index.
            y: Row index.

        Returns:
            The TerrainType at the given cell.
        """
        return self._map.get((x, y), TerrainType.PLAIN)

    def get_battery_cost(self, x: int, y: int) -> int:
        """
        Return the battery cost of moving into cell (x, y).

        Args:
            x: Column index.
            y: Row index.

        Returns:
            Battery units consumed when the rover moves onto this cell.
        """
        terrain = self.get_terrain(x, y)
        return TERRAIN_BATTERY_COST[terrain]

    @classmethod
    def from_config(cls, width: int, height: int,
                    terrain_config: List[Dict]) -> "TerrainMap":
        """
        Build a TerrainMap from a YAML/dict config list.

        Expected format per entry:
            { type: "sand", cells: [[x1,y1], [x2,y2], ...] }

        Args:
            width:          Grid width.
            height:         Grid height.
            terrain_config: List of terrain patch definitions.

        Returns:
            A populated TerrainMap instance.
        """
        terrain_map = cls(width, height)
        type_lookup = {t.value: t for t in TerrainType}

        for patch in terrain_config:
            t_type = type_lookup.get(patch.get("type", "plain"), TerrainType.PLAIN)
            for cell in patch.get("cells", []):
                terrain_map.set_terrain(cell[0], cell[1], t_type)

        return terrain_map
