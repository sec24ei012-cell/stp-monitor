"""
utils/alerts.py
---------------
Rule-based alert engine and prescriptive recommendation module.
Thresholds are tuned for a typical municipal STP secondary effluent.
"""

from datetime import datetime
from dataclasses import dataclass, field
from typing import Literal
import numpy as np
import pandas as pd


# ── Thresholds ────────────────────────────────────────────────────────────────
THRESHOLDS = {
    # parameter: (warning_level, critical_level)
    "turbidity": (100,  300),   # NTU
    "tds":       (500,  1000),  # ppm
    "level":     (75,   90),    # %
    "flow":      (20,   30),    # L/min  (overload thresholds)
}

# Baseline for overload-risk prediction (L/min)
FLOW_BASELINE = 12.0
OVERLOAD_THRESHOLD_PCT = 0.20   # 20% above baseline


# ── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class Alert:
    parameter:  str
    value:      float
    severity:   Literal["warning", "critical"]
    timestamp:  str
    message:    str
    action:     str
    icon:       str = ""

    def to_dict(self) -> dict:
        return self.__dict__


# ── Core alert generator ──────────────────────────────────────────────────────
def evaluate_alerts(latest: dict, df: pd.DataFrame | None = None) -> list[Alert]:
    """
    Evaluate current readings and recent trend for alert conditions.

    Parameters
    ----------
    latest : Most recent sensor dict (turbidity, tds, level, flow).
    df     : Optional rolling DataFrame for trend / overload prediction.

    Returns
    -------
    List of Alert objects sorted by severity (critical first).
    """
    alerts: list[Alert] = []
    ts = latest.get("timestamp", datetime.now().isoformat())

    # ── Per-parameter threshold checks ────────────────────────────────────────
    checks = [
        ("turbidity", latest.get("turbidity", 0),
         "Turbidity above threshold",
         {
             "warning":  "Increase aeration rate; check bio-reactor health.",
             "critical": "STOP effluent discharge. Increase aeration + add coagulant.",
         },
         "⚠"),

        ("tds", latest.get("tds", 0),
         "TDS above safe limit",
         {
             "warning":  "Check feed quality; review coagulation dosing.",
             "critical": "Halt discharge. Flush primary settler; inspect membranes.",
         },
         "🧪"),

        ("level", latest.get("level", 0),
         "Tank level high",
         {
             "warning":  "Open secondary bypass valve; reduce inflow gating.",
             "critical": "Activate emergency overflow protocol. Alert control room.",
         },
         "📊"),

        ("flow", latest.get("flow", 0),
         "Inflow rate elevated",
         {
             "warning":  "Monitor for storm-surge. Pre-stage sludge pump.",
             "critical": "Engage overflow management. Notify downstream plants.",
         },
         "🌊"),
    ]

    for param, value, msg_prefix, actions, icon in checks:
        warn_lvl, crit_lvl = THRESHOLDS[param]
        if value >= crit_lvl:
            alerts.append(Alert(
                parameter=param,
                value=round(value, 2),
                severity="critical",
                timestamp=ts,
                message=f"{msg_prefix}: {value:.1f}",
                action=actions["critical"],
                icon=icon,
            ))
        elif value >= warn_lvl:
            alerts.append(Alert(
                parameter=param,
                value=round(value, 2),
                severity="warning",
                timestamp=ts,
                message=f"{msg_prefix}: {value:.1f}",
                action=actions["warning"],
                icon=icon,
            ))

    # ── Overload-risk prediction (rolling 5-min average trend) ────────────────
    if df is not None and len(df) >= 60:
        recent = df.tail(300)["flow"]           # last 5 min
        predicted_flow = recent.ewm(span=60).mean().iloc[-1]
        excess_pct = (predicted_flow - FLOW_BASELINE) / FLOW_BASELINE

        if excess_pct > OVERLOAD_THRESHOLD_PCT * 2:   # >40 % above baseline
            alerts.append(Alert(
                parameter="flow_predict",
                value=round(predicted_flow, 2),
                severity="critical",
                timestamp=ts,
                message=f"Overload risk: predicted inflow {excess_pct*100:.0f}% above baseline",
                action="Engage overflow management and divert excess flow.",
                icon="🔴",
            ))
        elif excess_pct > OVERLOAD_THRESHOLD_PCT:      # >20 % above baseline
            alerts.append(Alert(
                parameter="flow_predict",
                value=round(predicted_flow, 2),
                severity="warning",
                timestamp=ts,
                message=f"Overload risk: predicted inflow {excess_pct*100:.0f}% above baseline",
                action="Pre-stage sludge pump; open secondary bypass.",
                icon="🟡",
            ))

    # Sort: critical first
    alerts.sort(key=lambda a: 0 if a.severity == "critical" else 1)
    return alerts


# ── Prescriptive recommendation engine ───────────────────────────────────────
PRESCRIPTIONS = [
    {
        "condition": lambda r: r.get("turbidity", 0) > THRESHOLDS["turbidity"][0],
        "parameter": "turbidity",
        "title":     "High turbidity detected",
        "steps": [
            "Increase aeration rate by 15–20%.",
            "Verify bio-reactor dissolved-oxygen levels (target 2–4 mg/L).",
            "Add coagulant (alum or ferric chloride) at 10–15 mg/L.",
            "Check return-activated-sludge (RAS) pump flow.",
        ],
        "severity": "warning",
    },
    {
        "condition": lambda r: r.get("tds", 0) > THRESHOLDS["tds"][0],
        "parameter": "tds",
        "title":     "High TDS — salt load elevated",
        "steps": [
            "Review industrial discharge permits upstream.",
            "Increase dilution water flow if available.",
            "Inspect and backwash RO/NF membranes.",
            "Log event for regulatory reporting.",
        ],
        "severity": "warning",
    },
    {
        "condition": lambda r: r.get("level", 0) > THRESHOLDS["level"][0],
        "parameter": "level",
        "title":     "Tank nearing capacity",
        "steps": [
            "Open secondary bypass valve to equalisation basin.",
            "Ramp up sludge withdrawal pump.",
            "Reduce influent gating if hydraulically possible.",
            "Alert on-call engineer if level exceeds 90%.",
        ],
        "severity": "warning",
    },
    {
        "condition": lambda r: r.get("flow", 0) > THRESHOLDS["flow"][0],
        "parameter": "flow",
        "title":     "High inflow — manage overflow",
        "steps": [
            "Activate storm-water bypass to holding lagoon.",
            "Increase primary clarifier surface-loading check.",
            "Notify downstream receiving plant.",
            "Document inflow event with timestamp.",
        ],
        "severity": "warning",
    },
    # pH proxy rules (TDS + turbidity correlation heuristic)
    {
        "condition": lambda r: r.get("tds", 0) < 100 and r.get("turbidity", 0) < 20,
        "parameter": "ph_low_proxy",
        "title":     "Possible low pH condition (low TDS + low turbidity pattern)",
        "steps": [
            "Measure pH directly at primary influent.",
            "If pH < 6.5: dose lime slurry at 50–100 mg/L.",
            "Re-check pH every 15 minutes until stabilised.",
            "Identify and notify upstream acidic discharge source.",
        ],
        "severity": "warning",
    },
    {
        "condition": lambda r: r.get("turbidity", 0) > 200,
        "parameter": "tss_high",
        "title":     "High TSS suspected — check sludge pump",
        "steps": [
            "Inspect waste-activated-sludge (WAS) pump operation.",
            "Check sludge blanket depth in secondary clarifier.",
            "Verify polymer dosing pump for thickener.",
            "Review sludge age / SRT targets.",
        ],
        "severity": "critical",
    },
]


def get_prescriptions(latest: dict) -> list[dict]:
    """Return applicable prescriptive actions for current readings."""
    result = []
    seen = set()
    for rule in PRESCRIPTIONS:
        try:
            if rule["condition"](latest) and rule["parameter"] not in seen:
                result.append({k: v for k, v in rule.items() if k != "condition"})
                seen.add(rule["parameter"])
        except Exception:
            pass
    return result
