# AI-Based Solar Power Generation Forecasting & Panel Performance Anomaly Detection

**Engineering Clinics Project**
**Department of Computer Science & Engineering | Chandigarh Engineering College, CGC University Mohali**
**B.Tech — 3rd Semester**

**Team:**
- Abhinav Kumar Jaiswal (2546023)
- Aryan Patel (2546081)
- Aditya Saumya (2546040)

**Supervisors:** Dr. Ashima Shahi, Dr. Rubaljeet

---

## Problem Statement

Solar photovoltaic (PV) installations lose 10-25% of their potential energy yield due to:
- Inability to predict output for scheduling and grid management
- Undetected performance degradation (dust, partial shading, wiring faults, thermal damage)

This project addresses both challenges using embedded sensing and machine learning.

---

## Solution Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  HARDWARE LAYER                         │
│  Arduino Uno + INA219 + DHT11 + LDR + 5V Solar Panel   │
│  Samples: V, I, P, Temperature, Humidity, Light         │
│  Output: JSON over USB Serial @ 115200 baud             │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              AI / ML PROCESSING PIPELINE                │
│                                                         │
│  Forecaster (Random Forest Regressor):                  │
│    Predicts power output 1-6 hours ahead                │
│    Features: time encoding, rolling stats, lag values    │
│                                                         │
│  Anomaly Detector (3 Layers):                           │
│    Layer 1: Z-Score statistical flagging                 │
│    Layer 2: Physics-informed rules engine                │
│    Layer 3: Isolation Forest unsupervised ML             │
│                                                         │
│  Panel Health Scorer:                                   │
│    Composite 0-100% score with maintenance alerts       │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│            STREAMLIT DASHBOARD (5 Tabs)                  │
│  Tab 1: Live PV monitoring (V, I, P, T, H, Light)      │
│  Tab 2: AI forecast curves + model accuracy metrics     │
│  Tab 3: Anomaly alert timeline + detection log          │
│  Tab 4: Panel health gauge + maintenance recommendations│
│  Tab 5: Raw data explorer + CSV export                  │
└─────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
Eng-Clinics/
├── arduino/
│   └── solar_monitor/
│       └── solar_monitor.ino         # Embedded data acquisition firmware
├── python_app/
│   ├── app.py                        # Streamlit 5-tab dashboard
│   ├── serial_reader.py              # USB serial + simulation engine
│   ├── database.py                   # SQLite time-series storage
│   ├── forecaster.py                 # Random Forest power forecaster
│   ├── anomaly_detector.py           # Z-Score + Rules + Isolation Forest
│   └── solar_geometry.py             # NOAA sun position calculator
├── WIRING_GUIDE.md                   # Circuit diagram & pin mapping
├── requirements.txt                  # Python dependencies
├── run_dashboard.bat                 # One-click launcher
└── .gitignore
```

---

## Quick Start

### 1. Flash Arduino Firmware
1. Open `arduino/solar_monitor/solar_monitor.ino` in Arduino IDE
2. Install library: **Adafruit INA219** (via Library Manager)
3. Select board (Arduino Uno) and COM port, click Upload

### 2. Run the Dashboard
```bash
pip install -r requirements.txt
cd python_app
streamlit run app.py
```
Or simply double-click `run_dashboard.bat`.

### 3. Demo Without Hardware
The dashboard includes a built-in physics simulator with fault injection.
Select different weather conditions and fault types from the sidebar to
demonstrate forecasting and anomaly detection capabilities.

---

## Hardware Pin Mapping

| Component | Arduino Pin | Function |
|:---|:---|:---|
| INA219 SDA | A4 | I2C data (voltage/current/power) |
| INA219 SCL | A5 | I2C clock |
| DHT11 DATA | D2 | Temperature & humidity |
| LDR + 10kΩ | A0 | Ambient light intensity |
| INA219 VIN+ | Solar Panel (+) | High-side power input |
| INA219 VIN- | Load | Load supply output |

Total hardware cost: ~₹1,200 (or ~₹50 if reusing components from previous project)
