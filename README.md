# 🚀 Mars Rover Mission Control

A progressive Mars Rover simulation built across three phases — from clean OOP terminal simulation to a full interactive web-based mission control dashboard. Built for learning, portfolio visibility, and showcasing the intersection of **Astronomy + Software Engineering**.

![Mars Rover](mars_rover.png)

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-lightgrey.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)

---

## 🌐 Web Mission Control (Phase 3)

> Control the rover directly from your browser — terrain-aware, battery-powered, A\* navigated.

![Mars Rover Web UI](web_ui_preview_dashboard_2.png)
<!-- ![Mars Rover Web UI](web_ui_preview_mission_analytics.png) -->

---

## 📋 Table of Contents

1. [Project Evolution](#project-evolution)
2. [Features](#features)
3. [Project Structure](#project-structure)
4. [Getting Started](#getting-started)
5. [Usage](#usage)
6. [Architecture](#architecture)
7. [Configuration](#configuration)
8. [Testing](#testing)
9. [Design Patterns](#design-patterns)
10. [Astronomy Connection](#astronomy-connection)

---

## 🧬 Project Evolution

This project was built in three deliberate phases, each adding a meaningful layer on top of the last:

| Phase | What was built | Key concepts |
|---|---|---|
| **Phase 1** | OOP core, Rich terminal UI, YAML config, telemetry | Strategy Pattern, Command Pattern, ABCs |
| **Phase 2** | A\* pathfinding, battery system, terrain types, waypoints | Graph search, energy modelling, inheritance |
| **Phase 3** | Flask REST API, interactive browser UI, analytics dashboard, batch commands | Client-server, reactive rendering, persistent telemetry |

---

## ✨ Features

### Phase 1 — Core Simulation
- **Grid-based navigation** with obstacle detection and boundary validation
- **Rich terminal UI** — color-coded grid, path trail, and live status tables
- **YAML configuration** — customize grid, obstacles, and rover start without touching code
- **Telemetry logging** — every mission exported to JSON automatically
- **24 unit tests** with pytest

### Phase 2 — Advanced Simulation
- **A\* Pathfinding** — shortest obstacle-free path using Manhattan distance heuristic
- **Battery system** — energy drains on every move based on terrain type, solar recharge available
- **Terrain types** — Plain, Sand, Rock, Ice each with distinct battery costs
- **Mission waypoints** — named science targets tracked and marked on the grid
- **38 unit tests** covering all Phase 2 systems

### Phase 3 — Web Visualization, Analytics & Sensor Systems
- **Interactive browser UI** — full mission control dashboard at `http://localhost:5000`
- **Live CSS grid** — terrain colors, glowing rover arrow, obstacles, waypoint beacons, path trail
- **Pulsing waypoint beacons** — animated landing zone rings; glowing "BASE ✦" marker when reached
- **Animated battery bar** — color shifts green → yellow → red in real time
- **D-pad + keyboard controls** — W/A/D/E for Move/Left/Right/Solar
- **Click-to-navigate** — click any grid cell to auto A\* navigate there
- **Batch command runner** — type commands or upload a `.txt` file; step-through animation mode
- **Analytics dashboard** — Chart.js battery timeline, command distribution, terrain coverage, path heatmap
- **Mission Replay** — load any saved mission and watch it animate step-by-step with full playback controls
- **Environmental Sensor Dashboard** — live REMS-style gauges: surface temperature, dust opacity (τ), UV index, slope
- **Dust-aware solar charging** — high atmospheric τ reduces solar yield by up to 50%
- **Persistent telemetry** — every web session auto-saved to `telemetry/` as a JSON file with sensor snapshots
- **Navigation between pages** — Mission Control ↔ Analytics via top nav

### Phase 3 Extensions — Mission Intelligence
- **Mission Feasibility Analysis** — every navigation and batch sequence passes through a pre-flight check before executing:
  - `◆ PLAN` button in the batch panel opens a full mission report modal
  - Clicking any grid cell or coordinate triggers the analysis before moving
  - Report includes: path length, energy cost, projected battery (colour bar), terrain breakdown (per-biome bars), atmospheric dust exposure, science targets on route
  - Risk scoring engine classifies routes as **LOW / MEDIUM / HIGH** with a final verdict: `SAFE TO EXECUTE`, `EXECUTE WITH CAUTION`, or `NOT RECOMMENDED`
  - Planned path previewed on the grid as a dashed cyan overlay while the modal is open
  - `EXECUTE MISSION` / `EXECUTE WITH CAUTION` / `ABORT PLAN` action buttons in modal footer
- **20 × 20 exploration grid** — map expanded from 10×10 to 20×20 (400 cells) with:
  - Five geographic terrain biomes: Sand Basin (SW), Rock Formation (NE), Ice Field (NW), Rock Ridge (SE), Sand Ridge (mid-east)
  - 20 strategically placed obstacle clusters forming natural chokepoints and corridors
  - Six mission waypoints distributed across all map quadrants
- **Science Survey Engine** — autonomous science target prioritization panel in the sidebar:
  - `◆ SCAN TARGETS` button calls `/api/recommend` to rank every unvisited cell by scientific value
  - Each cell scored on: terrain geological interest, terrain boundary-zone adjacency (multi-biome contact zones), UV anomaly, extreme temperature signature, designated waypoint bonus, dust storm penalty
  - Returns `science_value`, `travel_cost`, `efficiency` (science/cost ratio), and a `reasons[]` array explaining each score contribution
  - Top 3 targets rendered as ranked cards ①②③ in the sidebar with terrain tag, reason pills, and metrics
  - Corresponding grid cells highlighted with a magenta outline and rank badge overlay
  - Clicking any target card opens the **Mission Feasibility Modal** for that route — all missions still pass through the analyze → approve → execute flow
  - **Mission Science Score** accumulates in the panel header as the rover visits high-value cells
  - Rankings auto-refresh after each mission execution

### Phase 4 — Autonomous Agent & Mission Profiles
- **Autonomous Exploration Loop** — `⬡ AUTO EXPLORE` panel drives the rover without human input:
  - Each step: scan all unvisited cells → rank by efficiency → feasibility-check top candidates → execute best approved route → repeat
  - **Speed control** — Fast (800 ms) / Normal (1600 ms) / Slow (2800 ms) inter-step delay
  - Live **decision log** — colour-coded reasoning lines (✓ green · ⚠ amber · ✗ red · 🎯🔍🔋 cyan) scroll in real time
  - **Mission Science Score** accumulates in the panel header across all visited cells
  - Stops automatically when battery < 20u, no reachable candidates remain, or all routes are NOT_RECOMMENDED
  - Operator can stop at any time; score and grid state are preserved
- **Architecture refactor — `web/planners/` package** — planning logic extracted from `app.py` into independently testable modules:
  - `sensor_simulator.py` — REMS sensor simulation (extracted from `app.py` to eliminate circular imports)
  - `planners/science_engine.py` — `score_cell()`, `get_recommendations()`, `compute_mission_score()`
  - `planners/auto_explorer.py` — single-step autonomous exploration agent (`run_step()`)
  - `planners/mission_profiles.py` — profile registry and weight tables
  - Flask routes in `app.py` now only parse requests and call these modules
- **Mission Profiles** — five autonomous operating modes selectable from a `◆ MISSION PROFILE` dropdown in the Science Survey panel:

  | Profile | Bias | Accent colour |
  |---|---|---|
  | Balanced Exploration | All scoring factors equal | Cyan |
  | Geological Survey | Rock ×1.6, boundary zones ×1.5 | Orange |
  | Ice Detection | Ice ×1.8, extreme cold ×1.8 | Sky blue |
  | Energy Conservation | Travel-cost weight ×0.7 (favours nearby cells) | Green |
  | Hazard Mapping | Dust zones become targets (penalty removed) | Red |

  - Changing profile instantly re-runs an open scan with the new weights
  - The **Auto Explore** header badge shows the active profile name
  - All five profiles pass through the same `score_cell()` function — only the multiplier table differs, making future ML integration a drop-in replacement of one function

---

## 📁 Project Structure

```
Mars_Rover_Exercise/
│
├── rover.py                  # Phase 1 core (OOP, terminal, telemetry)
├── config.yaml               # Shared mission configuration
├── requirements.txt          # Python dependencies
│
├── phase2/                   # Phase 2 — Advanced simulation modules
│   ├── main.py               # Phase 2 terminal entry point
│   ├── pathfinder.py         # A* search algorithm
│   ├── battery.py            # Energy / battery system
│   ├── terrain.py            # Terrain types and cost map
│   └── mission.py            # Mission objectives and waypoints
│
├── web/                      # Phase 3/4 — Web visualization & planning engine
│   ├── app.py                # Flask server + REST API routes (thin wrappers only)
│   ├── sensor_simulator.py   # REMS-style environmental sensor simulation
│   ├── planners/             # Planning logic package
│   │   ├── science_engine.py # Cell scoring, recommendations, mission score
│   │   ├── auto_explorer.py  # Autonomous exploration step agent
│   │   └── mission_profiles.py # Profile definitions and scoring weight tables
│   ├── templates/
│   │   ├── index.html        # Mission Control single-page app
│   │   └── analytics.html    # Analytics dashboard page
│   └── static/
│       ├── style.css         # Dark space theme + all panel styles
│       ├── app.js            # Grid renderer + API client + survey/explore logic
│       ├── analytics.css     # Analytics dashboard styles
│       └── analytics.js      # Chart.js charts + heatmap renderer
│
├── tests/                    # All unit tests
│   ├── test_phase1.py        # 24 Phase 1 tests
│   └── test_phase2.py        # 38 Phase 2 tests
│
├── demo/                     # Automated demo scripts
│   ├── demo_phase1.py
│   └── demo_phase2.py
│
├── docs/                     # Per-phase documentation
│   ├── README_Phase1.md
│   └── README_Phase2.md
│
└── telemetry/                # Auto-generated mission JSON logs (all sessions)
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- pip

> **Note for Windows users:** Avoid using the Microsoft Store Python. Use python.org or a virtual environment to ensure packages install correctly.

### Installation

```bash
git clone https://github.com/your_username/Mars_Rover_Exercise.git
cd Mars_Rover_Exercise
pip install -r requirements.txt
```

**Dependencies:**
- `rich` — terminal UI (Phase 1 & 2)
- `pyyaml` — YAML config loading
- `flask` — web server (Phase 3)
- `pytest` — test framework

---

## 🎮 Usage

### Phase 3 — Web Mission Control *(recommended)*

```bash
python web/app.py
```

Open **http://localhost:5000** in your browser.

#### Mission Control Controls

| Control | Action |
|---|---|
| Click any grid cell | A\* auto-navigate to that cell |
| `W` / FWD button | Move forward |
| `A` / `D` buttons | Turn left / right |
| `E` / ☀ button | Solar charge (restore battery) |
| Type X, Y + **A\* GO** | Navigate to specific coordinates |
| **RESET MISSION** | Restart mission from `config.yaml` |

#### Batch Command Panel

Open the **BATCH COMMANDS** panel in the sidebar to run sequences of commands.

| Input mode | How to use |
|---|---|
| Text input | Type commands directly: `M M R M L G 5,7 S` |
| File upload | Drag & drop a `.txt` file or click to browse |
| Template | Click **Download sample template** for the correct format |

**Command format:**

| Command | Description |
|---|---|
| `M` | Move forward (uses battery) |
| `L` | Turn left 90° |
| `R` | Turn right 90° |
| `S` | Solar charge |
| `G x,y` | A\* navigate to coordinates e.g. `G 5,7` |
| `#` | Comment — ignored |

Use **STEP MODE** to animate through each command with a configurable speed slider.

#### Analytics Dashboard

Open **http://localhost:5000/analytics** or click the **Analytics** nav link.

- Select any saved mission from the dropdown
- View battery timeline, command mix, terrain coverage, and path heatmap
- Compare all missions in the history table
- Click **▶ REPLAY** (or the ▶ button on any table row) to open the Mission Replay panel

> Telemetry is saved automatically after every command, navigation, and batch run. Clicking **Refresh** fetches the latest records including your current session.

#### Mission Replay

Select any mission → click **▶ REPLAY** in the selector bar (or the ▶ button in any table row).

| Control | Action |
|---|---|
| `⏮` | Jump to mission start |
| `◀` | Step back one frame |
| `▶ / ⏸` | Play / Pause auto-playback |
| `▶` | Step forward one frame |
| `⏭` | Jump to mission end |
| Scrubber bar | Drag to any frame instantly |
| Speed slider | 100 ms (fast) → 2000 ms (slow) |

The replay grid shows terrain, obstacles, rover arrow, path trail building progressively, and waypoints lighting up the moment they are reached. The live telemetry sidebar shows battery, position, direction, and waypoint status for each frame.

#### Environmental Sensor Dashboard

The **ENVIRONMENTAL SENSORS** panel appears in the Mission Control sidebar between the battery panel and waypoints. Click the header to collapse or expand it.

| Sensor | What it measures | Real parallel |
|---|---|---|
| 🌡 **Surface Temp** | Terrain-based temperature (−80°C ice → +15°C sand) ± 3°C noise | Curiosity REMS thermometer |
| 🌪 **Dust Opacity (τ)** | Atmospheric dust — higher toward grid edges (dust storm zones) | Daily τ readings from Mars weather reports |
| ☢ **UV Radiation** | UV index increases with Y position (higher ground = thinner atmosphere) | Curiosity REMS UV sensor |
| 📐 **Surface Slope** | Terrain-based slope estimate (Rock ~18°, Plain ~2°) ± 1.5° noise | IMU tilt sensor on Perseverance |

**Dust effect on solar charging:** When τ ≥ 0.5, the `S` (Solar Charge) command yields less energy — linearly reduced up to **−50%** at τ = 2.5. The mission log shows exactly how much dust reduced the yield (e.g. `Solar charge (τ=1.8, -32% dust) — +3 units`).

---

### Phase 2 — Terminal Simulation

```bash
python phase2/main.py
```

| Command | Description |
|---|---|
| `M` | Move forward (drains battery by terrain cost) |
| `L` / `R` | Turn left / right |
| `S` | Solar charge |
| `G x,y` | A\* auto-navigate to (x, y) |
| `Q` | Quit and show mission summary |

---

### Phase 1 — Terminal Simulation (original)

```bash
python rover.py
```

---

### Automated Demos

```bash
python demo/demo_phase1.py   # Phase 1 scripted walkthrough
python demo/demo_phase2.py   # Full Phase 2 demo (A*, terrain, battery, waypoints)
```

---

## 🏗️ Architecture

### System Overview

```
Browser (HTML + CSS + JS)
     │  fetch() / REST API calls
     ▼
Flask Server  (web/app.py)
     │  ├─ Serves pages (/ and /analytics)
     │  ├─ REST API endpoints
     │  └─ Writes telemetry/*.json after every action
     │
     │  Python calls
     ▼
Phase 2 Engine  (phase2/)
     │  inherits from
     ▼
Phase 1 Core  (rover.py)
```

### Web API Contract

#### Mission Control

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Serve the Mission Control page |
| `/api/state` | GET | Full rover state as JSON |
| `/api/command` | POST | Execute `M` / `L` / `R` / `S` |
| `/api/navigate` | POST | A\* navigate to `{x, y}` |
| `/api/reset` | POST | Save current session, reset mission |

#### Batch

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/batch/execute` | POST | Run a list of commands, return all step states |
| `/api/batch/template` | GET | Download sample `.txt` command file |

#### Analytics

| Endpoint | Method | Purpose |
|---|---|---|
| `/analytics` | GET | Serve the Analytics dashboard |
| `/api/analytics/missions` | GET | List all telemetry files with metadata |
| `/api/analytics/mission/<file>` | GET | Full breakdown for one mission |

#### Mission Intelligence

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/plan` | POST | Mission Feasibility Analysis — dry-run route assessment (never mutates state) |
| `/api/recommend` | GET | Science Prioritization Engine — ranked list of top unvisited science targets. Query: `n`, `profile` |
| `/api/auto_explore/step` | POST | Autonomous Exploration Agent — execute one step. Query: `profile` |
| `/api/profiles` | GET | List all available mission profiles for the UI dropdown |

### Telemetry Persistence

Every web session generates one `telemetry/mission_YYYYMMDD_HHMMSS.json` file that follows the exact same schema as the terminal-generated files. Sensor readings are embedded in every event:

```json
{
  "mission_name": "Mars Exploration Mission",
  "start_time":   "2026-05-28T19:00:00",
  "end_time":     "2026-05-28T19:15:43",
  "final_status": { "position": {}, "direction": "", "battery": {} },
  "path_history": [[0,0], [0,1], "..."],
  "events": [
    { "timestamp": "...", "type": "mission_start", "data": { "battery": {}, "position": {} } },
    { "timestamp": "...", "type": "command", "data": {
        "command": "M",
        "rover_status": {},
        "mission_status": {},
        "sensors": {
          "surface_temp": -22.4,
          "dust_opacity": 0.87,
          "uv_index": 2.1,
          "slope_deg": 3.2,
          "solar_reduction_pct": 9.3
        }
    }},
    { "timestamp": "...", "type": "solar_charge", "data": { "gained": 3, "battery": {}, "sensors": {} } }
  ]
}
```

The file is **overwritten after every action** so it always reflects the latest state. On reset, the old file is finalized and a new session begins.

### Core Classes

```
Direction (ABC)
├── North / East / South / West          ← Strategy Pattern

Command (ABC)
├── MoveForward / TurnLeft / TurnRight   ← Command Pattern

Grid          → grid dimensions + obstacle tracking
Rover         → position, direction, path history
 └── RoverV2  → + battery + terrain-aware movement (Template Method)

Battery       → charge level, drain, dust-aware solar recharge
TerrainMap    → per-cell terrain type and battery cost mapping
Mission       → waypoint list + completion tracking
Pathfinder    → A* search with Manhattan heuristic (static methods)
SensorSimulator → REMS-style environmental readings (temperature,
                  dust opacity, UV index, slope) per grid position
```

---

## ⚙️ Configuration

All mission parameters live in `config.yaml` — no code changes needed:

```yaml
grid:
  width: 20
  height: 20
  obstacles:          # 20 strategic chokepoints
    - [9,  10]
    - [10, 10]
    - [11, 11]
    # ... (see config.yaml for full list)

rover:
  start_x: 0
  start_y: 0
  start_direction: "N"   # N | S | E | W

battery:
  max_charge: 100
  solar_rate: 5          # units restored per solar charge action

terrain:               # Five geographic biome regions
  - type: sand         # Sand Basin — southwest lowland dunes
    cells:
      - [1, 1]
      - [2, 1]
      # ... (26 cells total)
  - type: rock         # Rock Formation — northeast highland plateau
    cells:
      - [13, 13]
      # ... (20 cells total)
  - type: ice          # Ice Field — northwest polar permafrost
    cells:
      - [0, 13]
      # ... (25 cells total)

mission:
  name: "Mars Exploration Mission"
  enable_telemetry: true
  telemetry_folder: "telemetry"
  waypoints:           # Six targets across all map quadrants
    - name: "Sample Site Alpha"
      x: 5
      y: 8
    - name: "Olympus Outpost"
      x: 10
      y: 15
    - name: "Dust Basin Delta"
      x: 17
      y: 9
    - name: "Polar Ridge Epsilon"
      x: 3
      y: 18
    - name: "Iron Peak Zeta"
      x: 15
      y: 5
    - name: "High Ground Sigma"
      x: 18
      y: 19
```

### Terrain Battery Costs

| Terrain | Cost per move |
|---|---|
| Plain | 5 units |
| Sand | 10 units |
| Rock | 15 units |
| Ice | 3 units |

---

## 🧪 Testing

```bash
# All 62 tests (Phase 1 + Phase 2)
pytest tests/ -v

# Phase 1 only (24 tests)
pytest tests/test_phase1.py -v

# Phase 2 only (38 tests)
pytest tests/test_phase2.py -v
```

**Coverage:** Directions, Grid, Rover, Commands, Battery, Terrain, Mission, A\* Pathfinder, RoverV2 integration.

---

## 🎨 Design Patterns

| Pattern | Where used |
|---|---|
| **Strategy** | `Direction` classes — each encapsulates movement + rotation logic |
| **Command** | `MoveForward` / `TurnLeft` / `TurnRight` — rover actions as objects |
| **Template Method** | `RoverV2.move_forward()` overrides `Rover.move_forward()` to add battery drain |
| **Factory / Class Method** | `TerrainMap.from_config()`, `Mission.from_config()` — construct from YAML |

---

## 🌌 Astronomy Connection

> This simulation mirrors real Mars rover mission concepts:
>
> - **Battery management** — Perseverance uses an MMRTG power system with finite energy budgets per sol
> - **Terrain-aware navigation** — NASA's AEGIS AI selects paths by terrain difficulty and science value
> - **Waypoints** — Mission controllers uplink daily drive plans with named science target coordinates
> - **A\* pathfinding** — AutoNav uses stereo-vision + graph search to autonomously avoid hazards
> - **Telemetry** — Every rover sends continuous status packets; ground teams replay sessions for analysis
> - **REMS sensors** — Curiosity's weather station measures temperature, UV, and atmospheric dust (τ) daily
> - **Dust storms** — High τ events reduce solar panel efficiency; NASA plans conservative power budgets around them
> - **Mission replay** — JPL engineers replay telemetry recordings to diagnose rover behaviour and plan corrections
- **Science contact zones** — NASA's science teams prioritize cells at the boundary between two geological units (e.g. basalt–sediment contacts); the Science Survey Engine mirrors this by awarding boundary-zone bonuses
- **Autonomous science targeting** — Perseverance's AEGIS system autonomously ranks and photographs science targets; the `science_value / travel_cost` efficiency ratio in `/api/recommend` mirrors this reward-to-effort prioritization
- **Mission Feasibility Analysis** — before every drive, JPL engineers run trajectory simulations checking energy budget, terrain risk, and dust exposure; the `/api/plan` dry-run endpoint mirrors this pre-flight assessment workflow

---

## 📝 License

MIT License — see [choosealicense.com](https://choosealicense.com/licenses/mit/) for details.

---

**Built with passion for Astronomy + Engineering 🚀🔴**
