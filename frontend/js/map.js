/**
 * map.js — AGRANI Naval Surveillance Dashboard
 * Leaflet.js map setup:
 *   - Dark themed tile layer
 *   - India centered at [20.5937, 78.9629], zoom 5
 *   - Naval zone overlays (Arabian Sea, Bay of Bengal, etc.)
 *   - Custom threat-level markers with pulse for CRITICAL
 *   - Leaflet.heat heatmap layer toggle
 *   - Popup with full sensor details
 */

// ── Map initialisation ────────────────────────────────────────────────────────
const map = L.map("map", {
  center:      [20.5937, 78.9629],
  zoom:        5,
  zoomControl: false,
  attributionControl: false,
});

// Dark tile layer (Jawg Dark / Carto Dark Matter)
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  attribution: "© OpenStreetMap © CARTO",
  subdomains:  "abcd",
  maxZoom:     19,
}).addTo(map);

// Custom zoom control position
L.control.zoom({ position: "bottomright" }).addTo(map);

// ── Naval zone overlays ───────────────────────────────────────────────────────
const NAVAL_ZONES = [
  {
    name: "Arabian Sea Western Command",
    coords: [[8, 65], [8, 77], [24, 77], [24, 65]],
    color: "#0077ff",
  },
  {
    name: "Bay of Bengal Eastern Fleet",
    coords: [[8, 80], [8, 100], [23, 100], [23, 80]],
    color: "#00d4ff",
  },
  {
    name: "Gulf of Mannar",
    coords: [[8.0, 77.5], [8.0, 79.5], [9.5, 79.5], [9.5, 77.5]],
    color: "#00ff88",
  },
  {
    name: "Lakshadweep Sea",
    coords: [[8, 71], [8, 74], [12, 74], [12, 71]],
    color: "#0044cc",
  },
  {
    name: "Andaman Sea",
    coords: [[6, 90], [6, 97], [15, 97], [15, 90]],
    color: "#00aacc",
  },
];

let zonesLayer = null;

function buildZonesLayer() {
  const group = L.layerGroup();
  NAVAL_ZONES.forEach((zone) => {
    const poly = L.polygon(zone.coords, {
      color:       zone.color,
      fillColor:   zone.color,
      fillOpacity: 0.04,
      weight:      1.5,
      dashArray:   "6 4",
      opacity:     0.5,
    });
    poly.bindTooltip(`<span style="font-family:'Orbitron',monospace;font-size:10px;color:${zone.color};letter-spacing:2px;">${zone.name}</span>`, {
      sticky:    true,
      className: "zone-tooltip",
    });
    group.addLayer(poly);
  });
  return group;
}

zonesLayer = buildZonesLayer();
zonesLayer.addTo(map);   // zones on by default

let zonesActive = true;
function toggleZones() {
  if (zonesActive) {
    map.removeLayer(zonesLayer);
    document.getElementById("btn-zones").classList.remove("active");
  } else {
    map.addLayer(zonesLayer);
    document.getElementById("btn-zones").classList.add("active");
  }
  zonesActive = !zonesActive;
}
document.getElementById("btn-zones").classList.add("active");


// ── Heatmap layer ─────────────────────────────────────────────────────────────
let heatLayer    = null;
let heatActive   = false;
let heatPoints   = [];   // [lat, lon, intensity]

function updateHeatmap(nodes) {
  heatPoints = nodes
    .filter((n) => n.lat && n.lon)
    .map((n) => {
      const intensity = { LOW: 0.2, MEDIUM: 0.5, HIGH: 0.75, CRITICAL: 1.0 }[n.threat_level] || 0.1;
      return [n.lat, n.lon, intensity];
    });
  if (heatLayer && heatActive) {
    heatLayer.setLatLngs(heatPoints);
  }
}

function toggleHeatmap() {
  if (!heatActive) {
    heatLayer = L.heatLayer(heatPoints, {
      radius:    60,
      blur:      40,
      maxZoom:   10,
      gradient: { 0.2: "#0077ff", 0.5: "#ffd600", 0.75: "#ff6d00", 1.0: "#ff1744" },
    }).addTo(map);
    heatActive = true;
    document.getElementById("btn-heatmap").classList.add("active");
  } else {
    map.removeLayer(heatLayer);
    heatLayer   = null;
    heatActive  = false;
    document.getElementById("btn-heatmap").classList.remove("active");
  }
}


// ── Marker management ─────────────────────────────────────────────────────────
const nodeMarkers = {};   // node_id → { marker, pulseEl }

const THREAT_COLORS = {
  LOW:      "#00e676",
  MEDIUM:   "#ffd600",
  HIGH:     "#ff6d00",
  CRITICAL: "#ff1744",
};

function createMarkerIcon(threatLevel, nodeId) {
  const color  = THREAT_COLORS[threatLevel] || "#00e676";
  const isCrit = threatLevel === "CRITICAL";

  const pulse = isCrit
    ? `<div class="pulse-ring"></div><div class="pulse-ring" style="animation-delay:0.5s"></div>`
    : "";

  const html = `
    <div style="position:relative;width:22px;height:22px;">
      ${pulse}
      <div style="
        position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
        width:16px; height:16px; border-radius:50%;
        background:${color};
        border: 2px solid rgba(255,255,255,0.6);
        box-shadow: 0 0 ${isCrit ? "20px 6px" : "10px 3px"} ${color};
        ${isCrit ? "animation: blink 0.6s infinite;" : ""}
      "></div>
    </div>
  `;
  return L.divIcon({
    html,
    iconSize:   [22, 22],
    iconAnchor: [11, 11],
    className:  "",
  });
}

function buildPopupHtml(node) {
  const r        = node.last_reading || {};
  const tl       = node.threat_level || "LOW";
  const tlColor  = THREAT_COLORS[tl] || "#00e676";
  const ts       = node.last_seen
    ? new Date(node.last_seen).toLocaleTimeString()
    : "—";

  return `
    <div class="popup-header">⚓ ${node.node_id}</div>
    <div class="popup-threat" style="color:${tlColor};">▶ ${tl}</div>
    <div class="popup-row"><span class="popup-key">Location</span><span class="popup-val">${(+node.lat).toFixed(4)}°N ${(+node.lon).toFixed(4)}°E</span></div>
    <div class="popup-row"><span class="popup-key">Name</span><span class="popup-val">${escapeHtml(node.name || node.node_id)}</span></div>
    <hr style="border-color:rgba(0,212,255,0.15);margin:6px 0;">
    <div class="popup-row"><span class="popup-key">🧲 Magnetic</span><span class="popup-val">${r.magnetic ?? "—"} µT</span></div>
    <div class="popup-row"><span class="popup-key">📡 Doppler</span><span class="popup-val">${r.doppler ?? "—"} m/s</span></div>
    <div class="popup-row"><span class="popup-key">📏 Ultrasonic</span><span class="popup-val">${r.ultrasonic ?? "—"} m</span></div>
    ${r.ml_class ? `<div class="popup-row"><span class="popup-key">🧠 ML Class</span><span class="popup-val">${r.ml_class}</span></div>` : ""}
    <div class="popup-time">Last updated: ${ts}</div>
  `;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/**
 * Place or update a node marker on the map.
 * Called by dashboard.js whenever node data arrives.
 */
window.upsertNodeMarker = function (node) {
  if (!node.lat || !node.lon) return;

  const icon = createMarkerIcon(node.threat_level, node.node_id);

  if (nodeMarkers[node.node_id]) {
    const { marker } = nodeMarkers[node.node_id];
    marker.setIcon(icon);
    marker.setLatLng([node.lat, node.lon]);
    marker.setPopupContent(buildPopupHtml(node));
  } else {
    const marker = L.marker([node.lat, node.lon], { icon })
      .addTo(map)
      .bindPopup(buildPopupHtml(node), { maxWidth: 280, className: "agrani-popup" });

    marker.on("click", () => {
      window.onNodeMarkerClick && window.onNodeMarkerClick(node.node_id);
    });

    nodeMarkers[node.node_id] = { marker };
  }
};

/**
 * Update all node markers from a nodes array.
 */
window.renderAllMarkers = function (nodes) {
  nodes.forEach((n) => window.upsertNodeMarker(n));
  updateHeatmap(nodes);
};

/**
 * Focus the map on a specific node.
 */
window.focusNode = function (nodeId) {
  const entry = nodeMarkers[nodeId];
  if (entry) {
    map.setView(entry.marker.getLatLng(), 8, { animate: true });
    entry.marker.openPopup();
  }
};
