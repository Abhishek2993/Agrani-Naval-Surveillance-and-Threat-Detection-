"""
transmitter.py — Agrani Naval Surveillance System
Handles transmission of sensor data packets from the edge node (Raspberry Pi)
to the central Flask hub.

Supported transports:
  1. WiFi / Ethernet — HTTP POST to Flask API (primary)
  2. MQTT over WiFi   — publish to broker (mosquitto)
  3. LoRa             — stub for SX1276 via spidev (long-range, low bandwidth)
  4. BLE              — stub for BlueZ HCI advertisement beacon

Select transport by setting TRANSPORT env variable or passing at init.
"""

import json
import time
import logging
import os
import socket

logger = logging.getLogger("Transmitter")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")

# ─── Default config (override via env vars) ───────────────────────────────────
DEFAULT_HUB_URL   = os.getenv("AGRANI_HUB_URL",  "http://localhost:5000/api/ingest")
DEFAULT_TRANSPORT = os.getenv("AGRANI_TRANSPORT", "http")   # http | mqtt | lora | ble
MQTT_BROKER       = os.getenv("AGRANI_MQTT_BROKER", "localhost")
MQTT_PORT         = int(os.getenv("AGRANI_MQTT_PORT", "1883"))
MQTT_TOPIC        = "agrani/sensor"
HTTP_TIMEOUT      = 5   # seconds


class Transmitter:
    def __init__(self, transport: str = DEFAULT_TRANSPORT, hub_url: str = DEFAULT_HUB_URL):
        self.transport = transport.lower()
        self.hub_url   = hub_url
        self._mqtt_client = None
        self._setup()
        logger.info(f"Transmitter ready — transport: {self.transport.upper()}")

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup(self):
        if self.transport == "mqtt":
            self._setup_mqtt()
        elif self.transport == "lora":
            logger.warning("LoRa transport is a stub — packets will be logged only")
        elif self.transport == "ble":
            logger.warning("BLE transport is a stub — packets will be logged only")

    def _setup_mqtt(self):
        try:
            import paho.mqtt.client as mqtt
            self._mqtt_client = mqtt.Client(client_id="agrani_node")
            self._mqtt_client.on_connect = lambda c, u, f, rc: logger.info(f"MQTT connected: rc={rc}")
            self._mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self._mqtt_client.loop_start()
        except ImportError:
            logger.error("paho-mqtt not installed — falling back to HTTP")
            self.transport = "http"
        except Exception as e:
            logger.error(f"MQTT setup failed: {e} — falling back to HTTP")
            self.transport = "http"

    # ── Transmit ──────────────────────────────────────────────────────────────

    def send(self, packet: dict) -> bool:
        """
        Transmit a data packet. Returns True on success.
        Retries once on failure.
        """
        for attempt in range(2):
            try:
                if self.transport == "http":
                    return self._send_http(packet)
                elif self.transport == "mqtt":
                    return self._send_mqtt(packet)
                elif self.transport == "lora":
                    return self._send_lora(packet)
                elif self.transport == "ble":
                    return self._send_ble(packet)
            except Exception as e:
                logger.warning(f"Send attempt {attempt+1} failed: {e}")
                time.sleep(0.5)
        logger.error(f"Packet dropped for node {packet.get('node_id','?')} after retries")
        return False

    def _send_http(self, packet: dict) -> bool:
        import urllib.request
        import urllib.error
        payload = json.dumps(packet).encode("utf-8")
        req = urllib.request.Request(
            self.hub_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                status = resp.getcode()
                logger.debug(f"HTTP POST {self.hub_url} → {status}")
                return status == 200
        except urllib.error.URLError as e:
            raise ConnectionError(f"HTTP POST failed: {e}")

    def _send_mqtt(self, packet: dict) -> bool:
        if self._mqtt_client is None:
            raise RuntimeError("MQTT client not initialised")
        payload = json.dumps(packet)
        result  = self._mqtt_client.publish(MQTT_TOPIC, payload, qos=1)
        result.wait_for_publish(timeout=5)
        logger.debug(f"MQTT publish rc={result.rc}")
        return result.rc == 0

    def _send_lora(self, packet: dict) -> bool:
        """
        LoRa stub — in real deployment wire SX1276 via SPI.
        Payload must be < 255 bytes. Use compressed binary format for longer payloads.
        """
        payload = json.dumps(packet)
        if len(payload) > 200:
            # Trim sensor readings only for LoRa
            compact = {
                "n": packet["node_id"],
                "t": packet["timestamp"][-8:],
                "m": packet["sensor_readings"]["magnetic"],
                "d": packet["sensor_readings"]["doppler"],
                "u": packet["sensor_readings"]["ultrasonic"],
                "l": packet["threat_level"][0],
            }
            payload = json.dumps(compact)
        logger.info(f"[LoRa STUB] Would transmit {len(payload)}B: {payload[:80]}...")
        return True   # Stub always succeeds

    def _send_ble(self, packet: dict) -> bool:
        """
        BLE stub — in real deployment use BlueZ GATT or advertisement beacon.
        """
        logger.info(f"[BLE STUB] Would advertise node={packet['node_id']} threat={packet['threat_level']}")
        return True   # Stub always succeeds

    def close(self):
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()


# ─── Main firmware loop (entry point for Raspberry Pi) ───────────────────────
if __name__ == "__main__":
    from sensor_manager import SensorManager
    from anomaly_detection_edge import build_packet
    from power_manager import PowerManager

    NODE_ID  = os.getenv("AGRANI_NODE_ID", "AGRANI-001")
    LAT      = float(os.getenv("AGRANI_LAT", "19.0760"))
    LON      = float(os.getenv("AGRANI_LON", "72.8777"))

    sm   = SensorManager()
    pm   = PowerManager()
    tx   = Transmitter()

    logger.info(f"Starting Agrani edge node {NODE_ID} at ({LAT}, {LON})")

    try:
        while True:
            readings = sm.read_all()
            packet   = build_packet(NODE_ID, {"lat": LAT, "lon": LON}, readings)
            success  = tx.send(packet)
            pm.update_alert_state(packet["alert"])
            pm.sleep_until_next_cycle()
    except KeyboardInterrupt:
        logger.info("Shutting down node")
    finally:
        sm.cleanup()
        tx.close()
