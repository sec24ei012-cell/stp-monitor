"""
app.py  –  STP Monitoring Dashboard
=====================================
Run with:
    streamlit run app.py

Optional hardware:
    streamlit run app.py -- --port /dev/ttyUSB0
"""

import sys
import time
import argparse

import streamlit as st
import pandas as pd

# ── Parse CLI args (serial port) ─────────────────────────────────────────────
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--port", default=None, help="Serial port for ESP32")
parser.add_argument("--baud", type=int, default=115200)
parser.add_argument("--demo", action="store_true", default=True)
try:
    args, _ = parser.parse_known_args()
except Exception:
    args = parser.parse_args([])

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="STP Monitor",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'IBM Plex Mono', monospace !important; }
    .block-container { padding-top: 1.2rem; padding-bottom: 1rem; }
    .stTabs [data-baseweb="tab"] { font-size: 13px; }
    div[data-testid="stSidebarContent"] { padding-top: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Imports after page config ─────────────────────────────────────────────────
from utils.data_ingestion import start_ingestion, get_dataframe, get_latest
from utils.alerts import evaluate_alerts, get_prescriptions
from utils.chatbot import answer as chatbot_answer
from components.charts import (
    build_timeseries_chart, build_gauge_chart, build_correlation_heatmap
)
from components.status_cards import (
    render_all_cards, render_alert_panel, render_prescription_panel
)

# ── Start background data ingestion ──────────────────────────────────────────
start_ingestion(port=args.port, baud=args.baud, demo=args.demo)

# ── Session state for chatbot history ────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"role": "assistant", "content":
         "Hello! I'm the STP Assistant. Ask me about water quality, alerts, "
         "or type **status** to see live readings."}
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  SIDEBAR  –  Chatbot + settings
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<h2 style='font-family:IBM Plex Mono;font-size:16px;"
        "margin-bottom:4px;'>💬 STP Assistant</h2>",
        unsafe_allow_html=True,
    )
    st.caption("Ask about water quality, alerts, or operating procedures.")

    # Chat messages
    chat_box = st.container(height=340)
    with chat_box:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Input
    user_input = st.chat_input("Ask the STP assistant…")
    if user_input:
        latest = get_latest()
        reply  = chatbot_answer(user_input, latest)
        st.session_state.chat_history.append({"role": "user",      "content": user_input})
        st.session_state.chat_history.append({"role": "assistant",  "content": reply})
        st.rerun()

    st.divider()
    st.subheader("⚙️  Settings", anchor=False)
    refresh_rate   = st.slider("Refresh interval (s)", 1, 30, 5)
    show_anomalies = st.toggle("Highlight anomalies", value=True)
    selected_params = st.multiselect(
        "Parameters to chart",
        options=["turbidity", "tds", "level", "flow"],
        default=["turbidity", "tds", "level", "flow"],
        format_func=lambda x: {
            "turbidity": "Turbidity", "tds": "TDS",
            "level": "Tank Level", "flow": "Flow Rate"
        }[x],
    )

    st.divider()
    # Source indicator
    latest_src = get_latest().get("source", "simulated")
    badge = "🟢 Hardware" if latest_src == "hardware" else "🔵 Simulation"
    st.caption(f"Data source: **{badge}**")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN AREA
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='font-family:IBM Plex Mono;font-size:22px;"
    "margin-bottom:0;'>💧 Sewage Treatment Plant Monitor</h1>",
    unsafe_allow_html=True,
)
st.caption("Real-time sensor dashboard · 24-hour rolling window")
st.divider()

# ── Fetch data ────────────────────────────────────────────────────────────────
df     = get_dataframe()
latest = get_latest()

# Previous snapshot for delta calculation (~5 min ago)
prev = None
if len(df) > 300:
    prev_row = df.iloc[-300]
    prev = prev_row.to_dict()

# Evaluate alerts
alerts        = evaluate_alerts(latest, df)
prescriptions = get_prescriptions(latest)

# ─── Tab layout ──────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Live Overview",
    "📈 Trend Charts",
    "🔔 Alerts & Actions",
    "🔬 Diagnostics",
])

# ═══════════════════════════════════════════════════════════════════════
#  TAB 1 – LIVE OVERVIEW
# ═══════════════════════════════════════════════════════════════════════
with tab1:
    # Status cards grid
    st.subheader("Current Readings", anchor=False)
    render_all_cards(latest, prev)

    st.divider()

    # Gauge row
    st.subheader("Gauge View", anchor=False)
    gcols = st.columns(4)
    for col, param in zip(gcols, ["turbidity", "tds", "level", "flow"]):
        with col:
            st.plotly_chart(
                build_gauge_chart(latest.get(param, 0), param),
                use_container_width=True, config={"displayModeBar": False},
            )

    st.divider()

    # Active alert summary
    alert_count = len(alerts)
    crit_count  = sum(1 for a in alerts if a.severity == "critical")
    acols = st.columns(3)
    acols[0].metric("Active Alerts", alert_count)
    acols[1].metric("Critical Alerts", crit_count,
                    delta=None if crit_count == 0 else "⚠ Immediate action required",
                    delta_color="off")
    acols[2].metric("Prescriptions", len(prescriptions))

    if alerts:
        with st.expander("🔔 View active alerts", expanded=True):
            render_alert_panel(alerts)

# ═══════════════════════════════════════════════════════════════════════
#  TAB 2 – TREND CHARTS
# ═══════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("24-Hour Rolling Trend", anchor=False)
    if not selected_params:
        st.info("Select at least one parameter in the sidebar.")
    else:
        fig = build_timeseries_chart(df, selected_params, show_anomalies)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Parameter Correlation", anchor=False)
    st.plotly_chart(
        build_correlation_heatmap(df),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    # Raw data table
    with st.expander("📋 Raw data table"):
        display_df = df.tail(200).copy()
        display_df["timestamp"] = display_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(display_df, use_container_width=True, height=300)

# ═══════════════════════════════════════════════════════════════════════
#  TAB 3 – ALERTS & ACTIONS
# ═══════════════════════════════════════════════════════════════════════
with tab3:
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("🔔 Active Alerts", anchor=False)
        render_alert_panel(alerts)

    with col_b:
        st.subheader("🔧 Prescriptive Actions", anchor=False)
        render_prescription_panel(prescriptions)

    st.divider()

    # Alert threshold reference
    st.subheader("Threshold Reference", anchor=False)
    from utils.alerts import THRESHOLDS
    thresh_data = [
        {"Parameter": k, "Warning": v[0], "Critical": v[1],
         "Unit": {"turbidity":"NTU","tds":"ppm","level":"%","flow":"L/min"}[k]}
        for k, v in THRESHOLDS.items()
    ]
    st.dataframe(pd.DataFrame(thresh_data), use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════════════
#  TAB 4 – DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("System Diagnostics", anchor=False)

    dcols = st.columns(3)
    dcols[0].metric("Total records (24 h)", len(df))
    dcols[1].metric("Oldest record",
                    df["timestamp"].min().strftime("%H:%M:%S") if not df.empty else "—")
    dcols[2].metric("Latest record",
                    df["timestamp"].max().strftime("%H:%M:%S") if not df.empty else "—")

    st.divider()

    st.subheader("ESP32 Hardware Reference", anchor=False)
    hw_data = [
        {"Sensor": "Turbidity",   "Pin": "GPIO34", "Interface": "ADC (12-bit)", "Range": "0–3000 NTU"},
        {"Sensor": "TDS",         "Pin": "GPIO32", "Interface": "ADC + V-divider", "Range": "0–5000 ppm"},
        {"Sensor": "Water Level", "Pin": "GPIO35", "Interface": "ADC (12-bit)", "Range": "0–100 %"},
        {"Sensor": "Flow (YF-S201)", "Pin": "GPIO27", "Interface": "Interrupt", "Range": "0–200 L/min"},
    ]
    st.dataframe(pd.DataFrame(hw_data), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Statistics (last 1 h)", anchor=False)
    hour_df = df.tail(3600) if len(df) > 3600 else df
    if not hour_df.empty:
        params = ["turbidity", "tds", "level", "flow"]
        stats  = hour_df[params].describe().round(2)
        st.dataframe(stats, use_container_width=True)


# ── Auto-refresh ──────────────────────────────────────────────────────────────
time.sleep(refresh_rate)
st.rerun()
