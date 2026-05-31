/**
 * analytics.js — Mars Rover Analytics Dashboard
 *
 * Fetches telemetry data from the Flask API and renders:
 *  1. Mission selector dropdown
 *  2. 6 stat cards
 *  3. Battery timeline (Chart.js line chart)
 *  4. Command distribution (Chart.js doughnut)
 *  5. Terrain coverage (Chart.js horizontal bar)
 *  6. Path heatmap (custom CSS grid)
 *  7. All-missions comparison table
 */

"use strict";

// ── Chart.js global defaults ──────────────────────────────────────────────────
Chart.defaults.color          = "#64748b";
Chart.defaults.borderColor    = "#1e3054";
Chart.defaults.font.family    = "'JetBrains Mono', monospace";
Chart.defaults.font.size      = 11;
Chart.defaults.plugins.legend.labels.boxWidth = 12;

// ── Color palette ──────────────────────────────────────────────────────────────
const C = {
  rover:    "#22c55e",
  obstacle: "#dc2626",
  waypoint: "#e879f9",
  accent:   "#38bdf8",
  sand:     "#d97706",
  rock:     "#6b7280",
  ice:      "#0284c7",
  plain:    "#334155",
  batGood:  "#22c55e",
  batLow:   "#f59e0b",
  batCrit:  "#ef4444",
  turnL:    "#a78bfa",
  turnR:    "#fb923c",
  solar:    "#a3e635",
  move:     "#38bdf8",
};

// ── Active chart instances (destroyed on reload) ──────────────────────────────
let charts = {};

function destroyCharts() {
  Object.values(charts).forEach(c => c && c.destroy());
  charts = {};
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function apiFetch(url) {
  try {
    const res = await fetch(url);
    return await res.json();
  } catch {
    return null;
  }
}

function fmt(n, decimals = 0) {
  if (n === undefined || n === null) return "—";
  return Number(n).toFixed(decimals);
}

function batClass(pct) {
  if (pct > 60)  return "bat-good";
  if (pct > 30)  return "bat-low";
  return "bat-critical";
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// ── Mission list ───────────────────────────────────────────────────────────────

let allMissions = [];

async function refreshMissions() {
  document.getElementById("mission-count").textContent = "Loading...";
  const data = await apiFetch("/api/analytics/missions");
  if (!data) {
    document.getElementById("mission-count").textContent = "Error loading";
    return;
  }

  allMissions = data.missions || [];
  const sel   = document.getElementById("mission-select");
  const curr  = sel.value;

  sel.innerHTML = `<option value="">— Choose a mission —</option>`;
  for (const m of allMissions) {
    const opt = document.createElement("option");
    opt.value       = m.filename;
    opt.textContent = `${m.mission_name}  |  ${fmtDate(m.start_time)}`;
    sel.appendChild(opt);
  }

  // Restore selection
  if (curr && allMissions.find(m => m.filename === curr)) {
    sel.value = curr;
  } else if (allMissions.length > 0) {
    sel.value = allMissions[0].filename;
    loadMission(allMissions[0].filename);
  }

  const n = allMissions.length;
  document.getElementById("mission-count").textContent =
    `${n} mission${n !== 1 ? "s" : ""} recorded`;

  renderMissionsTable(allMissions);
}

async function loadMission(filename) {
  if (!filename) return;

  document.getElementById("empty-state").classList.add("hidden");
  document.getElementById("dashboard").classList.remove("hidden");

  const data = await apiFetch(`/api/analytics/mission/${encodeURIComponent(filename)}`);
  if (!data || data.error) return;

  updateStatCards(data);
  destroyCharts();
  renderBatteryChart(data.battery_timeline);
  renderCommandChart(data.command_counts);
  renderTerrainChart(data.terrain_visited);
  renderHeatmap(data.heatmap, data.grid, data.path_history);

  // Highlight active row in table
  document.querySelectorAll(".missions-table tbody tr").forEach(row => {
    row.classList.toggle("active-row", row.dataset.filename === filename);
  });
}

// ── Stat cards ────────────────────────────────────────────────────────────────

function updateStatCards(data) {
  const s = data.mission_stats;
  document.getElementById("s-commands").textContent  = fmt(s.total_commands);
  document.getElementById("s-cells").textContent     = fmt(s.cells_visited);
  document.getElementById("s-energy").textContent    = `${fmt(s.energy_consumed)} u`;
  document.getElementById("s-recharged").textContent = `${fmt(s.energy_recharged)} u`;
  document.getElementById("s-battery").textContent   = `${fmt(s.final_battery_pct, 1)}%`;
  document.getElementById("s-duration").textContent  = `${fmt(data.duration_seconds, 1)}s`;
}

// ── Battery timeline (Line chart) ─────────────────────────────────────────────

function renderBatteryChart(timeline) {
  const ctx    = document.getElementById("chart-battery").getContext("2d");
  const labels = timeline.map(t => t.step === 0 ? "START" : `#${t.step} ${t.command}`);
  const values = timeline.map(t => t.pct);

  // Point colors based on battery level
  const pointColors = values.map(v =>
    v > 60 ? C.batGood : v > 30 ? C.batLow : C.batCrit
  );

  // Gradient fill
  const grad = ctx.createLinearGradient(0, 0, 0, 200);
  grad.addColorStop(0,   "rgba(34,197,94,0.25)");
  grad.addColorStop(0.5, "rgba(245,158,11,0.12)");
  grad.addColorStop(1,   "rgba(239,68,68,0.05)");

  charts.battery = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label:           "Battery %",
        data:            values,
        borderColor:     C.batGood,
        borderWidth:     2,
        pointBackgroundColor: pointColors,
        pointBorderColor:     pointColors,
        pointRadius:     4,
        pointHoverRadius: 6,
        fill:            true,
        backgroundColor: grad,
        tension:         0.35,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `Battery: ${ctx.parsed.y.toFixed(1)}%`,
            afterLabel: ctx => {
              const t = timeline[ctx.dataIndex];
              return t.event === "solar"
                ? "&#9728; Solar charge"
                : `Command: ${t.command}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { maxRotation: 45, font: { size: 9 } },
          grid:  { color: "#1e3054" },
        },
        y: {
          min: 0, max: 100,
          ticks: { callback: v => `${v}%` },
          grid:  { color: "#1e3054" },
        },
      },
    },
  });
}

// ── Command distribution (Doughnut) ───────────────────────────────────────────

function renderCommandChart(counts) {
  const ctx    = document.getElementById("chart-commands").getContext("2d");
  const labels = ["Move (M)", "Turn Left (L)", "Turn Right (R)", "Solar (S)"];
  const values = [counts.M || 0, counts.L || 0, counts.R || 0, counts.S || 0];
  const colors = [C.move, C.turnL, C.turnR, C.solar];

  charts.commands = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data:            values,
        backgroundColor: colors.map(c => c + "cc"),
        borderColor:     colors,
        borderWidth:     2,
        hoverOffset:     8,
      }],
    },
    options: {
      responsive: true,
      cutout: "65%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { padding: 12, usePointStyle: true },
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              const total = values.reduce((a, b) => a + b, 0);
              const pct   = total ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
              return ` ${ctx.label}: ${ctx.parsed} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

// ── Terrain coverage (Horizontal bar) ────────────────────────────────────────

function renderTerrainChart(visited) {
  const ctx    = document.getElementById("chart-terrain").getContext("2d");
  const labels = ["Plain", "Sand", "Rock", "Ice"];
  const values = [visited.plain || 0, visited.sand || 0, visited.rock || 0, visited.ice || 0];
  const colors = [C.plain, C.sand, C.rock, C.ice];

  charts.terrain = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label:           "Cells Visited",
        data:            values,
        backgroundColor: colors.map(c => c + "cc"),
        borderColor:     colors,
        borderWidth:     2,
        borderRadius:    4,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: ctx => ` ${ctx.parsed.x} cell${ctx.parsed.x !== 1 ? "s" : ""}` },
        },
      },
      scales: {
        x: {
          grid:  { color: "#1e3054" },
          ticks: { stepSize: 1 },
        },
        y: { grid: { display: false } },
      },
    },
  });
}

// ── Path heatmap (custom CSS grid) ───────────────────────────────────────────

function renderHeatmap(heatmap, grid, pathHistory) {
  const container = document.getElementById("heatmap-grid");
  const { width, height } = grid;
  const maxVisits = Math.max(...Object.values(heatmap), 1);

  container.style.gridTemplateColumns = `repeat(${width}, 36px)`;
  container.innerHTML = "";

  for (let y = height - 1; y >= 0; y--) {
    for (let x = 0; x < width; x++) {
      const cell  = document.createElement("div");
      const key   = `${x},${y}`;
      const count = heatmap[key] || 0;

      cell.className = "heatmap-cell";
      cell.title     = count > 0 ? `(${x},${y}) — visited ${count}×` : `(${x},${y})`;

      if (count > 0) {
        const intensity = count / maxVisits;
        // Interpolate from dark blue → bright cyan
        const r = Math.round(14  + intensity * (34  - 14));
        const g = Math.round(74  + intensity * (197 - 74));
        const b = Math.round(111 + intensity * (94  - 111));
        cell.style.background    = `rgba(${r},${g},${b},${0.25 + intensity * 0.75})`;
        cell.style.borderColor   = `rgba(${r},${g},${b},0.6)`;
        cell.textContent         = count > 1 ? count : "";
        cell.classList.add("visited");
      }

      container.appendChild(cell);
    }
  }
}

// ── Missions table ────────────────────────────────────────────────────────────

function renderMissionsTable(missions) {
  const tbody = document.getElementById("missions-tbody");
  const count = document.getElementById("table-count");

  count.textContent = `${missions.length} mission${missions.length !== 1 ? "s" : ""} recorded`;
  tbody.innerHTML   = "";

  if (missions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-dim);padding:20px">
      No missions recorded yet. Run a mission to generate telemetry.</td></tr>`;
    return;
  }

  for (const m of missions) {
    const pct = Number(m.final_battery_pct || 0);
    const cls = batClass(pct);
    const tr  = document.createElement("tr");
    tr.dataset.filename = m.filename;
    tr.innerHTML = `
      <td>${m.mission_name}</td>
      <td>${fmtDate(m.start_time)}</td>
      <td>${fmt(m.duration_seconds, 1)}s</td>
      <td>${fmt(m.commands_executed)}</td>
      <td>${fmt(m.cells_visited)}</td>
      <td>${fmt(m.energy_consumed)} u</td>
      <td><span class="bat-pct ${cls}">${fmt(pct, 1)}%</span></td>
      <td style="display:flex;gap:5px">
        <button class="btn-load-row" onclick="selectMission('${m.filename}')">Load</button>
        <button class="btn-load-row" style="border-color:#e879f9;color:#e879f9"
          onclick="selectAndReplay('${m.filename}')">&#9654;</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

function selectMission(filename) {
  document.getElementById("mission-select").value = filename;
  loadMission(filename);
}

function selectAndReplay(filename) {
  selectMission(filename);
  // Small delay so loadMission can fetch and store data
  setTimeout(() => startReplay(), 600);
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  refreshMissions();
});


// ════════════════════════════════════════════════════════════════
//  MISSION REPLAY ENGINE
// ════════════════════════════════════════════════════════════════

let replayData   = null;   // full mission detail from API
let replayFrames = [];     // one frame per telemetry event
let replayCursor = 0;      // current frame index
let replayTimer  = null;   // setInterval handle
let replaySpeed  = 600;    // ms per frame

const DIR_ARROWS_R = { North: "▲", East: "▶", South: "▼", West: "◄" };

/**
 * Build a flat array of frames from the telemetry events.
 * Each frame = { command, x, y, direction, battery, eventType, pathSoFar, waypointsDone }
 */
function buildReplayFrames(data) {
  const frames   = [];
  const pathSoFar = [];
  const wpDone    = new Set();

  for (const ev of data.events) {
    const t    = ev.type;
    const d    = ev.data || {};

    if (t === "mission_start") {
      const pos = d.position || {};
      pathSoFar.push([pos.x, pos.y]);
      frames.push({
        command:     "START",
        eventType:   "mission_start",
        x:           pos.x ?? 0,
        y:           pos.y ?? 0,
        direction:   d.direction || "North",
        battery:     d.battery || {},
        pathSoFar:   [...pathSoFar],
        waypointsDone: new Set(wpDone),
      });

    } else if (t === "command") {
      const rs  = d.rover_status || {};
      const pos = rs.position || {};
      const ms  = d.mission_status || {};

      // Track waypoints reached up to this frame
      for (const wp of (ms.waypoints || [])) {
        if (wp.reached) wpDone.add(wp.name);
      }

      if (d.command === "M") pathSoFar.push([pos.x, pos.y]);

      frames.push({
        command:     d.command || "?",
        eventType:   "command",
        x:           pos.x ?? 0,
        y:           pos.y ?? 0,
        direction:   rs.direction || "North",
        battery:     rs.battery || {},
        pathSoFar:   [...pathSoFar],
        waypointsDone: new Set(wpDone),
        waypoints:   ms.waypoints || [],
      });

    } else if (t === "solar_charge") {
      const last = frames[frames.length - 1] || {};
      frames.push({
        command:     "S",
        eventType:   "solar_charge",
        x:           last.x ?? 0,
        y:           last.y ?? 0,
        direction:   last.direction || "North",
        battery:     d.battery || {},
        pathSoFar:   [...pathSoFar],
        waypointsDone: new Set(wpDone),
        waypoints:   last.waypoints || [],
      });
    }
  }
  return frames;
}

/** Build the replay grid DOM (called once per replay start). */
function buildReplayGrid(width, height) {
  const grid = document.getElementById("replay-grid");
  grid.style.gridTemplateColumns = `repeat(${width}, 38px)`;
  grid.innerHTML = "";
  for (let y = height - 1; y >= 0; y--) {
    for (let x = 0; x < width; x++) {
      const cell = document.createElement("div");
      cell.className = "rcell";
      cell.id = `rc-${x}-${y}`;
      // Apply terrain
      const tc = (replayData.terrain_cells || {})[`${x},${y}`] || "plain";
      if (tc !== "plain") cell.classList.add(`terrain-${tc}`);
      grid.appendChild(cell);
    }
  }
}

/** Render one frame onto the replay grid + telemetry sidebar. */
function renderReplayFrame(idx) {
  if (!replayFrames.length || !replayData) return;
  idx = Math.max(0, Math.min(idx, replayFrames.length - 1));
  replayCursor = idx;

  const frame     = replayFrames[idx];
  const { width, height } = replayData.grid;
  const obstacleSet = new Set((replayData.obstacles || []).map(([ox,oy]) => `${ox},${oy}`));
  const pathSet     = new Set((frame.pathSoFar || []).map(([px,py]) => `${px},${py}`));

  // Waypoint map from events (all waypoints in mission)
  const allWaypoints = frame.waypoints || [];
  const wpMap = {};
  for (const wp of allWaypoints) {
    wpMap[`${wp.position[0]},${wp.position[1]}`] = wp;
  }

  // Update every cell
  for (let y = height - 1; y >= 0; y--) {
    for (let x = 0; x < width; x++) {
      const key  = `${x},${y}`;
      const cell = document.getElementById(`rc-${x}-${y}`);
      if (!cell) continue;

      // Reset dynamic classes (keep terrain)
      cell.classList.remove("rc-obstacle","rc-visited","rc-rover",
                            "rc-waypoint-pending","rc-waypoint-reached");
      cell.innerHTML = "";

      if (obstacleSet.has(key)) {
        cell.classList.add("rc-obstacle");
        const s = document.createElement("span");
        s.className = "obs-glyph"; s.textContent = "✕";
        cell.appendChild(s);
        continue;
      }

      // Rover
      if (x === frame.x && y === frame.y) {
        cell.classList.add("rc-rover");
        const s = document.createElement("span");
        s.className = "rover-glyph";
        s.textContent = DIR_ARROWS_R[frame.direction] || "▶";
        cell.appendChild(s);
        continue;
      }

      // Waypoints
      if (wpMap[key]) {
        const wp = wpMap[key];
        const reached = frame.waypointsDone.has(wp.name);
        cell.classList.add(reached ? "rc-waypoint-reached" : "rc-waypoint-pending");
        const s = document.createElement("span");
        s.className = "wp-glyph";
        s.textContent = reached ? "★" : "◎";
        cell.appendChild(s);
        continue;
      }

      // Path trail
      if (pathSet.has(key)) {
        cell.classList.add("rc-visited");
        const dot = document.createElement("div");
        dot.className = "trail-dot";
        cell.appendChild(dot);
      }
    }
  }

  // Update telemetry sidebar
  const bat = frame.battery || {};
  const pct = bat.percentage ?? 100;
  const batColor = pct > 60 ? "#22c55e" : pct > 30 ? "#f59e0b" : "#ef4444";

  const cmdLabels = { M:"MOVE", L:"TURN L", R:"TURN R", S:"SOLAR", START:"START" };
  document.getElementById("rt-cmd").textContent   = cmdLabels[frame.command] || frame.command;
  document.getElementById("rt-pos").textContent   = `(${frame.x}, ${frame.y})`;
  document.getElementById("rt-dir").textContent   = frame.direction;
  document.getElementById("rt-bat-pct").textContent = `${pct.toFixed(1)}%`;
  document.getElementById("rt-bat-sub").textContent =
    `${bat.charge ?? "?"} / ${bat.max_charge ?? "?"} units`;
  document.getElementById("rt-event").textContent  = frame.eventType.replace("_"," ");

  const fill = document.getElementById("rt-bat-fill");
  fill.style.width      = `${pct}%`;
  fill.style.background = batColor;

  // Waypoints list
  const wpList = document.getElementById("rt-waypoints");
  wpList.innerHTML = "";
  for (const wp of (frame.waypoints || [])) {
    const done = frame.waypointsDone.has(wp.name);
    const item = document.createElement("div");
    item.className = `rt-wp-item ${done ? "rt-wp-done" : "rt-wp-todo"}`;
    item.innerHTML = `<span>${done ? "✔" : "○"}</span> ${wp.name}`;
    wpList.appendChild(item);
  }

  // Scrubber + step badge
  document.getElementById("replay-scrubber").value = idx;
  document.getElementById("replay-step-badge").textContent =
    `Frame ${idx + 1} / ${replayFrames.length}`;
}

// ── Replay controls ───────────────────────────────────────────────────────────

function startReplay() {
  if (!replayData) return;

  // Stop any running playback
  stopReplayTimer();

  // Build frames
  replayFrames = buildReplayFrames(replayData);
  replayCursor = 0;

  if (replayFrames.length === 0) return;

  // Show panel, set title
  const panel = document.getElementById("replay-panel");
  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
  document.getElementById("replay-mission-name").textContent =
    replayData.mission_name || "Unknown";

  // Configure scrubber
  const scrubber = document.getElementById("replay-scrubber");
  scrubber.max   = replayFrames.length - 1;
  scrubber.value = 0;
  document.getElementById("scrubber-max").textContent = replayFrames.length - 1;

  // Build grid DOM
  buildReplayGrid(replayData.grid.width, replayData.grid.height);

  // Render first frame
  renderReplayFrame(0);
}

function closeReplay() {
  stopReplayTimer();
  document.getElementById("replay-panel").classList.add("hidden");
  replayFrames = [];
  replayCursor = 0;
}

function toggleReplayPlay() {
  const btn = document.getElementById("replay-play-btn");
  if (replayTimer) {
    stopReplayTimer();
    btn.innerHTML = "&#9654;";
    btn.classList.remove("playing");
  } else {
    btn.innerHTML = "&#9646;&#9646;";
    btn.classList.add("playing");
    replayTimer = setInterval(() => {
      if (replayCursor >= replayFrames.length - 1) {
        stopReplayTimer();
        btn.innerHTML = "&#9654;";
        btn.classList.remove("playing");
        return;
      }
      renderReplayFrame(replayCursor + 1);
    }, replaySpeed);
  }
}

function stopReplayTimer() {
  if (replayTimer) { clearInterval(replayTimer); replayTimer = null; }
}

function replayStepForward()  { stopReplayTimer(); renderReplayFrame(replayCursor + 1); }
function replayStepBack()     { stopReplayTimer(); renderReplayFrame(replayCursor - 1); }
function replayGoStart()      { stopReplayTimer(); renderReplayFrame(0); }
function replayGoEnd()        { stopReplayTimer(); renderReplayFrame(replayFrames.length - 1); }
function scrubReplay(val)     { stopReplayTimer(); renderReplayFrame(parseInt(val, 10)); }

function updateReplaySpeed(val) {
  replaySpeed = parseInt(val, 10);
  document.getElementById("replay-speed-val").textContent = `${val}ms`;
  // Restart timer if playing
  if (replayTimer) { stopReplayTimer(); toggleReplayPlay(); }
}

// ── Hook loadMission to store replayData and show/hide REPLAY button ──────────

const _origLoadMission = loadMission;
loadMission = async function(filename) {
  const result = await _origLoadMission.call(this, filename);
  // After load, stash the data for replay
  if (filename) {
    const data = await apiFetch(`/api/analytics/mission/${encodeURIComponent(filename)}`);
    if (data && !data.error) {
      replayData = data;
      document.getElementById("btn-replay").classList.remove("hidden");
    }
  } else {
    document.getElementById("btn-replay").classList.add("hidden");
  }
  return result;
};
