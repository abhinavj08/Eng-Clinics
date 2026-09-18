"""
AI-Based Solar Power Forecasting & Panel Anomaly Detection Dashboard
Department of Computer Science & Engineering, CGC Mohali (B.Tech 3rd Sem)
"""

import time
import datetime
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from serial_reader import SerialReader
from forecaster import PowerForecaster
from anomaly_detector import AnomalyDetector
from solar_geometry import SolarGeometry
import database

st.set_page_config(
    page_title="PV Forecast & Anomaly Detection",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .hdr {padding:10px 16px; background:#111827; border-radius:6px;
          border-left:4px solid #2563eb; margin-bottom:12px;}
    .hdr h2 {margin:0; font-size:1.25rem; color:#e2e8f0;}
    .hdr p  {margin:2px 0 0; font-size:0.82rem; color:#64748b;}
    .pill {display:inline-block; padding:3px 10px; border-radius:4px;
           font-weight:600; font-size:0.78rem; font-family:monospace;}
    .pill-ok   {background:#064e3b; color:#6ee7b7;}
    .pill-warn {background:#78350f; color:#fbbf24;}
    .pill-crit {background:#7f1d1d; color:#fca5a5;}
    .pill-info {background:#1e3a5f; color:#7dd3fc;}
</style>
""", unsafe_allow_html=True)

# Singletons
reader = SerialReader()
forecaster = PowerForecaster()
detector = AnomalyDetector()
geo = SolarGeometry()

# ── SIDEBAR ──────────────────────────────────────────────────────────────

st.sidebar.markdown("### System Configuration")

# Hardware
st.sidebar.markdown("#### Serial Interface")
ports = reader.available_ports()
if ports:
    sel_port = st.sidebar.selectbox("COM Port", ports)
    c1, c2 = st.sidebar.columns(2)
    if c1.button("Connect"):
        if reader.connect(sel_port):
            st.sidebar.success(f"Online: {sel_port}")
        else:
            st.sidebar.error("Connection failed")
    if c2.button("Disconnect"):
        reader.disconnect()
else:
    st.sidebar.caption("No hardware detected. Simulation active.")

st.sidebar.markdown(f"`Status: {'HW CONNECTED' if not reader.sim_mode else 'SIMULATOR'}`")

# Weather & Fault Injection (Sim only)
if reader.sim_mode:
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### Environment Simulation")
    weather = st.sidebar.selectbox(
        "Atmospheric Conditions",
        ["Clear", "Cloudy", "Night"])
    reader.sim_weather = weather

    fault = st.sidebar.selectbox(
        "Fault Injection (for anomaly demo)",
        ["none", "dust", "shading", "wiring", "overheat"])
    reader.sim_fault_type = fault

# ML Controls
st.sidebar.markdown("---")
st.sidebar.markdown("#### AI Model Controls")

n_samples = database.sample_count()
st.sidebar.metric("Samples Collected", n_samples)

if st.sidebar.button("Train Forecaster"):
    ok = forecaster.train(force=True)
    if ok:
        st.sidebar.success(f"Trained! R2={forecaster.train_score.get('r2','?')}")
    else:
        st.sidebar.warning(f"Need {forecaster.min_samples}+ samples")

if st.sidebar.button("Train Anomaly Detector"):
    ok = detector.train_isolation_forest()
    if ok:
        st.sidebar.success("Isolation Forest trained")
    else:
        st.sidebar.warning(f"Need {detector.iso_min_samples}+ samples")

# Location
with st.sidebar.expander("Location & Ephemeris"):
    lat = st.number_input("Latitude", value=30.7046, format="%.4f")
    lon = st.number_input("Longitude", value=76.7179, format="%.4f")
    reader.geo = SolarGeometry(lat, lon)
    st.caption("Default: Mohali / Chandigarh")

# Database
with st.sidebar.expander("Database"):
    if st.button("Clear All Data"):
        database.clear_all()
        st.success("Database cleared")

# ── HEADER ───────────────────────────────────────────────────────────────

st.markdown("""
<div class="hdr">
    <h2>AI-Based Solar Power Forecasting & Panel Anomaly Detection</h2>
    <p>Chandigarh Engineering College, CGC University Mohali &mdash;
       Dept. of Computer Science & Engineering</p>
</div>
""", unsafe_allow_html=True)

# Get latest data & run detectors
pkt = reader.latest
alerts = detector.run_all_detectors(pkt)

# Auto-train models when enough data
if n_samples >= forecaster.min_samples:
    forecaster.train()
if n_samples >= detector.iso_min_samples:
    detector.train_isolation_forest()

now = datetime.datetime.now()
health = detector.get_health_report()

# Status Row
s1, s2, s3, s4 = st.columns(4)
with s1:
    h_cls = "pill-ok" if health["score"] >= 80 else ("pill-warn" if health["score"] >= 50 else "pill-crit")
    st.markdown(f'Panel Health: <span class="pill {h_cls}">{health["score"]}% — {health["status"]}</span>', unsafe_allow_html=True)
with s2:
    st.markdown(f'Alerts (1h): <span class="pill pill-info">{health["anomalies_1h"]}</span>', unsafe_allow_html=True)
with s3:
    fc_status = f"Trained (R2={forecaster.train_score.get('r2','—')})" if forecaster.is_trained else f"Collecting ({n_samples}/{forecaster.min_samples})"
    st.markdown(f"**Forecaster:** `{fc_status}`")
with s4:
    st.markdown(f"**Time:** `{now.strftime('%H:%M:%S')} IST`")

st.markdown("---")

# KPI Cards
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Power", f"{pkt.get('p',0):.1f} mW")
k2.metric("Voltage", f"{pkt.get('v',0):.2f} V")
k3.metric("Current", f"{pkt.get('i',0):.1f} mA")
k4.metric("Temperature", f"{pkt.get('t',25):.1f} °C")
k5.metric("Humidity", f"{pkt.get('h',50):.0f} %RH")
k6.metric("Light (ADC)", f"{pkt.get('l',0)}")

# ── TABS ─────────────────────────────────────────────────────────────────

tab_live, tab_forecast, tab_anomaly, tab_health, tab_data = st.tabs([
    "Live Monitor",
    "AI Power Forecast",
    "Anomaly Detection",
    "Panel Health",
    "Data Explorer"
])

recent_df = database.recent_samples(150)

# ── TAB 1: LIVE MONITOR ─────────────────────────────────────────────────

with tab_live:
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("##### Power Output (mW)")
        if recent_df is not None and not recent_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=recent_df["datetime"], y=recent_df["power"],
                mode="lines", line=dict(color="#f59e0b", width=2),
                fill="tozeroy", fillcolor="rgba(245,158,11,0.08)"
            ))
            fig.update_layout(template="plotly_dark", height=250,
                              margin=dict(l=30,r=15,t=10,b=30),
                              yaxis_title="mW")
            st.plotly_chart(fig, key="p_live")
        else:
            st.info("Collecting data...")

    with c2:
        st.markdown("##### Voltage & Current")
        if recent_df is not None and not recent_df.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=recent_df["datetime"], y=recent_df["voltage"],
                name="Voltage (V)", line=dict(color="#06b6d4", width=2)))
            fig2.add_trace(go.Scatter(
                x=recent_df["datetime"], y=recent_df["current"],
                name="Current (mA)", line=dict(color="#10b981", width=1.5, dash="dot"),
                yaxis="y2"))
            fig2.update_layout(template="plotly_dark", height=250,
                               margin=dict(l=30,r=30,t=10,b=30),
                               yaxis=dict(title="V"),
                               yaxis2=dict(title="mA", overlaying="y", side="right"),
                               legend=dict(orientation="h", y=1.08))
            st.plotly_chart(fig2, key="vi_live")
        else:
            st.info("Collecting data...")

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("##### Temperature & Humidity")
        if recent_df is not None and not recent_df.empty:
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=recent_df["datetime"], y=recent_df["temp_c"],
                name="Temp (°C)", line=dict(color="#ef4444", width=2)))
            fig3.add_trace(go.Scatter(
                x=recent_df["datetime"], y=recent_df["humidity"],
                name="Humidity (%)", line=dict(color="#8b5cf6", width=1.5, dash="dot"),
                yaxis="y2"))
            fig3.update_layout(template="plotly_dark", height=230,
                               margin=dict(l=30,r=30,t=10,b=30),
                               yaxis=dict(title="°C"),
                               yaxis2=dict(title="%RH", overlaying="y", side="right"),
                               legend=dict(orientation="h", y=1.08))
            st.plotly_chart(fig3, key="th_live")

    with c4:
        st.markdown("##### Light Intensity (ADC)")
        if recent_df is not None and not recent_df.empty:
            fig4 = px.area(recent_df, x="datetime", y="light",
                           template="plotly_dark",
                           color_discrete_sequence=["#fbbf24"])
            fig4.update_layout(height=230, margin=dict(l=30,r=15,t=10,b=30),
                               yaxis_title="ADC (0-1023)")
            st.plotly_chart(fig4, key="l_live")

# ── TAB 2: AI FORECAST ──────────────────────────────────────────────────

with tab_forecast:
    st.markdown("##### AI Power Generation Forecast (Random Forest Regressor)")

    if forecaster.is_trained:
        hrs = st.slider("Forecast Horizon (hours)", 1, 6, 3)
        fc_df = forecaster.predict_future(hours_ahead=hrs)

        if fc_df is not None and not fc_df.empty:
            # Actual recent + forecast
            fig_fc = go.Figure()

            # Historical
            if recent_df is not None and not recent_df.empty:
                fig_fc.add_trace(go.Scatter(
                    x=recent_df["datetime"], y=recent_df["power"],
                    name="Actual Power", mode="lines",
                    line=dict(color="#f59e0b", width=2)))

            # Forecast
            now_dt = datetime.datetime.now()
            fc_times = [now_dt + datetime.timedelta(minutes=15*(i+1))
                        for i in range(len(fc_df))]
            fig_fc.add_trace(go.Scatter(
                x=fc_times, y=fc_df["predicted_power_mw"],
                name="Forecast", mode="lines+markers",
                line=dict(color="#3b82f6", width=2.5, dash="dash"),
                marker=dict(size=4)))

            fig_fc.add_vline(x=now_dt, line_dash="dot", line_color="#e11d48",
                             annotation_text="Now")
            fig_fc.update_layout(template="plotly_dark", height=350,
                                 margin=dict(l=30,r=15,t=20,b=30),
                                 yaxis_title="Power (mW)",
                                 legend=dict(orientation="h", y=1.05))
            st.plotly_chart(fig_fc, key="fc_chart")

        # Model Metrics
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("MAE", f"{forecaster.train_score.get('mae', '—')} mW")
        mc2.metric("RMSE", f"{forecaster.train_score.get('rmse', '—')} mW")
        mc3.metric("R² Score", f"{forecaster.train_score.get('r2', '—')}")
        mc4.metric("Training Samples", forecaster.train_score.get("n_train", 0))

        # Feature Importance
        imp = forecaster.get_feature_importance()
        if imp:
            st.markdown("##### Feature Importance (Top 10)")
            imp_df = pd.DataFrame(
                [{"Feature": k, "Importance": v} for k, v in imp.items()])
            fig_imp = px.bar(imp_df, x="Feature", y="Importance",
                             template="plotly_dark",
                             color_discrete_sequence=["#6366f1"])
            fig_imp.update_layout(height=250, margin=dict(l=30,r=15,t=10,b=30))
            st.plotly_chart(fig_imp, key="imp_chart")
    else:
        st.info(f"Forecaster needs {forecaster.min_samples} samples to train. "
                f"Currently: {n_samples}. Keep the dashboard running to collect data.")

# ── TAB 3: ANOMALY DETECTION ────────────────────────────────────────────

with tab_anomaly:
    st.markdown("##### Real-Time Anomaly Detection & Alert Log")

    # Show current alerts
    if alerts:
        for a in alerts:
            sev = a["severity"]
            cls = "pill-crit" if sev == "CRITICAL" else ("pill-warn" if sev == "WARNING" else "pill-info")
            st.markdown(
                f'<span class="pill {cls}">{sev}</span> '
                f'**[{a["detector"]}]** {a["message"]}',
                unsafe_allow_html=True)
    else:
        st.success("No anomalies detected in current sample.")

    st.markdown("---")

    # Historical alert timeline
    anom_df = database.recent_anomalies(100)
    if anom_df is not None and not anom_df.empty:
        st.markdown("##### Alert Timeline")
        color_map = {"CRITICAL": "#ef4444", "WARNING": "#f59e0b", "INFO": "#3b82f6"}
        fig_anom = px.scatter(
            anom_df, x="datetime", y="value",
            color="severity", symbol="detector",
            color_discrete_map=color_map,
            hover_data=["message", "metric"],
            template="plotly_dark")
        fig_anom.update_layout(height=280, margin=dict(l=30,r=15,t=10,b=30))
        st.plotly_chart(fig_anom, key="anom_scatter")

        # Alert table
        st.dataframe(
            anom_df[["iso_time", "severity", "detector", "metric", "message"]].tail(20),
            height=200)
    else:
        st.caption("No alerts logged yet.")

    st.markdown("---")
    st.markdown("##### Detection Methods")
    st.markdown("""
    | Layer | Method | What It Catches |
    |:---|:---|:---|
    | 1 | **Z-Score Statistical** | Any sensor reading >2.5σ from rolling mean |
    | 2 | **Physics Rules Engine** | Wiring faults, dust/soiling, overheating, open circuit |
    | 3 | **Isolation Forest (ML)** | Subtle multivariate deviations from normal profile |
    """)

# ── TAB 4: PANEL HEALTH ─────────────────────────────────────────────────

with tab_health:
    st.markdown("##### Panel Health Assessment")

    h1, h2, h3 = st.columns(3)
    score = health["score"]

    with h1:
        # Health gauge
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": "Health Score"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#22c55e" if score >= 80 else ("#f59e0b" if score >= 50 else "#ef4444")},
                "steps": [
                    {"range": [0, 30], "color": "#1c1917"},
                    {"range": [30, 60], "color": "#1c1917"},
                    {"range": [60, 100], "color": "#1c1917"}
                ]
            }
        ))
        fig_gauge.update_layout(template="plotly_dark", height=220,
                                margin=dict(l=20,r=20,t=40,b=10))
        st.plotly_chart(fig_gauge, key="health_gauge")

    with h2:
        st.metric("Status", health["status"])
        st.metric("Anomalies (Last Hour)", health["anomalies_1h"])
        st.metric("Isolation Forest", "Trained" if health["iso_trained"] else "Untrained")

    with h3:
        st.markdown("##### Maintenance Recommendation")
        st.info(health["recommendation"])

    # Energy summary
    st.markdown("---")
    st.markdown("##### Energy Production Summary")
    es = database.energy_summary()
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Total Energy", f"{es['total_mwh']} mWh")
    e2.metric("Avg Power", f"{es['avg_power']} mW")
    e3.metric("Peak Power", f"{es['peak_power']} mW")
    e4.metric("Total Records", es["records"])

# ── TAB 5: DATA EXPLORER ────────────────────────────────────────────────

with tab_data:
    st.markdown("##### Telemetry Data Explorer")
    if recent_df is not None and not recent_df.empty:
        st.dataframe(recent_df.tail(30), height=280)
        csv = recent_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export Full Dataset (CSV)", csv,
            file_name=f"pv_telemetry_{now.strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv")
    else:
        st.info("No data collected yet.")

    # Solar trajectory reference
    st.markdown("---")
    st.markdown("##### Theoretical Solar Irradiance Profile (Today)")
    day_pts = geo.day_profile()
    df_sun = pd.DataFrame(day_pts)
    h_now = now.hour + now.minute / 60.0

    fig_sun = go.Figure()
    fig_sun.add_trace(go.Scatter(
        x=df_sun["hour"], y=df_sun["irradiance_wm2"],
        name="Clear-Sky Irradiance (W/m²)",
        line=dict(color="#f59e0b", width=2), fill="tozeroy",
        fillcolor="rgba(245,158,11,0.08)"))
    fig_sun.add_trace(go.Scatter(
        x=df_sun["hour"], y=df_sun["elevation"],
        name="Sun Elevation (°)",
        line=dict(color="#64748b", width=1.5, dash="dash")))
    fig_sun.add_vline(x=h_now, line_dash="dot", line_color="#e11d48",
                      annotation_text="Now")
    fig_sun.update_layout(
        template="plotly_dark", height=280,
        margin=dict(l=30, r=15, t=20, b=30),
        xaxis=dict(title="Hour", tickmode="array",
                   tickvals=list(range(0, 25, 3)),
                   ticktext=[f"{h:02d}:00" for h in range(0, 25, 3)]),
        legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig_sun, key="sun_profile")

# ── Auto-refresh ─────────────────────────────────────────────────────────
time.sleep(2.0)
st.rerun()
