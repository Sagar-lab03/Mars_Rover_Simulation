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
      <td><button class="btn-load-row" onclick="selectMission('${m.filename}')">Load</button></td>
    `;
    tbody.appendChild(tr);
  }
}

function selectMission(filename) {
  document.getElementById("mission-select").value = filename;
  loadMission(filename);
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  refreshMissions();
});
