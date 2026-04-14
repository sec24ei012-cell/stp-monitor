"""
components/status_cards.py
--------------------------
Render colour-coded metric cards using Streamlit's HTML/markdown.
Green = normal | Yellow = warning | Red = critical
"""

import streamlit as st
from utils.alerts import THRESHOLDS

UNITS = {"turbidity": "NTU", "tds": "ppm", "level": "%", "flow": "L/min"}
LABELS = {"turbidity": "Turbidity", "tds": "TDS", "level": "Tank Level", "flow": "Flow Rate"}
ICONS  = {"turbidity": "🌊", "tds": "🧪", "level": "📊", "flow": "💧"}


def _status_colour(param: str, value: float) -> tuple[str, str, str]:
    """Return (bg_hex, border_hex, label) based on threshold bands."""
    warn, crit = THRESHOLDS.get(param, (1e9, 1e9))
    if value >= crit:
        return "#FCEBEB", "#E24B4A", "CRITICAL"
    if value >= warn:
        return "#FAEEDA", "#BA7517", "WARNING"
    return "#EAF3DE", "#3B6D11", "NORMAL"


def render_status_card(param: str, value: float, delta: float | None = None):
    """Render a single metric card with colour coding and optional delta."""
    bg, border, label = _status_colour(param, value)
    label_colour = {"CRITICAL": "#A32D2D", "WARNING": "#854F0B", "NORMAL": "#27500A"}[label]
    unit  = UNITS.get(param, "")
    title = LABELS.get(param, param)
    icon  = ICONS.get(param, "")
    delta_html = ""
    if delta is not None:
        sign  = "+" if delta >= 0 else ""
        delta_colour = "#A32D2D" if delta > 0 else "#27500A"
        delta_html = (
            f'<p style="margin:0;font-size:12px;color:{delta_colour};">'
            f'{sign}{delta:.1f} {unit} vs 5 min ago</p>'
        )

    st.markdown(
        f"""
        <div style="
            background:{bg};
            border:1.5px solid {border};
            border-radius:12px;
            padding:14px 18px;
            margin-bottom:8px;
            font-family:'IBM Plex Mono',monospace;
        ">
            <p style="margin:0 0 4px;font-size:12px;color:{label_colour};font-weight:600;
                      letter-spacing:0.08em;">{icon} {title}</p>
            <p style="margin:0;font-size:26px;font-weight:700;color:#1a1a1a;">
                {value:.1f}
                <span style="font-size:14px;font-weight:400;color:#555;">{unit}</span>
            </p>
            {delta_html}
            <span style="
                display:inline-block;margin-top:6px;
                background:{border};color:#fff;
                font-size:10px;font-weight:600;letter-spacing:0.1em;
                padding:2px 8px;border-radius:20px;">
                {label}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_all_cards(latest: dict, prev: dict | None = None):
    """Render a 2×2 grid of status cards for all four parameters."""
    params = ["turbidity", "tds", "level", "flow"]
    cols   = st.columns(2)
    for i, param in enumerate(params):
        val   = latest.get(param, 0.0)
        delta = None
        if prev:
            delta = val - prev.get(param, val)
        with cols[i % 2]:
            render_status_card(param, val, delta)


def render_alert_panel(alerts: list):
    """Render the active alerts panel."""
    if not alerts:
        st.success("✅  No active alerts — all parameters within normal range.")
        return

    for alert in alerts:
        sev   = alert.severity if hasattr(alert, "severity") else alert.get("severity","warning")
        msg   = alert.message  if hasattr(alert, "message")  else alert.get("message","")
        action= alert.action   if hasattr(alert, "action")   else alert.get("action","")
        ts    = alert.timestamp if hasattr(alert, "timestamp") else alert.get("timestamp","")
        icon  = "🔴" if sev == "critical" else "🟡"
        bg    = "#FCEBEB" if sev == "critical" else "#FAEEDA"
        border= "#E24B4A" if sev == "critical" else "#BA7517"

        st.markdown(
            f"""
            <div style="background:{bg};border-left:4px solid {border};
                border-radius:8px;padding:10px 14px;margin-bottom:8px;
                font-family:'IBM Plex Mono',monospace;">
                <p style="margin:0;font-size:13px;font-weight:600;">{icon} {msg}</p>
                <p style="margin:4px 0 0;font-size:12px;color:#555;">
                    ⏰ {str(ts)[:19]}</p>
                <p style="margin:4px 0 0;font-size:12px;color:#333;">
                    🔧 <b>Action:</b> {action}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_prescription_panel(prescriptions: list):
    """Render prescriptive action cards."""
    if not prescriptions:
        st.info("No prescriptive actions required at this time.")
        return

    for rx in prescriptions:
        sev    = rx.get("severity", "warning")
        bg     = "#FCEBEB" if sev == "critical" else "#E6F1FB"
        border = "#E24B4A" if sev == "critical" else "#185FA5"
        steps  = rx.get("steps", [])
        steps_html = "".join(f"<li style='margin:3px 0;'>{s}</li>" for s in steps)

        st.markdown(
            f"""
            <div style="background:{bg};border:1px solid {border};
                border-radius:10px;padding:12px 16px;margin-bottom:10px;
                font-family:'IBM Plex Mono',monospace;">
                <p style="margin:0 0 8px;font-size:13px;font-weight:700;color:#1a1a1a;">
                    🔬 {rx.get('title','')}</p>
                <ol style="margin:0;padding-left:18px;font-size:12px;color:#333;line-height:1.7;">
                    {steps_html}
                </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )
