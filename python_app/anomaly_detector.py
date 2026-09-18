"""
Panel Performance Anomaly Detection Engine.
Three detection layers:
  1. Z-Score statistical detector (fast, explainable)
  2. Isolation Forest ML detector (unsupervised, catches subtle patterns)
  3. Domain rules engine (physics-informed fault signatures)
"""

import time
import numpy as np
from typing import Dict, Any, Optional, List
from collections import deque

try:
    from sklearn.ensemble import IsolationForest
    HAS_ISO = True
except ImportError:
    HAS_ISO = False

import database

# Severity levels
SEV_INFO = "INFO"
SEV_WARN = "WARNING"
SEV_CRIT = "CRITICAL"


class AnomalyDetector:
    def __init__(self):
        # Rolling history for Z-score computation (last ~100 samples)
        self.history = {
            "voltage": deque(maxlen=100),
            "current": deque(maxlen=100),
            "power":   deque(maxlen=100),
            "temp":    deque(maxlen=100),
            "pl_ratio": deque(maxlen=100),
        }
        self.zscore_threshold = 2.5  # Flag readings beyond 2.5 sigma

        # Isolation Forest
        self.iso_model: Optional[Any] = None
        self.iso_trained = False
        self.iso_min_samples = 80

        # Cooldown: suppress duplicate alerts within 30 seconds
        self.last_alert_ts: Dict[str, float] = {}
        self.alert_cooldown = 30.0

        # Overall health score (0-100)
        self.health_score = 100.0
        self.anomaly_count_1h = 0
        self.last_health_calc = 0

    def push_sample(self, pkt: Dict[str, Any]):
        """Feed a new telemetry packet into the detector."""
        v = pkt.get("v", 0)
        i = pkt.get("i", 0)
        p = pkt.get("p", 0)
        t = pkt.get("t", 25)
        l = pkt.get("l", 0)
        plr = (p / l) if l > 10 else 0.0

        self.history["voltage"].append(v)
        self.history["current"].append(i)
        self.history["power"].append(p)
        self.history["temp"].append(t)
        self.history["pl_ratio"].append(plr)

    def run_all_detectors(self, pkt: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute all three detection layers and return list of alerts."""
        self.push_sample(pkt)
        alerts = []

        # Layer 1: Z-Score
        alerts.extend(self._zscore_check(pkt))

        # Layer 2: Rules Engine
        alerts.extend(self._rules_check(pkt))

        # Layer 3: Isolation Forest (if trained)
        alerts.extend(self._isoforest_check(pkt))

        # Log to database (with cooldown)
        now = time.time()
        for a in alerts:
            key = f"{a['detector']}_{a['metric']}"
            if now - self.last_alert_ts.get(key, 0) > self.alert_cooldown:
                self.last_alert_ts[key] = now
                database.insert_anomaly(
                    ts=now,
                    detector=a["detector"],
                    severity=a["severity"],
                    message=a["message"],
                    metric=a.get("metric", ""),
                    value=a.get("value", 0)
                )

        # Update health score
        self._update_health(alerts)

        return alerts

    def _zscore_check(self, pkt: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts = []
        checks = [
            ("voltage", pkt.get("v", 0), "PV bus voltage"),
            ("current", pkt.get("i", 0), "Load current"),
            ("power",   pkt.get("p", 0), "Power output"),
            ("temp",    pkt.get("t", 25), "Panel temperature"),
        ]

        for metric, value, label in checks:
            arr = list(self.history[metric])
            if len(arr) < 15:
                continue

            mean = np.mean(arr)
            std = np.std(arr)
            if std < 0.001:
                continue

            z = abs((value - mean) / std)
            if z > self.zscore_threshold:
                direction = "above" if value > mean else "below"
                sev = SEV_CRIT if z > 4.0 else SEV_WARN
                alerts.append({
                    "detector": "Z-Score",
                    "severity": sev,
                    "metric": metric,
                    "value": round(value, 2),
                    "message": (f"{label} is {z:.1f} sigma {direction} "
                                f"rolling mean ({mean:.2f}). "
                                f"Current: {value:.2f}")
                })

        return alerts

    def _rules_check(self, pkt: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts = []
        v = pkt.get("v", 0)
        i = pkt.get("i", 0)
        p = pkt.get("p", 0)
        t = pkt.get("t", 25)
        l = pkt.get("l", 0)

        # Rule 1: Voltage drop with good sunlight => wiring fault
        if l > 300 and v < 3.0:
            alerts.append({
                "detector": "Rules",
                "severity": SEV_CRIT,
                "metric": "voltage",
                "value": v,
                "message": (f"Voltage critically low ({v:.2f}V) despite "
                            f"good irradiance (light={l}). "
                            f"Check wiring connections and solder joints.")
            })

        # Rule 2: Power-to-light ratio drop => dust/soiling
        pl_arr = list(self.history["pl_ratio"])
        if len(pl_arr) > 20 and l > 200:
            plr_now = (p / l) if l > 10 else 0
            plr_baseline = np.mean(pl_arr[:max(10, len(pl_arr)//2)])
            if plr_baseline > 0.1 and plr_now < plr_baseline * 0.70:
                alerts.append({
                    "detector": "Rules",
                    "severity": SEV_WARN,
                    "metric": "pl_ratio",
                    "value": round(plr_now, 3),
                    "message": (f"Power-to-light ratio dropped to "
                                f"{plr_now:.3f} (baseline: {plr_baseline:.3f}). "
                                f"Possible dust buildup or partial soiling.")
                })

        # Rule 3: Temperature above safe operating limit
        if t > 52.0:
            sev = SEV_CRIT if t > 65.0 else SEV_WARN
            alerts.append({
                "detector": "Rules",
                "severity": sev,
                "metric": "temperature",
                "value": t,
                "message": (f"Panel temperature at {t:.1f}C exceeds "
                            f"safe operating range. Risk of thermal degradation.")
            })

        # Rule 4: Current near zero but voltage present => open circuit
        if v > 3.0 and i < 2.0 and l > 200:
            alerts.append({
                "detector": "Rules",
                "severity": SEV_CRIT,
                "metric": "current",
                "value": i,
                "message": (f"Near-zero current ({i:.1f}mA) with voltage "
                            f"present ({v:.2f}V). Possible open-circuit "
                            f"fault or disconnected load.")
            })

        return alerts

    def _isoforest_check(self, pkt: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not HAS_ISO or not self.iso_trained or self.iso_model is None:
            return []

        features = np.array([[
            pkt.get("v", 0),
            pkt.get("i", 0),
            pkt.get("p", 0),
            pkt.get("t", 25),
            pkt.get("l", 0),
            (pkt.get("p", 0) / pkt.get("l", 1)) if pkt.get("l", 0) > 10 else 0
        ]])

        pred = self.iso_model.predict(features)
        score = self.iso_model.score_samples(features)

        if pred[0] == -1:  # Anomaly
            return [{
                "detector": "Isolation Forest",
                "severity": SEV_WARN,
                "metric": "multivariate",
                "value": round(float(score[0]), 4),
                "message": (f"Multivariate anomaly detected "
                            f"(isolation score: {score[0]:.4f}). "
                            f"Sensor combination deviates from learned "
                            f"normal operating profile.")
            }]
        return []

    def train_isolation_forest(self):
        """Train Isolation Forest on collected normal-operation data."""
        if not HAS_ISO:
            return False

        df = database.all_samples_df()
        if df is None or len(df) < self.iso_min_samples:
            return False

        features = df[["voltage", "current", "power",
                        "temp_c", "light"]].copy()
        features["pl_ratio"] = np.where(
            features["light"] > 10,
            features["power"] / features["light"], 0)

        X = features.values

        self.iso_model = IsolationForest(
            n_estimators=80,
            contamination=0.05,
            random_state=42
        )
        self.iso_model.fit(X)
        self.iso_trained = True
        return True

    def _update_health(self, new_alerts: List[Dict]):
        now = time.time()
        # Count alerts in last hour
        if now - self.last_health_calc > 10:
            self.last_health_calc = now
            anom_df = database.recent_anomalies(200)
            if anom_df is not None and not anom_df.empty:
                one_hr_ago = now - 3600
                recent = anom_df[anom_df["ts"] > one_hr_ago]
                self.anomaly_count_1h = len(recent)

                crit = len(recent[recent["severity"] == "CRITICAL"])
                warn = len(recent[recent["severity"] == "WARNING"])
                self.health_score = max(0, 100 - (crit * 15) - (warn * 5))
            else:
                self.anomaly_count_1h = 0
                self.health_score = 100.0

    def get_health_report(self) -> Dict[str, Any]:
        if self.health_score >= 85:
            status = "HEALTHY"
            recommendation = "Panel operating within normal parameters."
        elif self.health_score >= 60:
            status = "DEGRADED"
            recommendation = "Schedule inspection. Check for dust buildup or partial shading."
        elif self.health_score >= 30:
            status = "POOR"
            recommendation = "Immediate cleaning recommended. Inspect all wiring connections."
        else:
            status = "CRITICAL"
            recommendation = "Panel offline or severely faulted. Disconnect and inspect urgently."

        return {
            "score": round(self.health_score),
            "status": status,
            "anomalies_1h": self.anomaly_count_1h,
            "recommendation": recommendation,
            "iso_trained": self.iso_trained
        }
