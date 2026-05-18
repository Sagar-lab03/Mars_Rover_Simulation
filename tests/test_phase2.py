"""
tests/test_phase2.py - Unit Tests for Mars Rover Simulation Phase 2

Covers:
  - Battery system
  - Terrain system
  - Mission / Waypoint system
  - A* Pathfinder
  - RoverV2 integration

Run with:
    pytest tests/test_phase2.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from rover import Grid, North, East, South, West
from phase2.battery  import Battery
from phase2.terrain  import TerrainMap, TerrainType, TERRAIN_BATTERY_COST
from phase2.mission  import Mission, Waypoint
from phase2.pathfinder import Pathfinder
from phase2.main     import RoverV2


# =================================================================
# Battery Tests
# =================================================================

class TestBattery:
    """Tests for the Battery energy system."""

    def test_initial_full_charge(self):
        """Battery starts at max charge."""
        b = Battery(max_charge=100)
        assert b.charge == 100
        assert b.percentage == 100.0

    def test_consume_reduces_charge(self):
        """Consuming energy reduces the charge."""
        b = Battery(max_charge=100)
        b.consume(20)
        assert b.charge == 80

    def test_consume_cannot_go_below_zero(self):
        """Battery charge cannot drop below 0."""
        b = Battery(max_charge=50)
        b.consume(200)          # over-drain
        assert b.charge == 0

    def test_is_dead_when_empty(self):
        """is_dead returns True when charge is 0."""
        b = Battery(max_charge=10)
        b.consume(10)
        assert b.is_dead is True

    def test_is_not_dead_when_partial(self):
        """is_dead returns False when charge > 0."""
        b = Battery(max_charge=100)
        b.consume(50)
        assert b.is_dead is False

    def test_solar_charge_refills(self):
        """Solar charging increases the battery."""
        b = Battery(max_charge=100, solar_rate=10)
        b.consume(30)           # charge = 70
        gained = b.solar_charge()
        assert gained == 10
        assert b.charge == 80

    def test_solar_charge_does_not_exceed_max(self):
        """Solar charging cannot exceed max_charge."""
        b = Battery(max_charge=100, solar_rate=10)
        b.consume(5)            # charge = 95
        gained = b.solar_charge()
        assert gained == 5      # only 5 available before hitting max
        assert b.charge == 100

    def test_solar_charge_when_full(self):
        """Solar charging does nothing when already full."""
        b = Battery(max_charge=100, solar_rate=10)
        gained = b.solar_charge()
        assert gained == 0
        assert b.charge == 100

    def test_status_label_good(self):
        b = Battery(100)
        assert b.status_label == "Good"

    def test_status_label_low(self):
        b = Battery(100)
        b.consume(61)          # 39 left
        assert b.status_label == "Low"

    def test_status_label_critical(self):
        b = Battery(100)
        b.consume(75)          # 25 left
        assert b.status_label == "Critical"

    def test_total_consumed_tracks_correctly(self):
        b = Battery(100)
        b.consume(20)
        b.consume(15)
        assert b.total_consumed == 35

    def test_total_recharged_tracks_correctly(self):
        b = Battery(100, solar_rate=10)
        b.consume(30)
        b.solar_charge()
        b.solar_charge()
        assert b.total_recharged == 20


# =================================================================
# Terrain Tests
# =================================================================

class TestTerrain:
    """Tests for the TerrainMap system."""

    def test_default_terrain_is_plain(self):
        """Unset cells are PLAIN."""
        tm = TerrainMap(10, 10)
        assert tm.get_terrain(5, 5) == TerrainType.PLAIN

    def test_set_and_get_terrain(self):
        """Terrain can be set and retrieved."""
        tm = TerrainMap(10, 10)
        tm.set_terrain(3, 4, TerrainType.SAND)
        assert tm.get_terrain(3, 4) == TerrainType.SAND

    def test_battery_cost_plain(self):
        """PLAIN terrain costs the least."""
        tm = TerrainMap(10, 10)
        assert tm.get_battery_cost(0, 0) == TERRAIN_BATTERY_COST[TerrainType.PLAIN]

    def test_battery_cost_sand(self):
        """SAND terrain has higher battery cost than PLAIN."""
        tm = TerrainMap(10, 10)
        tm.set_terrain(1, 1, TerrainType.SAND)
        sand_cost  = tm.get_battery_cost(1, 1)
        plain_cost = TERRAIN_BATTERY_COST[TerrainType.PLAIN]
        assert sand_cost > plain_cost

    def test_battery_cost_rock_is_highest(self):
        """ROCK terrain costs more than SAND."""
        rock_cost = TERRAIN_BATTERY_COST[TerrainType.ROCK]
        sand_cost = TERRAIN_BATTERY_COST[TerrainType.SAND]
        assert rock_cost > sand_cost

    def test_from_config(self):
        """TerrainMap.from_config correctly assigns terrain from a list."""
        config = [
            {"type": "sand", "cells": [[1, 1], [2, 1]]},
            {"type": "rock", "cells": [[5, 5]]},
        ]
        tm = TerrainMap.from_config(10, 10, config)
        assert tm.get_terrain(1, 1) == TerrainType.SAND
        assert tm.get_terrain(2, 1) == TerrainType.SAND
        assert tm.get_terrain(5, 5) == TerrainType.ROCK
        assert tm.get_terrain(0, 0) == TerrainType.PLAIN   # default


# =================================================================
# Mission / Waypoint Tests
# =================================================================

class TestMission:
    """Tests for the Mission objectives system."""

    def test_waypoint_initially_not_reached(self):
        """New waypoints are not yet reached."""
        wp = Waypoint("Alpha", 3, 7)
        assert wp.reached is False

    def test_check_position_marks_waypoint(self):
        """check_position marks a matching waypoint as reached."""
        m = Mission("Test")
        m.add_waypoint(Waypoint("Alpha", 3, 7))
        reached = m.check_position(3, 7)
        assert reached is not None
        assert reached.name == "Alpha"
        assert m.waypoints[0].reached is True

    def test_check_position_wrong_cell(self):
        """check_position on a non-waypoint cell returns None."""
        m = Mission("Test")
        m.add_waypoint(Waypoint("Alpha", 3, 7))
        result = m.check_position(1, 1)
        assert result is None

    def test_mission_not_complete_until_all_reached(self):
        """Mission is not complete until every waypoint is reached."""
        m = Mission("Test")
        m.add_waypoint(Waypoint("A", 1, 1))
        m.add_waypoint(Waypoint("B", 2, 2))
        m.check_position(1, 1)
        assert m.is_complete is False

    def test_mission_complete_when_all_reached(self):
        """Mission is complete when all waypoints are reached."""
        m = Mission("Test")
        m.add_waypoint(Waypoint("A", 1, 1))
        m.add_waypoint(Waypoint("B", 2, 2))
        m.check_position(1, 1)
        m.check_position(2, 2)
        assert m.is_complete is True

    def test_reached_count(self):
        m = Mission("Test")
        m.add_waypoint(Waypoint("A", 1, 1))
        m.add_waypoint(Waypoint("B", 2, 2))
        m.check_position(1, 1)
        assert m.reached_count == 1

    def test_from_config(self):
        """Mission.from_config builds waypoints from a dict list."""
        cfg = [{"name": "Site A", "x": 4, "y": 6}]
        m = Mission.from_config("Test Mission", cfg)
        assert len(m.waypoints) == 1
        assert m.waypoints[0].x == 4
        assert m.waypoints[0].y == 6


# =================================================================
# A* Pathfinder Tests
# =================================================================

class TestPathfinder:
    """Tests for the A* pathfinding algorithm."""

    def _open_grid(self):
        """Return a 10x10 grid with no obstacles."""
        return Grid(10, 10)

    def test_trivial_same_start_goal(self):
        """Path from a cell to itself is just that cell."""
        grid = self._open_grid()
        path = Pathfinder.find_path(grid, (3, 3), (3, 3))
        assert path == [(3, 3)]

    def test_straight_path_north(self):
        """Path moving north should step through y coords."""
        grid = self._open_grid()
        path = Pathfinder.find_path(grid, (0, 0), (0, 3))
        assert path is not None
        assert path[0]  == (0, 0)
        assert path[-1] == (0, 3)
        assert len(path) == 4   # 0,1,2,3

    def test_path_avoids_obstacle(self):
        """Path must not pass through an obstacle."""
        grid = Grid(5, 5, obstacles=[(0, 1), (1, 1), (2, 1)])
        path = Pathfinder.find_path(grid, (0, 0), (0, 2))
        assert path is not None
        for pos in path:
            assert pos not in grid.obstacles

    def test_no_path_when_blocked(self):
        """Returns None when target is completely surrounded by obstacles."""
        # Surround (2,2) so it cannot be reached
        obstacles = [(1,2),(3,2),(2,1),(2,3)]
        grid = Grid(5, 5, obstacles=obstacles)
        path = Pathfinder.find_path(grid, (0, 0), (2, 2))
        assert path is None

    def test_goal_itself_is_obstacle(self):
        """Returns None when goal cell is an obstacle."""
        grid = Grid(5, 5, obstacles=[(3, 3)])
        path = Pathfinder.find_path(grid, (0, 0), (3, 3))
        assert path is None

    def test_path_to_commands_straight(self):
        """Straight north path from (0,0) to (0,2) should yield M,M."""
        path = [(0, 0), (0, 1), (0, 2)]
        cmds = Pathfinder.path_to_commands(path, "North")
        assert cmds == ["M", "M"]

    def test_path_to_commands_turn(self):
        """Path requiring a right turn: north then east."""
        path = [(0, 0), (0, 1), (1, 1)]
        cmds = Pathfinder.path_to_commands(path, "North")
        # Move N, turn R, move E
        assert "M" in cmds
        assert "R" in cmds


# =================================================================
# RoverV2 Integration Tests
# =================================================================

class TestRoverV2:
    """Integration tests for the Phase 2 rover."""

    def _make_rover(self, x=0, y=0, max_charge=100):
        grid    = Grid(10, 10)
        battery = Battery(max_charge=max_charge, solar_rate=5)
        terrain = TerrainMap(10, 10)
        return RoverV2(x, y, North(), grid, battery, terrain)

    def test_move_drains_battery(self):
        """Moving forward drains the battery."""
        rover = self._make_rover()
        initial = rover.battery.charge
        rover.move_forward()
        assert rover.battery.charge < initial

    def test_move_blocked_when_battery_dead(self):
        """Rover cannot move when battery is fully depleted."""
        rover = self._make_rover(max_charge=1)
        rover.battery.consume(1)   # kill battery
        result = rover.move_forward()
        assert result is False
        assert rover.y == 0        # did not move

    def test_terrain_sand_costs_more(self):
        """Moving onto SAND drains more battery than PLAIN."""
        grid    = Grid(10, 10)
        battery = Battery(100)
        terrain = TerrainMap(10, 10)
        terrain.set_terrain(0, 1, TerrainType.SAND)
        rover_sand = RoverV2(0, 0, North(), grid, battery, terrain)

        before = rover_sand.battery.charge
        rover_sand.move_forward()   # steps onto sand at (0,1)
        sand_cost = before - rover_sand.battery.charge

        # Compare with plain
        battery2  = Battery(100)
        terrain2  = TerrainMap(10, 10)   # all PLAIN
        rover_plain = RoverV2(0, 0, North(), grid, battery2, terrain2)
        before2 = rover_plain.battery.charge
        rover_plain.move_forward()
        plain_cost = before2 - rover_plain.battery.charge

        assert sand_cost > plain_cost

    def test_status_includes_battery(self):
        """get_status() should include battery info."""
        rover = self._make_rover()
        status = rover.get_status()
        assert "battery" in status
        assert "charge" in status["battery"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
