"""
utils/chatbot.py
----------------
Rule-based chatbot (RAG-lite) for STP operator queries.
Uses keyword matching + live sensor data to generate contextual answers.
Can be upgraded to a real LLM backend by swapping _llm_answer().
"""

import re
from datetime import datetime

# ── STP Knowledge Base ────────────────────────────────────────────────────────
KNOWLEDGE_BASE = [
    {
        "keywords": ["turbidity", "ntu", "cloudy", "suspended solids", "tss", "clarity"],
        "answer": (
            "**Turbidity** measures water cloudiness (NTU). "
            "Normal STP effluent: <50 NTU. "
            "High turbidity (>100 NTU) indicates poor settling or bio-reactor upset. "
            "Actions: increase aeration, add coagulant (alum 10–15 mg/L), check RAS flow."
        ),
    },
    {
        "keywords": ["tds", "total dissolved solids", "salinity", "conductivity"],
        "answer": (
            "**TDS** (Total Dissolved Solids) measures dissolved salts/ions (ppm). "
            "Acceptable effluent: <500 ppm. Above 1000 ppm may indicate industrial discharge. "
            "Actions: backwash membranes, review upstream industrial permits, increase dilution."
        ),
    },
    {
        "keywords": ["flow", "flow rate", "inflow", "litres", "lpm", "overflow"],
        "answer": (
            "**Flow rate** (L/min) tracks hydraulic load. Baseline is ~12 L/min. "
            ">20 L/min triggers overload warning; >30 L/min is critical. "
            "During high inflow: activate storm-water bypass, alert downstream plant."
        ),
    },
    {
        "keywords": ["level", "tank level", "capacity", "tank full", "fill"],
        "answer": (
            "**Tank level** (%) shows equalisation basin fill status. "
            "Target: 40–70%. Warning at 75%, critical at 90%. "
            "High level: open bypass valve, increase sludge withdrawal, reduce influent gating."
        ),
    },
    {
        "keywords": ["ph", "acid", "alkaline", "lime", "neutral"],
        "answer": (
            "**pH** should be maintained at 6.5–8.5 for biological treatment. "
            "Low pH (<6.5): dose lime slurry (50–100 mg/L) and notify upstream source. "
            "High pH (>9): add carbon dioxide or acid dosing. Recheck every 15 min."
        ),
    },
    {
        "keywords": ["aeration", "aerator", "dissolved oxygen", "do", "blower"],
        "answer": (
            "Maintain **dissolved oxygen (DO)** at 2–4 mg/L in the aeration basin. "
            "DO < 1 mg/L: filamentous bulking risk — increase blower speed by 15–20%. "
            "DO > 6 mg/L: over-aeration — reduce speed to save energy."
        ),
    },
    {
        "keywords": ["sludge", "srt", "wasting", "was pump", "clarifier", "blanket"],
        "answer": (
            "**Sludge management**: maintain SRT (sludge retention time) of 8–15 days. "
            "High sludge blanket in clarifier → increase WAS pumping rate. "
            "High TSS in effluent → check polymer dosing for thickener."
        ),
    },
    {
        "keywords": ["overload", "peak", "storm", "rain", "surge"],
        "answer": (
            "**Overload management**: storm-surge can 2–5× normal inflow. "
            "Actions: divert to equalisation basin, pre-stage sludge pump, "
            "notify downstream plant, document event for regulatory records."
        ),
    },
    {
        "keywords": ["normal", "safe", "acceptable", "limits", "standard", "target"],
        "answer": (
            "**Normal operating ranges**: "
            "Turbidity <50 NTU, TDS <500 ppm, Level 40–70%, Flow 8–15 L/min. "
            "Effluent standards (CPCB/WHO): BOD <30 mg/L, COD <250 mg/L, pH 6.5–8.5."
        ),
    },
    {
        "keywords": ["alert", "alarm", "warning", "critical", "emergency"],
        "answer": (
            "Alerts are colour-coded: 🟢 green = normal, 🟡 yellow = warning, 🔴 red = critical. "
            "Critical alerts require immediate operator action. "
            "Document all critical events with timestamp and action taken."
        ),
    },
    {
        "keywords": ["maintenance", "calibrate", "sensor", "probe", "cleaning"],
        "answer": (
            "**Sensor maintenance schedule**: "
            "• Turbidity probe: clean optical window weekly; calibrate fortnightly with NTU standards. "
            "• TDS probe: rinse with DI water after each deployment; calibrate monthly. "
            "• Flow sensor: inspect impeller quarterly for biofouling."
        ),
    },
    {
        "keywords": ["esp32", "arduino", "firmware", "serial", "hardware", "sensor pin"],
        "answer": (
            "**ESP32 pin mapping**: "
            "Turbidity → GPIO34 (ADC), TDS → GPIO32 (voltage-divided ≤3.3 V), "
            "Level → GPIO35 (ADC), Flow → GPIO27 (interrupt, YF-S201). "
            "Serial output at 115200 baud, JSON per line."
        ),
    },
]

GREETING_PATTERNS = re.compile(r"\b(hi|hello|hey|namaste|good morning|good evening)\b", re.I)
HELP_PATTERN      = re.compile(r"\b(help|what can you do|capabilities|topics)\b", re.I)
STATUS_PATTERN    = re.compile(r"\b(status|current|now|live|reading|latest)\b", re.I)


def _format_status(latest: dict) -> str:
    if not latest:
        return "No live data available yet."
    ts = latest.get("timestamp", "unknown")
    return (
        f"**Live readings** (as of {ts[:19]}):\n"
        f"- Turbidity: **{latest.get('turbidity',0):.1f} NTU**\n"
        f"- TDS: **{latest.get('tds',0):.1f} ppm**\n"
        f"- Tank level: **{latest.get('level',0):.1f}%**\n"
        f"- Flow rate: **{latest.get('flow',0):.1f} L/min**"
    )


def answer(query: str, latest: dict) -> str:
    """
    Generate a contextual answer for operator query.

    Parameters
    ----------
    query  : Raw text from the operator.
    latest : Most recent sensor reading dict.
    """
    q = query.lower().strip()

    if GREETING_PATTERNS.search(q):
        return (
            "Hello! I'm the STP Assistant. I can answer questions about water quality parameters, "
            "alerts, prescriptive actions, hardware setup, and normal operating ranges. "
            "Ask me anything — or type **status** to see live readings."
        )

    if HELP_PATTERN.search(q):
        topics = [
            "turbidity / TSS", "TDS / salinity", "flow rate / overload",
            "tank level", "pH management", "aeration / dissolved oxygen",
            "sludge management", "storm surge response",
            "normal operating ranges", "alerts", "sensor maintenance", "ESP32 setup",
        ]
        return "I can help with:\n" + "\n".join(f"- {t}" for t in topics)

    if STATUS_PATTERN.search(q):
        return _format_status(latest)

    # Knowledge base lookup – score by keyword match count
    best_score = 0
    best_answer = None
    for kb in KNOWLEDGE_BASE:
        score = sum(1 for kw in kb["keywords"] if kw in q)
        if score > best_score:
            best_score = score
            best_answer = kb["answer"]

    if best_answer:
        # Append live context if relevant value is available
        context_addons = []
        for param in ["turbidity", "tds", "level", "flow"]:
            if param in q and param in latest:
                context_addons.append(
                    f"Current {param}: **{latest[param]:.1f}**"
                )
        suffix = ("\n\n*Live context*: " + " | ".join(context_addons)
                  if context_addons else "")
        return best_answer + suffix

    # Fallback
    return (
        "I didn't find a specific answer for that query. "
        "Try asking about: turbidity, TDS, flow rate, tank level, pH, aeration, "
        "sludge management, overload risk, or type **status** for live readings."
    )
