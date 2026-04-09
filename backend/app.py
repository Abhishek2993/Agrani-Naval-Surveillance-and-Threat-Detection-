"""
app.py — Agrani Naval Surveillance System
Main Flask application entry point.

Usage:
  python app.py               # normal mode (no simulation)
  python app.py --simulate    # start with 10-node simulation

The app serves:
  - REST API  at /api/*  (defined in routes.py)
  - Frontend  at /       (serves frontend/index.html)
  - WebSocket via Socket.IO on same port
"""

import os
import sys
import argparse
import logging
from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("Agrani")

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
DB_PATH      = os.path.join(BASE_DIR, "agrani.db")


def create_app(simulate: bool = False, port: int = 5000) -> tuple:
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    app.config.update(
        SQLALCHEMY_DATABASE_URI    = f"sqlite:///{DB_PATH}",
        SQLALCHEMY_TRACK_MODIFICATIONS = False,
        SECRET_KEY                 = os.getenv("AGRANI_SECRET", "agrani-naval-2026"),
    )

    # ── Extensions ────────────────────────────────────────────────────────────
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading",
                        logger=False, engineio_logger=False)

    # Store socketio in app extensions for access in routes
    app.extensions["socketio"] = socketio

    # ── DB setup ──────────────────────────────────────────────────────────────
    from .models import db
    db.init_app(app)
    with app.app_context():
        db.create_all()
        logger.info(f"Database: {DB_PATH}")

    # ── Register blueprints ───────────────────────────────────────────────────
    from .routes import api as api_blueprint
    app.register_blueprint(api_blueprint)

    # ── Frontend routes ───────────────────────────────────────────────────────
    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/<path:filename>")
    def static_files(filename):
        return send_from_directory(FRONTEND_DIR, filename)

    # ── WebSocket events ──────────────────────────────────────────────────────
    @socketio.on("connect")
    def on_connect():
        logger.info(f"WS client connected")

    @socketio.on("disconnect")
    def on_disconnect():
        logger.info(f"WS client disconnected")

    @socketio.on("ping_nodes")
    def on_ping():
        """Client requests current node snapshot."""
        from .models import Node
        with app.app_context():
            nodes = [n.to_dict() for n in Node.query.all()]
        socketio.emit("nodes_snapshot", {"nodes": nodes})

    # ── Simulation mode ───────────────────────────────────────────────────────
    if simulate:
        import time
        def _start_sim(port=5000):
            time.sleep(2.0)   # wait for Flask to finish binding
            from .simulator import Simulator
            sim = Simulator(ingest_url=f"http://127.0.0.1:{port}/api/ingest")
            sim.start()
            logger.info("[SIM] Simulation running — 10 nodes active")

        import threading
        sim_thread = threading.Thread(target=_start_sim, args=(port,), daemon=True, name="sim-bootstrap")
        sim_thread.start()

    return app, socketio


def main():
    parser = argparse.ArgumentParser(description="Agrani Naval Surveillance Server")
    parser.add_argument("--simulate", action="store_true",
                        help="Start with 10-node simulation mode")
    parser.add_argument("--host",    default="0.0.0.0",  help="Bind host (default 0.0.0.0)")
    parser.add_argument("--port",    default=5000, type=int, help="Port (default 5000)")
    parser.add_argument("--debug",   action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  AGRANI Naval Surveillance & Threat Detection System")
    logger.info(f"  Simulation: {'ON' if args.simulate else 'OFF'}")
    logger.info(f"  Dashboard:  http://localhost:{args.port}/")
    logger.info("=" * 60)

    app, socketio = create_app(simulate=args.simulate, port=args.port)
    socketio.run(app, host=args.host, port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
