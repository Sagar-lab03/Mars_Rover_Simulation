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
  STATE: "/api/state",
  COMMAND: "/api/command",
  NAVIGATE: "/api/navigate",
  RESET: "/api/reset",
};

const DIR_ARROWS = {
  North: "&#9650;",   // ▲
  East: "&#9658;",   // ▶
  South: "&#9660;",   // ▼
  West: "&#9668;",   // ◀
};

const TERRAIN_CLASS = {
  sand: "terrain-sand",
  rock: "terrain-rock",
  ice: "terrain-ice",
  plain: "",
};

const TERRAIN_LABEL = {
  sand: "Sand",
  rock: "Rock",
  ice: "Ice",
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
  const dot = document.getElementById("status-dot");
  const label = document.getElementById("status-label");
  if (connected) {
    dot.style.background = "var(--rover)";
    dot.style.boxShadow = "0 0 8px var(--rover)";
    label.textContent = "ONLINE";
  } else {
    dot.style.background = "var(--obstacle)";
    dot.style.boxShadow = "0 0 8px var(--obstacle)";
    label.textContent = "OFFLINE";
  }
}

function lockUI(lock) {
  busy = lock;
  ["btn-M", "btn-L", "btn-R", "btn-S", "btn-nav", "btn-reset"].forEach(id => {
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

  container.style.gridTemplateColumns = `repeat(${width}, 40px)`;
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
  const pathSet = new Set(state.rover.path_history.map(([px, py]) => `${px},${py}`));
  const terrain = state.terrain;   // "x,y" -> type string

  // Waypoint lookup — server sends { position: [x, y], name, reached }
  const waypointMap = {};
  for (const wp of state.mission.waypoints) {
    const [wx, wy] = wp.position;
    waypointMap[`${wx},${wy}`] = wp;
  }

  for (let y = height - 1; y >= 0; y--) {
    for (let x = 0; x < width; x++) {
      const key = `${x},${y}`;
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
  const b = state.battery;
  const pct = b.percentage;
  const fill = document.getElementById("battery-fill");
  const label = document.getElementById("battery-label");

  // Color by level
  let color;
  if (pct > 60) { color = "var(--bat-good)"; label.style.color = "var(--bat-good)"; }
  else if (pct > 30) { color = "var(--bat-low)"; label.style.color = "var(--bat-low)"; }
  else { color = "var(--bat-critical)"; label.style.color = "var(--bat-critical)"; }

  fill.style.width = `${pct}%`;
  fill.style.background = color;
  fill.style.boxShadow = `0 0 6px ${color}`;

  document.getElementById("battery-pct").textContent = `${pct.toFixed(0)}%`;
  document.getElementById("battery-raw").textContent
    = `${b.charge} / ${b.max_charge} units`;
  document.getElementById("battery-label").textContent = b.status.toUpperCase();
  document.getElementById("bat-consumed").textContent = b.total_consumed;
  document.getElementById("bat-recharged").textContent = b.total_recharged;
}

function updateWaypoints(state) {
  const m = state.mission;
  const list = document.getElementById("waypoint-list");
  const prog = document.getElementById("wp-progress");

  prog.textContent = `${m.reached_waypoints} / ${m.total_waypoints}`;
  list.innerHTML = "";

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
  const entries = document.getElementById("log-entries");
  const countEl = document.getElementById("log-count");
  const logItems = state.log || [];

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

// ── Environmental Sensors ───────────────────────────────────────────────────

function updateSensors(state) {
  const s = state.sensors;
  if (!s) return;

  // ── Surface Temperature (-80 to +20 °C range) ──
  const temp = s.surface_temp;
  const tempNorm = Math.max(5, ((temp + 80) / 100) * 100); // map -80..+20 -> 0..100%
  const tempColor = temp < -50 ? "#0ea5e9"        // ice blue
    : temp < -10 ? "#818cf8"        // cool violet
      : temp < 5 ? "#f59e0b"        // warm amber
        : "#f97316";                     // hot orange
  const tempLabel = temp < -50 ? "Extreme Cold"
    : temp < -10 ? "Cold"
      : temp < 5 ? "Mild"
        : "Warm";
  _setSensor("sen-temp", `${temp}°C`, tempNorm, tempColor);
  document.getElementById("sen-temp-sub").textContent = `${tempLabel} — ${s.terrain} terrain`;

  // ── Dust Opacity (τ: 0.1 – 3.0) ──
  const tau = s.dust_opacity;
  const dustNorm = Math.max(5, (tau / 3.0) * 100);
  const dustColor = tau < 0.5 ? "#22c55e"   // clear
    : tau < 1.0 ? "#a3e635"   // light
      : tau < 1.5 ? "#f59e0b"   // moderate
        : "#ef4444";               // heavy
  const solEff = 100 - (s.solar_reduction_pct || 0);
  _setSensor("sen-dust", `τ = ${tau}`, dustNorm, dustColor);
  // Warn if dust is high
  const dustEl = document.getElementById("sen-dust");
  dustEl.classList.toggle("sensor-dust-warn", tau >= 1.5);
  document.getElementById("sen-solar-eff").textContent =
    `Solar: ${solEff.toFixed(0)}% efficient${tau >= 1.5 ? " ⚠ Dust storm" : ""}`;

  // ── UV Radiation Index (0.5 – 5.0 UVI) ──
  const uv = s.uv_index;
  const uvNorm = Math.max(5, (uv / 5.0) * 100);
  const uvColor = uv < 2.0 ? "#22c55e"
    : uv < 3.5 ? "#f59e0b"
      : "#ef4444";
  const uvLabel = uv < 2.0 ? "Low exposure"
    : uv < 3.5 ? "Moderate — shield recommended"
      : "High — maximum shielding";
  _setSensor("sen-uv", `${uv} UVI`, uvNorm, uvColor);
  document.getElementById("sen-uv-sub").textContent = uvLabel;

  // ── Surface Slope (0 – 25° range) ──
  const slope = s.slope_deg;
  const slopeNorm = Math.max(5, (slope / 25) * 100);
  const slopeColor = slope < 5 ? "#22c55e"
    : slope < 12 ? "#f59e0b"
      : "#ef4444";
  const slopeLabel = slope < 5 ? "Flat surface"
    : slope < 12 ? "Moderate grade"
      : "Steep terrain — high battery cost";
  _setSensor("sen-slope", `${slope}°`, slopeNorm, slopeColor);
  document.getElementById("sen-slope-sub").textContent = slopeLabel;
}

/** Helper: update a sensor value + bar in one call. */
function _setSensor(valId, text, barPct, color) {
  const valEl = document.getElementById(valId);
  const barEl = document.getElementById(valId + "-bar");
  if (valEl) valEl.textContent = text;
  if (barEl) {
    barEl.style.width = `${barPct}%`;
    barEl.style.background = color;
    barEl.style.color = color;  // drives box-shadow currentColor
  }
}

/** Toggle the sensor panel open/closed. */
function toggleSensors() {
  const body = document.getElementById("sensors-body");
  const icon = document.getElementById("sensors-toggle-icon");
  if (!body) return;
  const isHidden = body.classList.toggle("hidden");
  icon.classList.toggle("collapsed", isHidden);
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
  updateSensors(state);
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
  // Don't fire when typing in inputs or textareas
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

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
  initBatchPanel();
});

// ═══════════════════════════════════════════════════════════
//  BATCH COMMANDS PANEL
// ═══════════════════════════════════════════════════════════

let parsedCommands = [];   // currently parsed command list

/** Toggle expand/collapse of batch panel body. */
function toggleBatch() {
  const body = document.getElementById("batch-body");
  const icon = document.getElementById("batch-toggle-icon");
  const open = !body.classList.contains("hidden");
  body.classList.toggle("hidden", open);
  icon.classList.toggle("open", !open);
}

/** Switch between TEXT INPUT and FILE UPLOAD tabs. */
function switchTab(mode) {
  document.getElementById("mode-text").classList.toggle("hidden", mode !== "text");
  document.getElementById("mode-file").classList.toggle("hidden", mode !== "file");
  document.getElementById("tab-text").classList.toggle("active", mode === "text");
  document.getElementById("tab-file").classList.toggle("active", mode === "file");
  clearBatch();
}

/** Parse raw text (from textarea or file) into a clean command array. */
function parseBatchText(text) {
  const cmds = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    // Handle inline comments after commands
    const withoutComment = trimmed.split("#")[0].trim();
    const tokens = withoutComment.split(/\s+/);

    let i = 0;
    while (i < tokens.length) {
      const t = tokens[i].toUpperCase();
      if (t === "G" && i + 1 < tokens.length) {
        // "G 5,7" (two tokens) or handled as single below
        cmds.push(`G ${tokens[i + 1]}`);
        i += 2;
      } else if (t.startsWith("G") && t.length > 1) {
        // "G5,7" (one token, no space)
        cmds.push(t);
        i++;
      } else if (["M", "L", "R", "S"].includes(t)) {
        cmds.push(t);
        i++;
      } else {
        i++;  // skip unknown tokens
      }
    }
  }
  return cmds;
}

/** Read textarea / current file and show preview pills. */
function parseBatch() {
  const activeMode = document.getElementById("tab-text").classList.contains("active")
    ? "text" : "file";

  const text = activeMode === "text"
    ? document.getElementById("batch-input").value
    : (document.getElementById("file-name-display").dataset.content || "");

  parsedCommands = parseBatchText(text);
  renderPreview(parsedCommands);
}

/** Render the color-coded command pills and enable exec buttons. */
function renderPreview(cmds) {
  const preview = document.getElementById("batch-preview");
  const pills = document.getElementById("preview-pills");
  const label = document.getElementById("preview-label");

  if (cmds.length === 0) {
    preview.classList.add("hidden");
    setExecEnabled(false);
    return;
  }

  preview.classList.remove("hidden");
  label.textContent = `${cmds.length} command${cmds.length !== 1 ? "s" : ""} parsed`;
  pills.innerHTML = "";

  for (const cmd of cmds) {
    const pill = document.createElement("span");
    const type = cmd.startsWith("G") ? "G" : cmd;
    pill.className = `pill pill-${type}`;
    pill.textContent = cmd;
    pills.appendChild(pill);
  }

  setExecEnabled(true);
}

function setExecEnabled(enabled) {
  document.getElementById("btn-exec").disabled = !enabled;
  document.getElementById("btn-exec-step").disabled = !enabled;
}

/** Clear parsed state and hide preview. */
function clearBatch() {
  parsedCommands = [];
  document.getElementById("batch-preview").classList.add("hidden");
  document.getElementById("batch-input").value = "";
  document.getElementById("file-name-display").classList.add("hidden");
  document.getElementById("file-name-display").dataset.content = "";
  setExecEnabled(false);
}

/** Sleep helper for step animation. */
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

/**
 * Execute the batch.
 * @param {boolean} animate - If true, step through each command with a delay.
 */
async function executeBatch(animate) {
  if (busy || parsedCommands.length === 0) return;

  lockUI(true);
  setExecEnabled(false);

  const progress = document.getElementById("batch-progress");
  const fill = document.getElementById("progress-fill");
  const progText = document.getElementById("progress-text");
  const delayMs = parseInt(document.getElementById("step-speed").value, 10) || 400;

  progress.classList.remove("hidden");
  fill.style.width = "0%";

  const result = await apiFetch("/api/batch/execute", {
    method: "POST",
    body: JSON.stringify({ commands: parsedCommands }),
  });

  if (!result) {
    progress.classList.add("hidden");
    lockUI(false);
    setExecEnabled(true);
    return;
  }

  const steps = result.steps || [];

  if (animate && steps.length > 0) {
    for (let i = 0; i < steps.length; i++) {
      render(steps[i].state);
      const pct = Math.round(((i + 1) / steps.length) * 100);
      fill.style.width = `${pct}%`;
      progText.textContent = `Step ${i + 1} / ${steps.length} — ${steps[i].command}`;
      await sleep(delayMs);
    }
  } else {
    render(result.final_state);
    fill.style.width = "100%";
    progText.textContent = `Done — ${steps.length} steps executed`;
  }

  const s = result.summary;
  if (s) {
    progText.textContent =
      `Done: ${s.total_steps} steps${s.error_count ? `, ${s.error_count} skipped` : ""} — final pos ${s.final_pos}`;
  }

  lockUI(false);
  setExecEnabled(true);
}

// ── File upload / drag-drop ───────────────────────────────────────────────

function onFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;
  readFile(file);
}

function onDragOver(event) {
  event.preventDefault();
  document.getElementById("file-drop-zone").classList.add("drag-over");
}

function onDrop(event) {
  event.preventDefault();
  document.getElementById("file-drop-zone").classList.remove("drag-over");
  const file = event.dataTransfer.files[0];
  if (file) readFile(file);
}

function readFile(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const content = e.target.result;
    const display = document.getElementById("file-name-display");
    display.textContent = `📄 ${file.name} loaded`;
    display.dataset.content = content;
    display.classList.remove("hidden");
    // Auto-parse
    parsedCommands = parseBatchText(content);
    renderPreview(parsedCommands);
  };
  reader.readAsText(file);
}

// ── Speed slider live update ──────────────────────────────────────────────

function initBatchPanel() {
  const slider = document.getElementById("step-speed");
  const val = document.getElementById("speed-val");
  if (slider && val) {
    slider.addEventListener("input", () => {
      val.textContent = `${slider.value}ms`;
    });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  MISSION FEASIBILITY ANALYSIS ENGINE
// ─────────────────────────────────────────────────────────────────────────────

let _planCtx = null;   // { mode, payload }

// Gate btn-plan alongside the exec buttons
const _setExecOrig = setExecEnabled;
function setExecEnabled(en) {
  _setExecOrig(en);
  const p = document.getElementById("btn-plan");
  if (p) p.disabled = !en;
}

/** navigate() — now shows feasibility modal before executing. */
async function navigate() {
  if (busy) return;
  const x = parseInt(document.getElementById("nav-x").value, 10);
  const y = parseInt(document.getElementById("nav-y").value, 10);
  if (isNaN(x) || isNaN(y)) { showError("Please enter valid X and Y coordinates."); return; }
  lockUI(true);
  const plan = await apiFetch("/api/plan", { method: "POST", body: JSON.stringify({ x, y }) });
  lockUI(false);
  if (plan) showPlanModal(plan, "navigate", { x, y });
}

/** Plan a batch sequence — open modal without executing. */
async function planBatch() {
  if (parsedCommands.length === 0) return;
  lockUI(true);
  const plan = await apiFetch("/api/plan", { method: "POST", body: JSON.stringify({ commands: parsedCommands }) });
  lockUI(false);
  if (plan) showPlanModal(plan, "batch", null);
}

/** Populate and display the Mission Feasibility Modal. */
function showPlanModal(plan, mode, payload) {
  _planCtx = { mode, payload };

  // Header
  document.getElementById("mfp-subtitle").textContent =
    mode === "navigate" ? `A* route to (${payload.x}, ${payload.y})` : `Batch — ${parsedCommands.length} commands`;
  const badge = document.getElementById("mfp-risk-badge");
  badge.textContent = plan.risk_level || "—";
  badge.className = `mfp-risk-badge mfp-risk-${plan.risk_level || "LOW"}`;

  // Path length
  document.getElementById("mfp-steps").textContent = plan.steps ?? "—";

  // Energy
  const cost = plan.energy_cost ?? 0, gained = plan.solar_gain ?? 0, cur = plan.current_battery ?? 100;
  document.getElementById("mfp-cost").textContent = `\u2212${cost}${gained > 0 ? ` / +${gained}` : ""} u`;
  document.getElementById("mfp-cost-sub").textContent =
    `${cur} units available${gained > 0 ? ` \u00b7 ${gained} solar est.` : ""}`;

  // Projected battery
  const pp = plan.projected_pct ?? 0, pb = plan.projected_battery ?? 0;
  const bc = pp > 60 ? "#22c55e" : pp > 25 ? "#f59e0b" : "#ef4444";
  document.getElementById("mfp-proj-pct").textContent = `${pp.toFixed(1)}%`;
  const projBar = document.getElementById("mfp-proj-bar");
  projBar.style.width = `${Math.max(2, pp)}%`; projBar.style.background = bc;
  document.getElementById("mfp-proj-sub").textContent = `${pb} / ${cur} units projected`;

  // Terrain breakdown
  const tb = plan.terrain_breakdown || {}, total = Object.values(tb).reduce((a, b) => a + b, 0);
  const tcols = { plain: "#38bdf8", sand: "#f59e0b", rock: "#6b7280", ice: "#0ea5e9" };
  const tel = document.getElementById("mfp-terrain"); tel.innerHTML = "";
  for (const [type, count] of Object.entries(tb)) {
    if (count === 0 && total > 0) continue;
    const pct = total > 0 ? Math.round(count / total * 100) : 0;
    const row = document.createElement("div"); row.className = "mfp-terrain-row";
    row.innerHTML = `<div class="mfp-terrain-label-row"><span class="mfp-terrain-name">${type[0].toUpperCase() + type.slice(1)}</span><span class="mfp-terrain-count">${count} cell${count !== 1 ? "s" : ""} (${pct}%)</span></div><div class="mfp-terrain-bar-track"><div class="mfp-terrain-bar" style="width:${pct}%;background:${tcols[type] || "#38bdf8"}"></div></div>`;
    tel.appendChild(row);
  }
  if (total === 0) tel.textContent = "No movement steps";

  // Atmospheric
  const ad = plan.avg_dust ?? 0, md = plan.max_dust ?? 0;
  const dp = Math.min(100, (ad / 3) * 100);
  const dc = ad < 0.5 ? "#22c55e" : ad < 1.0 ? "#a3e635" : ad < 1.5 ? "#f59e0b" : "#ef4444";
  const solRed = Math.max(0, Math.min(50, (ad - 0.5) * 25));
  document.getElementById("mfp-avg-dust").textContent = ad.toFixed(2);
  document.getElementById("mfp-max-dust").textContent = md.toFixed(2);
  const dustBar = document.getElementById("mfp-dust-bar");
  dustBar.style.width = `${dp}%`; dustBar.style.background = dc;
  document.getElementById("mfp-solar-note").textContent =
    ad >= 1.5 ? `\u26a0 Dust storm \u2014 solar \u2248 ${(100 - solRed).toFixed(0)}%`
      : `Solar: \u2248${(100 - solRed).toFixed(0)}% efficient`;

  // Science targets
  const wl = document.getElementById("mfp-waypoints"); wl.innerHTML = "";
  const wps = plan.waypoints_on_route || [];
  if (wps.length === 0) {
    wl.innerHTML = `<span style="font-size:10px;color:var(--text-secondary)">No waypoints on route</span>`;
  } else {
    for (const wp of wps) {
      const item = document.createElement("div"); item.className = "mfp-wp-item";
      item.innerHTML = `<div class="mfp-wp-dot"></div>${wp.name} <span style="color:var(--text-secondary)">(${wp.position[0]},${wp.position[1]})</span>`;
      wl.appendChild(item);
    }
  }

  // Risk warnings
  const wel = document.getElementById("mfp-warnings"); wel.innerHTML = "";
  const ws = plan.warnings || [], rl = plan.risk_level || "LOW";
  const wicon = rl === "HIGH" ? "\u25cf" : rl === "MEDIUM" ? "\u25b2" : "\u25c6";
  if (ws.length === 0) {
    wel.innerHTML = `<div class="mfp-no-warnings">\u2714 No critical risks \u2014 route is clear.</div>`;
  } else {
    for (const w of ws)
      wel.innerHTML += `<div class="mfp-warning-item"><span class="mfp-warn-icon mfp-warn-${rl}">${wicon}</span><span>${w}</span></div>`;
  }

  // Verdict
  const rec = plan.recommendation || "NOT_RECOMMENDED";
  const VM = {
    SAFE_TO_EXECUTE: { text: "SAFE TO EXECUTE", cls: "mfp-verdict-SAFE", note: "All systems nominal. Route approved for immediate execution." },
    EXECUTE_WITH_CAUTION: { text: "EXECUTE WITH CAUTION", cls: "mfp-verdict-CAUTION", note: "Route is feasible but risk factors detected. Monitor battery closely." },
    NOT_RECOMMENDED: { text: "NOT RECOMMENDED", cls: "mfp-verdict-NO", note: "Mission parameters exceed safe thresholds. Resolve warnings first." },
  };
  const v = VM[rec] || VM["NOT_RECOMMENDED"];
  const ve = document.getElementById("mfp-verdict");
  ve.textContent = v.text; ve.className = `mfp-verdict ${v.cls}`;
  document.getElementById("mfp-verdict-note").textContent = v.note;

  // Footer buttons
  document.getElementById("mfp-btn-execute").classList.toggle("hidden", rec !== "SAFE_TO_EXECUTE");
  document.getElementById("mfp-btn-caution").classList.toggle("hidden", rec !== "EXECUTE_WITH_CAUTION");

  // Path grid overlay
  clearPlannedOverlay();
  for (const [px, py] of (plan.path || [])) {
    const c = document.getElementById(`cell-${px}-${py}`);
    if (c) c.classList.add("cell-planned");
  }

  document.getElementById("mfp-overlay").classList.remove("hidden");
}

function clearPlannedOverlay() {
  document.querySelectorAll(".cell-planned").forEach(c => c.classList.remove("cell-planned"));
}

function closePlanModal() {
  document.getElementById("mfp-overlay").classList.add("hidden");
  clearPlannedOverlay();
  _planCtx = null;
}

async function confirmPlanExecute() {
  if (!_planCtx) return;
  const { mode, payload } = _planCtx;
  closePlanModal();
  lockUI(true);
  if (mode === "navigate") {
    const state = await apiFetch(API.NAVIGATE, { method: "POST", body: JSON.stringify(payload) });
    render(state);
  } else {
    await executeBatch(false);
  }
  lockUI(false);
  // Auto-refresh survey rankings if the survey panel is currently active
  const surveyResultsEl = document.getElementById("survey-results");
  if (surveyResultsEl && !surveyResultsEl.classList.contains("hidden")) {
    clearSurveyOverlay();
    await runSurvey();
  }
}


document.addEventListener("keydown", e => { if (e.key === "Escape") closePlanModal(); });

// ─────────────────────────────────────────────────────────────────────────────
//  SCIENCE SURVEY ENGINE
// ─────────────────────────────────────────────────────────────────────────────

const RANK_SYMBOLS = ["①", "②", "③", "④", "⑤"];

// ── Mission Profile helpers ────────────────────────────────────────────────

/** Fetch available profiles from /api/profiles and populate the dropdown. */
async function initProfiles() {
  const select = document.getElementById("mission-profile");
  if (!select) return;
  const data = await apiFetch("/api/profiles");
  if (!data || !data.profiles) return;
  select.innerHTML = data.profiles
    .map(p => `<option value="${p.id}">${p.label}</option>`)
    .join("");
  _applyProfileStyles(select.value);
}

/** Return the currently selected profile id. */
function getActiveProfile() {
  return document.getElementById("mission-profile")?.value || "balanced";
}

/** Called when the profile dropdown changes. */
function onProfileChange() {
  const profile = getActiveProfile();
  _applyProfileStyles(profile);
  // Auto-refresh an already-open scan with the new profile
  const resultsEl = document.getElementById("survey-results");
  if (resultsEl && !resultsEl.classList.contains("hidden")) {
    clearSurveyOverlay();
    runSurvey();
  }
}

/** Apply colour accents and update the Auto Explore profile label. */
function _applyProfileStyles(profileId) {
  const row = document.querySelector(".profile-selector-row");
  if (row) row.className = `profile-selector-row profile-active-${profileId}`;
  const label = document.getElementById("ae-profile-label");
  const select = document.getElementById("mission-profile");
  if (label && select) {
    const opt = select.querySelector(`option[value="${profileId}"]`);
    label.textContent = opt ? opt.textContent.split(" ")[0] : profileId;
  }
}

// Initialise profile dropdown on page load
initProfiles();

/** Toggle the Science Survey panel open/closed. */
function toggleSurvey() {
  const body = document.getElementById("survey-body");
  const icon = document.getElementById("survey-toggle-icon");
  if (!body) return;
  const hidden = body.style.display === "none";
  body.style.display = hidden ? "" : "none";
  icon.classList.toggle("collapsed", !hidden);
}

/** Remove all survey overlays from grid cells. */
function clearSurveyOverlay() {
  document.querySelectorAll(".cell-survey").forEach(c => {
    c.classList.remove("cell-survey");
    c.removeAttribute("data-survey-rank");
  });
}

/**
 * Navigate to (x, y) by calling /api/plan and opening the feasibility modal.
 * All survey recommendations route through the standard analyze→approve→execute flow.
 */
async function navigateTo(x, y) {
  if (busy) return;
  lockUI(true);
  const plan = await apiFetch("/api/plan", { method: "POST", body: JSON.stringify({ x, y }) });
  lockUI(false);
  if (plan) showPlanModal(plan, "navigate", { x, y });
}

/** Call /api/recommend and render the ranked target cards + grid overlays. */
async function runSurvey() {
  const btn = document.getElementById("btn-survey");
  const hint = document.getElementById("survey-hint");
  const resultsEl = document.getElementById("survey-results");

  btn.classList.add("loading");
  btn.disabled = true;
  hint.textContent = "Scanning…";
  clearSurveyOverlay();
  resultsEl.classList.add("hidden");
  resultsEl.innerHTML = "";

  const data = await apiFetch(`/api/recommend?n=3&profile=${getActiveProfile()}`);

  btn.classList.remove("loading");
  btn.disabled = false;

  if (!data) {
    hint.textContent = "Scan failed — is server running?";
    return;
  }

  const recs = data.recommendations || [];
  const missionScore = data.mission_score ?? 0;
  const total = data.total_candidates ?? 0;

  // Update score badge in panel header
  const scoreBadge = document.getElementById("survey-score-badge");
  if (scoreBadge) scoreBadge.textContent = `${missionScore} pts`;

  hint.textContent = `${recs.length} of ${total} candidates`;

  if (recs.length === 0) {
    resultsEl.innerHTML = `<div style="font-size:10px;color:var(--text-secondary);text-align:center;padding:8px">All high-value cells explored.</div>`;
    resultsEl.classList.remove("hidden");
    return;
  }

  // Terrain CSS class map
  const terrainCls = { rock: "survey-terrain-rock", ice: "survey-terrain-ice", sand: "survey-terrain-sand", plain: "survey-terrain-plain" };

  recs.forEach((rec, i) => {
    const [x, y] = rec.position;
    const rank = RANK_SYMBOLS[i] || `#${i + 1}`;
    const profileAccentCls = `profile-accent-${getActiveProfile()}`;

    // ── Grid overlay badge ──
    const cell = document.getElementById(`cell-${x}-${y}`);
    if (cell) {
      cell.classList.add("cell-survey");
      cell.setAttribute("data-survey-rank", rank);
    }

    // ── Sidebar card ──
    const reasons = (rec.reasons || []).map(r =>
      `<span class="survey-reason-pill">${r}</span>`
    ).join("");

    const card = document.createElement("div");
    card.className = `survey-card ${profileAccentCls}`;
    card.title = `Click to plan route to (${x}, ${y})`;
    card.innerHTML = `
      <div class="survey-card-header">
        <span class="survey-rank-badge">${rank}</span>
        <span class="survey-pos">(${x}, ${y})</span>
        <span class="survey-terrain-tag ${terrainCls[rec.terrain] || ""}">${rec.terrain}</span>
      </div>
      <div class="survey-reasons">${reasons || '<span class="survey-reason-pill">Plain terrain</span>'}</div>
      <div class="survey-metrics">
        <div class="survey-metric">
          <span class="survey-metric-label">SCIENCE</span>
          <span class="survey-metric-value">${rec.science_value}</span>
        </div>
        <div class="survey-metric">
          <span class="survey-metric-label">COST</span>
          <span class="survey-metric-value">${rec.travel_cost}u</span>
        </div>
        <div class="survey-metric">
          <span class="survey-metric-label">EFFICIENCY</span>
          <span class="survey-metric-value">${rec.efficiency.toFixed(2)}</span>
        </div>
      </div>
      <div class="survey-action-hint">▶ Click to open feasibility analysis</div>
    `;
    card.addEventListener("click", () => navigateTo(x, y));
    resultsEl.appendChild(card);
  });

  resultsEl.classList.remove("hidden");
}

// ─────────────────────────────────────────────────────────────────────────────
//  AUTONOMOUS EXPLORATION ENGINE
// ─────────────────────────────────────────────────────────────────────────────

let _aeActive   = false;
let _aeTimer    = null;
let _aeSteps    = 0;

/** Toggle the Auto Explore panel open/collapsed. */
function toggleAutoExplorePanel() {
  const body = document.getElementById("ae-body");
  const icon = document.getElementById("ae-panel-toggle");
  if (!body) return;
  const hidden = body.style.display === "none";
  body.style.display = hidden ? "" : "none";
  icon.classList.toggle("collapsed", !hidden);
}

/** Start or stop the autonomous exploration loop. */
function toggleAutoExplore() {
  if (_aeActive) {
    _stopAutoExplore("Stopped by operator.");
  } else {
    _startAutoExplore();
  }
}

function _startAutoExplore() {
  _aeActive = true;
  _aeSteps  = 0;
  const btn = document.getElementById("btn-ae-start");
  const statusEl = document.getElementById("ae-status");
  btn.classList.add("running");
  btn.textContent = "⏹ STOP EXPLORING";
  statusEl.className = "ae-status-label running";
  statusEl.textContent = "Exploring…";
  document.getElementById("ae-log").innerHTML = "";
  appendAeLog("◆ Autonomous exploration started.", "info");
  _aeLoop();
}

function _stopAutoExplore(reason) {
  _aeActive = false;
  clearTimeout(_aeTimer);
  const btn = document.getElementById("btn-ae-start");
  const statusEl = document.getElementById("ae-status");
  btn.classList.remove("running");
  btn.textContent = "◆ AUTO EXPLORE";
  statusEl.className = "ae-status-label stopped";
  statusEl.textContent = "Stopped";
  if (reason) appendAeLog(reason, "warn");
}

async function _aeLoop() {
  if (!_aeActive) return;

  const result = await apiFetch(`/api/auto_explore/step?profile=${getActiveProfile()}`, { method: "POST" });

  if (!result) {
    _stopAutoExplore("Connection error — exploration halted.");
    return;
  }

  // ── Step divider ──
  _aeSteps++;
  document.getElementById("ae-step-count").textContent = `${_aeSteps} step${_aeSteps !== 1 ? "s" : ""}`;
  appendAeLog(`── Step ${_aeSteps} ──`, "step-divider");

  // ── Log each reasoning line ──
  (result.reasoning || []).forEach(line => appendAeLog(line));

  // ── Update grid + sidebar ──
  if (result.state) render(result.state);

  // ── Update score badge ──
  const score = result.mission_score ?? 0;
  const scoreBadge = document.getElementById("ae-score-badge");
  if (scoreBadge) {
    scoreBadge.textContent = `${score} pts`;
    scoreBadge.classList.toggle("active", score > 0);
  }

  // ── Also refresh survey overlay if it's open ──
  const surveyResultsEl = document.getElementById("survey-results");
  if (surveyResultsEl && !surveyResultsEl.classList.contains("hidden")) {
    clearSurveyOverlay();
    // Don't await — let it refresh in background
    runSurvey();
  }

  // ── Continue or stop ──
  if (!_aeActive) return;

  if (!result.should_continue) {
    _stopAutoExplore(result.stop_reason || "Exploration complete.");
    return;
  }

  const delay = parseInt(document.getElementById("ae-speed")?.value || "1600", 10);
  _aeTimer = setTimeout(_aeLoop, delay);
}

/**
 * Append one line to the decision log with automatic colour classification.
 * Colour is derived from the leading emoji/character:
 *   ✓  → green (ok)    ⚠  → amber (warn)    ✗/⛔ → red (error)
 *   🎯/🔍/🔋/◆ → cyan (info)   ── → dim (step-divider)
 */
function appendAeLog(text, forceClass) {
  const log = document.getElementById("ae-log");
  if (!log) return;

  let cls = forceClass || "";
  if (!cls) {
    if (text.startsWith("✓"))                   cls = "ok";
    else if (text.startsWith("⚠"))             cls = "warn";
    else if (text.startsWith("✗") || text.startsWith("⛔")) cls = "error";
    else if (text.startsWith("🎯") || text.startsWith("🔍") ||
             text.startsWith("🔋") || text.startsWith("◆")) cls = "info";
  }

  const line = document.createElement("div");
  line.className = `ae-log-line${cls ? " " + cls : ""}`;
  line.textContent = text;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}
