"""
simulator.py — Agrani Naval Surveillance System
Simulation mode: spawns 10 virtual Agrani nodes at real Indian coastal coordinates.
Generates realistic, randomised sensor readings with occasional threat spikes.
Streams data through the same /api/ingest endpoint as real hardware.

Node locations (real Indian coastal/naval sites):
  AGRANI-001  Mumbai        (19.0760, 72.8777)
  AGRANI-002  Chennai       (13.0827, 80.2707)
  AGRANI-003  Visakhapatnam (17.6868, 83.2185)
  AGRANI-004  Kochi         (9.9312,  76.2673)
  AGRANI-005  Port Blair    (11.6234, 92.7265)
  AGRANI-006  Lakshadweep   (10.5667, 72.6417)
  AGRANI-007  Dwarka        (22.2442, 68.9685)
  AGRANI-008  Paradip       (20.3167, 86.6117)
  AGRANI-009  Karwar        (14.8000, 74.1300)
  AGRANI-010  Mandapam      (9.2740,  79.1232)
"""

import time
import json
import random
import math
import threading
import logging
import datetime
import urllib.request
import urllib.error

logger = logging.getLogger("Simulator")

NODES = [
    {"node_id": "AGRANI-001", "name": "Mumbai Naval Base",         "lat": 19.0760, "lon": 72.8777},
    {"node_id": "AGRANI-002", "name": "Chennai Eastern Fleet",     "lat": 13.0827, "lon": 80.2707},
    {"node_id": "AGRANI-003", "name": "Visakhapatnam Submarine",   "lat": 17.6868, "lon": 83.2185},
    {"node_id": "AGRANI-004", "name": "Kochi Southern Command",    "lat":  9.9312, "lon": 76.2673},
    {"node_id": "AGRANI-005", "name": "Port Blair Andaman",        "lat": 11.6234, "lon": 92.7265},
    {"node_id": "AGRANI-006", "name": "Lakshadweep Outpost",       "lat": 10.5667, "lon": 72.6417},
    {"node_id": "AGRANI-007", "name": "Dwarka Gulf Station",       "lat": 22.2442, "lon": 68.9685},
    {"node_id": "AGRANI-008", "name": "Paradip Bay Monitor",       "lat": 20.3167, "lon": 86.6117},
    {"node_id": "AGRANI-009", "name": "Karwar Western Shore",      "lat": 14.8000, "lon": 74.1300},
    {"node_id": "AGRANI-010", "name": "Mandapam Gulf Mannar",      "lat":  9.2740, "lon": 79.1232},
]

# Probability of a threat spike event per node per cycle
SPIKE_PROBABILITY = 0.08


def _simulate_readings(node_id: str, spike: bool = False) -> dict:
    """Generate realistic sensor readings, optionally with a threat spike."""
    if spike:
        spike_type = random.choice(["diver", "watercraft", "submarine", "mine"])
        if spike_type == "diver":
            magnetic   = random.gauss(65, 10)
            doppler    = random.gauss(1.2, 0.3)
            ultrasonic = random.gauss(9, 2)
        elif spike_type == "watercraft":
            magnetic   = random.gauss(98, 18)
            doppler    = random.gauss(4.5, 0.8)
            ultrasonic = random.gauss(13, 3)
        elif spike_type == "submarine":
            magnetic   = random.gauss(190, 20)
            doppler    = random.gauss(1.5, 0.5)
            ultrasonic = random.gauss(5, 1.5)
        else:  # mine
            magnetic   = random.gauss(215, 15)
            doppler    = random.gauss(0.05, 0.03)
            ultrasonic = random.gauss(1.4, 0.3)
    else:
        # Normal ambient conditions with slight variation per node
        seed_offset = hash(node_id) % 10
        magnetic   = random.gauss(30 + seed_offset * 0.5, 6)
        doppler    = random.gauss(0.4, 0.2)
        ultrasonic = random.gauss(22 + seed_offset * 0.3, 4)

    return {
        "magnetic":   round(max(0, magnetic),   2),
        "doppler":    round(max(0, doppler),    3),
        "ultrasonic": round(max(0.3, ultrasonic), 2),
    }


def _assess_threat_local(readings: dict) -> tuple[str, bool]:
    """Mirror of firmware edge detection for simulation fidelity."""
    m, d, u = readings["magnetic"], readings["doppler"], readings["ultrasonic"]
    m_score = 3 if m >= 200 else (2 if m >= 150 else (1 if m >= 80  else 0))
    d_score = 3 if d >= 7.0 else (2 if d >= 5.0  else (1 if d >= 2.0  else 0))
    u_score = 3 if u <= 1.5 else (2 if u <= 4.0  else (1 if u <= 8.0  else 0))

    if m_score == 3 or d_score == 3 or u_score == 3:
        level = "CRITICAL"
    elif m_score == 2 or d_score == 2 or u_score == 2:
        level = "HIGH"
    elif (m_score + d_score + u_score) >= 2:
        level = "HIGH"
    elif (m_score + d_score + u_score) == 1:
        level = "MEDIUM"
    else:
        level = "LOW"

    return level, level in ("HIGH", "CRITICAL")


def _build_packet(node: dict, readings: dict, threat_level: str, alert: bool) -> dict:
    return {
        "node_id":   node["node_id"],
        "name":      node["name"],
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "location":  {"lat": node["lat"], "lon": node["lon"]},
        "sensor_readings": readings,
        "threat_level":    threat_level,
        "alert":           alert,
    }


def _post_packet(packet: dict, url: str) -> bool:
    payload = json.dumps(packet).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.getcode() == 200
    except Exception as e:
        logger.debug(f"Post failed for {packet['node_id']}: {e}")
        return False


def _node_thread(node: dict, ingest_url: str, stop_event: threading.Event):
    """Worker thread for a single simulated node."""
    node_id = node["node_id"]
    logger.info(f"[SIM] Node {node_id} started at ({node['lat']:.4f}, {node['lon']:.4f})")
    in_alert = False

    while not stop_event.is_set():
        spike    = random.random() < SPIKE_PROBABILITY
        readings = _simulate_readings(node_id, spike=spike)
        threat_level, alert = _assess_threat_local(readings)

        packet  = _build_packet(node, readings, threat_level, alert)
        success = _post_packet(packet, ingest_url)

        if alert:
            logger.warning(f"[SIM] {node_id} → {threat_level} | mag={readings['magnetic']} µT | ok={success}")
            in_alert = True
        else:
            if in_alert:
                logger.info(f"[SIM] {node_id} returned to LOW")
            in_alert = False

        interval = 1.0 if alert else 5.0
        stop_event.wait(interval + random.uniform(-0.2, 0.2))


class Simulator:
    """Manages all simulation node threads."""

    def __init__(self, ingest_url: str = "http://localhost:5000/api/ingest"):
        self.ingest_url = ingest_url
        self._stop      = threading.Event()
        self._threads   = []

    def start(self):
        logger.info(f"[SIM] Starting simulation with {len(NODES)} nodes → {self.ingest_url}")
        for node in NODES:
            t = threading.Thread(
                target=_node_thread,
                args=(node, self.ingest_url, self._stop),
                daemon=True,
                name=f"sim-{node['node_id']}",
            )
            t.start()
            self._threads.append(t)
            time.sleep(0.3)   # stagger starts to avoid DB write contention

    def stop(self):
        logger.info("[SIM] Stopping simulation threads")
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3)
        logger.info("[SIM] All simulation threads stopped")


# ─── Standalone run (without Flask) ──────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
    sim = Simulator()
    sim.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sim.stop()
