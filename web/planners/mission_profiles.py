"""
web/planners/mission_profiles.py
─────────────────────────────────
Mission Profile definitions for the Science Prioritization Engine.

A profile is a dict of multipliers applied on top of the baseline
_score_cell() factors.  Adding a new profile here is the only change
needed to expose a new autonomous operating mode — no scoring logic
needs to be touched.

Currently defined profiles
──────────────────────────
  balanced          Default behaviour (all weights × 1.0).
  geological        Prioritises Rock terrain and biome boundaries.
  ice_detection     Maximises Ice terrain and cold temperature signals.
  energy_saving     Multiplies travel-cost penalty to favour nearby cells.
  hazard_mapping    Rewards dust and slope-heavy areas for risk cataloguing.
"""

from __future__ import annotations
from typing import TypedDict


class ProfileWeights(TypedDict):
    """Multipliers applied to each scoring factor."""
    rock:          float   # terrain_base multiplier for rock cells
    ice:           float   # terrain_base multiplier for ice cells
    sand:          float   # terrain_base multiplier for sand cells
    plain:         float   # terrain_base multiplier for plain cells
    boundary:      float   # boundary-zone bonus multiplier
    uv:            float   # UV anomaly bonus multiplier
    temperature:   float   # extreme-temp bonus multiplier
    waypoint:      float   # mission waypoint bonus multiplier
    dust_penalty:  float   # dust storm penalty multiplier
    cost_weight:   float   # efficiency blend weight (replaces 0.4 in score formula)


# ── Profile registry ──────────────────────────────────────────────────────────

PROFILES: dict[str, ProfileWeights] = {

    "balanced": ProfileWeights(
        rock=1.0, ice=1.0, sand=1.0, plain=1.0,
        boundary=1.0, uv=1.0, temperature=1.0, waypoint=1.0,
        dust_penalty=1.0, cost_weight=0.4,
    ),

    "geological": ProfileWeights(
        rock=1.6, ice=0.8, sand=0.9, plain=0.7,
        boundary=1.5, uv=0.8, temperature=0.5, waypoint=1.0,
        dust_penalty=0.8, cost_weight=0.35,
    ),

    "ice_detection": ProfileWeights(
        rock=0.7, ice=1.8, sand=0.6, plain=0.5,
        boundary=1.1, uv=0.6, temperature=1.8, waypoint=1.0,
        dust_penalty=1.2, cost_weight=0.3,
    ),

    "energy_saving": ProfileWeights(
        rock=1.0, ice=1.0, sand=1.0, plain=1.0,
        boundary=1.0, uv=1.0, temperature=1.0, waypoint=1.0,
        dust_penalty=1.5, cost_weight=0.7,   # high cost_weight = strong efficiency bias
    ),

    "hazard_mapping": ProfileWeights(
        rock=1.1, ice=0.8, sand=1.2, plain=1.0,
        boundary=0.9, uv=1.3, temperature=0.7, waypoint=0.5,
        dust_penalty=0.0,       # dust zones are the TARGET, so no penalty
        cost_weight=0.4,
    ),
}

# Human-readable labels for the UI dropdown
PROFILE_LABELS: dict[str, str] = {
    "balanced":      "Balanced Exploration",
    "geological":    "Geological Survey",
    "ice_detection": "Ice Detection",
    "energy_saving": "Energy Conservation",
    "hazard_mapping":"Hazard Mapping",
}


def get_profile(name: str) -> ProfileWeights:
    """Return the named profile, falling back to 'balanced' if unknown."""
    return PROFILES.get(name, PROFILES["balanced"])


def list_profiles() -> list[dict]:
    """Return a list of {id, label} dicts for UI consumption."""
    return [{"id": pid, "label": PROFILE_LABELS[pid]} for pid in PROFILES]
