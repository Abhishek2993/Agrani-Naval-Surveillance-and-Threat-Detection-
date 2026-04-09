"""
ml_inference.py — Agrani Naval Surveillance System
Loads the trained RandomForest pipeline and exposes a predict() function
for real-time threat classification on incoming sensor packets.
"""

import os
import pickle
import logging
import numpy as np
from datetime import datetime

logger = logging.getLogger("MLInference")

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ML_DIR     = os.path.join(BASE_DIR, "..", "ml")
MODEL_PATH = os.path.join(ML_DIR, "model.pkl")
LE_PATH    = os.path.join(ML_DIR, "label_encoder.pkl")

# ─── Threat mapping: ML class → Agrani threat level ──────────────────────────
CLASS_TO_THREAT = {
    "normal":           "LOW",
    "diver":            "MEDIUM",
    "small_watercraft": "HIGH",
    "submarine":        "CRITICAL",
    "mine":             "CRITICAL",
}

# ─── Rolling baseline per node (for baseline_deviation feature) ───────────────
_node_baselines: dict[str, list] = {}
BASELINE_WINDOW = 12   # last 12 readings (~60 s at 5-s cycle)


def _get_baseline_deviation(node_id: str, current_magnetic: float) -> float:
    history = _node_baselines.setdefault(node_id, [])
    history.append(current_magnetic)
    if len(history) > BASELINE_WINDOW:
        history.pop(0)
    if len(history) < 3:
        return 0.0
    mean = sum(history) / len(history)
    if mean == 0:
        return 0.0
    return round(abs((current_magnetic - mean) / mean) * 100, 2)


# ─── Model loader ─────────────────────────────────────────────────────────────
_pipeline     = None
_label_encoder = None


def _load_model():
    global _pipeline, _label_encoder
    if _pipeline is not None:
        return True
    if not os.path.exists(MODEL_PATH):
        logger.error(f"Model not found at {MODEL_PATH} — run ml/train_model.py first")
        return False
    try:
        with open(MODEL_PATH, "rb") as f:
            _pipeline = pickle.load(f)
        with open(LE_PATH, "rb") as f:
            _label_encoder = pickle.load(f)
        logger.info(f"ML model loaded from {MODEL_PATH}")
        return True
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return False


def predict(packet: dict) -> dict:
    """
    Run ML inference on a sensor packet.

    Args:
        packet: canonical Agrani packet dict (must contain node_id, sensor_readings, timestamp)

    Returns:
        dict with keys: ml_class, ml_confidence, ml_threat_level
    """
    if not _load_model():
        return {"ml_class": "unknown", "ml_confidence": 0.0, "ml_threat_level": packet.get("threat_level", "LOW")}

    readings = packet.get("sensor_readings", {})
    node_id  = packet.get("node_id", "UNKNOWN")

    # Parse hour from timestamp
    try:
        ts = packet.get("timestamp", "")
        hour = datetime.fromisoformat(ts.rstrip("Z")).hour if ts else datetime.utcnow().hour
    except Exception:
        hour = datetime.utcnow().hour

    magnetic   = float(readings.get("magnetic",   30.0))
    doppler    = float(readings.get("doppler",     0.5))
    ultrasonic = float(readings.get("ultrasonic", 20.0))
    baseline_dev = _get_baseline_deviation(node_id, magnetic)

    X = np.array([[magnetic, doppler, ultrasonic, hour, baseline_dev]])

    try:
        label_idx   = int(_pipeline.predict(X)[0])
        proba       = _pipeline.predict_proba(X)[0]
        confidence  = float(proba[label_idx])
        class_name  = _label_encoder.classes_[label_idx]
        threat_level = CLASS_TO_THREAT.get(class_name, "LOW")
        return {
            "ml_class":        class_name,
            "ml_confidence":   round(confidence, 3),
            "ml_threat_level": threat_level,
        }
    except Exception as e:
        logger.error(f"Inference error: {e}")
        return {"ml_class": "error", "ml_confidence": 0.0, "ml_threat_level": "LOW"}


# Pre-load on import
_load_model()
