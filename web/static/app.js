/**
 * app.js — Mars Rover Mission Control
 *
 * Responsibilities:
 *  1. Fetch state from Flask API on load
 *  2. Render the CSS grid (terrain, rover, obstacles, waypoints, path)
 *  3. Send commands (M/L/R/S) and A* navigate requests
 *  4. Update all sidebar panels reactively from state JSON
 *  5. Handle keyboard shortcuts (W/A/D/E)
 */

"use strict";

// ── Constants ──────────────────────────────────────────────────────────────

const API = {
  STATE:    "/api/state",
  COMMAND:  "/api/command",
  NAVIGATE: "/api/navigate",
  RESET:    "/api/reset",
};

const DIR_ARROWS = {
  North: "&#9650;",   // ▲
  East:  "&#9658;",   // ▶
  South: "&#9660;",   // ▼
  West:  "&#9668;",   // ◀
};

const TERRAIN_CLASS = {
  sand:  "terrain-sand",
  rock:  "terrain-rock",
  ice:   "terrain-ice",
  plain: "",
};

const TERRAIN_LABEL = {
  sand:  "Sand",
  rock:  "Rock",
  ice:   "Ice",
  plain: "Plain",
};

// ── State ─────────────────────────────────────────────────────────────────

let busy = false;   // prevent double-clicks during fetch

// ── Helpers ───────────────────────────────────────────────────────────────

/** Generic fetch wrapper — returns parsed JSON or null on error. */
async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json();
    if (!res.ok && data.error) {
      showError(data.error);
    }
    return data;
  } catch (err) {
    showError("Connection error — is the server running?");
    return null;
  }
}

function setStatus(connected) {
  const dot   = document.getElementById("status-dot");
  const label = document.getElementById("status-label");
  if (connected) {
    dot.style.background  = "var(--rover)";
    dot.style.boxShadow   = "0 0 8px var(--rover)";
    label.textContent     = "ONLINE";
  } else {
    dot.style.background  = "var(--obstacle)";
    dot.style.boxShadow   = "0 0 8px var(--obstacle)";
    label.textContent     = "OFFLINE";
  }
}

function lockUI(lock) {
  busy = lock;
  ["btn-M","btn-L","btn-R","btn-S","btn-nav","btn-reset"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = lock;
  });
}

/** Show an error toast for 3 seconds. */
function showError(msg) {
  const toast = document.getElementById("error-toast");
  toast.textContent = msg;
  toast.classList.remove("hidden");
  clearTimeout(showError._timer);
  showError._timer = setTimeout(() => toast.classList.add("hidden"), 3500);
}

// ── Grid renderer ─────────────────────────────────────────────────────────

/**
 * Build (or rebuild) the entire CSS grid from scratch.
 * Called once on load and whenever grid dimensions could change (reset).
 */
function buildGrid(state) {
  const container = document.getElementById("rover-grid");
  const { width, height } = state.grid;

  container.style.gridTemplateColumns = `repeat(${width}, 46px)`;
  container.innerHTML = "";

  for (let y = height - 1; y >= 0; y--) {
    for (let x = 0; x < width; x++) {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.id = `cell-${x}-${y}`;
      cell.setAttribute("data-x", x);
      cell.setAttribute("data-y", y);
      cell.setAttribute("role", "gridcell");

      // Coordinate label
      const coord = document.createElement("span");
      coord.className = "coord";
      coord.textContent = `${x},${y}`;
      cell.appendChild(coord);

      // Click to navigate
      cell.addEventListener("click", () => {
        document.getElementById("nav-x").value = x;
        document.getElementById("nav-y").value = y;
        navigate();
      });

      container.appendChild(cell);
    }
  }
}

/**
 * Update every cell's appearance without rebuilding the DOM.
 */
function updateGrid(state) {
  const { width, height, obstacles } = state.grid;
  const obstacleSet = new Set(obstacles.map(([ox, oy]) => `${ox},${oy}`));
  const pathSet     = new Set(state.rover.path_history.map(([px, py]) => `${px},${py}`));
  const terrain     = state.terrain;   // "x,y" -> type string

  // Waypoint lookup — server sends { position: [x, y], name, reached }
  const waypointMap = {};
  for (const wp of state.mission.waypoints) {
    const [wx, wy] = wp.position;
    waypointMap[`${wx},${wy}`] = wp;
  }

  for (let y = height - 1; y >= 0; y--) {
    for (let x = 0; x < width; x++) {
      const key  = `${x},${y}`;
      const cell = document.getElementById(`cell-${x}-${y}`);
      if (!cell) continue;

      // Reset classes (keep base + coord)
      cell.className = "cell";

      // 1) Terrain
      const terrainType = terrain[key] || "plain";
      if (TERRAIN_CLASS[terrainType]) {
        cell.classList.add(TERRAIN_CLASS[terrainType]);
      }

      // 2) Path trail (behind everything else)
      if (pathSet.has(key)) {
        cell.classList.add("visited");
      }

      // Clear inner content (keep coord span)
      const coordSpan = cell.querySelector(".coord");
      cell.innerHTML = "";
      if (coordSpan) cell.appendChild(coordSpan);

      // 3) Obstacle
      if (obstacleSet.has(key)) {
        cell.classList.add("obstacle");
        const mark = document.createElement("span");
        mark.className = "obstacle-mark";
        mark.textContent = "X";
        cell.appendChild(mark);
        cell.setAttribute("aria-label", `Obstacle at ${x},${y}`);
        continue;
      }

      // 4) Rover
      if (x === state.rover.x && y === state.rover.y) {
        cell.classList.add("rover-cell");
        const arrow = document.createElement("span");
        arrow.className = "rover-arrow";
        arrow.innerHTML = DIR_ARROWS[state.rover.direction] || "R";
        cell.appendChild(arrow);
        cell.setAttribute("aria-label", `Rover at ${x},${y} facing ${state.rover.direction}`);
        continue;
      }

      // 5) Waypoint — pulsing beacon or "landed" marker
      if (waypointMap[key]) {
        const wp = waypointMap[key];
        if (wp.reached) {
          cell.classList.add("reached");
          // "Landed" marker: star + label
          cell.innerHTML = `
            <div class="wp-landed">
              <span class="wp-landed-star">&#10022;</span>
              <span class="wp-landed-label">BASE</span>
            </div>
            <span class="coord">${x},${y}</span>
          `;
          cell.setAttribute("aria-label", `Reached waypoint: ${wp.name} at ${x},${y}`);
        } else {
          cell.classList.add("waypoint");
          // Beacon: pulsing ring + crosshair
          cell.innerHTML = `
            <div class="wp-beacon">
              <div class="wp-ring"></div>
              <div class="wp-ring wp-ring-2"></div>
              <span class="wp-cross">+</span>
            </div>
            <span class="coord">${x},${y}</span>
          `;
          cell.setAttribute("aria-label", `Waypoint: ${wp.name} at ${x},${y}`);
        }
        continue;
      }

      // Default aria
      cell.setAttribute("aria-label",
        `${terrainType} terrain at ${x},${y}${pathSet.has(key) ? " (visited)" : ""}`);
    }
  }
}

// ── Sidebar updaters ──────────────────────────────────────────────────────

function updateStatus(state) {
  const r = state.rover;
  document.getElementById("stat-pos").textContent
    = `(${r.x}, ${r.y})`;
  document.getElementById("stat-dir").textContent
    = r.direction;
  document.getElementById("stat-cmds").textContent
    = r.commands_executed;
  document.getElementById("stat-cells").textContent
    = new Set(r.path_history.map(p => `${p[0]},${p[1]}`)).size;

  // Update D-pad center icon
  const icon = document.getElementById("rover-direction-icon");
  if (icon) icon.innerHTML = DIR_ARROWS[r.direction] || "R";
}

function updateBattery(state) {
  const b   = state.battery;
  const pct = b.percentage;
  const fill = document.getElementById("battery-fill");
  const label = document.getElementById("battery-label");

  // Color by level
  let color;
  if (pct > 60)      { color = "var(--bat-good)";     label.style.color = "var(--bat-good)";     }
  else if (pct > 30) { color = "var(--bat-low)";      label.style.color = "var(--bat-low)";      }
  else               { color = "var(--bat-critical)";  label.style.color = "var(--bat-critical)"; }

  fill.style.width      = `${pct}%`;
  fill.style.background = color;
  fill.style.boxShadow  = `0 0 6px ${color}`;

  document.getElementById("battery-pct").textContent = `${pct.toFixed(0)}%`;
  document.getElementById("battery-raw").textContent
    = `${b.charge} / ${b.max_charge} units`;
  document.getElementById("battery-label").textContent = b.status.toUpperCase();
  document.getElementById("bat-consumed").textContent  = b.total_consumed;
  document.getElementById("bat-recharged").textContent = b.total_recharged;
}

function updateWaypoints(state) {
  const m    = state.mission;
  const list = document.getElementById("waypoint-list");
  const prog = document.getElementById("wp-progress");

  prog.textContent = `${m.reached_waypoints} / ${m.total_waypoints}`;
  list.innerHTML   = "";

  for (const wp of m.waypoints) {
    const li = document.createElement("li");
    if (wp.reached) li.classList.add("wp-li-done");

    li.innerHTML = `
      <span class="wp-icon">${wp.reached ? "&#9670;" : "&#9671;"}</span>
      <div class="wp-info">
        <div class="wp-name">${wp.name}</div>
        <div class="wp-coord">(${wp.position[0]}, ${wp.position[1]})</div>
      </div>
      <span class="wp-status ${wp.reached ? "wp-done" : "wp-todo"}">
        ${wp.reached ? "DONE" : "TODO"}
      </span>
    `;
    list.appendChild(li);
  }

  const banner = document.getElementById("mission-complete");
  if (m.complete) {
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

function updateLog(state) {
  const entries   = document.getElementById("log-entries");
  const countEl   = document.getElementById("log-count");
  const logItems  = state.log || [];

  countEl.textContent = `${logItems.length} event${logItems.length !== 1 ? "s" : ""}`;
  entries.innerHTML = "";

  for (const msg of logItems) {
    const div = document.createElement("div");
    div.className = "log-entry";

    // Colour-code by content
    const lower = msg.toLowerCase();
    if (lower.includes("waypoint reached") || lower.includes("mission complete")) {
      div.classList.add("log-waypoint");
    } else if (lower.includes("blocked") || lower.includes("dead") || lower.includes("aborted")) {
      div.classList.add("log-warning");
    } else if (lower.includes("error") || lower.includes("no path")) {
      div.classList.add("log-error");
    } else if (lower.includes("a*") || lower.includes("navigation") || lower.includes("path found")) {
      div.classList.add("log-nav");
    }

    div.textContent = msg;
    entries.appendChild(div);
  }
}

function updateMissionName(state) {
  const el = document.getElementById("mission-name");
  if (el) el.textContent = state.mission.name || "Mars Mission";
}

// ── Master render ─────────────────────────────────────────────────────────

let gridBuilt = false;

function render(state) {
  if (!state) return;

  if (!gridBuilt) {
    buildGrid(state);
    gridBuilt = true;
  }

  updateGrid(state);
  updateStatus(state);
  updateBattery(state);
  updateWaypoints(state);
  updateLog(state);
  updateMissionName(state);
  setStatus(true);

  if (state.error) showError(state.error);
}

// ── API actions ───────────────────────────────────────────────────────────

/** Load initial state from server. */
async function loadState() {
  const state = await apiFetch(API.STATE);
  if (state) render(state);
  else setStatus(false);
}

/** Send a single command (M/L/R/S). */
async function sendCommand(cmd) {
  if (busy) return;
  lockUI(true);
  const state = await apiFetch(API.COMMAND, {
    method: "POST",
    body: JSON.stringify({ command: cmd }),
  });
  render(state);
  lockUI(false);
}

/** Trigger A* navigation to the coordinates in the input boxes. */
async function navigate() {
  if (busy) return;
  const x = parseInt(document.getElementById("nav-x").value, 10);
  const y = parseInt(document.getElementById("nav-y").value, 10);

  if (isNaN(x) || isNaN(y)) {
    showError("Please enter valid X and Y coordinates.");
    return;
  }

  lockUI(true);
  const state = await apiFetch(API.NAVIGATE, {
    method: "POST",
    body: JSON.stringify({ x, y }),
  });
  render(state);
  lockUI(false);
}

/** Reset mission to initial state. */
async function resetMission() {
  if (busy) return;
  if (!confirm("Reset the mission? All progress will be lost.")) return;
  lockUI(true);
  gridBuilt = false;   // force grid rebuild after reset
  const state = await apiFetch(API.RESET, { method: "POST" });
  render(state);
  lockUI(false);
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────

document.addEventListener("keydown", (e) => {
  // Don't fire when typing in inputs
  if (e.target.tagName === "INPUT") return;

  switch (e.key.toUpperCase()) {
    case "W": sendCommand("M"); break;
    case "A": sendCommand("L"); break;
    case "D": sendCommand("R"); break;
    case "E": sendCommand("S"); break;
  }
});

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadState();
});
