"""
USB Serial reader + high-fidelity hardware simulation fallback.
Runs a background thread that continuously feeds the latest sensor
packet to the dashboard and ML pipeline.
"""

import time
import json
import math
import random
import threading
import datetime
from typing import Optional, Dict, Any, List

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

from solar_geometry import SolarGeometry
import database

class SerialReader:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                obj = super().__new__(cls)
                obj._setup()
                cls._instance = obj
            return cls._instance

    def _setup(self):
        self.port: Optional[Any] = None
        self.port_name: Optional[str] = None
        self.baud = 115200
        self.running = False
        self.sim_mode = True
        self.thread: Optional[threading.Thread] = None

        self.latest: Dict[str, Any] = self._default_pkt()
        self.geo = SolarGeometry()

        # Simulation knobs (controlled from UI)
        self.sim_weather = "Clear"          # Clear / Cloudy / Night / Fault
        self.sim_fault_type = "none"        # none / dust / shading / wiring / overheat

        self.start()

    def _default_pkt(self):
        return {
            "ts_real": time.time(),
            "v": 5.1, "i": 180.0, "p": 918.0,
            "t": 32.0, "h": 55.0, "l": 680,
            "plr": 1.35, "simulated": True
        }

    # ── Port management ──────────────────────────────────────────────

    def available_ports(self) -> List[str]:
        if not HAS_SERIAL:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, name: str) -> bool:
        if not HAS_SERIAL:
            return False
        try:
            self.disconnect()
            self.port = serial.Serial(name, self.baud, timeout=1.0)
            time.sleep(2.0)
            self.port_name = name
            self.sim_mode = False
            return True
        except Exception as e:
            print(f"[SERIAL] open failed: {e}")
            self.sim_mode = True
            return False

    def disconnect(self):
        if self.port and self.port.is_open:
            try:
                self.port.close()
            except Exception:
                pass
        self.port = None
        self.port_name = None
        self.sim_mode = True

    # ── Background worker ────────────────────────────────────────────

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        self.disconnect()

    def _loop(self):
        last_db = 0
        while self.running:
            now = time.time()

            if self.port and self.port.is_open:
                try:
                    line = self.port.readline().decode("utf-8", errors="ignore").strip()
                    if line.startswith("{") and line.endswith("}"):
                        pkt = json.loads(line)
                        pkt["ts_real"] = now
                        pkt["simulated"] = False
                        self.latest = pkt
                        if now - last_db >= 2.0:
                            last_db = now
                            database.insert_sample(pkt)
                except Exception:
                    self.disconnect()
            else:
                pkt = self._sim_step()
                self.latest = pkt
                if now - last_db >= 2.0:
                    last_db = now
                    database.insert_sample(pkt)

            time.sleep(0.5)

    # ── Realistic physical simulation ────────────────────────────────

    def _sim_step(self) -> Dict[str, Any]:
        now = time.time()
        sun = self.geo.sun_position()
        el = sun["elevation"]
        irr = sun["irradiance_wm2"]
        weather = self.sim_weather
        fault = self.sim_fault_type

        # Base conditions from sun elevation
        if el <= 0 or weather == "Night":
            light = random.randint(5, 25)
            voltage = random.uniform(0.1, 0.4)
            current = random.uniform(0.0, 2.0)
            temp = random.uniform(18.0, 24.0)
            humidity = random.uniform(65.0, 85.0)
        elif weather == "Cloudy":
            cloud_factor = random.uniform(0.15, 0.35)
            light = int(irr * cloud_factor * 1.023 / 1.0 + random.randint(-10, 10))
            light = max(40, min(400, light))
            voltage = random.uniform(3.5, 4.3)
            current = random.uniform(25.0, 65.0)
            temp = random.uniform(26.0, 34.0)
            humidity = random.uniform(60.0, 80.0)
        else:  # Clear
            light = int(irr * 1.023 / 1.0 + random.randint(-8, 8))
            light = max(50, min(1000, light))
            voltage = 4.8 + (el / 90.0) * 0.9 + random.uniform(-0.03, 0.03)
            current = 120.0 + (el / 90.0) * 180.0 + random.uniform(-3, 3)
            temp = 28.0 + (el / 90.0) * 14.0 + random.uniform(-0.5, 0.5)
            humidity = 45.0 - (el / 90.0) * 10.0 + random.uniform(-2, 2)

        # Apply fault injection for anomaly detection demonstration
        if fault == "dust":
            # Dust/soiling: power drops ~30% but light stays same
            current *= 0.68
            voltage *= 0.92
        elif fault == "shading":
            # Partial shading: current drops dramatically, voltage mostly ok
            current *= 0.30
        elif fault == "wiring":
            # Loose connection: intermittent voltage spikes/drops
            if random.random() < 0.4:
                voltage *= random.uniform(0.3, 0.6)
                current *= 0.1
        elif fault == "overheat":
            # Temperature runaway: temp spikes, efficiency drops
            temp = random.uniform(55.0, 72.0)
            current *= 0.75
            voltage *= 0.88

        power = max(0, voltage * current)
        plr = (power / light) if light > 10 else 0.0

        return {
            "ts_real": now,
            "v": round(voltage, 2),
            "i": round(current, 1),
            "p": round(power, 1),
            "t": round(temp, 1),
            "h": round(humidity, 1),
            "l": int(light),
            "plr": round(plr, 3),
            "simulated": True
        }
