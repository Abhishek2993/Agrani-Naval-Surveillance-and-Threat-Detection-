"""
power_manager.py — Agrani Naval Surveillance System
Battery power management for Raspberry Pi edge node.

Strategy:
  NORMAL mode:  Transmit every 5 s — sleep ~4.8 s between sensor reads
  ALERT mode:   Transmit every 1 s — no sleep (full power for rapid reporting)
  DEEP_SLEEP:   Full CPU suspend when no motion for > 5 minutes (optional)

Uses iterative sleep rather than true OS suspend for cross-platform compatibility.
On actual Pi hardware, you can configure /sys/power/state for deeper savings.
"""

import time
import logging

logger = logging.getLogger("PowerManager")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")

# ─── Timing constants (seconds) ───────────────────────────────────────────────
NORMAL_CYCLE_INTERVAL  = 5.0   # Transmit interval in normal mode
ALERT_CYCLE_INTERVAL   = 1.0   # Transmit interval when alert is active
NORMAL_SLEEP_DURATION  = 4.7   # Sleep within normal cycle (wakes for sensor read)
IDLE_TIMEOUT           = 300   # Seconds of no alerts before considering deep sleep


class PowerManager:
    """Manages the transmit/sleep duty cycle of the Agrani edge node."""

    def __init__(self):
        self._alert_mode     = False
        self._last_alert_ts  = None
        self._cycle_count    = 0
        logger.info("PowerManager initialised → NORMAL mode (5 s cycle)")

    # ── Public API ────────────────────────────────────────────────────────────

    def update_alert_state(self, alert: bool):
        """Call this after each packet assembly to adjust the power mode."""
        if alert:
            if not self._alert_mode:
                logger.warning("Switching to ALERT mode → 1 s transmit cycle")
            self._alert_mode    = True
            self._last_alert_ts = time.monotonic()
        else:
            if self._alert_mode:
                idle_for = time.monotonic() - (self._last_alert_ts or 0)
                if idle_for > IDLE_TIMEOUT:
                    logger.info(f"No alerts for {idle_for:.0f}s → returning to NORMAL mode")
                    self._alert_mode = False

    def sleep_until_next_cycle(self):
        """
        Sleep for the appropriate interval based on current power mode.
        Returns the mode that was active during this sleep.
        """
        self._cycle_count += 1
        if self._alert_mode:
            # In alert mode: minimal sleep to hit ~1 s cycle
            time.sleep(ALERT_CYCLE_INTERVAL)
            return "ALERT"
        else:
            # In normal mode: sleep for bulk of cycle to save power
            logger.debug(f"Cycle {self._cycle_count}: sleeping {NORMAL_SLEEP_DURATION}s")
            time.sleep(NORMAL_SLEEP_DURATION)
            return "NORMAL"

    @property
    def cycle_interval(self) -> float:
        return ALERT_CYCLE_INTERVAL if self._alert_mode else NORMAL_CYCLE_INTERVAL

    @property
    def mode(self) -> str:
        return "ALERT" if self._alert_mode else "NORMAL"

    def attempt_deep_sleep(self, duration_seconds: float = 60.0):
        """
        Attempt OS-level deep sleep on Raspberry Pi (requires root).
        Falls back to time.sleep on non-Pi hardware.
        """
        logger.info(f"Attempting deep sleep for {duration_seconds}s...")
        try:
            import subprocess
            # Wake-up via RTC or GPIO interrupt would be configured separately
            subprocess.run(
                ["sudo", "sh", "-c", f"echo +{int(duration_seconds)} > /sys/class/rtc/rtc0/wakealarm && echo mem > /sys/power/state"],
                check=True, timeout=5
            )
            logger.info("Deep sleep complete — waking up")
        except Exception as e:
            logger.warning(f"Deep sleep not available ({e}), using time.sleep fallback")
            time.sleep(duration_seconds)


# ─── Standalone demo ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    pm = PowerManager()
    for i in range(6):
        alert = (i in [2, 3])   # Simulate alerts on cycles 2 & 3
        pm.update_alert_state(alert)
        print(f"Cycle {i+1}: mode={pm.mode} | interval={pm.cycle_interval}s")
        time.sleep(pm.cycle_interval)
