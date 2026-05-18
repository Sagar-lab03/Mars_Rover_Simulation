"""
battery.py - Battery / Energy System for Mars Rover Simulation (Phase 2)

Models the rover's power pack. The battery drains when the rover moves
(with terrain-dependent cost) and recharges via the solar panel each
"turn" the rover is stationary (or as a post-move bonus, configurable).

Key concepts
------------
- max_charge  : Maximum energy capacity (units).
- charge      : Current energy level (units).
- solar_rate  : Units recharged per stationary turn.
- is_dead     : True when charge reaches 0 — rover cannot act.
"""

from typing import Optional


class Battery:
    """
    Represents the rover's rechargeable battery.

    Attributes:
        max_charge  (int): Maximum battery capacity in units.
        charge      (int): Current charge level.
        solar_rate  (int): Units recharged when the rover rests.
        total_consumed (int): Cumulative energy consumed during the mission.
        total_recharged(int): Cumulative energy recharged during the mission.
    """

    def __init__(self, max_charge: int = 100, solar_rate: int = 5):
        """
        Initialise the battery at full charge.

        Args:
            max_charge: Maximum energy capacity (default 100 units).
            solar_rate: Energy recharged per solar-charge action (default 5).
        """
        self.max_charge: int = max_charge
        self.charge: int = max_charge
        self.solar_rate: int = solar_rate
        self.total_consumed: int = 0
        self.total_recharged: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_dead(self) -> bool:
        """Return True if the battery is fully depleted."""
        return self.charge <= 0

    @property
    def percentage(self) -> float:
        """Return the current charge as a percentage of maximum."""
        return (self.charge / self.max_charge) * 100

    @property
    def status_label(self) -> str:
        """Return a human-readable status string for display."""
        pct = self.percentage
        if pct > 60:
            return "Good"
        elif pct > 30:
            return "Low"
        else:
            return "Critical"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def consume(self, amount: int) -> bool:
        """
        Drain energy from the battery.

        Args:
            amount: Units of energy to consume (must be >= 0).

        Returns:
            True if the battery had enough charge to cover the cost,
            False if the rover runs out of energy (charge hits 0).
        """
        if amount < 0:
            raise ValueError("Battery consumption amount must be non-negative.")

        if self.charge == 0:
            return False

        self.charge = max(0, self.charge - amount)
        self.total_consumed += amount
        return self.charge > 0

    def solar_charge(self) -> int:
        """
        Recharge the battery using solar panels (one "tick").

        Returns:
            The number of units actually recharged.
        """
        if self.charge >= self.max_charge:
            return 0  # Already full

        gained = min(self.solar_rate, self.max_charge - self.charge)
        self.charge += gained
        self.total_recharged += gained
        return gained

    def get_status(self) -> dict:
        """
        Return a snapshot of battery state for telemetry / display.

        Returns:
            Dictionary with charge, max, percentage, and status label.
        """
        return {
            "charge": self.charge,
            "max_charge": self.max_charge,
            "percentage": round(self.percentage, 1),
            "status": self.status_label,
            "total_consumed": self.total_consumed,
            "total_recharged": self.total_recharged,
        }
