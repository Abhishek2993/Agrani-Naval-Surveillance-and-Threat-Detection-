# AGRANI — Naval Surveillance & Threat Detection System
**Edge-deployed subsurface threat detection network for Indian coastal and harbour zones**

---

## Overview

AGRANI is a full-stack naval surveillance platform designed for the Indian Navy. It combines Raspberry Pi edge firmware, a machine-learning threat classifier, a real-time Flask backend, and a Leaflet.js live map dashboard to monitor underwater threats across 10 coastal deployment points.

```
agrani/
├── firmware/                  ← Raspberry Pi edge node code
│   ├── sensor_manager.py      ← BLE magnetic + Doppler + Ultrasonic sensors
│   ├── anomaly_detection_edge.py ← Threshold-based edge threat assessment
│   ├── power_manager.py       ← Sleep/wake battery cycle
│   └── transmitter.py        ← HTTP / MQTT / LoRa / BLE packet transmission
│
├── ml/                        ← Machine learning threat classifier
│   ├── generate_training_data.py  ← 50,000 synthetic samples (5 classes)
│   ├── train_model.py         ← RandomForest pipeline + evaluation
│   ├── model.pkl              ← Trained model (auto-generated)
│   └── label_encoder.pkl      ← Class label encoder (auto-generated)
│
├── backend/                   ← Flask REST + WebSocket server
│   ├── app.py                 ← Main entry point (Flask + Socket.IO)
│   ├── models.py              ← SQLAlchemy ORM (Node, SensorReading)
│   ├── routes.py              ← REST endpoints: /api/ingest, /nodes, /alerts
│   ├── ml_inference.py        ← Real-time ML prediction on ingest
│   ├── simulator.py           ← 10-node simulation engine
│   └── requirements.txt
│
├── frontend/                  ← Live dashboard
│   ├── index.html             ← Main page
│   ├── css/style.css          ← Dark navy theme
│   └── js/
│       ├── map.js             ← Leaflet map, markers, heatmap, zones
│       └── dashboard.js       ← Socket.IO, sidebar, alerts, Chart.js
│
└── start.sh                   ← One-command launcher
```

---

## Quick Start

```bash
# Clone / navigate to project root
cd "Naval security"

# Make launcher executable and run
chmod +x start.sh
bash start.sh
```

This will:
1. Create a Python virtual environment
2. Install all dependencies
3. Generate training data and train the ML model (first run only)
4. Start the Flask backend in **simulation mode** (10 virtual nodes)
5. Open the dashboard at `http://localhost:5000`

---

## Running Modes

### Simulation Mode (default via `start.sh`)
Spawns 10 virtual nodes at real Indian coastal coordinates with realistic sensor readings and random threat spikes:

| Node | Location | Coordinates |
|------|----------|-------------|
| AGRANI-001 | Mumbai Naval Base | 19.07°N 72.87°E |
| AGRANI-002 | Chennai Eastern Fleet | 13.08°N 80.27°E |
| AGRANI-003 | Visakhapatnam Submarine | 17.68°N 83.21°E |
| AGRANI-004 | Kochi Southern Command | 9.93°N 76.26°E |
| AGRANI-005 | Port Blair Andaman | 11.62°N 92.72°E |
| AGRANI-006 | Lakshadweep Outpost | 10.56°N 72.64°E |
| AGRANI-007 | Dwarka Gulf Station | 22.24°N 68.96°E |
| AGRANI-008 | Paradip Bay Monitor | 20.31°N 86.61°E |
| AGRANI-009 | Karwar Western Shore | 14.80°N 74.13°E |
| AGRANI-010 | Mandapam Gulf Mannar | 9.27°N 79.12°E |

### Manual Server Start
```bash
# Without simulation (awaiting real hardware nodes)
python -m backend.app

# With simulation
python -m backend.app --simulate

# Custom port / host
python -m backend.app --simulate --host 0.0.0.0 --port 8080
```

---

## Hardware Setup (Raspberry Pi)

### Wiring

| Component | Interface | Pi Pin |
|-----------|-----------|--------|
| QMC5883L Magnetic Sensor | I2C (SDA/SCL) | GPIO 2/3 |
| CDM324 Doppler Radar | GPIO Digital | GPIO 17 |
| JSN-SR04T Ultrasonic | GPIO Trig/Echo | GPIO 23/24 |

### Running on Pi
```bash
# Set node identity via env vars
export AGRANI_NODE_ID="AGRANI-001"
export AGRANI_LAT="19.0760"
export AGRANI_LON="72.8777"
export AGRANI_HUB_URL="http://192.168.1.100:5000/api/ingest"
export AGRANI_TRANSPORT="http"   # or: mqtt | lora | ble

# Run the firmware transmitter loop
cd firmware
python transmitter.py
```

### Transport options

| Transport | Range | Notes |
|-----------|-------|-------|
| `http` (WiFi) | ~100 m (AP coverage) | Primary, easiest to deploy |
| `mqtt` (WiFi) | ~100 m (AP coverage) | Requires Mosquitto broker |
| `lora` | 2–15 km | Requires SX1276 module, stub impl |
| `ble` | ~10 m | Stub impl, for relay nodes |

---

## API Reference

### `POST /api/ingest`
Submit sensor data from a node.

```json
{
  "node_id": "AGRANI-001",
  "timestamp": "2026-04-10T03:00:00Z",
  "location": { "lat": 19.076, "lon": 72.877 },
  "sensor_readings": {
    "magnetic": 45.2,
    "doppler": 0.8,
    "ultrasonic": 22.5
  },
  "threat_level": "LOW",
  "alert": false
}
```

### `GET /api/nodes`
Returns all known nodes with latest threat levels and sensor readings.

### `GET /api/alerts`
Returns the last 50 HIGH/CRITICAL alert events.

### `GET /api/history/<node_id>`
Returns the last 100 sensor readings for a specific node.

### `GET /api/stats`
System-wide summary (total nodes, total readings, critical/high counts).

---

## ML Threat Classification

The model is trained on **50,000 synthetic samples** across 5 classes:

| Class | Description | Key Signatures |
|-------|-------------|----------------|
| `normal` | Ambient sea activity | Low magnetic, low doppler, far ultrasonic |
| `diver` | Swimmer with dive gear | Medium magnetic, slow doppler, medium range |
| `small_watercraft` | Speedboat / RIB | Medium-high magnetic, fast doppler |
| `submarine` | Large metallic submersible | High magnetic (>150µT), slow, close |
| `mine` | Stationary metallic threat | Very high magnetic (>200µT), near-zero doppler, very close |

**Features used:** `magnetic_intensity`, `doppler_velocity`, `ultrasonic_distance`, `hour_of_day`, `baseline_deviation`

**Algorithm:** `RandomForestClassifier` (200 trees) with `StandardScaler` — typically achieves >94% accuracy on the test set.

---

## Dashboard Features

- **Live Map** — Leaflet.js centered on India [20.59°N, 78.96°E]
- **Naval Zone Overlays** — Arabian Sea, Bay of Bengal, Gulf of Mannar, Lakshadweep, Andaman Sea
- **Threat Markers** — 🟢 LOW / 🟡 MEDIUM / 🔴 HIGH / 🚨 Pulsing CRITICAL
- **Heatmap Toggle** — density overlay of threat activity along coastline
- **Live Sidebar** — all nodes sorted CRITICAL-first with real-time updates
- **Alert Banner** — flashing top bar when any CRITICAL node detected
- **Chart.js Sparklines** — per-node magnetic, doppler, ultrasonic history
- **ML Panel** — shows predicted class and confidence for selected node
- **WebSocket** — real-time push via Socket.IO; falls back to 5-second polling

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Edge firmware | Python, RPi.GPIO (simulated fallback) |
| ML model | scikit-learn (RandomForest), pandas, numpy |
| Backend | Flask 3, Flask-SocketIO, Flask-SQLAlchemy, SQLite |
| Frontend | HTML5, Vanilla CSS, Leaflet.js, Chart.js, Socket.IO |
| Comms | HTTP/WiFi (primary), MQTT, LoRa/BLE (stubs) |

---

## Security Notes

> ⚠️ This is a **demonstration / research prototype**. Before operational naval deployment:
> - Enable HTTPS with TLS certificates
> - Add API key or mutual-TLS authentication on `/api/ingest`
> - Replace SQLite with a hardened PostgreSQL instance
> - Harden the Raspberry Pi OS (disable SSH default credentials, firewall rules)
> - Encrypt data at rest and in transit
