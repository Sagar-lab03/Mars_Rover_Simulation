# 🚀 Mars Rover Simulation — Phase 2

## Overview

Phase 2 builds on the clean OOP foundation from Phase 1 and adds four realistic simulation layers that make the project feel genuinely space-mission-worthy:

| Feature | What it adds |
|---|---|
| **Terrain System** | 4 surface types — each costs the battery differently |
| **Battery / Energy** | Finite energy, terrain-aware drain, solar recharging |
| **Mission Waypoints** | Named science targets the rover must visit |
| **A\* Pathfinding** | Automatic shortest-path navigation avoiding obstacles |

---

## Project Structure

```
Mars_Rover_Exercise/
│
├── rover.py                  # Phase 1 core (unchanged)
├── config.yaml               # Shared config (Phase 1 + 2 settings)
├── requirements.txt
│
├── phase2/                   # All Phase 2 source modules
│   ├── __init__.py
│   ├── main.py               # Phase 2 entry point
│   ├── terrain.py            # Terrain types & TerrainMap
│   ├── battery.py            # Battery / energy system
│   ├── mission.py            # Mission objectives & waypoints
│   └── pathfinder.py         # A* search algorithm
│
├── tests/                    # All unit tests
│   ├── __init__.py
│   ├── test_phase1.py        # 24 Phase 1 tests
│   └── test_phase2.py        # 38 Phase 2 tests
│
├── demo/                     # Automated demo scripts
│   ├── demo_phase1.py
│   └── demo_phase2.py
│
├── docs/                     # Documentation
│   ├── README_Phase1.md
│   └── README_Phase2.md      # (this file)
│
└── telemetry/                # Auto-generated mission JSON logs
```

---

## Phase 2 Features in Detail

### 1. Terrain System (`phase2/terrain.py`)

Four Martian surface types, each with different battery costs:

| Terrain | Symbol | Battery Cost | Description |
|---------|--------|-------------|-------------|
| **Plain** | `.` | 5 units | Standard flat ground |
| **Sand** | `~` | 10 units | Loose sand, harder to drive |
| **Rock** | `#` | 15 units | Rocky patches, max effort |
| **Ice** | `*` | 3 units | Icy, surprisingly efficient |

Terrain patches are defined in `config.yaml` — no code changes needed.

### 2. Battery System (`phase2/battery.py`)

The rover has a finite energy supply that drains as it moves:

- **`max_charge`**: Total energy capacity (default 100 units)
- **`solar_rate`**: Units recharged per `S` (solar) command (default 5)
- Battery drain = terrain cost of the *destination* cell
- Status labels: **Good** (>60%) | **Low** (>30%) | **Critical** (≤30%)
- Rover **cannot move** when battery is at 0

### 3. Mission Objectives (`phase2/mission.py`)

Named waypoints (science targets) the rover must visit:

- Defined in `config.yaml` under `mission.waypoints`
- Each waypoint shows on the grid as `W` (pending) or `*` (reached)
- Mission is complete when **all** waypoints are reached
- Progress is tracked in telemetry JSON

### 4. A\* Pathfinder (`phase2/pathfinder.py`)

Automatically navigates to any reachable cell:

- Uses **A\* search** with **Manhattan distance** heuristic
- Respects all obstacles and grid boundaries
- Converts the found path into `M / L / R` rover commands
- Triggered with the `G x,y` command (e.g. `G 5,7`)

**Why A\*?**
> A\* is the algorithm behind Google Maps, game AI, and robotics navigation.
> It's perfect for demonstrating algorithmic thinking with an Astronomy twist!

---

## Getting Started

### Installation

```bash
pip install -r requirements.txt
```

### Run Phase 2 (Interactive)

```bash
python phase2/main.py
```

### Run Automated Demo

```bash
python demo/demo_phase2.py
```

### Run All Tests

```bash
# All tests (Phase 1 + Phase 2)
pytest tests/ -v

# Phase 2 only
pytest tests/test_phase2.py -v
```

---

## Commands

| Command | Description |
|---------|-------------|
| `M` | Move forward one step (drains battery by terrain cost) |
| `L` | Turn left 90° |
| `R` | Turn right 90° |
| `G x,y` | Auto-navigate to (x,y) using A\* — e.g. `G 5,7` |
| `S` | Solar charge — rest 1 turn, recharge battery |
| `Q` | Quit mission and show summary |

---

## Configuration (`config.yaml`)

```yaml
battery:
  max_charge: 100    # Total energy units
  solar_rate: 5      # Recharged per solar action

terrain:
  - type: sand       # plain | sand | rock | ice
    cells:
      - [1, 1]
      - [2, 1]

mission:
  waypoints:
    - name: "Sample Site Alpha"
      x: 5
      y: 7
```

---

## Test Results

```
tests/test_phase1.py  — 24 tests  ✅
tests/test_phase2.py  — 38 tests  ✅
Total: 62 tests, all passing
```

---

## Design Patterns Used

| Pattern | Where |
|---------|-------|
| **Strategy** | Direction classes (North/East/South/West) |
| **Command** | MoveForward / TurnLeft / TurnRight |
| **Template Method** | RoverV2 extends Rover (move_forward override) |
| **Factory / Class Method** | `TerrainMap.from_config()`, `Mission.from_config()` |

---

## Key Learnings

- **A\* Algorithm**: Informed search combining cost + heuristic — the backbone of real navigation systems
- **Energy Modelling**: How terrain affects power consumption in real rover missions (Perseverance has a similar system!)
- **Inheritance in OOP**: `RoverV2` cleanly extends `Rover` without breaking Phase 1
- **Data-driven design**: Terrain, waypoints, and battery all configured via YAML — no hardcoding

---

## Astronomy Connection

> NASA's **Perseverance** rover uses similar concepts:
> - **Battery monitoring** — Perseverance has a Multi-Mission Radioisotope Thermoelectric Generator (MMRTG)
> - **Terrain-aware navigation** — AEGIS AI selects science targets
> - **Waypoint-based planning** — Mission controllers uplink daily drive plans
> - **Pathfinding** — AutoNav uses stereo vision + graph search to avoid hazards

---

## What's Next — Phase 3 Preview

- 🌐 **Web-based visualisation** (HTML / JS / Canvas)
- 📊 **Mission analytics dashboard** from telemetry data
- 🛰️ **Multi-rover coordination** (two rovers, collision avoidance)

---

*Phase 2 — Advanced Features Complete ✅*
