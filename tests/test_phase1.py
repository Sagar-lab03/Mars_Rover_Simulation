"""
tests/test_phase1.py - Unit Tests for Mars Rover Simulation Phase 1
(Canonical location; mirrors the root-level test_rover.py)

Run with:
    pytest tests/test_phase1.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from rover import (
    North, East, South, West,
    Grid, Rover,
    MoveForward, TurnLeft, TurnRight,
)


class TestDirections:
    """Test direction classes."""

    def test_north_movement(self):
        north = North()
        x, y = north.move_forward(5, 5)
        assert (x, y) == (5, 6)

    def test_east_movement(self):
        east = East()
        x, y = east.move_forward(5, 5)
        assert (x, y) == (6, 5)

    def test_south_movement(self):
        south = South()
        x, y = south.move_forward(5, 5)
        assert (x, y) == (5, 4)

    def test_west_movement(self):
        west = West()
        x, y = west.move_forward(5, 5)
        assert (x, y) == (4, 5)

    def test_turn_left_from_north(self):
        assert isinstance(North().turn_left(), West)

    def test_turn_right_from_north(self):
        assert isinstance(North().turn_right(), East)

    def test_full_rotation_left(self):
        d = North()
        for _ in range(4):
            d = d.turn_left()
        assert isinstance(d, North)

    def test_full_rotation_right(self):
        d = North()
        for _ in range(4):
            d = d.turn_right()
        assert isinstance(d, North)


class TestGrid:
    """Test grid functionality."""

    def test_grid_creation(self):
        grid = Grid(10, 10)
        assert grid.width == 10
        assert grid.height == 10

    def test_obstacle_detection(self):
        grid = Grid(10, 10, obstacles=[(2, 2), (5, 5)])
        assert grid.has_obstacle(2, 2) is True
        assert grid.has_obstacle(3, 3) is False

    def test_valid_position(self):
        grid = Grid(10, 10)
        assert grid.is_valid_position(5, 5) is True
        assert grid.is_valid_position(-1, 5) is False
        assert grid.is_valid_position(10, 5) is False


class TestRover:
    """Test rover functionality."""

    def test_rover_initialization(self):
        rover = Rover(5, 5, North(), Grid(10, 10))
        assert rover.x == 5 and rover.y == 5

    def test_rover_move_forward_success(self):
        rover = Rover(5, 5, North(), Grid(10, 10))
        assert rover.move_forward() is True
        assert rover.y == 6

    def test_rover_blocked_by_obstacle(self):
        rover = Rover(5, 5, North(), Grid(10, 10, obstacles=[(5, 6)]))
        assert rover.move_forward() is False
        assert rover.y == 5

    def test_rover_blocked_by_boundary(self):
        rover = Rover(0, 0, South(), Grid(10, 10))
        assert rover.move_forward() is False

    def test_rover_turn_left(self):
        rover = Rover(5, 5, North(), Grid(10, 10))
        rover.turn_left()
        assert isinstance(rover.direction, West)

    def test_rover_turn_right(self):
        rover = Rover(5, 5, North(), Grid(10, 10))
        rover.turn_right()
        assert isinstance(rover.direction, East)

    def test_rover_path_tracking(self):
        rover = Rover(0, 0, North(), Grid(10, 10))
        rover.move_forward()
        rover.turn_right()
        rover.move_forward()
        assert (0, 0) in rover.path_history
        assert (0, 1) in rover.path_history
        assert (1, 1) in rover.path_history

    def test_rover_command_counting(self):
        rover = Rover(5, 5, North(), Grid(10, 10))
        rover.move_forward()
        rover.turn_left()
        rover.turn_right()
        assert rover.command_count == 3


class TestCommands:
    """Test command pattern implementation."""

    def test_move_forward_command(self):
        rover = Rover(5, 5, North(), Grid(10, 10))
        MoveForward().execute(rover)
        assert rover.y == 6

    def test_turn_left_command(self):
        rover = Rover(5, 5, North(), Grid(10, 10))
        TurnLeft().execute(rover)
        assert isinstance(rover.direction, West)

    def test_turn_right_command(self):
        rover = Rover(5, 5, North(), Grid(10, 10))
        TurnRight().execute(rover)
        assert isinstance(rover.direction, East)


class TestIntegration:
    """Integration tests."""

    def test_square_path(self):
        rover = Rover(5, 5, North(), Grid(10, 10))
        rover.move_forward()
        rover.turn_right()
        rover.move_forward()
        rover.turn_right()
        rover.move_forward()
        rover.turn_right()
        rover.move_forward()
        assert rover.x == 5 and rover.y == 5

    def test_obstacle_navigation(self):
        rover = Rover(5, 5, North(), Grid(10, 10, obstacles=[(5, 6)]))
        rover.move_forward()          # blocked
        assert rover.y == 5
        rover.turn_right()
        rover.move_forward()          # (6,5)
        rover.turn_left()
        rover.move_forward()          # (6,6)
        rover.turn_left()
        rover.move_forward()          # blocked at (5,6)
        assert rover.x == 6 and rover.y == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
