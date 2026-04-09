"""
sensor_manager.py — Agrani Naval Surveillance System
Raspberry Pi edge node: interfaces with three sensors
  1. Nano BLE Magnetic Sensor (I2C) — detects ferromagnetic objects
  2. Doppler Radar Sensor (UART/GPIO) — detects motion & velocity
  3. Waterproof Ultrasonic Sensor (GPIO) — measures proximity

In SIMULATION mode (no physical hardware), returns realistic randomised values.
"""

import time
import random
import math
import logging

logger = logging.getLogger("SensorManager")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")

# ─── Hardware availability flag ───────────────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    import smbus2
    HARDWARE_AVAILABLE = True
    logger.info("Hardware GPIO & I2C available — running in HARDWARE mode")
except ImportError:
    HARDWARE_AVAILABLE = False
    logger.warning("RPi.GPIO / smbus2 not found — running in SIMULATION mode")

# ─── GPIO Pins ────────────────────────────────────────────────────────────────
ULTRASONIC_TRIG_PIN = 23
ULTRASONIC_ECHO_PIN = 24
DOPPLER_GPIO_PIN    = 17   # digital output from radar module

# ─── I2C Config (BLE Magnetic Sensor — e.g. HMC5883L / QMC5883L) ─────────────
I2C_BUS       = 1
MAG_ADDR      = 0x0D   # QMC5883L default address
MAG_REG_DATA  = 0x00
MAG_REG_CTRL  = 0x09
MAG_CTRL_VAL  = 0x1D   # Continuous mode, 200Hz, 8G range

# ─── Hardware setup ───────────────────────────────────────────────────────────
def setup_hardware():
    """Initialise GPIO pins and I2C bus."""
    if not HARDWARE_AVAILABLE:
        return None, None
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(ULTRASONIC_TRIG_PIN, GPIO.OUT)
        GPIO.setup(ULTRASONIC_ECHO_PIN, GPIO.IN)
        GPIO.setup(DOPPLER_GPIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.output(ULTRASONIC_TRIG_PIN, False)
        time.sleep(0.1)

        bus = smbus2.SMBus(I2C_BUS)
        bus.write_byte_data(MAG_ADDR, MAG_REG_CTRL, MAG_CTRL_VAL)
        logger.info("Hardware setup complete: GPIO + I2C initialised")
        return bus, GPIO
    except Exception as e:
        logger.error(f"Hardware setup failed: {e}")
        return None, None


# ─── Magnetic Sensor ──────────────────────────────────────────────────────────
def read_magnetic(bus):
    """
    Read magnetic field intensity from QMC5883L via I2C.
    Returns resultant field strength in microtesla (µT).
    """
    if not HARDWARE_AVAILABLE or bus is None:
        return _sim_magnetic()
    try:
        data = bus.read_i2c_block_data(MAG_ADDR, MAG_REG_DATA, 6)
        x = _twos_complement(data[1] << 8 | data[0], 16)
        y = _twos_complement(data[3] << 8 | data[2], 16)
        z = _twos_complement(data[5] << 8 | data[4], 16)
        # Scale to µT (8G range, 3000 LSB/G → 1 LSB = 0.333 µT)
        scale = 0.333
        magnitude = math.sqrt(x**2 + y**2 + z**2) * scale
        return round(magnitude, 2)
    except Exception as e:
        logger.warning(f"Magnetic read error: {e}")
        return _sim_magnetic()


def _twos_complement(val, bits):
    if val >= (1 << (bits - 1)):
        val -= (1 << bits)
    return val


def _sim_magnetic():
    """Simulate magnetic field with occasional spikes."""
    base = random.gauss(35.0, 5.0)   # Typical Earth field ~25–65 µT
    spike = random.choices([0, random.uniform(80, 220)], weights=[0.92, 0.08])[0]
    return round(abs(base + spike), 2)


# ─── Doppler Radar Sensor ─────────────────────────────────────────────────────
def read_doppler(gpio=None):
    """
    Read Doppler radar motion signal. Returns estimated velocity (m/s).
    Hardware: digital HIGH/LOW from CDM324 or similar module.
    Simulation: randomised velocity with occasional spikes.
    """
    if not HARDWARE_AVAILABLE or gpio is None:
        return _sim_doppler()
    try:
        # Simple digital: movement detected = 1
        digital_val = GPIO.input(DOPPLER_GPIO_PIN)
        # In real deployment, feed ADC output for actual velocity calculation
        # For now: binary → scaled estimate
        velocity = random.uniform(1.5, 4.0) if digital_val else random.uniform(0.0, 0.3)
        return round(velocity, 2)
    except Exception as e:
        logger.warning(f"Doppler read error: {e}")
        return _sim_doppler()


def _sim_doppler():
    """Simulate Doppler velocity with occasional high-speed events."""
    base = random.gauss(0.5, 0.3)
    spike = random.choices([0, random.uniform(3.0, 8.0)], weights=[0.90, 0.10])[0]
    return round(max(0.0, base + spike), 2)


# ─── Ultrasonic Sensor ────────────────────────────────────────────────────────
def read_ultrasonic(gpio=None):
    """
    Waterproof ultrasonic sensor (JSN-SR04T or HC-SR04 waterproof variant).
    Returns distance in metres.
    """
    if not HARDWARE_AVAILABLE or gpio is None:
        return _sim_ultrasonic()
    try:
        # Send 10µs trigger pulse
        GPIO.output(ULTRASONIC_TRIG_PIN, True)
        time.sleep(0.00001)
        GPIO.output(ULTRASONIC_TRIG_PIN, False)

        # Wait for echo
        pulse_start = time.time()
        timeout = pulse_start + 0.04
        while GPIO.input(ULTRASONIC_ECHO_PIN) == 0:
            pulse_start = time.time()
            if pulse_start > timeout:
                raise TimeoutError("Echo start timeout")

        pulse_end = time.time()
        timeout = pulse_end + 0.04
        while GPIO.input(ULTRASONIC_ECHO_PIN) == 1:
            pulse_end = time.time()
            if pulse_end > timeout:
                raise TimeoutError("Echo end timeout")

        pulse_duration = pulse_end - pulse_start
        # Speed of sound in water ≈ 1500 m/s; in air ≈ 343 m/s
        # Using air (surface mode). For true underwater: multiply by (1500/343)/2
        distance = pulse_duration * 171.5   # metres
        return round(min(distance, 50.0), 2)
    except Exception as e:
        logger.warning(f"Ultrasonic read error: {e}")
        return _sim_ultrasonic()


def _sim_ultrasonic():
    """Simulate ultrasonic distance with occasional close-proximity events."""
    base = random.gauss(20.0, 4.0)
    close = random.choices([0, -random.uniform(14, 18)], weights=[0.90, 0.10])[0]
    return round(max(0.5, base + close), 2)


# ─── SensorManager class ──────────────────────────────────────────────────────
class SensorManager:
    """Unified interface for all three sensors."""

    def __init__(self):
        self.bus, self.gpio = setup_hardware()
        logger.info("SensorManager ready")

    def read_all(self):
        """Read all three sensors and return a dict of values."""
        magnetic   = read_magnetic(self.bus)
        doppler    = read_doppler(self.gpio)
        ultrasonic = read_ultrasonic(self.gpio)
        reading = {
            "magnetic":   magnetic,
            "doppler":    doppler,
            "ultrasonic": ultrasonic,
        }
        logger.debug(f"Sensor readings: {reading}")
        return reading

    def cleanup(self):
        """Release GPIO resources."""
        if HARDWARE_AVAILABLE:
            try:
                GPIO.cleanup()
            except Exception:
                pass


# ─── Standalone test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    sm = SensorManager()
    try:
        for i in range(10):
            readings = sm.read_all()
            print(f"[{i+1}] {readings}")
            time.sleep(1)
    finally:
        sm.cleanup()
