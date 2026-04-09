"""
anomaly_detection_edge.py — Agrani Naval Surveillance System
Local threshold-based anomaly detection running on the Raspberry Pi edge node.
Combines multi-sensor readings to assign a threat level and build the canonical
data packet for transmission to the central hub.

Threat Level Rules:
  LOW      — All readings within normal parameters
  MEDIUM   — One sensor crosses primary threshold
  HIGH     — Two or more sensors cross thresholds   OR  one sensor is extreme
  CRITICAL — Multiple sensors extreme OR magnetic > 200 µT (submarine/mine class)
"""

import datetime
import logging

logger = logging.getLogger("EdgeAnomalyDetection")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")

# ─── Threshold configuration ──────────────────────────────────────────────────
THRESHOLDS = {
    "magnetic": {
        "medium":   80.0,   # µT — metallic debris / small object
        "high":    150.0,   # µT — large metallic object / diver with gear
        "critical": 200.0,  # µT — submarine / mine class
    },
    "doppler": {
        "medium":   2.0,    # m/s — slow-moving diver / current anomaly
        "high":     5.0,    # m/s — fast-moving object / small watercraft
        "critical":  7.0,   # m/s — high-speed threat
    },
    "ultrasonic": {
        "medium":   8.0,    # m  — object within 8 m
        "high":     4.0,    # m  — object within 4 m (inverted: smaller = closer)
        "critical": 1.5,    # m  — object within 1.5 m (immediate proximity)
    },
}

# ─── Threat scoring ───────────────────────────────────────────────────────────
def _score_magnetic(val):
    t = THRESHOLDS["magnetic"]
    if val >= t["critical"]: return 3
    if val >= t["high"]:     return 2
    if val >= t["medium"]:   return 1
    return 0

def _score_doppler(val):
    t = THRESHOLDS["doppler"]
    if val >= t["critical"]: return 3
    if val >= t["high"]:     return 2
    if val >= t["medium"]:   return 1
    return 0

def _score_ultrasonic(val):
    """Note: lower distance = higher threat."""
    t = THRESHOLDS["ultrasonic"]
    if val <= t["critical"]: return 3
    if val <= t["high"]:     return 2
    if val <= t["medium"]:   return 1
    return 0

THREAT_LEVELS = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "CRITICAL"}

def assess_threat(sensor_readings: dict) -> tuple[str, bool]:
    """
    Compute overall threat level from sensor readings.
    Returns (threat_level: str, alert: bool)
    """
    m_score = _score_magnetic(sensor_readings.get("magnetic", 0))
    d_score = _score_doppler(sensor_readings.get("doppler", 0))
    u_score = _score_ultrasonic(sensor_readings.get("ultrasonic", 50))

    # Critical if any single sensor hits critical level
    if m_score == 3 or d_score == 3 or u_score == 3:
        level = "CRITICAL"
    # High if any sensor hits high OR two sensors hit medium+
    elif m_score == 2 or d_score == 2 or u_score == 2:
        level = "HIGH"
    elif (m_score + d_score + u_score) >= 2:
        level = "HIGH"
    elif (m_score + d_score + u_score) == 1:
        level = "MEDIUM"
    else:
        level = "LOW"

    alert = level in ("HIGH", "CRITICAL")
    logger.debug(
        f"Scores — magnetic:{m_score} doppler:{d_score} ultrasonic:{u_score} → {level}"
    )
    return level, alert


# ─── Packet builder ───────────────────────────────────────────────────────────
def build_packet(node_id: str, location: dict, sensor_readings: dict) -> dict:
    """
    Build the canonical Agrani data packet.

    Args:
        node_id: e.g. "AGRANI-001"
        location: {"lat": float, "lon": float}
        sensor_readings: {"magnetic": float, "doppler": float, "ultrasonic": float}

    Returns:
        Fully formed packet dict ready for JSON serialisation.
    """
    threat_level, alert = assess_threat(sensor_readings)
    packet = {
        "node_id":        node_id,
        "timestamp":      datetime.datetime.utcnow().isoformat() + "Z",
        "location":       location,
        "sensor_readings": sensor_readings,
        "threat_level":   threat_level,
        "alert":          alert,
    }
    if alert:
        logger.warning(f"[{node_id}] ALERT! Threat level: {threat_level} | Readings: {sensor_readings}")
    return packet


# ─── Standalone test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_cases = [
        {"magnetic": 30.0,  "doppler": 0.3,  "ultrasonic": 25.0},   # LOW
        {"magnetic": 90.0,  "doppler": 0.5,  "ultrasonic": 20.0},   # MEDIUM
        {"magnetic": 160.0, "doppler": 3.0,  "ultrasonic": 6.0},    # HIGH
        {"magnetic": 210.0, "doppler": 7.5,  "ultrasonic": 1.0},    # CRITICAL
    ]
    loc = {"lat": 19.0760, "lon": 72.8777}
    for i, readings in enumerate(test_cases):
        packet = build_packet(f"AGRANI-00{i+1}", loc, readings)
        print(f"  → {packet['threat_level']} | alert={packet['alert']}")
