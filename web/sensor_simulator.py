"""
web/sensor_simulator.py
────────────────────────
Environmental Sensor Simulator — extracted from app.py so that
web/planners/ modules can import it without circular dependencies.

Mirrors real Curiosity / Perseverance sensor systems (REMS).
"""

import random


class SensorSimulator:
    """
    Simulates environmental sensor readings for the rover's current position.
    Mirrors real Curiosity / Perseverance sensor systems (REMS).
    """

    # Surface temperature base values by terrain (°C)
    _TEMP_BASE = {"plain": -20, "sand": 15, "rock": -5, "ice": -80}

    # Slope base values by terrain (degrees)
    _SLOPE_BASE = {"plain": 2.0, "sand": 5.0, "rock": 18.0, "ice": 8.0}

    @classmethod
    def surface_temp(cls, terrain: str) -> float:
        """Terrain-dependent surface temperature with ±3 °C noise."""
        base = cls._TEMP_BASE.get(terrain, -20)
        return round(base + random.uniform(-3, 3), 1)

    @classmethod
    def dust_opacity(cls, x: int, y: int, grid_w: int, grid_h: int) -> float:
        """
        Atmospheric dust opacity (τ).  Higher toward grid edges
        — simulates dust storm zones away from the landing site.
        τ range: 0.1 (crystal clear) → 3.0 (full dust storm).
        """
        cx, cy = grid_w / 2.0, grid_h / 2.0
        dx     = abs(x - cx) / max(cx, 1)
        dy     = abs(y - cy) / max(cy, 1)
        edge   = max(dx, dy)          # 0 at centre, 1 at corner
        tau    = 0.3 + edge * 1.8 + random.uniform(-0.1, 0.1)
        return round(max(0.1, min(tau, 3.0)), 2)

    @classmethod
    def uv_index(cls, y: int, grid_h: int) -> float:
        """
        UV radiation index.  Higher ground (larger Y) = thinner
        atmosphere = stronger UV.  Range: 0.5 – 5.0 UVI.
        """
        uv = 1.0 + (y / max(grid_h - 1, 1)) * 3.5 + random.uniform(-0.2, 0.2)
        return round(max(0.5, min(uv, 5.0)), 1)

    @classmethod
    def slope_deg(cls, terrain: str) -> float:
        """Estimated surface slope in degrees, ±1.5° noise."""
        base = cls._SLOPE_BASE.get(terrain, 2.0)
        return round(max(0.0, base + random.uniform(-1.5, 1.5)), 1)

    @classmethod
    def get_all(cls, x: int, y: int, terrain: str,
                grid_w: int, grid_h: int) -> dict:
        """Return a complete sensor snapshot for the current rover position."""
        tau = cls.dust_opacity(x, y, grid_w, grid_h)
        # Solar reduction: 0 % at τ ≤ 0.5, linear up to 50 % at τ = 2.5
        solar_reduction_pct = round(max(0.0, min(50.0, (tau - 0.5) * 25.0)), 1)
        return {
            "surface_temp":        cls.surface_temp(terrain),
            "dust_opacity":        tau,
            "uv_index":            cls.uv_index(y, grid_h),
            "slope_deg":           cls.slope_deg(terrain),
            "solar_reduction_pct": solar_reduction_pct,
            "terrain":             terrain,
        }
