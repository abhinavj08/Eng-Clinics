"""
SQLite time-series telemetry storage.
Stores every sample from the Arduino serial stream and provides
query helpers for the ML pipeline and dashboard.
"""

import sqlite3
import os
import time
import datetime
from typing import Dict, Any, Optional, List

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telemetry.db")

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS samples (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        REAL    NOT NULL,
                iso_time  TEXT    NOT NULL,
                voltage   REAL,
                current   REAL,
                power     REAL,
                temp_c    REAL,
                humidity  REAL,
                light     INTEGER,
                pl_ratio  REAL,
                simulated INTEGER DEFAULT 0
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_ts ON samples(ts)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS anomalies (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        REAL    NOT NULL,
                iso_time  TEXT    NOT NULL,
                detector  TEXT,
                severity  TEXT,
                message   TEXT,
                metric    TEXT,
                value     REAL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_anom_ts ON anomalies(ts)")
        c.commit()

def insert_sample(d: Dict[str, Any]):
    now = time.time()
    iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute("""
            INSERT INTO samples (ts, iso_time, voltage, current, power,
                                 temp_c, humidity, light, pl_ratio, simulated)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            d.get("ts_real", now),
            iso,
            d.get("v", 0),
            d.get("i", 0),
            d.get("p", 0),
            d.get("t", 25),
            d.get("h", 50),
            d.get("l", 0),
            d.get("plr", 0),
            1 if d.get("simulated") else 0
        ))
        c.commit()

def insert_anomaly(ts: float, detector: str, severity: str,
                   message: str, metric: str = "", value: float = 0):
    iso = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute("""
            INSERT INTO anomalies (ts, iso_time, detector, severity, message, metric, value)
            VALUES (?,?,?,?,?,?,?)
        """, (ts, iso, detector, severity, message, metric, value))
        c.commit()

def recent_samples(n: int = 200) -> Optional[Any]:
    if not HAS_PANDAS:
        return None
    with _conn() as c:
        df = pd.read_sql_query(
            f"SELECT * FROM samples ORDER BY id DESC LIMIT {int(n)}", c)
    if df is not None and not df.empty:
        df = df.iloc[::-1].reset_index(drop=True)
        df["datetime"] = pd.to_datetime(df["iso_time"])
    return df

def all_samples_df() -> Optional[Any]:
    if not HAS_PANDAS:
        return None
    with _conn() as c:
        df = pd.read_sql_query("SELECT * FROM samples ORDER BY id ASC", c)
    if df is not None and not df.empty:
        df["datetime"] = pd.to_datetime(df["iso_time"])
    return df

def recent_anomalies(n: int = 50) -> Optional[Any]:
    if not HAS_PANDAS:
        return None
    with _conn() as c:
        df = pd.read_sql_query(
            f"SELECT * FROM anomalies ORDER BY id DESC LIMIT {int(n)}", c)
    if df is not None and not df.empty:
        df = df.iloc[::-1].reset_index(drop=True)
        df["datetime"] = pd.to_datetime(df["iso_time"])
    return df

def sample_count() -> int:
    with _conn() as c:
        row = c.execute("SELECT COUNT(*) as cnt FROM samples").fetchone()
        return row["cnt"] if row else 0

def energy_summary() -> Dict[str, float]:
    """Compute total energy harvested (mWh) and averages."""
    with _conn() as c:
        rows = c.execute(
            "SELECT ts, power FROM samples ORDER BY id ASC").fetchall()

    if not rows or len(rows) < 2:
        return {"total_mwh": 0, "avg_power": 0, "peak_power": 0, "records": 0}

    total_mwh = 0
    peak = 0
    power_sum = 0
    for idx in range(1, len(rows)):
        dt_h = max(0.0001, min(0.1, (rows[idx]["ts"] - rows[idx-1]["ts"]) / 3600.0))
        p = rows[idx]["power"] or 0
        total_mwh += p * dt_h
        power_sum += p
        if p > peak:
            peak = p

    return {
        "total_mwh": round(total_mwh, 2),
        "avg_power": round(power_sum / len(rows), 2),
        "peak_power": round(peak, 1),
        "records": len(rows)
    }

def clear_all():
    with _conn() as c:
        c.execute("DELETE FROM samples")
        c.execute("DELETE FROM anomalies")
        c.commit()

# Auto-create tables on import
init_db()
