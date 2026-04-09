"""
routes.py — Agrani Naval Surveillance System
Flask REST API routes:
  POST /api/ingest            — receive sensor packet, run ML, store, push WS event
  GET  /api/nodes             — all nodes with latest threat levels and positions
  GET  /api/alerts            — last 50 HIGH/CRITICAL alerts
  GET  /api/history/<node_id> — last 100 readings for a specific node
  GET  /api/stats             — system-wide stats
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from .models import db, Node, SensorReading
from . import ml_inference

logger = logging.getLogger("Routes")

api = Blueprint("api", __name__, url_prefix="/api")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _merge_threat_level(edge_level: str, ml_level: str) -> str:
    """Take the higher of the two threat levels for final decision."""
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    return edge_level if order.get(edge_level, 0) >= order.get(ml_level, 0) else ml_level


def _emit_event(socketio, event: str, data: dict):
    """Safe Socket.IO emit — no-op if socketio not configured."""
    try:
        socketio.emit(event, data)
    except Exception as e:
        logger.debug(f"WS emit error: {e}")


# ─── POST /api/ingest ─────────────────────────────────────────────────────────

@api.route("/ingest", methods=["POST"])
def ingest():
    """Receive a sensor packet, persist it, run ML inference, push WS alert."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    node_id  = data.get("node_id")
    loc      = data.get("location", {})
    readings = data.get("sensor_readings", {})

    if not node_id or not readings:
        return jsonify({"error": "Missing node_id or sensor_readings"}), 422

    # Run ML inference
    ml_result    = ml_inference.predict(data)
    edge_level   = data.get("threat_level", "LOW")
    final_level  = _merge_threat_level(edge_level, ml_result["ml_threat_level"])
    alert        = data.get("alert", False) or final_level in ("HIGH", "CRITICAL")

    try:
        ts = datetime.fromisoformat(data.get("timestamp", "").rstrip("Z"))
    except Exception:
        ts = datetime.utcnow()

    # Upsert Node record
    node = Node.query.get(node_id)
    if node is None:
        node = Node(node_id=node_id)
        db.session.add(node)
    node.name         = data.get("name", node_id)
    node.lat          = float(loc.get("lat", node.lat or 0.0))
    node.lon          = float(loc.get("lon", node.lon or 0.0))
    node.last_seen    = ts
    node.threat_level = final_level
    node.alert        = alert

    # Insert SensorReading
    reading = SensorReading(
        node_id       = node_id,
        timestamp     = ts,
        magnetic      = float(readings.get("magnetic",   0.0)),
        doppler       = float(readings.get("doppler",    0.0)),
        ultrasonic    = float(readings.get("ultrasonic", 0.0)),
        threat_level  = final_level,
        ml_class      = ml_result.get("ml_class"),
        ml_confidence = ml_result.get("ml_confidence"),
        alert         = alert,
    )
    db.session.add(reading)
    db.session.commit()

    # Push WebSocket event to all connected clients
    socketio = current_app.extensions.get("socketio")
    event_data = {
        "node_id":      node_id,
        "threat_level": final_level,
        "ml_class":     ml_result.get("ml_class"),
        "alert":        alert,
        "lat":          node.lat,
        "lon":          node.lon,
        "timestamp":    ts.isoformat() + "Z",
        "readings":     readings,
    }
    _emit_event(socketio, "sensor_update", event_data)
    if alert:
        _emit_event(socketio, "threat_alert", event_data)

    return jsonify({
        "status":        "ok",
        "node_id":       node_id,
        "threat_level":  final_level,
        "ml_class":      ml_result.get("ml_class"),
        "ml_confidence": ml_result.get("ml_confidence"),
        "alert":         alert,
    }), 200


# ─── GET /api/nodes ───────────────────────────────────────────────────────────

@api.route("/nodes", methods=["GET"])
def get_nodes():
    """Return all known nodes with their latest positions and threat levels."""
    nodes = Node.query.all()
    return jsonify([n.to_dict() for n in nodes]), 200


# ─── GET /api/alerts ──────────────────────────────────────────────────────────

@api.route("/alerts", methods=["GET"])
def get_alerts():
    """Return the last 50 HIGH or CRITICAL alert readings."""
    alerts = (SensorReading.query
              .filter(SensorReading.alert == True)
              .order_by(SensorReading.timestamp.desc())
              .limit(50)
              .all())
    return jsonify([a.to_dict() for a in alerts]), 200


# ─── GET /api/history/<node_id> ───────────────────────────────────────────────

@api.route("/history/<node_id>", methods=["GET"])
def get_history(node_id):
    """Return the last 100 readings for a specific node."""
    readings = (SensorReading.query
                .filter_by(node_id=node_id)
                .order_by(SensorReading.timestamp.desc())
                .limit(100)
                .all())
    return jsonify([r.to_dict() for r in readings]), 200


# ─── GET /api/stats ───────────────────────────────────────────────────────────

@api.route("/stats", methods=["GET"])
def get_stats():
    """System-wide summary stats."""
    total_nodes    = Node.query.count()
    total_readings = SensorReading.query.count()
    critical_nodes = Node.query.filter_by(threat_level="CRITICAL").count()
    high_nodes     = Node.query.filter_by(threat_level="HIGH").count()
    return jsonify({
        "total_nodes":    total_nodes,
        "total_readings": total_readings,
        "critical_nodes": critical_nodes,
        "high_nodes":     high_nodes,
    }), 200
