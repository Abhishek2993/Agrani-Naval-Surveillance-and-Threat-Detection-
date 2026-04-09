/**
 * dashboard.js — AGRANI Naval Surveillance Dashboard
 *
 * Handles:
 *  - Socket.IO real-time connection with 5-s polling fallback
 *  - Node list sidebar (sorted CRITICAL → LOW)
 *  - Critical alert banner
 *  - Right-panel sensor details and Chart.js sparklines
 *  - Countdown refresh timer
 *  - System status stats (header counters)
 */

// ── Config ─────────────────────────────────────────────────────────────────────
const API_BASE = window.location.origin;
const REFRESH_SECS = 5;

// ── State ──────────────────────────────────────────────────────────────────────
let nodeData = {};     // node_id → node dict
let selectedNodeId = null;
let countdown = REFRESH_SECS;
let refreshTimer = null;
let alertDismissed = false;
let socketConnected = false;

// Chart.js instances
let charts = { magnetic: null, doppler: null, ultrasonic: null };

// Colour mapping
const THREAT_COLORS = {
    LOW: "#00e676",
    MEDIUM: "#ffd600",
    HIGH: "#ff6d00",
    CRITICAL: "#ff1744",
};
const THREAT_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

// ── Clock ──────────────────────────────────────────────────────────────────────
function updateClock() {
    const now = new Date();
    document.getElementById("clock").textContent =
        now.toUTCString().slice(17, 25) + " UTC";
}
setInterval(updateClock, 1000);
updateClock();

// ── Socket.IO connection ───────────────────────────────────────────────────────
function initSocket() {
    let socket;
    try {
        socket = io(API_BASE, { transports: ["websocket", "polling"], timeout: 5000 });
    } catch (e) {
        console.warn("Socket.IO unavailable, using polling only");
        startPolling();
        return;
    }

    socket.on("connect", () => {
        socketConnected = true;
        setConnectionStatus("live");
        socket.emit("ping_nodes");
    });

    socket.on("disconnect", () => {
        socketConnected = false;
        setConnectionStatus("connecting");
    });

    socket.on("nodes_snapshot", (data) => {
        if (data.nodes) {
            data.nodes.forEach(updateNode);
            renderSidebar();
            window.renderAllMarkers(Object.values(nodeData));
        }
    });

    socket.on("sensor_update", (data) => {
        // Merge into nodeData
        if (!nodeData[data.node_id]) {
            nodeData[data.node_id] = { node_id: data.node_id };
        }
        const n = nodeData[data.node_id];
        n.lat = data.lat;
        n.lon = data.lon;
        n.threat_level = data.threat_level;
        n.alert = data.alert;
        n.last_seen = data.timestamp;
        n.last_reading = {
            magnetic: data.readings?.magnetic,
            doppler: data.readings?.doppler,
            ultrasonic: data.readings?.ultrasonic,
            ml_class: data.ml_class,
            ml_confidence: data.ml_confidence,
        };

        window.upsertNodeMarker(n);
        renderSidebar();
        updateHeaderStats();

        // Update right panel if this is the selected node
        if (data.node_id === selectedNodeId) {
            renderNodeDetail(n);
            fetchAndRenderCharts(data.node_id);
        }
    });

    socket.on("threat_alert", (data) => {
        if (data.alert && data.threat_level === "CRITICAL") {
            triggerCriticalAlert(data.node_id, data.threat_level);
        }
    });

    socket.on("connect_error", () => {
        if (!socketConnected) startPolling();
    });
}

// ── Polling fallback ─────────────────────────────────────────────────────────
let pollingActive = false;
function startPolling() {
    if (pollingActive) return;
    pollingActive = true;
    setConnectionStatus("warning");
    fetchNodes();
    refreshTimer = setInterval(() => {
        fetchNodes();
        countdown = REFRESH_SECS;
    }, REFRESH_SECS * 1000);

    // Countdown display
    setInterval(() => {
        countdown = Math.max(0, countdown - 1);
        const el = document.getElementById("refresh-countdown");
        if (el) el.textContent = countdown;
        if (countdown <= 0) countdown = REFRESH_SECS;
    }, 1000);
}

async function fetchNodes() {
    try {
        const resp = await fetch(`${API_BASE}/api/nodes`);
        if (!resp.ok) throw new Error(resp.statusText);
        const nodes = await resp.json();
        nodes.forEach(updateNode);
        renderSidebar();
        window.renderAllMarkers(Object.values(nodeData));
        updateHeaderStats();
        setConnectionStatus("live");
    } catch (e) {
        console.error("Failed to fetch nodes:", e);
        setConnectionStatus("warning");
    }
}

async function fetchAlerts() {
    try {
        const resp = await fetch(`${API_BASE}/api/alerts`);
        const alerts = await resp.json();
        renderAlertList(alerts);
        const criticalAlert = alerts.find((a) => a.threat_level === "CRITICAL" && !alertDismissed);
        if (criticalAlert) triggerCriticalAlert(criticalAlert.node_id, criticalAlert.threat_level);
    } catch (e) {
        // fail silently
    }
}

// ── Node state management ─────────────────────────────────────────────────────
function updateNode(node) {
    nodeData[node.node_id] = { ...nodeData[node.node_id], ...node };
}

// ── Sidebar rendering ─────────────────────────────────────────────────────────
function renderSidebar() {
    const list = document.getElementById("node-list");
    const nodes = Object.values(nodeData).sort((a, b) =>
        (THREAT_ORDER[a.threat_level] ?? 4) - (THREAT_ORDER[b.threat_level] ?? 4)
    );

    document.getElementById("sidebar-node-count").textContent = nodes.length;

    if (nodes.length === 0) {
        list.innerHTML = `<div class="loading-pulse">Waiting for nodes...</div>`;
        return;
    }

    list.innerHTML = nodes.map((n) => {
        const tl = n.threat_level || "LOW";
        const time = n.last_seen ? new Date(n.last_seen).toLocaleTimeString() : "—";
        const active = n.node_id === selectedNodeId ? " selected" : "";
        return `
      <div class="node-card ${tl.toLowerCase()}${active}" onclick="selectNode('${n.node_id}')">
        <div class="node-id">${n.node_id}</div>
        <div class="node-name">${escapeHtml(n.name || n.node_id)}</div>
        <div class="node-threat tl-${tl}">${tl}${n.alert ? " 🚨" : ""}</div>
        <div class="node-time">${time}</div>
      </div>
    `;
    }).join("");
}

function renderAlertList(alerts) {
    const el = document.getElementById("alert-list");
    if (!alerts || alerts.length === 0) {
        el.innerHTML = `<div class="loading-pulse">No recent alerts</div>`;
        return;
    }
    el.innerHTML = alerts.slice(0, 10).map((a) => `
    <div class="alert-item" onclick="selectNode('${a.node_id}')">
      <div class="alert-item-id">${a.node_id}</div>
      <div class="alert-item-meta">
        ${a.threat_level} · ${a.ml_class || "—"} ·
        ${new Date(a.timestamp).toLocaleTimeString()}
      </div>
    </div>
  `).join("");
}

// ── Node selection ─────────────────────────────────────────────────────────────
window.selectNode = function (nodeId) {
    selectedNodeId = nodeId;
    const node = nodeData[nodeId];
    if (!node) return;
    renderNodeDetail(node);
    fetchAndRenderCharts(nodeId);
    renderSidebar();   // re-render to highlight selected
    window.focusNode(nodeId);
};

// Called from map.js when a marker is clicked
window.onNodeMarkerClick = function (nodeId) {
    window.selectNode(nodeId);
};

// ── Right-panel node detail ───────────────────────────────────────────────────
function renderNodeDetail(node) {
    const tl = node.threat_level || "LOW";
    const r = node.last_reading || {};
    const el = document.getElementById("selected-node-info");

    el.innerHTML = `
    <div class="node-detail-header">${node.node_id}</div>
    <div class="node-detail-name">${escapeHtml(node.name || node.node_id)}</div>
    <div class="detail-badge ${tl}">${tl}</div>
    <div class="sensor-grid">
      <div class="sensor-cell">
        <div class="lbl">🧲 MAGNETIC</div>
        <div class="val">${r.magnetic ?? "—"}</div>
        <div class="unit">µT</div>
      </div>
      <div class="sensor-cell">
        <div class="lbl">📡 DOPPLER</div>
        <div class="val">${r.doppler ?? "—"}</div>
        <div class="unit">m/s</div>
      </div>
      <div class="sensor-cell">
        <div class="lbl">📏 ULTRASONIC</div>
        <div class="val">${r.ultrasonic ?? "—"}</div>
        <div class="unit">m</div>
      </div>
      <div class="sensor-cell">
        <div class="lbl">📍 LOCATION</div>
        <div class="val" style="font-size:10px;">${(+node.lat).toFixed(3)}°N</div>
        <div class="unit">${(+node.lon).toFixed(3)}°E</div>
      </div>
    </div>
  `;

    // ML panel
    const mlEl = document.getElementById("ml-panel");
    if (r.ml_class) {
        const conf = r.ml_confidence ? Math.round(r.ml_confidence * 100) : 0;
        mlEl.innerHTML = `
      <div class="ml-class-badge">${(r.ml_class || "unknown").toUpperCase().replace("_", " ")}</div>
      <div class="ml-confidence-bar">
        <div class="ml-confidence-fill" style="width:${conf}%"></div>
      </div>
      <div class="ml-confidence-label">Confidence: ${conf}%</div>
    `;
    } else {
        mlEl.innerHTML = `<div class="no-selection">No ML data yet</div>`;
    }

    document.getElementById("sensor-charts").style.display = "block";
}

// ── Chart.js sparklines ───────────────────────────────────────────────────────
function initChart(canvasId, label, color) {
    const ctx = document.getElementById(canvasId)?.getContext("2d");
    if (!ctx) return null;
    return new Chart(ctx, {
        type: "line",
        data: {
            labels: [],
            datasets: [{
                label,
                data: [],
                borderColor: color,
                backgroundColor: color + "22",
                borderWidth: 1.5,
                pointRadius: 0,
                tension: 0.3,
                fill: true,
            }],
        },
        options: {
            animation: { duration: 300 },
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { display: false },
                y: {
                    grid: { color: "rgba(0,212,255,0.06)" },
                    ticks: { color: "#7ab8d4", font: { size: 9 } },
                    border: { color: "transparent" },
                },
            },
        },
    });
}

function ensureCharts() {
    if (!charts.magnetic) charts.magnetic = initChart("chart-magnetic", "Magnetic (µT)", "#00d4ff");
    if (!charts.doppler) charts.doppler = initChart("chart-doppler", "Doppler (m/s)", "#00ff88");
    if (!charts.ultrasonic) charts.ultrasonic = initChart("chart-ultrasonic", "Ultrasonic (m)", "#ffd600");
}

async function fetchAndRenderCharts(nodeId) {
    ensureCharts();
    try {
        const resp = await fetch(`${API_BASE}/api/history/${nodeId}`);
        const readings = await resp.json();
        const rev = [...readings].reverse();   // oldest first for charts

        const labels = rev.map((r) => new Date(r.timestamp).toLocaleTimeString());
        const magnetics = rev.map((r) => r.magnetic);
        const dopplers = rev.map((r) => r.doppler);
        const ultrasonics = rev.map((r) => r.ultrasonic);

        function pushToChart(chart, labels, data) {
            chart.data.labels = labels.slice(-40);
            chart.data.datasets[0].data = data.slice(-40);
            chart.update("none");
        }

        pushToChart(charts.magnetic, labels, magnetics);
        pushToChart(charts.doppler, labels, dopplers);
        pushToChart(charts.ultrasonic, labels, ultrasonics);
    } catch (e) {
        console.error("Chart fetch error:", e);
    }
}

// ── Alert banner ───────────────────────────────────────────────────────────────
function triggerCriticalAlert(nodeId, level) {
    if (alertDismissed) return;
    const banner = document.getElementById("alert-banner");
    const msg = document.getElementById("alert-msg");
    msg.textContent = `🚨 CRITICAL THREAT — NODE ${nodeId}`;
    banner.style.display = "flex";
    document.querySelector(".main-layout").classList.add("has-alert");
    setConnectionStatus("critical");
}

window.dismissAlert = function () {
    alertDismissed = true;
    document.getElementById("alert-banner").style.display = "none";
    document.querySelector(".main-layout").classList.remove("has-alert");
    setTimeout(() => { alertDismissed = false; }, 30000);   // re-arm after 30 s
};

// ── Header stats ───────────────────────────────────────────────────────────────
function updateHeaderStats() {
    const nodes = Object.values(nodeData);
    const critical = nodes.filter((n) => n.threat_level === "CRITICAL").length;
    const high = nodes.filter((n) => n.threat_level === "HIGH").length;

    document.getElementById("stat-nodes").textContent = nodes.length;
    document.getElementById("stat-critical").textContent = critical;
    document.getElementById("stat-high").textContent = high;

    if (critical > 0) setConnectionStatus("critical");
    else if (high > 0) setConnectionStatus("warning");
}

// ── Connection status pill ────────────────────────────────────────────────────
function setConnectionStatus(state) {
    const pill = document.getElementById("conn-status");
    const labels = { live: "LIVE", warning: "ALERT", critical: "CRITICAL", connecting: "CONNECTING" };
    pill.className = `status-pill ${state}`;
    pill.querySelector(".status-label").textContent = labels[state] || "LIVE";
}

// ── Manual refresh ─────────────────────────────────────────────────────────────
window.manualRefresh = function () {
    fetchNodes();
    fetchAlerts();
    if (selectedNodeId) fetchAndRenderCharts(selectedNodeId);
};

// ── Utils ──────────────────────────────────────────────────────────────────────
function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
}

// ── Startup sequence ───────────────────────────────────────────────────────────
(async function init() {
    setConnectionStatus("connecting");
    await fetchNodes();
    await fetchAlerts();

    // Kick off Socket.IO; falls back to polling if unavailable
    initSocket();

    // Polling always supplements for alerts tab
    setInterval(fetchAlerts, 15000);

    // Refresh countdown display while in polling mode
    setInterval(() => {
        const el = document.getElementById("refresh-countdown");
        if (el && pollingActive) {
            el.textContent = countdown;
        }
    }, 1000);
})();
