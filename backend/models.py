"""
models.py — Agrani Naval Surveillance System
SQLAlchemy database models for the Flask backend.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Node(db.Model):
    """Represents a deployed Agrani sensor node."""
    __tablename__ = "nodes"

    node_id      = db.Column(db.String(32),  primary_key=True)
    name         = db.Column(db.String(64),  nullable=True)
    lat          = db.Column(db.Float,       nullable=False, default=0.0)
    lon          = db.Column(db.Float,       nullable=False, default=0.0)
    last_seen    = db.Column(db.DateTime,    nullable=True)
    threat_level = db.Column(db.String(16),  nullable=False, default="LOW")
    alert        = db.Column(db.Boolean,     nullable=False, default=False)

    readings = db.relationship("SensorReading", backref="node", lazy="dynamic",
                               foreign_keys="SensorReading.node_id")

    def to_dict(self):
        last = self.readings.order_by(SensorReading.timestamp.desc()).first()
        return {
            "node_id":      self.node_id,
            "name":         self.name or self.node_id,
            "lat":          self.lat,
            "lon":          self.lon,
            "last_seen":    self.last_seen.isoformat() + "Z" if self.last_seen else None,
            "threat_level": self.threat_level,
            "alert":        self.alert,
            "last_reading": last.to_dict() if last else None,
        }


class SensorReading(db.Model):
    """Individual sensor reading record from a node."""
    __tablename__ = "sensor_readings"

    id              = db.Column(db.Integer,  primary_key=True, autoincrement=True)
    node_id         = db.Column(db.String(32), db.ForeignKey("nodes.node_id"), nullable=False, index=True)
    timestamp       = db.Column(db.DateTime,   nullable=False, default=datetime.utcnow, index=True)
    magnetic        = db.Column(db.Float,      nullable=False, default=0.0)
    doppler         = db.Column(db.Float,      nullable=False, default=0.0)
    ultrasonic      = db.Column(db.Float,      nullable=False, default=0.0)
    threat_level    = db.Column(db.String(16), nullable=False, default="LOW")
    ml_class        = db.Column(db.String(32), nullable=True)
    ml_confidence   = db.Column(db.Float,      nullable=True)
    alert           = db.Column(db.Boolean,    nullable=False, default=False)

    def to_dict(self):
        return {
            "id":            self.id,
            "node_id":       self.node_id,
            "timestamp":     self.timestamp.isoformat() + "Z",
            "magnetic":      self.magnetic,
            "doppler":       self.doppler,
            "ultrasonic":    self.ultrasonic,
            "threat_level":  self.threat_level,
            "ml_class":      self.ml_class,
            "ml_confidence": round(self.ml_confidence, 3) if self.ml_confidence else None,
            "alert":         self.alert,
        }
